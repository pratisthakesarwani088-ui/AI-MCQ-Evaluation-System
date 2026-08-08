"""
ocr_service.py
---------------
Wraps PaddleOCR to read text from an answer-key image and parses
that text into a clean {question_number: correct_option} mapping.

This is the ONLY place in the project that talks to PaddleOCR for
the answer key. Keeping it isolated here means the rest of the app
never has to worry about OCR-library details.
"""

import re

# PaddleOCR is imported lazily (inside get_ocr_engine) so that the
# rest of the application can still start up even before the OCR
# model files have finished downloading on first run.
_ocr_engine = None


def get_ocr_engine():
    """
    Creates (once) and returns a shared PaddleOCR engine instance.
    Reusing one instance avoids reloading the model on every
    request, which would be very slow.
    """
    global _ocr_engine
    if _ocr_engine is None:
        try:
            from paddleocr import PaddleOCR
            _ocr_engine = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
        except Exception as exc:
            raise RuntimeError(
                "Could not start the OCR engine. Make sure PaddleOCR and "
                f"PaddlePaddle are installed correctly. Details: {exc}"
            )
    return _ocr_engine


def extract_text_lines(image_path: str):
    """
    Runs OCR on the given image and returns a list of dicts:
        [{"text": "1 A", "confidence": 0.98}, ...]

    Raises RuntimeError with a friendly message if OCR fails
    (corrupt file, unreadable image, engine crash, etc.).
    """
    engine = get_ocr_engine()

    try:
        result = engine.ocr(image_path, cls=True)
    except Exception as exc:
        raise RuntimeError(
            f"OCR failed to process the image. It may be blurry, corrupted, "
            f"or in an unsupported format. Details: {exc}"
        )

    lines = []
    # PaddleOCR returns a list-of-pages; for a single image we use page 0.
    if result and len(result) > 0 and result[0]:
        for detection in result[0]:
            # detection format: [box_points, (text, confidence)]
            # box_points is a list of 4 [x, y] corner points of the
            # detected text region -- kept here so other services
            # (like mark detection on normal MCQ sheets) can crop the
            # exact image region a piece of text came from.
            box_points = detection[0]
            text = detection[1][0]
            confidence = float(detection[1][1])
            lines.append({"text": text, "confidence": confidence, "box": box_points})

    return lines


def parse_answer_key(lines):
    """
    Parses OCR-detected text lines into a {question_number: option}
    dictionary.

    Supports common handwritten/printed formats such as:
        "1 A"     "1. A"     "1-A"     "1) A"     "1:A"
    and also lines where several Q-A pairs were merged into one
    line by the OCR engine, e.g. "1 A  2 B  3 C".

    Returns:
        answer_map: dict[int, str]   e.g. {1: "A", 2: "C", 3: "D"}
        avg_confidence: float        average OCR confidence (0-1)
    """
    # Matches: question number, optional punctuation/space, then a
    # single option letter A-E (case-insensitive), as a whole word.
    pattern = re.compile(r'(\d{1,3})\s*[\.\)\-:]?\s*([A-Ea-e])\b')

    answer_map = {}
    confidences = []

    for line_obj in lines:
        text = line_obj["text"]
        confidence = line_obj["confidence"]
        matches = pattern.findall(text)
        for q_str, option in matches:
            question_number = int(q_str)
            answer_map[question_number] = option.upper()
            confidences.append(confidence)

    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return answer_map, avg_confidence
