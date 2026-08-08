"""
ai_assistant_router.py
-------------------------
API endpoints for the standalone AI Assistant panel.

Several of the panel's actions reuse endpoints that already exist
elsewhere rather than duplicating logic:
  - "Generate Answer Key"        -> POST /api/ai-evaluation/generate-answer-key/{exam_id}
                                     (AI-Based Evaluation module)
  - "Analyze Results" /
    "Weak Topics" / "Strong Topics" /
    "Suggestions"                -> POST /api/evaluation/analyze/{sheet_id}
                                     (Evaluation + Result module) -- one Gemini
                                     call already returns strong topics, weak
                                     topics, AND suggestions together, so the
                                     panel simply displays different parts of
                                     that same response.
  - Exam/student pickers          -> GET /api/exams, GET /api/previous-exams/{exam_id}/students
                                     (already built, just reused by the frontend)

This router only adds the two capabilities nothing else covers:
    POST /api/ai-assistant/explain-answer   -> Explain why an answer is right/wrong
    POST /api/ai-assistant/generate-mcqs    -> Generate brand-new MCQs
    POST /api/ai-assistant/save-mcqs/{exam_id} -> Save generated MCQs into an exam
"""

from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.database import get_db
from app.models.exam import Exam, ExamType
from app.models.question import Question, QuestionSource
from app.models.verified_answer_key import VerifiedAnswerKey
from app.models.ai_response import AIResponse, AIRequestType
from app.services.gemini_service import explain_answer as gemini_explain_answer
from app.services.gemini_service import generate_mcqs as gemini_generate_mcqs

router = APIRouter(prefix="/api/ai-assistant", tags=["AI Assistant"])


# ---------------------------------------------------------------
# Schemas (kept local to this router since they're small and only
# used here, consistent with how other single-purpose request
# bodies are handled elsewhere in the app)
# ---------------------------------------------------------------
class ExplainAnswerRequest(BaseModel):
    exam_id: int
    question_number: int = Field(..., gt=0)


class GenerateMCQsRequest(BaseModel):
    subject: Optional[str] = None
    topic: str = Field(..., min_length=1)
    difficulty: str = "Medium"

    @field_validator("difficulty")
    @classmethod
    def difficulty_must_be_valid(cls, value: str):
        value = (value or "Medium").strip().capitalize()
        if value not in ("Easy", "Medium", "Hard"):
            raise ValueError("difficulty must be 'Easy', 'Medium', or 'Hard'.")
        return value

    count: int = Field(5, gt=0, le=20)


class GeneratedMCQ(BaseModel):
    question_text: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_option: str
    explanation: Optional[str] = ""


class SaveMCQsRequest(BaseModel):
    mcqs: List[GeneratedMCQ]


@router.post("/explain-answer", response_model=dict)
def explain_answer(payload: ExplainAnswerRequest, db: Session = Depends(get_db)):
    """
    Explains why the verified correct answer for one question is
    right, and why the other available options are wrong.

    Works best for AI-Based Evaluation exams (which store question
    text and options on the Questions table). If no question text
    is available (e.g. an OMR exam with no parsed question paper),
    a friendly error explains why this feature needs it.
    """
    exam = db.query(Exam).filter(Exam.exam_id == payload.exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail=f"Exam with id {payload.exam_id} not found.")

    question = (
        db.query(Question)
        .filter(Question.exam_id == payload.exam_id, Question.question_number == payload.question_number)
        .first()
    )
    if not question:
        raise HTTPException(
            status_code=400,
            detail=(
                f"No stored question text was found for question {payload.question_number} of this exam. "
                "This feature requires the question's text and options -- available for AI-Based Evaluation "
                "exams, or OMR exams with a successfully parsed question paper."
            ),
        )

    key_row = (
        db.query(VerifiedAnswerKey)
        .filter(
            VerifiedAnswerKey.exam_id == payload.exam_id,
            VerifiedAnswerKey.question_number == payload.question_number,
            VerifiedAnswerKey.is_verified.is_(True),
        )
        .first()
    )
    if not key_row:
        raise HTTPException(
            status_code=400,
            detail=f"Question {payload.question_number} does not have a verified correct answer yet.",
        )

    options = {
        "A": question.option_a,
        "B": question.option_b,
        "C": question.option_c,
        "D": question.option_d,
        "E": question.option_e,
    }

    try:
        result = gemini_explain_answer(question.question_text, options, key_row.correct_option)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    try:
        db.add(AIResponse(
            exam_id=payload.exam_id,
            request_type=AIRequestType.EXPLAIN_ANSWER,
            prompt_text=result["prompt"],
            response_text=result["explanation"],
        ))
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        # Logging the exchange is best-effort -- the explanation
        # itself was already generated successfully, so we still
        # return it to the teacher even if the log write failed.
        pass

    return {
        "success": True,
        "question_number": payload.question_number,
        "correct_option": key_row.correct_option,
        "explanation": result["explanation"],
    }


@router.post("/generate-mcqs", response_model=dict)
def generate_mcqs(payload: GenerateMCQsRequest, db: Session = Depends(get_db)):
    """
    Generates brand-new MCQs on a topic/difficulty using Gemini.
    Does NOT save them anywhere -- the teacher reviews the result
    and can then call /save-mcqs/{exam_id} to add the ones they want
    to a specific exam, or download them client-side.
    """
    try:
        result = gemini_generate_mcqs(
            subject=payload.subject,
            topic=payload.topic,
            difficulty=payload.difficulty,
            count=payload.count,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    try:
        db.add(AIResponse(
            exam_id=None,
            request_type=AIRequestType.GENERATE_MCQS,
            prompt_text=result["prompt"],
            response_text=result["raw_response"],
        ))
        db.commit()
    except SQLAlchemyError:
        db.rollback()

    return {
        "success": True,
        "message": f"Generated {len(result['mcqs'])} question(s).",
        "mcqs": result["mcqs"],
    }


@router.post("/save-mcqs/{exam_id}", response_model=dict)
def save_mcqs(exam_id: int, payload: SaveMCQsRequest, db: Session = Depends(get_db)):
    """
    Saves a set of (typically AI-generated) MCQs into an exam's
    Questions table, auto-numbering after any existing questions,
    and also stores each one's correct option as a DRAFT (unverified)
    row in verified_answer_keys so it's ready for the teacher to
    review on the exam's Verify Answer Key step.
    """
    exam = db.query(Exam).filter(Exam.exam_id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail=f"Exam with id {exam_id} not found.")
    if exam.exam_type != ExamType.AI:
        raise HTTPException(
            status_code=400,
            detail="Only AI-Based Evaluation exams can have questions saved to them this way.",
        )

    if not payload.mcqs:
        raise HTTPException(status_code=400, detail="No questions were provided to save.")

    try:
        max_number_row = (
            db.query(Question.question_number)
            .filter(Question.exam_id == exam_id)
            .order_by(Question.question_number.desc())
            .first()
        )
        next_number = (max_number_row[0] + 1) if max_number_row else 1

        existing_key_rows = {
            row.question_number: row
            for row in db.query(VerifiedAnswerKey).filter(VerifiedAnswerKey.exam_id == exam_id).all()
        }

        saved_count = 0
        for mcq in payload.mcqs:
            question_number = next_number
            db.add(Question(
                exam_id=exam_id,
                question_number=question_number,
                question_text=mcq.question_text,
                option_a=mcq.option_a,
                option_b=mcq.option_b,
                option_c=mcq.option_c,
                option_d=mcq.option_d,
                option_e=None,
                source=QuestionSource.MANUAL,
            ))

            if question_number in existing_key_rows:
                row = existing_key_rows[question_number]
                if not row.is_verified:
                    row.correct_option = mcq.correct_option
            else:
                db.add(VerifiedAnswerKey(
                    exam_id=exam_id,
                    question_number=question_number,
                    correct_option=mcq.correct_option,
                    is_verified=False,
                ))

            next_number += 1
            saved_count += 1

        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error while saving the generated questions: {exc}")

    return {
        "success": True,
        "message": f"Saved {saved_count} question(s) to '{exam.exam_name}'. Review them on the AI-Based Evaluation page.",
        "saved_count": saved_count,
    }
