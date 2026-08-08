"""
normal_mcq_service.py
------------------------
Processes a "normal" (non-OMR) MCQ answer sheet: one where the
student wrote answers by hand (e.g. "1-B", "2. C") and/or marked a
printed option letter with a tick, circle, or box.

Two detection passes are combined:

  PASS 1 - Direct handwritten text (PaddleOCR):
      Reads lines like "1-B", "2) C", "3 D" directly. This is the
      simplest and most reliable case, and covers the answer
      formats explicitly supported by this project.

  PASS 2 - Marked printed option (OpenCV + PaddleOCR):
      For sheets where options are pre-printed (e.g. "1) A B C D")
      and the student circles/boxes/ticks one letter instead of
      writing it, PASS 1 finds no clean "number-letter" pair. For
      those questions only, this pass looks at the ink density
      around every lone option-letter OCR detected in that row.
      A letter that has been circled, boxed, or ticked collects
      noticeably more surrounding ink than a plain printed letter,
      so the option with unusually high ink density (compared to
      its row neighbours) is treated as the one the student marked.

If a question has more than one option that appears marked, or the
OCR confidence for its answer is too low, the response is marked
INVALID rather than guessed.
"""

import re
import cv2
import numpy as np

from app.services.ocr_service import extract_text_lines

TEXT_PATTERN = re.compile(r'(\d{1,3})\s*[\.\)\-:]?\s*([A-Ea-e])\b')
QUESTION_NUMBER_PATTERN = re.compile(r'^(\d{1,3})\s*[\.\)\-:]?$')
SINGLE_LETTER_PATTERN = re.compile(r'^[A-Ea-e]$')

MIN_CONFIDENCE = 0.55
# An option's ink density must be at least this many times the row's
# minimum density to be considered "marked" (circled/boxed/ticked).
MARK_DENSITY_MULTIPLIER = 1.6
MARGIN = 6  # pixels of padding added around a letter's box when cropping


def _box_to_rect(box_points):
    """Converts a 4-point OCR box into (x, y, w, h)."""
    xs = [p[0] for p in box_points]
    ys = [p[1] for p in box_points]
    x_min, x_max = int(min(xs)), int(max(xs))
    y_min, y_max = int(min(ys)), int(max(ys))
    return x_min, y_min, x_max - x_min, y_max - y_min


def _ink_density(image: np.ndarray, box_points, margin: int = MARGIN) -> float:
    """
    Returns the fraction of dark ("ink") pixels in a slightly
    expanded crop around a detected letter -- used to tell a plain
    printed letter apart from one that's been circled/boxed/ticked.
    """
    x, y, w, h = _box_to_rect(box_points)
    y0 = max(0, y - margin)
    y1 = min(image.shape[0], y + h + margin)
    x0 = max(0, x - margin)
    x1 = min(image.shape[1], x + w + margin)

    crop = image[y0:y1, x0:x1]
    if crop.size == 0:
        return 0.0

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if len(crop.shape) == 3 else crop
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    dark_pixels = cv2.countNonZero(thresh)
    total_pixels = thresh.shape[0] * thresh.shape[1]
    return dark_pixels / total_pixels if total_pixels else 0.0


def _detect_marked_options_pass(image: np.ndarray, lines: list, still_blank_questions: set) -> dict:
    """
    PASS 2: for questions still unanswered after the direct-text
    pass, tries to find a circled/boxed/ticked option letter printed
    on the same row as that question's number.
    """
    question_tokens = []  # [(question_number, box)]
    letter_tokens = []    # [(letter, box, ocr_confidence)]

    for line_obj in lines:
        text = line_obj["text"].strip()
        box = line_obj["box"]

        q_match = QUESTION_NUMBER_PATTERN.match(text)
        if q_match:
            question_tokens.append((int(q_match.group(1)), box))
            continue

        l_match = SINGLE_LETTER_PATTERN.match(text)
        if l_match:
            letter_tokens.append((text.upper(), box, line_obj["confidence"]))

    results = {}

    for question_number, q_box in question_tokens:
        if question_number not in still_blank_questions:
            continue

        # A letter belongs to this question's row if its vertical
        # center falls within the question number token's vertical span.
        _, q_y, _, q_h = _box_to_rect(q_box)
        row_top, row_bottom = q_y - q_h * 0.5, q_y + q_h * 1.5

        row_letters = []
        for letter, l_box, confidence in letter_tokens:
            _, l_y, _, l_h = _box_to_rect(l_box)
            l_center_y = l_y + l_h / 2
            if row_top <= l_center_y <= row_bottom:
                row_letters.append((letter, l_box, confidence))

        # Sort left-to-right so duplicate letters can still be told apart.
        row_letters.sort(key=lambda item: _box_to_rect(item[1])[0])

        if len(row_letters) < 2:
            continue  # Not enough printed options detected on this row.

        densities = [_ink_density(image, l_box) for _, l_box, _ in row_letters]
        min_density = min(densities)

        marked_indices = [
            i for i, d in enumerate(densities)
            if min_density > 0 and d >= min_density * MARK_DENSITY_MULTIPLIER
        ]
        # Guard against the (unlikely) case where min_density is 0
        # for every letter, which would make the ratio check invalid.
        if min_density == 0:
            marked_indices = [i for i, d in enumerate(densities) if d > 0.15]

        if not marked_indices:
            continue  # No option stood out -- leave as BLANK.

        marked_letters = [row_letters[i][0] for i in marked_indices]
        avg_confidence = sum(row_letters[i][2] for i in marked_indices) / len(marked_indices)

        if len(marked_letters) > 1:
            results[question_number] = {
                "selected_option": ",".join(sorted(set(marked_letters))),
                "status": "INVALID",
                "confidence": avg_confidence,
            }
        else:
            results[question_number] = {
                "selected_option": marked_letters[0],
                "status": "DETECTED",
                "confidence": avg_confidence,
            }

    return results


def process_normal_sheet(image_path: str, total_questions: int) -> dict:
    """
    Main entry point: reads a normal MCQ sheet image and returns
    detected responses for every question.

    Returns the same shape as omr_service.process_omr_sheet():
        {question_number: {"selected_option": ..., "status": ..., "confidence": ...}}
    """
    image = cv2.imread(image_path)
    if image is None:
        raise RuntimeError(
            "The image file could not be read. It may be corrupted or in an unsupported format."
        )

    lines = extract_text_lines(image_path)
    if not lines:
        raise RuntimeError(
            "No readable text was found on the student sheet. Please upload a clearer photo."
        )

    # ---------- PASS 1: direct "number-letter" text pairs ----------
    detections = {}
    for line_obj in lines:
        for q_str, option in TEXT_PATTERN.findall(line_obj["text"]):
            question_number = int(q_str)
            detections.setdefault(question_number, []).append((option.upper(), line_obj["confidence"]))

    responses = {}
    still_blank = set()

    for question_number in range(1, total_questions + 1):
        found = detections.get(question_number, [])

        if not found:
            responses[question_number] = {"selected_option": None, "status": "BLANK", "confidence": None}
            still_blank.add(question_number)
            continue

        options_found = {opt for opt, _ in found}
        avg_confidence = sum(c for _, c in found) / len(found)

        if len(options_found) > 1:
            responses[question_number] = {
                "selected_option": ",".join(sorted(options_found)),
                "status": "INVALID",
                "confidence": avg_confidence,
            }
        elif avg_confidence < MIN_CONFIDENCE:
            responses[question_number] = {
                "selected_option": None,
                "status": "INVALID",
                "confidence": avg_confidence,
            }
        else:
            responses[question_number] = {
                "selected_option": next(iter(options_found)),
                "status": "DETECTED",
                "confidence": avg_confidence,
            }

    # ---------- PASS 2: marked printed options (only for BLANK questions) ----------
    if still_blank:
        try:
            pass2_results = _detect_marked_options_pass(image, lines, still_blank)
            responses.update(pass2_results)
        except Exception:
            # Pass 2 is a best-effort enhancement -- if it fails for
            # any reason, we simply keep the PASS 1 (BLANK) results
            # rather than letting the whole evaluation crash.
            pass

    return responses
