"""
gemini_service.py
--------------------
Wraps Google's Gemini API to generate an answer key (and, optionally,
short explanations) for a list of MCQ questions.

This is the only file that talks to the Gemini SDK directly -- every
other part of the AI-Based Evaluation module works with plain
Python dicts, so the rest of the app doesn't need to know anything
about the AI provider.
"""

import json
import re

from app.config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_ENABLED

OPTION_LETTERS = ["A", "B", "C", "D", "E"]


def _get_model():
    """
    Creates a configured Gemini model client. Raises RuntimeError
    with a friendly message if the API key is missing or the SDK
    isn't installed.
    """
    if not GEMINI_ENABLED:
        raise RuntimeError(
            "The AI Assistant is not configured. Please set GEMINI_API_KEY in your .env file "
            "to use AI-Based Evaluation (get a key at https://aistudio.google.com/apikey)."
        )

    try:
        import google.generativeai as genai
    except ImportError as exc:
        raise RuntimeError(
            "The 'google-generativeai' package is not installed. "
            "Please install it (see requirements.txt) to use AI-Based Evaluation."
        ) from exc

    try:
        genai.configure(api_key=GEMINI_API_KEY)
        return genai.GenerativeModel(GEMINI_MODEL)
    except Exception as exc:
        raise RuntimeError(f"Could not initialize the Gemini AI model: {exc}")


def _extract_json_block(raw_text: str) -> str:
    """
    Gemini often wraps JSON responses in markdown code fences
    (```json ... ```). This strips those so the text can be parsed.
    """
    text = raw_text.strip()
    fence_match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()
    return text


def _build_prompt(questions: list, include_explanations: bool) -> str:
    lines = [
        "You are assisting a teacher in creating an answer key for a multiple-choice exam.",
        "For every question below, determine the single best correct option (A, B, C, D, or E, "
        "matching only the options that were actually provided for that question).",
    ]
    if include_explanations:
        lines.append("Also write a short, student-friendly explanation (1-2 sentences) for each answer.")

    lines.append("")
    keys = '"question_number", "correct_option"' + (', "explanation"' if include_explanations else "")
    lines.append(
        f"Respond with ONLY a JSON array (no markdown formatting, no commentary before or after), "
        f"where each item is an object with exactly these keys: {keys}."
    )
    lines.append("")
    lines.append("Questions:")

    for q in questions:
        lines.append(f"\nQuestion {q['question_number']}: {q['question_text']}")
        for letter in OPTION_LETTERS:
            option_text = q.get(f"option_{letter.lower()}")
            if option_text:
                lines.append(f"{letter}) {option_text}")

    return "\n".join(lines)


def generate_answer_key(questions: list, include_explanations: bool = False) -> dict:
    """
    Args:
        questions: list of dicts, each with question_number,
                   question_text, and option_a..option_e (some may
                   be None/empty for questions with fewer options).
        include_explanations: whether to also request a short
                   explanation for each answer.

    Returns:
        {
          "results": [
             {"question_number": 1, "correct_option": "B", "explanation": "..."},
             ...
          ],
          "raw_response": "<the raw text Gemini returned>",
          "prompt": "<the prompt that was sent>",
        }

    Raises RuntimeError with a friendly, specific message on any
    failure: missing API key, network/API error, or a response that
    couldn't be understood.
    """
    if not questions:
        raise RuntimeError("No questions were provided to generate an answer key for.")

    model = _get_model()
    prompt = _build_prompt(questions, include_explanations)

    try:
        response = model.generate_content(prompt)
        raw_text = response.text
    except Exception as exc:
        raise RuntimeError(f"The AI Assistant (Gemini) could not be reached or returned an error: {exc}")

    if not raw_text or not raw_text.strip():
        raise RuntimeError("The AI Assistant returned an empty response. Please try again.")

    json_text = _extract_json_block(raw_text)

    try:
        parsed = json.loads(json_text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise RuntimeError(
            f"The AI Assistant's response could not be understood (not valid JSON). Details: {exc}"
        )

    if not isinstance(parsed, list):
        raise RuntimeError("The AI Assistant's response was not in the expected list format.")

    results = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        try:
            question_number = int(item["question_number"])
            correct_option = str(item["correct_option"]).strip().upper()
        except (KeyError, TypeError, ValueError):
            continue  # Skip a malformed entry rather than failing the whole batch.

        if correct_option not in OPTION_LETTERS:
            continue

        explanation = str(item.get("explanation", "")).strip() if include_explanations else ""
        results.append({
            "question_number": question_number,
            "correct_option": correct_option,
            "explanation": explanation,
        })

    if not results:
        raise RuntimeError(
            "The AI Assistant's response did not contain any usable answers. Please try again."
        )

    return {
        "results": results,
        "raw_response": raw_text,
        "prompt": prompt,
    }


def _build_analysis_prompt(exam_name: str, question_results: list, summary: dict, question_texts: dict) -> str:
    lines = [
        f"You are an AI teaching assistant reviewing one student's performance on the exam \"{exam_name}\".",
        "Based on the question-by-question results below, identify:",
        "1. Strong topics/areas (questions answered correctly)",
        "2. Weak topics/areas (questions answered wrong, left blank, or invalid)",
        "3. 2-4 short, actionable suggestions for the student to improve",
        "",
        "If question text is not available for a question, refer to it by its question number instead of guessing a topic.",
        "",
        "Respond with ONLY a JSON object (no markdown, no commentary) with exactly these keys: "
        '"strong_topics" (array of short strings), "weak_topics" (array of short strings), '
        '"suggestions" (a single string with 2-4 sentences or short bullet-style tips).',
        "",
        f"Summary: {summary['correct_count']} correct, {summary['wrong_count']} wrong, "
        f"{summary['blank_count']} unanswered, {summary['invalid_count']} invalid, "
        f"out of {summary['correct_count'] + summary['wrong_count'] + summary['blank_count'] + summary['invalid_count']} questions. "
        f"Final marks: {summary['final_marks']}/{summary['max_marks']} ({summary['percentage']}%).",
        "",
        "Question-by-question results:",
    ]

    for q in question_results:
        q_num = q["question_number"]
        text = question_texts.get(q_num)
        label = f"Question {q_num}" + (f" ({text})" if text else "")
        lines.append(f"- {label}: {q['status']} (selected: {q['selected_option'] or 'none'}, correct: {q['correct_option']})")

    return "\n".join(lines)


def analyze_performance(exam_name: str, question_results: list, summary: dict, question_texts: dict = None) -> dict:
    """
    Args:
        exam_name: the exam's display name, for context in the prompt.
        question_results: the per-question list returned by
                   evaluation_service.evaluate_sheet().
        summary: the summary dict returned by the same function
                   (correct/wrong/blank/invalid counts, marks, percentage).
        question_texts: optional {question_number: question_text} --
                   available for AI-Based Evaluation exams (which
                   store question text), empty/absent for OMR exams
                   (which only ever capture marked options, not
                   question content).

    Returns:
        {
          "strong_topics": [...],
          "weak_topics": [...],
          "suggestions": "...",
          "formatted_text": "<human-readable combined summary>",
          "raw_response": "<raw Gemini text>",
          "prompt": "<prompt sent>",
        }

    Raises RuntimeError with a friendly message on any failure.
    """
    if not question_results:
        raise RuntimeError("No question results were provided to analyze.")

    question_texts = question_texts or {}
    model = _get_model()
    prompt = _build_analysis_prompt(exam_name, question_results, summary, question_texts)

    try:
        response = model.generate_content(prompt)
        raw_text = response.text
    except Exception as exc:
        raise RuntimeError(f"The AI Assistant (Gemini) could not be reached or returned an error: {exc}")

    if not raw_text or not raw_text.strip():
        raise RuntimeError("The AI Assistant returned an empty response. Please try again.")

    json_text = _extract_json_block(raw_text)

    try:
        parsed = json.loads(json_text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise RuntimeError(
            f"The AI Assistant's response could not be understood (not valid JSON). Details: {exc}"
        )

    if not isinstance(parsed, dict):
        raise RuntimeError("The AI Assistant's response was not in the expected object format.")

    strong_topics = parsed.get("strong_topics", [])
    weak_topics = parsed.get("weak_topics", [])
    suggestions = str(parsed.get("suggestions", "")).strip()

    if not isinstance(strong_topics, list):
        strong_topics = [str(strong_topics)]
    if not isinstance(weak_topics, list):
        weak_topics = [str(weak_topics)]

    if not strong_topics and not weak_topics and not suggestions:
        raise RuntimeError("The AI Assistant's response did not contain any usable analysis.")

    formatted_lines = []
    if strong_topics:
        formatted_lines.append("Strong Topics:\n" + "\n".join(f"- {t}" for t in strong_topics))
    if weak_topics:
        formatted_lines.append("Weak Topics:\n" + "\n".join(f"- {t}" for t in weak_topics))
    if suggestions:
        formatted_lines.append("Suggestions:\n" + suggestions)
    formatted_text = "\n\n".join(formatted_lines)

    return {
        "strong_topics": strong_topics,
        "weak_topics": weak_topics,
        "suggestions": suggestions,
        "formatted_text": formatted_text,
        "raw_response": raw_text,
        "prompt": prompt,
    }


def explain_answer(question_text: str, options: dict, correct_option: str) -> dict:
    """
    Explains why the correct option is right and (where applicable)
    why the other provided options are wrong, for one question.

    Args:
        question_text: the question's text.
        options: {"A": "...", "B": "...", ...} -- only options that
                 actually exist for this question should be included.
        correct_option: the single correct option letter, e.g. "B".

    Returns:
        {"explanation": "...", "raw_response": "...", "prompt": "..."}

    Raises RuntimeError with a friendly message on any failure.
    """
    if not question_text or not question_text.strip():
        raise RuntimeError("No question text was provided to explain.")
    if correct_option not in OPTION_LETTERS:
        raise RuntimeError(f"'{correct_option}' is not a valid option letter.")

    model = _get_model()

    option_lines = "\n".join(f"{letter}) {text}" for letter, text in options.items() if text)
    prompt = (
        "You are a teaching assistant explaining an MCQ answer to a student.\n\n"
        f"Question: {question_text}\n"
        f"{option_lines}\n\n"
        f"The correct answer is option {correct_option}.\n\n"
        "Explain, in 3-5 short sentences: (1) why option "
        f"{correct_option} is correct, and (2) briefly why each of the "
        "other listed options is incorrect. Write in plain, student-friendly "
        "language. Respond with ONLY the explanation text -- no markdown, no JSON, no preamble."
    )

    try:
        response = model.generate_content(prompt)
        raw_text = response.text
    except Exception as exc:
        raise RuntimeError(f"The AI Assistant (Gemini) could not be reached or returned an error: {exc}")

    if not raw_text or not raw_text.strip():
        raise RuntimeError("The AI Assistant returned an empty response. Please try again.")

    return {
        "explanation": raw_text.strip(),
        "raw_response": raw_text,
        "prompt": prompt,
    }


def generate_mcqs(subject: str, topic: str, difficulty: str, count: int) -> dict:
    """
    Generates brand-new MCQs on a given subject/topic/difficulty.

    Args:
        subject: e.g. "Computer Science"
        topic: e.g. "Binary Search Trees"
        difficulty: "Easy" | "Medium" | "Hard"
        count: how many questions to generate (kept to a sane range
               by the caller/router; this function doesn't cap it).

    Returns:
        {
          "mcqs": [
             {"question_text": "...", "option_a": "...", "option_b": "...",
              "option_c": "...", "option_d": "...", "correct_option": "B",
              "explanation": "..."},
             ...
          ],
          "raw_response": "...",
          "prompt": "...",
        }

    Raises RuntimeError with a friendly message on any failure.
    """
    if not topic or not topic.strip():
        raise RuntimeError("Please provide a topic to generate questions about.")
    if count < 1:
        raise RuntimeError("Number of questions must be at least 1.")

    model = _get_model()

    prompt = (
        f"Generate {count} multiple-choice question(s) for a {difficulty}-difficulty exam"
        f"{f' on the subject {subject}' if subject else ''}, specifically about the topic: {topic}.\n\n"
        "Each question must have exactly 4 options (A-D), exactly one correct option, "
        "and a short (1-2 sentence) explanation of the correct answer.\n\n"
        'Respond with ONLY a JSON array (no markdown, no commentary), where each item has '
        'exactly these keys: "question_text", "option_a", "option_b", "option_c", "option_d", '
        '"correct_option" (a single letter A-D), "explanation".'
    )

    try:
        response = model.generate_content(prompt)
        raw_text = response.text
    except Exception as exc:
        raise RuntimeError(f"The AI Assistant (Gemini) could not be reached or returned an error: {exc}")

    if not raw_text or not raw_text.strip():
        raise RuntimeError("The AI Assistant returned an empty response. Please try again.")

    json_text = _extract_json_block(raw_text)

    try:
        parsed = json.loads(json_text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise RuntimeError(f"The AI Assistant's response could not be understood (not valid JSON). Details: {exc}")

    if not isinstance(parsed, list):
        raise RuntimeError("The AI Assistant's response was not in the expected list format.")

    mcqs = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        try:
            question_text = str(item["question_text"]).strip()
            option_a = str(item["option_a"]).strip()
            option_b = str(item["option_b"]).strip()
            option_c = str(item["option_c"]).strip()
            option_d = str(item["option_d"]).strip()
            correct_option = str(item["correct_option"]).strip().upper()
        except (KeyError, TypeError):
            continue

        if correct_option not in ("A", "B", "C", "D") or not question_text:
            continue

        mcqs.append({
            "question_text": question_text,
            "option_a": option_a,
            "option_b": option_b,
            "option_c": option_c,
            "option_d": option_d,
            "correct_option": correct_option,
            "explanation": str(item.get("explanation", "")).strip(),
        })

    if not mcqs:
        raise RuntimeError("The AI Assistant's response did not contain any usable questions. Please try again.")

    return {
        "mcqs": mcqs,
        "raw_response": raw_text,
        "prompt": prompt,
    }
