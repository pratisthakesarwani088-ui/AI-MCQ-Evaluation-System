"""
question_extraction_service.py
---------------------------------
Shared logic for turning a QuestionPaper's extracted text into
individual Question rows in the database. Used by BOTH:
  - ai_evaluation_router.py's explicit "Extract Questions" step
  - omr_router.py's automatic best-effort extraction right after a
    question paper is uploaded

Keeping this in one place means OMR exams and AI-Based exams get
identical question-text extraction behavior, which in turn lets the
AI Performance Analysis feature (evaluation_router.py) give
topic-wise feedback for both exam types, not just AI-Based ones.
"""

from sqlalchemy.orm import Session

from app.models.question import Question, QuestionSource
from app.models.question_paper import QuestionPaper
from app.services.question_parser_service import parse_questions_from_text


def extract_and_save_questions(paper: QuestionPaper, db: Session) -> dict:
    """
    Parses `paper.extracted_text` into Question rows for
    `paper.exam_id`, skipping any question number that already
    exists for that exam (so re-running this is always safe).

    Returns:
        {
          "parsed": bool,        # whether parsing found any questions at all
          "added_count": int,
          "skipped_count": int,
          "error": str or None,  # human-readable reason if parsed=False
        }

    This function does NOT raise -- callers that want extraction to
    be a hard requirement (AI-Based Evaluation) should check the
    returned "parsed"/"error" fields and raise their own
    HTTPException; callers where it's best-effort (OMR Evaluation)
    can simply ignore a False "parsed" result.
    """
    if not paper.extracted_text or not paper.extracted_text.strip():
        return {"parsed": False, "added_count": 0, "skipped_count": 0, "error": "No extracted text available to parse."}

    try:
        parsed_questions = parse_questions_from_text(paper.extracted_text)
    except RuntimeError as exc:
        return {"parsed": False, "added_count": 0, "skipped_count": 0, "error": str(exc)}

    existing_numbers = {
        q.question_number
        for q in db.query(Question).filter(Question.exam_id == paper.exam_id).all()
    }

    added_count = 0
    skipped_count = 0
    for q in parsed_questions:
        if q["question_number"] in existing_numbers:
            skipped_count += 1
            continue
        db.add(Question(
            exam_id=paper.exam_id,
            paper_id=paper.paper_id,
            question_number=q["question_number"],
            question_text=q["question_text"],
            option_a=q["option_a"],
            option_b=q["option_b"],
            option_c=q["option_c"],
            option_d=q["option_d"],
            option_e=q["option_e"],
            source=QuestionSource.EXTRACTED,
        ))
        existing_numbers.add(q["question_number"])
        added_count += 1

    db.commit()

    return {"parsed": True, "added_count": added_count, "skipped_count": skipped_count, "error": None}
