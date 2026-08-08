"""
evaluation_router.py
----------------------
API endpoints for running the evaluation engine (scoring a
processed student sheet against the verified answer key), retrieving
a previously computed result, and generating an AI Performance
Analysis of that result with Gemini.

This is the SAME evaluation engine used by both AI-Based Evaluation
and OMR Evaluation -- neither mode has its own scoring logic; both
simply call these endpoints once their student responses exist.

Endpoints:
    POST /api/evaluation/evaluate/{sheet_id}  -> Compute & save the result
    GET  /api/evaluation/{sheet_id}            -> Fetch a saved result
    POST /api/evaluation/analyze/{sheet_id}    -> Generate AI Performance Analysis
"""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.database import get_db
from app.models.exam import Exam
from app.models.verified_answer_key import VerifiedAnswerKey
from app.models.student_sheet import StudentAnswerSheet
from app.models.student_response import StudentResponse
from app.models.evaluation_result import EvaluationResult
from app.models.question import Question
from app.models.ai_response import AIResponse, AIRequestType
from app.services.evaluation_service import evaluate_sheet
from app.services.gemini_service import analyze_performance as gemini_analyze_performance

router = APIRouter(prefix="/api/evaluation", tags=["Evaluation"])


def _load_sheet_and_exam(sheet_id: int, db: Session):
    sheet = db.query(StudentAnswerSheet).filter(StudentAnswerSheet.sheet_id == sheet_id).first()
    if not sheet:
        raise HTTPException(status_code=404, detail=f"Student sheet with id {sheet_id} not found.")

    exam = db.query(Exam).filter(Exam.exam_id == sheet.exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="The exam linked to this sheet could not be found.")

    return sheet, exam


def _build_question_results(sheet_id: int, exam: Exam, db: Session):
    """
    Loads the verified answer key and the student's detected
    responses from the database and runs the shared scoring engine.
    """
    key_rows = (
        db.query(VerifiedAnswerKey)
        .filter(VerifiedAnswerKey.exam_id == exam.exam_id, VerifiedAnswerKey.is_verified.is_(True))
        .all()
    )
    if len(key_rows) < exam.total_questions:
        raise HTTPException(
            status_code=400,
            detail="The verified answer key for this exam is incomplete. Please finish verifying the answer key first.",
        )
    verified_answers = {row.question_number: row.correct_option for row in key_rows}

    response_rows = db.query(StudentResponse).filter(StudentResponse.sheet_id == sheet_id).all()
    if not response_rows:
        raise HTTPException(
            status_code=400,
            detail="This sheet has not been processed yet. Please upload/process the student sheet before evaluating it.",
        )
    student_responses = {
        row.question_number: {
            "selected_option": row.selected_option,
            "detection_status": row.detection_status.value
            if hasattr(row.detection_status, "value")
            else str(row.detection_status),
        }
        for row in response_rows
    }

    question_results, summary = evaluate_sheet(
        total_questions=exam.total_questions,
        marks_per_correct=exam.marks_per_correct,
        negative_marks=exam.negative_marks,
        verified_answers=verified_answers,
        student_responses=student_responses,
    )
    return question_results, summary


@router.post("/evaluate/{sheet_id}", response_model=dict)
def evaluate_student_sheet(sheet_id: int, db: Session = Depends(get_db)):
    """
    Computes the final result for a student sheet and saves the
    summary (correct/wrong/blank/invalid counts, marks, percentage)
    into the evaluation_results table. Safe to call again -- it
    updates the existing result instead of creating duplicates.
    """
    sheet, exam = _load_sheet_and_exam(sheet_id, db)
    question_results, summary = _build_question_results(sheet_id, exam, db)

    try:
        existing_result = (
            db.query(EvaluationResult).filter(EvaluationResult.sheet_id == sheet_id).first()
        )
        if existing_result:
            existing_result.correct_count = summary["correct_count"]
            existing_result.wrong_count = summary["wrong_count"]
            existing_result.blank_count = summary["blank_count"]
            existing_result.invalid_count = summary["invalid_count"]
            existing_result.final_marks = summary["final_marks"]
            existing_result.max_marks = summary["max_marks"]
            existing_result.percentage = summary["percentage"]
        else:
            db.add(EvaluationResult(
                sheet_id=sheet_id,
                exam_id=exam.exam_id,
                correct_count=summary["correct_count"],
                wrong_count=summary["wrong_count"],
                blank_count=summary["blank_count"],
                invalid_count=summary["invalid_count"],
                final_marks=summary["final_marks"],
                max_marks=summary["max_marks"],
                percentage=summary["percentage"],
            ))
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error while saving the evaluation result: {exc}")

    return {
        "success": True,
        "message": "Evaluation complete.",
        "exam_name": exam.exam_name,
        "student_name": sheet.student_name,
        "roll_number": sheet.roll_number,
        "sheet_type": sheet.sheet_type.value if hasattr(sheet.sheet_type, "value") else str(sheet.sheet_type),
        "summary": summary,
        "question_results": question_results,
    }


@router.get("/{sheet_id}", response_model=dict)
def get_evaluation_result(sheet_id: int, db: Session = Depends(get_db)):
    """
    Returns a previously computed result for a student sheet,
    including the full question-wise breakdown and any previously
    generated AI Performance Analysis.
    """
    sheet, exam = _load_sheet_and_exam(sheet_id, db)

    saved_result = db.query(EvaluationResult).filter(EvaluationResult.sheet_id == sheet_id).first()
    if not saved_result:
        raise HTTPException(
            status_code=404,
            detail="This sheet has not been evaluated yet. Please run the evaluation first.",
        )

    # The question-wise breakdown is recomputed from the stored
    # answer key + detected responses (both of which are already
    # saved), so it always stays consistent with the saved summary
    # without needing a separate "question results" table.
    question_results, summary = _build_question_results(sheet_id, exam, db)

    return {
        "success": True,
        "exam_name": exam.exam_name,
        "student_name": sheet.student_name,
        "roll_number": sheet.roll_number,
        "sheet_type": sheet.sheet_type.value if hasattr(sheet.sheet_type, "value") else str(sheet.sheet_type),
        "summary": summary,
        "question_results": question_results,
        "ai_analysis": saved_result.ai_analysis,
        "evaluated_at": saved_result.evaluated_at.isoformat() if saved_result.evaluated_at else None,
    }


@router.post("/analyze/{sheet_id}", response_model=dict)
def analyze_performance(sheet_id: int, db: Session = Depends(get_db)):
    """
    Generates an AI Performance Analysis (strong topics, weak
    topics, suggestions) for an already-evaluated student sheet
    using Gemini, then saves it onto the evaluation_results row and
    logs the full exchange in ai_responses.

    For AI-Based Evaluation exams, question text (stored on the
    Question table) is included so Gemini can reason about real
    topics. OMR exams have no stored question text, so Gemini
    reasons using question numbers and correct/wrong patterns only
    (see README/TESTING notes for this limitation).
    """
    sheet, exam = _load_sheet_and_exam(sheet_id, db)

    saved_result = db.query(EvaluationResult).filter(EvaluationResult.sheet_id == sheet_id).first()
    if not saved_result:
        raise HTTPException(
            status_code=400,
            detail="This sheet has not been evaluated yet. Please run the evaluation first.",
        )

    question_results, summary = _build_question_results(sheet_id, exam, db)

    # Question text is used so Gemini can reason about real topics
    # rather than just question numbers. This works for BOTH exam
    # types now: AI-Based Evaluation always has Question rows (from
    # manual entry or extraction), and OMR exams have them too if a
    # question paper was uploaded and successfully parsed (see
    # omr_router.py). If no Question rows exist for this exam
    # (e.g. no question paper was uploaded for an OMR exam), this is
    # simply an empty dict and the analysis falls back to reasoning
    # by question number only -- see the "Known limitations" note.
    questions = db.query(Question).filter(Question.exam_id == exam.exam_id).all()
    question_texts = {q.question_number: q.question_text for q in questions}

    try:
        analysis = gemini_analyze_performance(
            exam_name=exam.exam_name,
            question_results=question_results,
            summary=summary,
            question_texts=question_texts,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    try:
        db.add(AIResponse(
            exam_id=exam.exam_id,
            request_type=AIRequestType.ANALYZE_RESULTS,
            prompt_text=analysis["prompt"],
            response_text=json.dumps({
                "strong_topics": analysis["strong_topics"],
                "weak_topics": analysis["weak_topics"],
                "suggestions": analysis["suggestions"],
            }),
        ))
        saved_result.ai_analysis = analysis["formatted_text"]
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error while saving the AI performance analysis: {exc}")

    return {
        "success": True,
        "message": "AI Performance Analysis generated.",
        "strong_topics": analysis["strong_topics"],
        "weak_topics": analysis["weak_topics"],
        "suggestions": analysis["suggestions"],
        "ai_analysis": analysis["formatted_text"],
    }
