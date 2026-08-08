"""
reports_router.py
--------------------
API endpoints for the Reports module: Student Report, Exam Report,
statistics, and PDF export.

Reuses existing logic wherever possible:
  - _load_sheet_and_exam / _build_question_results are imported
    directly from evaluation_router.py (the same helpers that
    already power the Result page), rather than re-querying the
    database in a slightly different way here.
  - statistics_service.py and pdf_report_service.py are the two
    genuinely new pieces this module needed (aggregate statistics
    across many students, and PDF rendering -- neither existed
    anywhere else in the app).

Endpoints:
    GET  /api/reports/student/{sheet_id}        -> Student Report data
    GET  /api/reports/exam/{exam_id}            -> Exam Report + statistics data
    POST /api/reports/student/{sheet_id}/pdf    -> Generate & save Student Report PDF
    POST /api/reports/exam/{exam_id}/pdf        -> Generate & save Exam Report PDF
    GET  /api/reports/list/{exam_id}            -> List previously generated reports
    GET  /api/reports/download/{report_id}      -> Download a generated report PDF
"""

import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.database import get_db
from app.config import REPORTS_DIR
from app.models.exam import Exam
from app.models.evaluation_result import EvaluationResult
from app.models.report import Report, ReportType
from app.routers.evaluation_router import _load_sheet_and_exam, _build_question_results
from app.services.statistics_service import compute_exam_statistics
from app.services.pdf_report_service import generate_student_report_pdf, generate_exam_report_pdf

router = APIRouter(prefix="/api/reports", tags=["Reports"])


def _get_exam_or_404(exam_id: int, db: Session) -> Exam:
    exam = db.query(Exam).filter(Exam.exam_id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail=f"Exam with id {exam_id} not found.")
    return exam


def _gather_student_report_data(sheet_id: int, db: Session) -> dict:
    """
    Reuses the same sheet/exam loading and scoring logic as the
    Result page (evaluation_router.py) to build the Student Report
    data, then adds the exam's subject (which the evaluation
    endpoints don't need but reports do).
    """
    sheet, exam = _load_sheet_and_exam(sheet_id, db)

    saved_result = db.query(EvaluationResult).filter(EvaluationResult.sheet_id == sheet_id).first()
    if not saved_result:
        raise HTTPException(
            status_code=400,
            detail="This sheet has not been evaluated yet. Please run the evaluation first.",
        )

    return {
        "exam_id": exam.exam_id,
        "sheet_id": sheet_id,
        "exam_name": exam.exam_name,
        "subject": exam.subject,
        "student_name": sheet.student_name,
        "roll_number": sheet.roll_number,
        "correct_count": saved_result.correct_count,
        "wrong_count": saved_result.wrong_count,
        "blank_count": saved_result.blank_count,
        "invalid_count": saved_result.invalid_count,
        "final_marks": saved_result.final_marks,
        "max_marks": saved_result.max_marks,
        "percentage": saved_result.percentage,
        "evaluated_at": saved_result.evaluated_at.isoformat() if saved_result.evaluated_at else None,
        "ai_analysis": saved_result.ai_analysis,
    }


def _gather_exam_report_data(exam_id: int, db: Session) -> dict:
    """Builds the Exam Report data: exam info + aggregate statistics across every evaluated student."""
    exam = _get_exam_or_404(exam_id, db)

    results = db.query(EvaluationResult).filter(EvaluationResult.exam_id == exam_id).all()
    stats = compute_exam_statistics(results)

    return {
        "exam_id": exam.exam_id,
        "exam_name": exam.exam_name,
        "subject": exam.subject,
        "exam_type": exam.exam_type.value if hasattr(exam.exam_type, "value") else str(exam.exam_type),
        **stats,
    }


@router.get("/student/{sheet_id}", response_model=dict)
def get_student_report(sheet_id: int, db: Session = Depends(get_db)):
    """Returns the Student Report data (for on-screen display, not the PDF)."""
    data = _gather_student_report_data(sheet_id, db)
    return {"success": True, **data}


@router.get("/exam/{exam_id}", response_model=dict)
def get_exam_report(exam_id: int, db: Session = Depends(get_db)):
    """Returns the Exam Report + statistics data (for on-screen display, not the PDF)."""
    data = _gather_exam_report_data(exam_id, db)
    return {"success": True, **data}


@router.post("/student/{sheet_id}/pdf", response_model=dict)
def generate_student_report_pdf_endpoint(sheet_id: int, db: Session = Depends(get_db)):
    """Generates the Student Report PDF, saves it to disk, and records it in the reports table."""
    data = _gather_student_report_data(sheet_id, db)

    reports_folder = os.path.join(REPORTS_DIR, str(data["exam_id"]))
    os.makedirs(reports_folder, exist_ok=True)
    file_name = f"student_report_sheet_{sheet_id}.pdf"
    output_path = os.path.join(reports_folder, file_name)

    try:
        generate_student_report_pdf(data, output_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to generate the Student Report PDF: {exc}")

    try:
        report = Report(
            exam_id=data["exam_id"],
            sheet_id=sheet_id,
            report_type=ReportType.STUDENT,
            file_path=output_path,
        )
        db.add(report)
        db.commit()
        db.refresh(report)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error while saving the report record: {exc}")

    return {
        "success": True,
        "message": "Student Report PDF generated.",
        "report_id": report.report_id,
    }


@router.post("/exam/{exam_id}/pdf", response_model=dict)
def generate_exam_report_pdf_endpoint(exam_id: int, db: Session = Depends(get_db)):
    """Generates the Exam Report PDF, saves it to disk, and records it in the reports table."""
    data = _gather_exam_report_data(exam_id, db)

    if data["total_students"] == 0:
        raise HTTPException(
            status_code=400,
            detail="No students have been evaluated for this exam yet, so an exam report can't be generated.",
        )

    reports_folder = os.path.join(REPORTS_DIR, str(exam_id))
    os.makedirs(reports_folder, exist_ok=True)
    file_name = f"exam_report_exam_{exam_id}.pdf"
    output_path = os.path.join(reports_folder, file_name)

    try:
        generate_exam_report_pdf(data, output_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to generate the Exam Report PDF: {exc}")

    try:
        report = Report(
            exam_id=exam_id,
            sheet_id=None,
            report_type=ReportType.EXAM,
            file_path=output_path,
        )
        db.add(report)
        db.commit()
        db.refresh(report)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error while saving the report record: {exc}")

    return {
        "success": True,
        "message": "Exam Report PDF generated.",
        "report_id": report.report_id,
    }


@router.get("/list/{exam_id}", response_model=dict)
def list_reports(exam_id: int, db: Session = Depends(get_db)):
    """Lists every previously generated report for an exam, most recent first."""
    _get_exam_or_404(exam_id, db)

    reports = (
        db.query(Report)
        .filter(Report.exam_id == exam_id)
        .order_by(Report.generated_at.desc())
        .all()
    )

    return {
        "success": True,
        "reports": [
            {
                "report_id": r.report_id,
                "report_type": r.report_type.value if hasattr(r.report_type, "value") else str(r.report_type),
                "sheet_id": r.sheet_id,
                "generated_at": r.generated_at.isoformat() if r.generated_at else None,
            }
            for r in reports
        ],
    }


@router.get("/download/{report_id}")
def download_report(report_id: int, db: Session = Depends(get_db)):
    """Downloads a previously generated report PDF."""
    report = db.query(Report).filter(Report.report_id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail=f"Report with id {report_id} not found.")

    if not report.file_path or not os.path.exists(report.file_path):
        raise HTTPException(status_code=404, detail="The report file could not be found on disk. It may have been moved or deleted.")

    download_name = os.path.basename(report.file_path)
    return FileResponse(report.file_path, media_type="application/pdf", filename=download_name)
