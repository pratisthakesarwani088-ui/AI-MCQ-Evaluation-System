"""
student_sheet_router.py
-------------------------
API endpoints for uploading a student's answer sheet image.

Endpoints:
    POST /api/student-sheet/upload/{exam_id}   -> Upload one student sheet
    GET  /api/student-sheet/exam/{exam_id}     -> List all sheets for an exam
    GET  /api/student-sheet/{sheet_id}         -> Get one sheet's details

NOTE: Sheet-type detection and OMR/Normal-MCQ processing (reading
the actual marked answers out of the image) are implemented in
Module 5. This module only handles saving the upload safely.
"""

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.database import get_db
from app.config import EXAMS_DIR
from app.models.exam import Exam
from app.models.verified_answer_key import VerifiedAnswerKey
from app.models.student_sheet import StudentAnswerSheet, SheetType
from app.models.student_response import StudentResponse, DetectionStatus
from app.schemas.student_sheet_schema import StudentSheetOut
from app.utils.file_utils import save_upload_file
from app.services.mcq_processing_service import process_student_sheet

router = APIRouter(prefix="/api/student-sheet", tags=["Student Sheet"])


def _get_exam_or_404(exam_id: int, db: Session) -> Exam:
    exam = db.query(Exam).filter(Exam.exam_id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail=f"Exam with id {exam_id} not found.")
    return exam


def _ensure_answer_key_verified(exam: Exam, db: Session):
    """
    A student sheet can only be uploaded once the teacher has fully
    verified the answer key -- otherwise there is nothing correct
    to evaluate against.
    """
    verified_count = (
        db.query(VerifiedAnswerKey)
        .filter(
            VerifiedAnswerKey.exam_id == exam.exam_id,
            VerifiedAnswerKey.is_verified.is_(True),
        )
        .count()
    )
    if verified_count < exam.total_questions:
        raise HTTPException(
            status_code=400,
            detail=(
                "The answer key for this exam has not been fully verified yet. "
                "Please complete Step 3 (Verify Answer Key) before uploading a student sheet."
            ),
        )


@router.post("/upload/{exam_id}", response_model=dict)
def upload_student_sheet(
    exam_id: int,
    file: UploadFile = File(...),
    student_name: Optional[str] = Form(None),
    roll_number: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """
    Saves an uploaded student answer sheet image and creates a
    database record for it. Sheet type starts as UNKNOWN and is
    filled in during processing (Module 5).
    """
    exam = _get_exam_or_404(exam_id, db)
    _ensure_answer_key_verified(exam, db)

    destination_folder = os.path.join(EXAMS_DIR, str(exam_id), "student_sheets")
    saved_path = save_upload_file(file, destination_folder)

    try:
        sheet = StudentAnswerSheet(
            exam_id=exam_id,
            student_name=(student_name or "").strip() or None,
            roll_number=(roll_number or "").strip() or None,
            image_path=saved_path,
            sheet_type=SheetType.UNKNOWN,
        )
        db.add(sheet)
        db.commit()
        db.refresh(sheet)
    except SQLAlchemyError as exc:
        db.rollback()
        # Clean up the saved file if the DB write failed, so we
        # don't leave orphaned images on disk.
        if os.path.exists(saved_path):
            os.remove(saved_path)
        raise HTTPException(status_code=500, detail=f"Database error while saving student sheet: {exc}")

    return {
        "success": True,
        "message": "Student answer sheet uploaded successfully.",
        "sheet": StudentSheetOut.model_validate(sheet).model_dump(),
    }


@router.get("/exam/{exam_id}", response_model=dict)
def list_student_sheets(exam_id: int, db: Session = Depends(get_db)):
    """Returns every student sheet uploaded for a given exam."""
    _get_exam_or_404(exam_id, db)

    sheets = (
        db.query(StudentAnswerSheet)
        .filter(StudentAnswerSheet.exam_id == exam_id)
        .order_by(StudentAnswerSheet.uploaded_at.desc())
        .all()
    )

    return {
        "success": True,
        "sheets": [StudentSheetOut.model_validate(s).model_dump() for s in sheets],
    }


@router.post("/process/{sheet_id}", response_model=dict)
def process_sheet(sheet_id: int, db: Session = Depends(get_db)):
    """
    Runs sheet-type detection followed by OMR or normal-MCQ
    processing on an already-uploaded student sheet, then saves
    (or re-saves, if run again) the detected per-question responses.

    This does NOT compute marks -- it only figures out what the
    student actually selected for each question. Scoring against
    the verified answer key happens in the evaluation engine.
    """
    sheet = db.query(StudentAnswerSheet).filter(StudentAnswerSheet.sheet_id == sheet_id).first()
    if not sheet:
        raise HTTPException(status_code=404, detail=f"Student sheet with id {sheet_id} not found.")

    exam = _get_exam_or_404(sheet.exam_id, db)

    try:
        sheet_type, responses = process_student_sheet(sheet.image_path, exam.total_questions)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    try:
        sheet.sheet_type = SheetType.OMR if sheet_type == "OMR" else SheetType.NORMAL

        existing_responses = {
            r.question_number: r
            for r in db.query(StudentResponse).filter(StudentResponse.sheet_id == sheet_id).all()
        }

        for question_number, result in responses.items():
            status_value = DetectionStatus(result["status"])
            if question_number in existing_responses:
                row = existing_responses[question_number]
                row.selected_option = result["selected_option"]
                row.detection_status = status_value
                row.confidence = result["confidence"]
            else:
                db.add(StudentResponse(
                    sheet_id=sheet_id,
                    question_number=question_number,
                    selected_option=result["selected_option"],
                    detection_status=status_value,
                    confidence=result["confidence"],
                ))

        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error while saving detected responses: {exc}")

    ordered_responses = [
        {
            "question_number": q,
            "selected_option": responses[q]["selected_option"],
            "status": responses[q]["status"],
            "confidence": responses[q]["confidence"],
        }
        for q in sorted(responses.keys())
    ]

    return {
        "success": True,
        "message": f"Sheet processed as a {sheet_type} sheet.",
        "sheet_type": sheet_type,
        "responses": ordered_responses,
    }


@router.get("/{sheet_id}", response_model=dict)
def get_student_sheet(sheet_id: int, db: Session = Depends(get_db)):
    """Returns a single student sheet's details."""
    sheet = db.query(StudentAnswerSheet).filter(StudentAnswerSheet.sheet_id == sheet_id).first()
    if not sheet:
        raise HTTPException(status_code=404, detail=f"Student sheet with id {sheet_id} not found.")

    return {
        "success": True,
        "sheet": StudentSheetOut.model_validate(sheet).model_dump(),
    }
