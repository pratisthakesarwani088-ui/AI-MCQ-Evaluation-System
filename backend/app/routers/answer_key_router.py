"""
answer_key_router.py
----------------------
API endpoints for uploading an answer-key image, running OCR
extraction on it, and saving the teacher-verified final answer key.

Endpoints:
    POST /api/answer-key/upload/{exam_id}  -> Upload image + run OCR
    GET  /api/answer-key/{exam_id}         -> Get current answer key rows
    POST /api/answer-key/verify/{exam_id}  -> Save teacher-verified answers
"""

import os

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.database import get_db
from app.config import EXAMS_DIR
from app.models.exam import Exam, ExamType
from app.models.question_paper import QuestionPaper, PaperType, FileType
from app.models.verified_answer_key import VerifiedAnswerKey
from app.schemas.answer_key_schema import VerifyAnswerKeyRequest
from app.utils.file_utils import save_upload_file
from app.services.ocr_service import extract_text_lines, parse_answer_key

router = APIRouter(prefix="/api/answer-key", tags=["Answer Key"])


def _get_exam_or_404(exam_id: int, db: Session) -> Exam:
    exam = db.query(Exam).filter(Exam.exam_id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail=f"Exam with id {exam_id} not found.")
    return exam


@router.post("/upload/{exam_id}", response_model=dict)
def upload_answer_key(exam_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Saves the uploaded answer-key image, runs OCR on it, and stores
    a DRAFT (unverified) answer key in the database so the teacher
    can review/correct it on the "Verify Answer Key" page.

    This is the OMR Evaluation upload path. AI-Based Evaluation exams
    generate their answer key via the AI Assistant instead (see
    ai_assistant_router.py).
    """
    exam = _get_exam_or_404(exam_id, db)

    if exam.exam_type != ExamType.OMR:
        raise HTTPException(
            status_code=400,
            detail=(
                "This exam is configured for AI-Based Evaluation. "
                "Use the AI Assistant to generate the answer key instead of uploading an image."
            ),
        )

    # 1. Save the uploaded image to uploads/exams/{exam_id}/answer_key/
    destination_folder = os.path.join(EXAMS_DIR, str(exam_id), "answer_key")
    saved_path = save_upload_file(file, destination_folder)

    # 2. Record the image in the database as an ANSWER_KEY paper.
    try:
        paper_record = QuestionPaper(
            exam_id=exam_id,
            paper_type=PaperType.ANSWER_KEY,
            file_path=saved_path,
            file_type=FileType.IMAGE,
        )
        db.add(paper_record)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error while saving image record: {exc}")

    # 3. Run OCR on the saved image.
    try:
        text_lines = extract_text_lines(saved_path)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if not text_lines:
        raise HTTPException(
            status_code=422,
            detail="No readable text was found in the image. Please upload a clearer photo of the answer key.",
        )

    answer_map, avg_confidence = parse_answer_key(text_lines)

    if not answer_map:
        raise HTTPException(
            status_code=422,
            detail=(
                "Text was detected in the image, but no question/answer pairs "
                "could be recognized (expected formats like '1 A', '1. B'). "
                "Please upload a clearer photo, or verify the answers manually."
            ),
        )

    # 4. Upsert a draft (is_verified=False) row for every question in
    #    the exam. Missing questions are left blank for manual entry.
    try:
        existing_rows = {
            row.question_number: row
            for row in db.query(VerifiedAnswerKey).filter(VerifiedAnswerKey.exam_id == exam_id).all()
        }

        for question_number in range(1, exam.total_questions + 1):
            detected_option = answer_map.get(question_number, "")
            if question_number in existing_rows:
                row = existing_rows[question_number]
                # Only overwrite if the teacher hasn't already verified
                # a previous answer key for this exam.
                if not row.is_verified:
                    row.correct_option = detected_option
            else:
                db.add(VerifiedAnswerKey(
                    exam_id=exam_id,
                    question_number=question_number,
                    correct_option=detected_option,
                    is_verified=False,
                ))
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error while saving extracted answers: {exc}")

    detected_count = len([q for q in answer_map if 1 <= q <= exam.total_questions])
    missing_count = exam.total_questions - detected_count

    return {
        "success": True,
        "message": (
            f"Extracted {detected_count} of {exam.total_questions} answers "
            f"(average OCR confidence: {round(avg_confidence * 100, 1)}%). "
            f"{missing_count} question(s) need manual entry."
            if missing_count > 0
            else f"Successfully extracted all {detected_count} answers."
        ),
        "detected_count": detected_count,
        "missing_count": missing_count,
    }


@router.get("/{exam_id}", response_model=dict)
def get_answer_key(exam_id: int, db: Session = Depends(get_db)):
    """
    Returns the current answer key rows for an exam (draft or
    verified), ordered by question number. If no rows exist yet,
    returns an empty list of the correct length so the frontend can
    still render an editable table.
    """
    exam = _get_exam_or_404(exam_id, db)

    rows = (
        db.query(VerifiedAnswerKey)
        .filter(VerifiedAnswerKey.exam_id == exam_id)
        .order_by(VerifiedAnswerKey.question_number)
        .all()
    )

    existing = {row.question_number: row for row in rows}
    answers = []
    for question_number in range(1, exam.total_questions + 1):
        row = existing.get(question_number)
        answers.append({
            "question_number": question_number,
            "correct_option": row.correct_option if row else "",
            "is_verified": row.is_verified if row else False,
        })

    all_verified = bool(rows) and all(row.is_verified for row in rows) and len(rows) == exam.total_questions

    return {
        "success": True,
        "exam_id": exam_id,
        "total_questions": exam.total_questions,
        "is_fully_verified": all_verified,
        "answers": answers,
    }


@router.post("/verify/{exam_id}", response_model=dict)
def verify_answer_key(exam_id: int, payload: VerifyAnswerKeyRequest, db: Session = Depends(get_db)):
    """
    Saves the teacher's final, reviewed answer key. This is the ONLY
    data used later during evaluation.
    """
    exam = _get_exam_or_404(exam_id, db)

    if len(payload.answers) != exam.total_questions:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Expected answers for all {exam.total_questions} questions, "
                f"but received {len(payload.answers)}."
            ),
        )

    question_numbers = {row.question_number for row in payload.answers}
    expected_numbers = set(range(1, exam.total_questions + 1))
    if question_numbers != expected_numbers:
        raise HTTPException(
            status_code=400,
            detail="Question numbers do not match the exam's total questions (1..N). Please refresh and try again.",
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
        raise HTTPException(status_code=500, detail=f"Database error while saving verified answer key: {exc}")

    return {
        "success": True,
        "message": f"Verified answer key saved for all {exam.total_questions} questions.",
    }
