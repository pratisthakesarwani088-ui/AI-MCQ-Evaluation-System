"""
file_utils.py
-------------
Small reusable helpers for validating and saving uploaded image
files, and for setting up an exam's folder structure on disk. Used
by the exam, answer-key, and student-sheet routers.
"""

import os
import uuid
from fastapi import UploadFile, HTTPException

from app.config import (
    ALLOWED_IMAGE_EXTENSIONS,
    ALLOWED_DOCUMENT_EXTENSIONS,
    MAX_UPLOAD_SIZE_MB,
    EXAMS_DIR,
    REPORTS_DIR,
)


def create_exam_directories(exam_id: int) -> dict:
    """
    Creates every local folder a new exam will need, right when the
    exam is created, so later steps (uploading a question paper,
    answer key, or student sheets, and generating reports) never
    have to worry about missing directories.

    Returns a dict of the created paths, keyed by purpose.
    """
    exam_root = os.path.join(EXAMS_DIR, str(exam_id))
    question_papers_dir = os.path.join(exam_root, "question_papers")
    answer_key_dir = os.path.join(exam_root, "answer_key")
    student_sheets_dir = os.path.join(exam_root, "student_sheets")
    exam_reports_dir = os.path.join(REPORTS_DIR, str(exam_id))

    for folder in (exam_root, question_papers_dir, answer_key_dir, student_sheets_dir, exam_reports_dir):
        os.makedirs(folder, exist_ok=True)

    return {
        "exam_root": exam_root,
        "question_papers": question_papers_dir,
        "answer_key": answer_key_dir,
        "student_sheets": student_sheets_dir,
        "reports": exam_reports_dir,
    }


def validate_extension(filename: str, allowed_extensions: set, kind_label: str = "file") -> str:
    """
    Checks that `filename` ends in one of `allowed_extensions`
    (e.g. {'.pdf', '.docx', '.txt'}). Returns the lowercase
    extension if valid, otherwise raises a friendly HTTPException
    naming the allowed types.
    """
    _, ext = os.path.splitext(filename.lower())
    if ext not in allowed_extensions:
        allowed_list = ", ".join(sorted(e.lstrip(".").upper() for e in allowed_extensions))
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported {kind_label} type '{ext}'. Only {allowed_list} are allowed.",
        )
    return ext


def validate_image_extension(filename: str) -> str:
    """Backwards-compatible wrapper: validates an image file extension."""
    return validate_extension(filename, ALLOWED_IMAGE_EXTENSIONS, kind_label="file")


def validate_document_extension(filename: str) -> str:
    """Validates a question-paper document extension (PDF/DOCX/TXT)."""
    return validate_extension(filename, ALLOWED_DOCUMENT_EXTENSIONS, kind_label="document")


def save_upload_file(upload_file: UploadFile, destination_folder: str, allowed_extensions: set = None) -> str:
    """
    Saves an UploadFile to `destination_folder` with a unique,
    collision-free filename, and returns the full path where it was
    saved. Creates the destination folder if it doesn't exist.

    `allowed_extensions` defaults to image extensions (the original
    behavior of this function); pass ALLOWED_DOCUMENT_EXTENSIONS to
    save a question-paper document instead.

    Raises HTTPException on invalid file type or oversized file.
    """
    if allowed_extensions is None:
        allowed_extensions = ALLOWED_IMAGE_EXTENSIONS

    ext = validate_extension(upload_file.filename, allowed_extensions)

    os.makedirs(destination_folder, exist_ok=True)

    # Generate a unique filename so two uploads never overwrite
    # each other, even if the original filenames match.
    unique_name = f"{uuid.uuid4().hex}{ext}"
    full_path = os.path.join(destination_folder, unique_name)

    # Read the file in chunks so we can also enforce a max size
    # without loading a huge file fully into memory first.
    max_bytes = MAX_UPLOAD_SIZE_MB * 1024 * 1024
    total_bytes = 0

    try:
        with open(full_path, "wb") as buffer:
            while True:
                chunk = upload_file.file.read(1024 * 1024)  # 1 MB chunks
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    buffer.close()
                    os.remove(full_path)
                    raise HTTPException(
                        status_code=400,
                        detail=f"File too large. Maximum allowed size is {MAX_UPLOAD_SIZE_MB} MB.",
                    )
                buffer.write(chunk)
    except HTTPException:
        raise
    except Exception as exc:
        # Clean up a partially written file on any unexpected error.
        if os.path.exists(full_path):
            os.remove(full_path)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save uploaded file: {exc}",
        )
    finally:
        upload_file.file.close()

    return full_path


def save_document_file(upload_file: UploadFile, destination_folder: str) -> str:
    """Convenience wrapper: saves a question-paper document (PDF/DOCX/TXT)."""
    return save_upload_file(upload_file, destination_folder, allowed_extensions=ALLOWED_DOCUMENT_EXTENSIONS)
