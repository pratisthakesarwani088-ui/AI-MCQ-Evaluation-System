"""
omr_router.py
---------------
API endpoints specific to the OMR Evaluation module that aren't
already covered by other routers.

Everything else OMR Evaluation needs -- uploading/OCR-extracting
the answer key, uploading a student sheet, OpenCV bubble detection
with perspective/rotation correction, and automatic evaluation --
is already implemented and reused as-is from:
    answer_key_router.py    (Upload Answer Key, Verify Answer Key)
    student_sheet_router.py (Upload Student Sheet, sheet processing)
    evaluation_router.py    (Automatic evaluation, saving results)

This router adds the pieces those don't cover:
  - Uploading the Question Paper for an OMR exam (PDF/DOCX/TXT via
    direct text extraction, or a scanned image via OCR -- reusing
    the same PaddleOCR-based ocr_service.py used elsewhere).
  - Automatically parsing that text into Question rows (reusing the
    same question_extraction_service.py used by AI-Based
    Evaluation), so OMR exams also get real question text stored --
    this is what lets AI Performance Analysis give topic-wise
    feedback for OMR exams too, not just AI-Based ones.

Both the text extraction and the question-row extraction are
best-effort here: the question paper is still saved successfully
even if no text/questions could be pulled out of it, since it also
serves as a plain reference document for the teacher.

Endpoints:
    POST /api/omr-evaluation/upload-paper/{exam_id} -> Upload question paper
    GET  /api/omr-evaluation/papers/{exam_id}        -> List uploaded papers
"""

import os

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.database import get_db
from app.config import EXAMS_DIR, ALLOWED_DOCUMENT_EXTENSIONS, ALLOWED_IMAGE_EXTENSIONS
from app.models.exam import Exam, ExamType
from app.models.question_paper import QuestionPaper, PaperType, FileType
from app.utils.file_utils import save_upload_file
from app.services.document_parser_service import extract_text_from_document
from app.services.ocr_service import extract_text_lines
from app.services.question_extraction_service import extract_and_save_questions

router = APIRouter(prefix="/api/omr-evaluation", tags=["OMR Evaluation"])

# OMR question papers may be a text document OR a scanned/photographed
# image -- unlike AI-Based Evaluation's upload, which is document-only
# since Gemini needs clean text either way.
ALLOWED_QUESTION_PAPER_EXTENSIONS = ALLOWED_DOCUMENT_EXTENSIONS | ALLOWED_IMAGE_EXTENSIONS


def _get_exam_or_404(exam_id: int, db: Session) -> Exam:
    exam = db.query(Exam).filter(Exam.exam_id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail=f"Exam with id {exam_id} not found.")
    return exam


def _file_type_from_extension(filename: str) -> FileType:
    ext = os.path.splitext(filename.lower())[1]
    return {
        ".pdf": FileType.PDF,
        ".docx": FileType.DOCX,
        ".txt": FileType.TXT,
        ".jpg": FileType.IMAGE,
        ".jpeg": FileType.IMAGE,
        ".png": FileType.IMAGE,
    }.get(ext, FileType.TXT)


def _extract_text_best_effort(saved_path: str, file_type: FileType):
    """
    Extracts text from the saved question paper, using OCR for image
    files and direct document parsing for PDF/DOCX/TXT. Returns
    (extracted_text_or_None, error_message_or_None) -- this never
    raises, since question-paper upload treats extraction as
    best-effort.
    """
    try:
        if file_type == FileType.IMAGE:
            lines = extract_text_lines(saved_path)
            if not lines:
                return None, "No readable text was found in the image."
            text = "\n".join(line["text"] for line in lines)
            return text, None
        else:
            text = extract_text_from_document(saved_path, file_type.value)
            return text, None
    except RuntimeError as exc:
        return None, str(exc)


@router.post("/upload-paper/{exam_id}", response_model=dict)
def upload_omr_question_paper(exam_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Saves the question paper for an OMR exam (PDF/DOCX/TXT or a
    scanned image), extracts its text (via OCR for images, direct
    parsing otherwise), and automatically parses that text into
    Question rows so the exam has real question content available
    for AI Performance Analysis later.

    All of this is best-effort: the file is saved successfully even
    if text extraction or question parsing doesn't find anything
    usable, since the paper also serves as a reference document.
    """
    exam = _get_exam_or_404(exam_id, db)
    if exam.exam_type != ExamType.OMR:
        raise HTTPException(
            status_code=400,
            detail="This exam is configured for AI-Based Evaluation. Use that flow's question paper upload instead.",
        )

    destination_folder = os.path.join(EXAMS_DIR, str(exam_id), "question_papers")
    saved_path = save_upload_file(file, destination_folder, allowed_extensions=ALLOWED_QUESTION_PAPER_EXTENSIONS)
    file_type = _file_type_from_extension(file.filename)

    extracted_text, extraction_warning = _extract_text_best_effort(saved_path, file_type)

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

    # Best-effort: automatically parse the extracted text into
    # individual Question rows (question text + options), reusing
    # the exact same logic AI-Based Evaluation uses. If this doesn't
    # find any recognizable questions, that's fine -- the paper is
    # already saved either way.
    extraction_result = {"added_count": 0, "skipped_count": 0}
    if extracted_text:
        try:
            extraction_result = extract_and_save_questions(paper, db)
        except SQLAlchemyError as exc:
            db.rollback()
            # Saving the paper itself already succeeded and was
            # committed above -- a failure here just means we skip
            # auto-populating Question rows, not the whole upload.
            extraction_result = {"added_count": 0, "skipped_count": 0}

    message = "Question paper uploaded and saved."
    if extraction_warning:
        message += f" (Note: no text could be extracted -- {extraction_warning})"
    elif extraction_result.get("added_count"):
        message += f" Extracted {extraction_result['added_count']} question(s) for AI performance analysis."

    return {
        "success": True,
        "message": message,
        "paper_id": paper.paper_id,
        "character_count": len(extracted_text) if extracted_text else 0,
        "questions_extracted": extraction_result.get("added_count", 0),
    }


@router.get("/papers/{exam_id}", response_model=dict)
def list_omr_question_papers(exam_id: int, db: Session = Depends(get_db)):
    """Lists every question-paper document uploaded for an OMR exam."""
    _get_exam_or_404(exam_id, db)

    papers = (
        db.query(QuestionPaper)
        .filter(QuestionPaper.exam_id == exam_id, QuestionPaper.paper_type == PaperType.QUESTION_PAPER)
        .order_by(QuestionPaper.uploaded_at.desc())
        .all()
    )

    return {
        "success": True,
        "papers": [
            {
                "paper_id": p.paper_id,
                "file_type": p.file_type.value if p.file_type else None,
                "uploaded_at": p.uploaded_at.isoformat() if p.uploaded_at else None,
                "has_extracted_text": bool(p.extracted_text),
            }
            for p in papers
        ],
    }
