"""
ai_evaluation_router.py
--------------------------
API endpoints for the AI-Based Evaluation module:
  - Uploading a question paper (PDF/DOCX/TXT) and extracting text
  - Turning that text into individual questions (or entering them
    manually), with full add/edit/delete support
  - Generating an answer key (and optional explanations) via Gemini
  - Verifying and saving the final answer key

Endpoints:
    POST   /api/ai-evaluation/upload-paper/{exam_id}       -> Upload question paper
    POST   /api/ai-evaluation/extract-questions/{paper_id} -> Parse paper text into questions
    POST   /api/ai-evaluation/questions/{exam_id}          -> Add a question manually
    GET    /api/ai-evaluation/questions/{exam_id}          -> List all questions for an exam
    PUT    /api/ai-evaluation/questions/{question_id}      -> Edit a question
    DELETE /api/ai-evaluation/questions/{question_id}      -> Delete a question
    POST   /api/ai-evaluation/generate-answer-key/{exam_id}-> Generate answer key with Gemini
    GET    /api/ai-evaluation/answer-key/{exam_id}         -> Get current answer key + explanations
    POST   /api/ai-evaluation/verify-answer-key/{exam_id}  -> Save the verified answer key
"""

import os
import json

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.database import get_db
from app.config import EXAMS_DIR
from app.models.exam import Exam, ExamType
from app.models.question_paper import QuestionPaper, PaperType, FileType
from app.models.question import Question, QuestionSource
from app.models.ai_response import AIResponse, AIRequestType
from app.models.verified_answer_key import VerifiedAnswerKey
from app.schemas.question_schema import QuestionCreate, QuestionUpdate, QuestionOut, GenerateAnswerKeyRequest
from app.schemas.answer_key_schema import VerifyAnswerKeyRequest
from app.utils.file_utils import save_document_file
from app.services.document_parser_service import extract_text_from_document
from app.services.question_extraction_service import extract_and_save_questions
from app.services.gemini_service import generate_answer_key as gemini_generate_answer_key

router = APIRouter(prefix="/api/ai-evaluation", tags=["AI-Based Evaluation"])


# ---------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------
def _get_exam_or_404(exam_id: int, db: Session) -> Exam:
    exam = db.query(Exam).filter(Exam.exam_id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail=f"Exam with id {exam_id} not found.")
    return exam


def _ensure_ai_exam(exam: Exam):
    if exam.exam_type != ExamType.AI:
        raise HTTPException(
            status_code=400,
            detail="This exam is configured for OMR Evaluation. Use the OMR Evaluation flow instead of AI-Based Evaluation.",
        )


def _file_type_from_extension(filename: str) -> FileType:
    ext = os.path.splitext(filename.lower())[1]
    return {
        ".pdf": FileType.PDF,
        ".docx": FileType.DOCX,
        ".txt": FileType.TXT,
    }.get(ext, FileType.TXT)


# ---------------------------------------------------------------
# 1. Upload Question Paper
# ---------------------------------------------------------------
@router.post("/upload-paper/{exam_id}", response_model=dict)
def upload_question_paper(exam_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Saves an uploaded question paper (PDF, DOCX, or TXT), extracts
    its text, and stores both the file path and extracted text on a
    new QuestionPaper record.
    """
    exam = _get_exam_or_404(exam_id, db)
    _ensure_ai_exam(exam)

    # save_document_file validates the extension is .pdf/.docx/.txt
    # and raises a friendly 400 error for any other ("unsupported
    # format") file type.
    destination_folder = os.path.join(EXAMS_DIR, str(exam_id), "question_papers")
    saved_path = save_document_file(file, destination_folder)
    file_type = _file_type_from_extension(file.filename)

    try:
        extracted_text = extract_text_from_document(saved_path, file_type.value)
    except RuntimeError as exc:
        # Clean up the saved file if we can't actually use it, so we
        # don't leave orphaned uploads with no usable content.
        if os.path.exists(saved_path):
            os.remove(saved_path)
        raise HTTPException(status_code=422, detail=str(exc))

    try:
        paper = QuestionPaper(
            exam_id=exam_id,
            paper_type=PaperType.QUESTION_PAPER,
            file_path=saved_path,
            file_type=file_type,
            extracted_text=extracted_text,
        )
        db.add(paper)
        db.commit()
        db.refresh(paper)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error while saving the question paper: {exc}")

    preview = extracted_text[:500] + ("..." if len(extracted_text) > 500 else "")

    return {
        "success": True,
        "message": "Question paper uploaded and text extracted successfully.",
        "paper_id": paper.paper_id,
        "character_count": len(extracted_text),
        "text_preview": preview,
    }


# ---------------------------------------------------------------
# Extract structured questions from an uploaded paper's raw text
# ---------------------------------------------------------------
@router.post("/extract-questions/{paper_id}", response_model=dict)
def extract_questions(paper_id: int, db: Session = Depends(get_db)):
    """
    Parses the raw extracted text of a QuestionPaper into
    individual Question rows (source=EXTRACTED). Existing question
    numbers for the exam are skipped rather than duplicated.
    """
    paper = db.query(QuestionPaper).filter(QuestionPaper.paper_id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail=f"Question paper with id {paper_id} not found.")

    try:
        result = extract_and_save_questions(paper, db)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error while saving extracted questions: {exc}")

    if not result["parsed"]:
        raise HTTPException(status_code=422, detail=result["error"])

    added_count = result["added_count"]
    skipped_count = result["skipped_count"]
    message = f"Extracted {added_count} new question(s) from the document."
    if skipped_count:
        message += f" Skipped {skipped_count} question(s) that already existed (matching question number)."

    return {
        "success": True,
        "message": message,
        "added_count": added_count,
        "skipped_count": skipped_count,
    }


# ---------------------------------------------------------------
# 2. Manual Question Entry (Add / List / Edit / Delete)
# ---------------------------------------------------------------
@router.post("/questions/{exam_id}", response_model=dict)
def add_question(exam_id: int, question_data: QuestionCreate, db: Session = Depends(get_db)):
    """Adds a single question manually. Auto-assigns the next question number if not provided."""
    exam = _get_exam_or_404(exam_id, db)
    _ensure_ai_exam(exam)

    try:
        if question_data.question_number is not None:
            question_number = question_data.question_number
            duplicate = (
                db.query(Question)
                .filter(Question.exam_id == exam_id, Question.question_number == question_number)
                .first()
            )
            if duplicate:
                raise HTTPException(
                    status_code=400,
                    detail=f"Question {question_number} already exists for this exam. Edit it instead, or choose a different number.",
                )
        else:
            max_number = (
                db.query(Question.question_number)
                .filter(Question.exam_id == exam_id)
                .order_by(Question.question_number.desc())
                .first()
            )
            question_number = (max_number[0] + 1) if max_number else 1

        new_question = Question(
            exam_id=exam_id,
            question_number=question_number,
            question_text=question_data.question_text,
            option_a=question_data.option_a,
            option_b=question_data.option_b,
            option_c=question_data.option_c,
            option_d=question_data.option_d,
            option_e=question_data.option_e,
            source=QuestionSource.MANUAL,
        )
        db.add(new_question)
        db.commit()
        db.refresh(new_question)
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error while adding the question: {exc}")

    return {
        "success": True,
        "message": f"Question {question_number} added.",
        "question": QuestionOut.model_validate(new_question).model_dump(),
    }


@router.get("/questions/{exam_id}", response_model=dict)
def list_questions(exam_id: int, db: Session = Depends(get_db)):
    """Lists every question for an exam, ordered by question number."""
    _get_exam_or_404(exam_id, db)

    questions = (
        db.query(Question)
        .filter(Question.exam_id == exam_id)
        .order_by(Question.question_number)
        .all()
    )

    return {
        "success": True,
        "questions": [QuestionOut.model_validate(q).model_dump() for q in questions],
    }


@router.put("/questions/{question_id}", response_model=dict)
def update_question(question_id: int, question_data: QuestionUpdate, db: Session = Depends(get_db)):
    """Edits an existing question's text/options."""
    question = db.query(Question).filter(Question.question_id == question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail=f"Question with id {question_id} not found.")

    try:
        question.question_text = question_data.question_text
        question.option_a = question_data.option_a
        question.option_b = question_data.option_b
        question.option_c = question_data.option_c
        question.option_d = question_data.option_d
        question.option_e = question_data.option_e
        db.commit()
        db.refresh(question)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error while updating the question: {exc}")

    return {
        "success": True,
        "message": f"Question {question.question_number} updated.",
        "question": QuestionOut.model_validate(question).model_dump(),
    }


@router.delete("/questions/{question_id}", response_model=dict)
def delete_question(question_id: int, db: Session = Depends(get_db)):
    """Deletes a question. Its verified answer key row (if any) is left untouched."""
    question = db.query(Question).filter(Question.question_id == question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail=f"Question with id {question_id} not found.")

    try:
        question_number = question.question_number
        db.delete(question)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error while deleting the question: {exc}")

    return {"success": True, "message": f"Question {question_number} deleted."}


# ---------------------------------------------------------------
# 3. Gemini AI Integration - Generate Answer Key
# ---------------------------------------------------------------
@router.post("/generate-answer-key/{exam_id}", response_model=dict)
def generate_answer_key(exam_id: int, payload: GenerateAnswerKeyRequest, db: Session = Depends(get_db)):
    """
    Sends every question for this exam to Gemini, gets back a
    suggested correct option (and optional explanation) for each,
    logs the full exchange in ai_responses, and stores the result
    as a DRAFT (unverified) answer key.
    """
    exam = _get_exam_or_404(exam_id, db)
    _ensure_ai_exam(exam)

    questions = (
        db.query(Question)
        .filter(Question.exam_id == exam_id)
        .order_by(Question.question_number)
        .all()
    )
    if not questions:
        raise HTTPException(
            status_code=400,
            detail="This exam has no questions yet. Upload a question paper or add questions manually first.",
        )

    question_dicts = [
        {
            "question_number": q.question_number,
            "question_text": q.question_text,
            "option_a": q.option_a,
            "option_b": q.option_b,
            "option_c": q.option_c,
            "option_d": q.option_d,
            "option_e": q.option_e,
        }
        for q in questions
    ]

    try:
        ai_result = gemini_generate_answer_key(question_dicts, include_explanations=payload.include_explanations)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    try:
        ai_log = AIResponse(
            exam_id=exam_id,
            request_type=AIRequestType.GENERATE_ANSWER_KEY,
            prompt_text=ai_result["prompt"],
            response_text=json.dumps(ai_result["results"]),
        )
        db.add(ai_log)

        existing_rows = {
            row.question_number: row
            for row in db.query(VerifiedAnswerKey).filter(VerifiedAnswerKey.exam_id == exam_id).all()
        }

        valid_question_numbers = {q.question_number for q in questions}
        applied_count = 0
        for item in ai_result["results"]:
            if item["question_number"] not in valid_question_numbers:
                continue  # Ignore any hallucinated question number outside our set.

            if item["question_number"] in existing_rows:
                row = existing_rows[item["question_number"]]
                if not row.is_verified:
                    row.correct_option = item["correct_option"]
            else:
                db.add(VerifiedAnswerKey(
                    exam_id=exam_id,
                    question_number=item["question_number"],
                    correct_option=item["correct_option"],
                    is_verified=False,
                ))
            applied_count += 1

        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error while saving the AI-generated answer key: {exc}")

    return {
        "success": True,
        "message": f"Gemini generated answers for {applied_count} of {len(questions)} question(s). Please review and verify below.",
        "generated_count": applied_count,
        "total_questions": len(questions),
    }


# ---------------------------------------------------------------
# 4. AI Response Verification
# ---------------------------------------------------------------
@router.get("/answer-key/{exam_id}", response_model=dict)
def get_ai_answer_key(exam_id: int, db: Session = Depends(get_db)):
    """
    Returns every question for the exam alongside its current
    (draft or verified) answer and, if available, the explanation
    from the most recent Gemini generation.
    """
    exam = _get_exam_or_404(exam_id, db)

    questions = (
        db.query(Question)
        .filter(Question.exam_id == exam_id)
        .order_by(Question.question_number)
        .all()
    )

    key_rows = {
        row.question_number: row
        for row in db.query(VerifiedAnswerKey).filter(VerifiedAnswerKey.exam_id == exam_id).all()
    }

    # Look up explanations from the most recent answer-key generation
    # logged for this exam (best-effort -- if parsing fails or none
    # exists, explanations are simply left blank).
    explanations = {}
    latest_ai_log = (
        db.query(AIResponse)
        .filter(AIResponse.exam_id == exam_id, AIResponse.request_type == AIRequestType.GENERATE_ANSWER_KEY)
        .order_by(AIResponse.created_at.desc())
        .first()
    )
    if latest_ai_log and latest_ai_log.response_text:
        try:
            parsed = json.loads(latest_ai_log.response_text)
            for item in parsed:
                explanations[item["question_number"]] = item.get("explanation", "")
        except (json.JSONDecodeError, TypeError, KeyError):
            explanations = {}

    answers = []
    for q in questions:
        key_row = key_rows.get(q.question_number)
        answers.append({
            "question_number": q.question_number,
            "question_text": q.question_text,
            "correct_option": key_row.correct_option if key_row else "",
            "is_verified": key_row.is_verified if key_row else False,
            "explanation": explanations.get(q.question_number, ""),
        })

    all_verified = bool(questions) and all(a["is_verified"] for a in answers)

    return {
        "success": True,
        "exam_id": exam_id,
        "total_questions": len(questions),
        "is_fully_verified": all_verified,
        "answers": answers,
    }


@router.post("/verify-answer-key/{exam_id}", response_model=dict)
def verify_ai_answer_key(exam_id: int, payload: VerifyAnswerKeyRequest, db: Session = Depends(get_db)):
    """
    Saves the teacher's final, reviewed answer key -- the ONLY data
    used later during evaluation. Validated against the exam's
    actual Question rows (not the exam's declared total_questions,
    since AI-Based exams build their question count dynamically).
    """
    exam = _get_exam_or_404(exam_id, db)

    question_numbers_in_exam = {
        q.question_number
        for q in db.query(Question.question_number).filter(Question.exam_id == exam_id).all()
    }
    if not question_numbers_in_exam:
        raise HTTPException(status_code=400, detail="This exam has no questions yet.")

    submitted_numbers = {row.question_number for row in payload.answers}
    if submitted_numbers != question_numbers_in_exam:
        raise HTTPException(
            status_code=400,
            detail="The submitted answers don't match this exam's current question numbers. Please refresh and try again.",
        )

    try:
        existing_rows = {
            row.question_number: row
            for row in db.query(VerifiedAnswerKey).filter(VerifiedAnswerKey.exam_id == exam_id).all()
        }

        for answer_row in payload.answers:
            if answer_row.question_number in existing_rows:
                row = existing_rows[answer_row.question_number]
                row.correct_option = answer_row.correct_option
                row.is_verified = True
            else:
                db.add(VerifiedAnswerKey(
                    exam_id=exam_id,
                    question_number=answer_row.question_number,
                    correct_option=answer_row.correct_option,
                    is_verified=True,
                ))
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error while saving the verified answer key: {exc}")

    return {
        "success": True,
        "message": f"Verified answer key saved for all {len(payload.answers)} question(s).",
    }
