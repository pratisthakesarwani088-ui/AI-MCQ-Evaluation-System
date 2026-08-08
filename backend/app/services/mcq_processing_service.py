"""
mcq_processing_service.py
----------------------------
Top-level orchestrator for turning a student's uploaded sheet image
into a set of per-question detected responses.

Steps:
    1. Detect whether the sheet is OMR or a normal MCQ sheet.
    2. Run the matching processor (omr_service or normal_mcq_service).
    3. Return both the detected sheet type and the responses so the
       router can persist them.
"""

from app.services.sheet_detection_service import detect_sheet_type
from app.services.omr_service import process_omr_sheet
from app.services.normal_mcq_service import process_normal_sheet


def process_student_sheet(image_path: str, total_questions: int):
    """
    Returns a tuple: (sheet_type: str, responses: dict)

    sheet_type is one of "OMR" or "NORMAL".
    responses has the shape:
        {question_number: {"selected_option": ..., "status": ..., "confidence": ...}}

    Raises RuntimeError with a friendly message if the sheet type
    cannot be determined, or if the matching processor fails.
    """
    sheet_type = detect_sheet_type(image_path, total_questions)

    if sheet_type == "UNKNOWN":
        raise RuntimeError(
            "Could not determine whether this is an OMR sheet or a normal MCQ sheet. "
            "Please upload a clearer, well-lit photo of the answer sheet."
        )

    if sheet_type == "OMR":
        responses = process_omr_sheet(image_path, total_questions)
    else:
        responses = process_normal_sheet(image_path, total_questions)

    return sheet_type, responses
