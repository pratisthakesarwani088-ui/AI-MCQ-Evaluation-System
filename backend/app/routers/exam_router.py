"""
exam_router.py
--------------
API endpoints for creating, listing, and fetching exams.

Endpoints:
    POST   /api/exams          -> Create a new exam
    GET    /api/exams          -> List exams (search/filter/sort, most recent first by default)
    GET    /api/exams/{id}     -> Get a single exam by id
    DELETE /api/exams/{id}     -> Delete an exam (and all related data)
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.database import get_db
from app.models.exam import Exam, ExamType
from app.models.evaluation_result import EvaluationResult
from app.schemas.exam_schema import ExamCreate, ExamOut
from app.utils.file_utils import create_exam_directories

router = APIRouter(prefix="/api/exams", tags=["Exams"])


@router.post("", response_model=dict)
def create_exam(exam_data: ExamCreate, db: Session = Depends(get_db)):
    """
    Creates a new exam record, then sets up its local folder
    structure (question papers, answer key, student sheets, and
    reports) so every later step already has somewhere to save
    files.

    Basic sanity check: negative marks configured cannot be larger
    than the marks awarded per correct answer (that would be an
    unusual, likely-mistaken configuration for a teacher).
    """
    if exam_data.negative_marks > exam_data.marks_per_correct:
        raise HTTPException(
            status_code=400,
            detail="Negative marks cannot be greater than marks per correct answer.",
        )

    try:
        new_exam = Exam(
            exam_name=exam_data.exam_name.strip(),
            subject=exam_data.subject,
            exam_type=ExamType(exam_data.exam_type),
            total_questions=exam_data.total_questions,
            marks_per_correct=exam_data.marks_per_correct,
            negative_marks=exam_data.negative_marks,
        )
        db.add(new_exam)
        db.commit()
        db.refresh(new_exam)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Database error while creating exam: {exc}",
        )

    # The exam record is safely saved at this point. Setting up its
    # folders is a best-effort step: if it fails (e.g. a disk/
    # permissions issue), we don't undo the exam -- we just let the
    # teacher know, since folders are also created lazily on first
    # upload as a fallback (see save_upload_file).
    directories_created = True
    try:
        create_exam_directories(new_exam.exam_id)
    except OSError:
        directories_created = False

    message = f"Exam '{new_exam.exam_name}' created successfully."
    if not directories_created:
        message += " (Note: could not pre-create upload folders; they will be created automatically on first upload instead.)"

    return {
        "success": True,
        "message": message,
        "exam": ExamOut.model_validate(new_exam).model_dump(),
        "directories_created": directories_created,
    }


@router.get("", response_model=dict)
def list_exams(
    db: Session = Depends(get_db),
    search: Optional[str] = Query(None, description="Search by exam name (partial match)"),
    subject: Optional[str] = Query(None, description="Filter by subject (partial match)"),
    exam_type: Optional[str] = Query(None, description="Filter by exam type: 'AI' or 'OMR'"),
    sort: str = Query("newest", description="Sort order: 'newest', 'oldest', or 'name'"),
):
    """
    Returns exams, optionally filtered by name/subject/type and
    sorted. All parameters are optional and default to the original
    behavior (every exam, most recently created first), so existing
    callers that don't pass any query params are unaffected.

    Each exam also includes `evaluated_count` -- the number of
    student sheets that have a saved evaluation result for it.
    """
    try:
        query = db.query(Exam)

        if search:
            query = query.filter(Exam.exam_name.ilike(f"%{search.strip()}%"))
        if subject:
            query = query.filter(Exam.subject.ilike(f"%{subject.strip()}%"))
        if exam_type:
            exam_type_clean = exam_type.strip().upper()
            if exam_type_clean not in ("AI", "OMR"):
                raise HTTPException(status_code=400, detail="exam_type filter must be either 'AI' or 'OMR'.")
            query = query.filter(Exam.exam_type == ExamType(exam_type_clean))

        if sort == "oldest":
            query = query.order_by(Exam.created_at.asc())
        elif sort == "name":
            query = query.order_by(Exam.exam_name.asc())
        else:
            query = query.order_by(Exam.created_at.desc())

        exams = query.all()

        # Count evaluated students per exam in one query rather than
        # N+1 queries per exam.
        exam_ids = [e.exam_id for e in exams]
        counts_by_exam = {}
        if exam_ids:
            count_rows = (
                db.query(EvaluationResult.exam_id, func.count(EvaluationResult.result_id))
                .filter(EvaluationResult.exam_id.in_(exam_ids))
                .group_by(EvaluationResult.exam_id)
                .all()
            )
            counts_by_exam = {exam_id: count for exam_id, count in count_rows}
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Database error: {exc}")

    exams_out = []
    for e in exams:
        exam_dict = ExamOut.model_validate(e).model_dump()
        exam_dict["evaluated_count"] = counts_by_exam.get(e.exam_id, 0)
        exams_out.append(exam_dict)

    return {
        "success": True,
        "exams": exams_out,
    }


@router.get("/{exam_id}", response_model=dict)
def get_exam(exam_id: int, db: Session = Depends(get_db)):
    """Returns a single exam by its id, including its evaluated student count."""
    exam = db.query(Exam).filter(Exam.exam_id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail=f"Exam with id {exam_id} not found.")

    evaluated_count = (
        db.query(func.count(EvaluationResult.result_id))
        .filter(EvaluationResult.exam_id == exam_id)
        .scalar()
    ) or 0

    exam_dict = ExamOut.model_validate(exam).model_dump()
    exam_dict["evaluated_count"] = evaluated_count

    return {
        "success": True,
        "exam": exam_dict,
    }


@router.delete("/{exam_id}", response_model=dict)
def delete_exam(exam_id: int, db: Session = Depends(get_db)):
    """
    Deletes an exam along with all its related data (answer keys,
    student sheets, responses, results) thanks to cascading deletes
    defined in the ORM models / database schema.
    """
    exam = db.query(Exam).filter(Exam.exam_id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail=f"Exam with id {exam_id} not found.")

    try:
        db.delete(exam)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error while deleting exam: {exc}")

    return {"success": True, "message": f"Exam '{exam.exam_name}' deleted."}
