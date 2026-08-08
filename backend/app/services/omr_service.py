"""
omr_service.py
---------------
Processes a scanned/photographed OMR (bubble) answer sheet using
OpenCV only (no OCR needed for this format).

Pipeline:
    1. Correct perspective/rotation (best-effort) so the sheet is
       viewed straight-on.
    2. Threshold the image so filled bubbles become bright blobs.
    3. Find bubble-shaped contours (circular, consistent size).
    4. Group bubbles into rows (one row = one question) and columns
       (one column = one option, A/B/C/D/[E]) -- this grouping IS
       the "configurable template": it is auto-detected from
       whatever grid the bubbles actually form, so it adapts to
       different sheet layouts without needing a hand-made template
       file.
    5. For every bubble, measure how "filled" it is. 0 filled in a
       row = BLANK, exactly 1 = DETECTED, more than 1 = INVALID.
"""

import cv2
import numpy as np

OPTION_LETTERS = ["A", "B", "C", "D", "E"]
FILL_THRESHOLD = 0.45  # fraction of a bubble's area that must be dark/filled ink


def _order_points(pts: np.ndarray) -> np.ndarray:
    """Orders 4 corner points as [top-left, top-right, bottom-right, bottom-left]."""
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect


def correct_perspective(image: np.ndarray) -> np.ndarray:
    """
    Attempts to detect the sheet's outer paper boundary and warp it
    into a straight top-down view. This corrects basic rotation,
    perspective skew, and scan distortion. If no confident 4-sided
    boundary is found, the original image is returned unchanged --
    a safe fallback for already-straight scans.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edged = cv2.Canny(blurred, 50, 150)
    edged = cv2.dilate(edged, None, iterations=2)

    contours, _ = cv2.findContours(edged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return image

    largest = max(contours, key=cv2.contourArea)
    image_area = image.shape[0] * image.shape[1]

    if cv2.contourArea(largest) < 0.4 * image_area:
        return image

    peri = cv2.arcLength(largest, True)
    approx = cv2.approxPolyDP(largest, 0.02 * peri, True)

    if len(approx) != 4:
        return image

    pts = approx.reshape(4, 2).astype("float32")
    rect = _order_points(pts)
    (tl, tr, br, bl) = rect

    width_a = np.linalg.norm(br - bl)
    width_b = np.linalg.norm(tr - tl)
    max_width = int(max(width_a, width_b))

    height_a = np.linalg.norm(tr - br)
    height_b = np.linalg.norm(tl - bl)
    max_height = int(max(height_a, height_b))

    if max_width < 100 or max_height < 100:
        return image

    dst = np.array([
        [0, 0],
        [max_width - 1, 0],
        [max_width - 1, max_height - 1],
        [0, max_height - 1],
    ], dtype="float32")

    matrix = cv2.getPerspectiveTransform(rect, dst)
    warped = cv2.warpPerspective(image, matrix, (max_width, max_height))
    return warped


def compute_bubble_threshold(image: np.ndarray) -> np.ndarray:
    """
    Shared preprocessing step: converts a BGR image into the binary
    (inverted) threshold image that both bubble-fill scoring
    (process_omr_sheet) and sheet-type detection
    (sheet_detection_service.py) use to find bubble-shaped contours.
    Kept in one place so both callers always use identical tuning.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    thresh = cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 21, 10
    )
    return thresh


def find_bubble_contours(thresh_image: np.ndarray):
    """Finds contours that look like OMR bubbles (small, roughly circular)."""
    # RETR_EXTERNAL only keeps the outermost contour of each blob, so
    # a hollow (unfilled) bubble's outline isn't counted twice (once
    # for its outer edge, once for its inner edge).
    contours, _ = cv2.findContours(thresh_image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    bubbles = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < 80 or area > 6000:
            continue
        perimeter = cv2.arcLength(c, True)
        if perimeter == 0:
            continue
        circularity = 4 * np.pi * (area / (perimeter * perimeter))
        x, y, w, h = cv2.boundingRect(c)
        aspect_ratio = w / float(h) if h else 0
        if circularity > 0.55 and 0.7 <= aspect_ratio <= 1.3:
            cx, cy = x + w // 2, y + h // 2
            bubbles.append({"cx": cx, "cy": cy, "x": x, "y": y, "w": w, "h": h, "contour": c})
    return bubbles


def _group_into_rows(bubbles, row_gap_ratio: float = 0.6):
    """Groups bubble centers into horizontal rows (one row = one question)."""
    if not bubbles:
        return []

    bubbles_sorted = sorted(bubbles, key=lambda b: b["cy"])
    avg_h = float(np.mean([b["h"] for b in bubbles_sorted]))
    row_gap = avg_h * row_gap_ratio if avg_h > 0 else 10

    rows = []
    current_row = [bubbles_sorted[0]]
    for b in bubbles_sorted[1:]:
        if b["cy"] - current_row[-1]["cy"] <= row_gap:
            current_row.append(b)
        else:
            rows.append(current_row)
            current_row = [b]
    rows.append(current_row)

    for row in rows:
        row.sort(key=lambda b: b["cx"])
    rows.sort(key=lambda row: row[0]["cy"])
    return rows


def _compute_fill_ratio(thresh_image: np.ndarray, bubble: dict) -> float:
    """Returns the fraction (0-1) of a bubble's contour area that is filled/dark ink."""
    mask = np.zeros(thresh_image.shape, dtype="uint8")
    cv2.drawContours(mask, [bubble["contour"]], -1, 255, -1)
    filled_pixels = cv2.countNonZero(cv2.bitwise_and(thresh_image, mask))
    total_pixels = cv2.countNonZero(mask)
    if total_pixels == 0:
        return 0.0
    return filled_pixels / total_pixels


def process_omr_sheet(image_path: str, total_questions: int) -> dict:
    """
    Main entry point: reads an OMR sheet image and returns detected
    responses for every question.

    Returns:
        {
          1: {"selected_option": "B", "status": "DETECTED", "confidence": 0.9},
          2: {"selected_option": None, "status": "BLANK", "confidence": None},
          3: {"selected_option": "B,C", "status": "INVALID", "confidence": None},
          ...
        }

    Raises RuntimeError with a friendly message if the image can't
    be read or no bubble grid can be reliably detected.
    """
    image = cv2.imread(image_path)
    if image is None:
        raise RuntimeError(
            "The image file could not be read. It may be corrupted or in an unsupported format."
        )

    image = correct_perspective(image)
    thresh = compute_bubble_threshold(image)

    bubbles = find_bubble_contours(thresh)
    if len(bubbles) < max(total_questions, 4):
        raise RuntimeError(
            "Could not reliably detect bubble marks on this sheet. "
            "Please make sure the OMR sheet is clearly scanned/photographed with good, even lighting."
        )

    rows = _group_into_rows(bubbles)

    row_lengths = [len(row) for row in rows]
    options_count = max(set(row_lengths), key=row_lengths.count)
    options_count = min(options_count, len(OPTION_LETTERS))

    valid_rows = [row for row in rows if len(row) == options_count]

    responses = {}
    for question_number, row in enumerate(valid_rows[:total_questions], start=1):
        filled_options = []
        for i, bubble in enumerate(row[:options_count]):
            fill_ratio = _compute_fill_ratio(thresh, bubble)
            if fill_ratio >= FILL_THRESHOLD:
                filled_options.append(OPTION_LETTERS[i])

        if len(filled_options) == 0:
            responses[question_number] = {"selected_option": None, "status": "BLANK", "confidence": None}
        elif len(filled_options) == 1:
            responses[question_number] = {"selected_option": filled_options[0], "status": "DETECTED", "confidence": 0.9}
        else:
            responses[question_number] = {
                "selected_option": ",".join(filled_options),
                "status": "INVALID",
                "confidence": None,
            }

    for question_number in range(1, total_questions + 1):
        if question_number not in responses:
            responses[question_number] = {"selected_option": None, "status": "BLANK", "confidence": None}

    return responses
