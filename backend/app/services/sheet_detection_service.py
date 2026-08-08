"""
sheet_detection_service.py
----------------------------
Automatically decides whether an uploaded student answer sheet is:
    - an OMR sheet (filled circular bubbles), or
    - a normal MCQ sheet (ticks/circles/boxes/handwritten answers)

Detection combines two pieces of evidence:
    1. How many clean "question number + option letter" text pairs
       OCR can read directly (strong evidence of a NORMAL sheet,
       e.g. handwritten "1-B", "2-C").
    2. How many circular, bubble-like shapes OpenCV finds arranged
       in a row/column grid (strong evidence of an OMR sheet).

Whichever type has stronger evidence wins. If neither has enough
evidence, the sheet type is reported as UNKNOWN so the caller can
show a friendly error instead of guessing wrong.
"""

import re
import cv2

from app.services.ocr_service import extract_text_lines
from app.services.omr_service import compute_bubble_threshold, find_bubble_contours

TEXT_PATTERN = re.compile(r'(\d{1,3})\s*[\.\)\-:]?\s*([A-Ea-e])\b')


def _count_text_answer_pairs(image_path: str) -> int:
    """Counts distinct question numbers found in "N-Option" style text."""
    try:
        lines = extract_text_lines(image_path)
    except RuntimeError:
        return 0

    question_numbers = set()
    for line_obj in lines:
        for q_str, _option in TEXT_PATTERN.findall(line_obj["text"]):
            question_numbers.add(int(q_str))
    return len(question_numbers)


def _count_bubble_like_shapes(image_path: str) -> int:
    """
    Counts contours that look like OMR bubbles -- the hallmark of a
    printed OMR answer sheet. Reuses the exact same thresholding and
    contour-filtering logic as omr_service.py's actual bubble-fill
    scoring, so sheet-type detection always agrees with what the
    real OMR processing pipeline would find.
    """
    image = cv2.imread(image_path)
    if image is None:
        return 0

    thresh = compute_bubble_threshold(image)
    bubbles = find_bubble_contours(thresh)
    return len(bubbles)


def detect_sheet_type(image_path: str, total_questions: int) -> str:
    """
    Returns one of: "OMR", "NORMAL", "UNKNOWN".

    Heuristic:
      - If at least 40% of questions have a readable "N-Option" text
        pair, treat it as a NORMAL sheet.
      - Else, if the number of bubble-like shapes found is at least
        roughly (total_questions * min_options), treat it as OMR.
      - Otherwise UNKNOWN.
    """
    text_pair_count = _count_text_answer_pairs(image_path)
    if total_questions > 0 and text_pair_count >= 0.4 * total_questions:
        return "NORMAL"

    bubble_count = _count_bubble_like_shapes(image_path)
    # A real OMR sheet needs at least ~2 bubbles per question (2-5
    # options) to be plausible.
    if total_questions > 0 and bubble_count >= 2 * total_questions:
        return "OMR"

    # Weak/partial text evidence is still better than nothing --
    # fall back to NORMAL if we found at least a few pairs.
    if text_pair_count > 0:
        return "NORMAL"

    return "UNKNOWN"
