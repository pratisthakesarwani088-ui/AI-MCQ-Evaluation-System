"""
previous_exams_router.py
---------------------------
API endpoints for the Previous Exams + Student Records module.

Listing/searching/filtering exams (GET /api/exams) and viewing a
single exam's details (GET /api/exams/{id}) already exist in
exam_router.py and are reused as-is. This router adds the two
pieces those don't cover:

  - Fetching the list of EVALUATED students for a specific exam,
    joining student_answer_sheets with evaluation_results (neither
    existing router returns marks/percentage alongside sheet info).
  - Permanently deleting a single student's record (sheet + its
    responses + its evaluation result, thanks to the existing
    cascading foreign keys -- see database.sql), removing the
    uploaded image file from disk, and logging the action.

Endpoints:
    GET    /api/previous-exams/{exam_id}/students -> List evaluated students for an exam
    DELETE /api/previous-exams/students/{sheet_id} -> Delete a student's record
"""

import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.database import get_db
from app.models.exam import Exam
from app.models.student_sheet import StudentAnswerSheet
from app.models.evaluation_result import EvaluationResult
from app.models.activity_log import ActivityLog

router = APIRouter(prefix="/api/previous-exams", tags=["Previous Exams"])


@router.get("/{exam_id}/students", response_model=dict)
def list_evaluated_students(exam_id: int, db: Session = Depends(get_db)):
    """
    Returns every student sheet for this exam that has a saved
    evaluation result, with the marks/percentage/evaluation date
    alongside the student's name/roll number.
    """
    exam = db.query(Exam).filter(Exam.exam_id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail=f"Exam with id {exam_id} not found.")

    rows = (
        db.query(StudentAnswerSheet, EvaluationResult)
        .join(EvaluationResult, EvaluationResult.sheet_id == StudentAnswerSheet.sheet_id)
        .filter(StudentAnswerSheet.exam_id == exam_id)
        .order_by(EvaluationResult.evaluated_at.desc())
        .all()
    )

    students = []
    for sheet, result in rows:
        students.append({
            "sheet_id": sheet.sheet_id,
            "student_name": sheet.student_name,
            "roll_number": sheet.roll_number,
            "sheet_type": sheet.sheet_type.value if hasattr(sheet.sheet_type, "value") else str(sheet.sheet_type),
            "final_marks": result.final_marks,
            "max_marks": result.max_marks,
            "percentage": result.percentage,
            "evaluated_at": result.evaluated_at.isoformat() if result.evaluated_at else None,
        })

    return {
        "success": True,
        "exam_id": exam_id,
        "exam_name": exam.exam_name,
        "students": students,
    }


@router.delete("/students/{sheet_id}", response_model=dict)
def delete_student_record(sheet_id: int, db: Session = Depends(get_db)):
    """
    Permanently deletes a student's record: the student sheet row
    (which cascades to delete its student_responses and
    evaluation_results rows via the existing foreign key
    ON DELETE CASCADE constraints -- see database.sql), the
    uploaded sheet image from disk, and logs the action in
    activity_logs.
    """
    sheet = db.query(StudentAnswerSheet).filter(StudentAnswerSheet.sheet_id == sheet_id).first()
    if not sheet:
        raise HTTPException(status_code=404, detail=f"Student sheet with id {sheet_id} not found.")

    exam = db.query(Exam).filter(Exam.exam_id == sheet.exam_id).first()
    exam_name = exam.exam_name if exam else f"exam #{sheet.exam_id}"
    student_label = sheet.student_name or sheet.roll_number or f"sheet #{sheet_id}"
    image_path = sheet.image_path

    try:
        # Deleting the sheet row cascades to student_responses and
        # evaluation_results automatically at the database level.
        db.delete(sheet)

        db.add(ActivityLog(
            action="DELETE_STUDENT_RECORD",
            description=(
                f"Deleted student record for '{student_label}' (sheet_id={sheet_id}) "
                f"from exam '{exam_name}' (exam_id={sheet.exam_id})."
            ),
        ))
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error while deleting the student record: {exc}")

    # Remove the uploaded image from disk if it still exists. This
    # happens after the DB commit succeeds, so a missing/already-
    # removed file never blocks the actual record deletion.
    file_removed = False
    if image_path and os.path.exists(image_path):
        try:
            os.remove(image_path)
            file_removed = True
        except OSError:
            file_removed = False

    return {
        "success": True,
        "message": f"Student record for '{student_label}' deleted permanently.",
        "file_removed": file_removed,
    }
