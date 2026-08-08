"""
question_parser_service.py
-----------------------------
Parses the raw text extracted from a question paper into individual
structured questions (question text + options A-E), so they can be
saved as Question rows and later sent to Gemini.

Expected format (numbered questions, lettered options), e.g.:

    1. What is the powerhouse of the cell?
    A) Nucleus
    B) Mitochondria
    C) Ribosome
    D) Golgi apparatus

    2. Which gas do plants absorb for photosynthesis?
    A) Oxygen
    B) Nitrogen
    C) Carbon Dioxide
    D) Hydrogen
"""

import re

# Matches a line that starts a new question: "1.", "1)", "Q1." etc.
QUESTION_START_PATTERN = re.compile(r'^\s*(?:Q\.?\s*)?(\d{1,3})[\.\)]\s+(.*)$', re.IGNORECASE)

# Matches a line that is a single lettered option: "A) ...", "A. ..."
OPTION_PATTERN = re.compile(r'^\s*([A-Ea-e])[\.\)]\s+(.*)$')


def parse_questions_from_text(text: str) -> list:
    """
    Parses raw text into a list of dicts:
        [{"question_number": 1, "question_text": "...",
          "option_a": "...", ..., "option_e": "..." (or None)}, ...]

    Lines that don't match a question or option pattern while a
    question is "open" are treated as a continuation of that
    question's text (handles line-wrapped questions).

    Raises RuntimeError if no questions could be recognized at all.
    """
    lines = text.splitlines()
    raw_questions = []
    current = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        opt_match = OPTION_PATTERN.match(stripped)
        q_match = None if opt_match else QUESTION_START_PATTERN.match(stripped)

        if q_match:
            if current:
                raw_questions.append(current)
            current = {
                "question_number": int(q_match.group(1)),
                "question_text": q_match.group(2).strip(),
                "options": {},
            }
        elif opt_match and current is not None:
            letter = opt_match.group(1).upper()
            # Only keep the first occurrence of a given letter per
            # question, in case of accidental duplicate lines.
            if letter not in current["options"]:
                current["options"][letter] = opt_match.group(2).strip()
        elif current is not None:
            # A wrapped continuation of the current question's text.
            current["question_text"] += " " + stripped

    if current:
        raw_questions.append(current)

    if not raw_questions:
        raise RuntimeError(
            "Could not detect any numbered questions in this document "
            "(expected a format like '1. Question text' followed by 'A) Option'). "
            "Please check the file's formatting, or use Manual Question Entry instead."
        )

    questions = []
    for q in raw_questions:
        options = q["options"]
        questions.append({
            "question_number": q["question_number"],
            "question_text": q["question_text"].strip(),
            "option_a": options.get("A"),
            "option_b": options.get("B"),
            "option_c": options.get("C"),
            "option_d": options.get("D"),
            "option_e": options.get("E"),
        })

    return questions
