"""
evaluation_service.py
------------------------
Pure scoring logic: compares a student's detected responses against
the teacher's verified answer key and computes the exact marks and
percentage.

Scoring rules (no AI, no partial credit -- exact MCQ matching only):
    Correct   -> + marks_per_correct
    Wrong     -> - negative_marks
    Blank     -> 0
    Invalid   -> 0  (e.g. more than one option was marked)

This is the single shared evaluation engine used by BOTH AI-Based
Evaluation and OMR Evaluation (see evaluation_router.py) -- neither
mode has its own separate scoring logic, so results are computed
identically regardless of which pipeline produced the student's
responses.
"""


def evaluate_sheet(
    total_questions: int,
    marks_per_correct: float,
    negative_marks: float,
    verified_answers: dict,
    student_responses: dict,
):
    """
    Args:
        total_questions: number of questions in the exam.
        marks_per_correct: marks awarded for each correct answer.
        negative_marks: marks deducted for each wrong answer.
        verified_answers: {question_number: correct_option}
        student_responses: {
            question_number: {
                "selected_option": str or None,
                "detection_status": "DETECTED" | "BLANK" | "INVALID",
            }
        }

    Returns:
        (question_results, summary)

        question_results: list of dicts, one per question:
            {
                "question_number": int,
                "selected_option": str or None,
                "correct_option": str,
                "status": "Correct" | "Wrong" | "Unanswered" | "Invalid",
                "marks": float,
            }

        summary: dict with correct_count, wrong_count, blank_count,
                 invalid_count, final_marks, max_marks, percentage.
    """
    question_results = []
    correct_count = 0
    wrong_count = 0
    blank_count = 0
    invalid_count = 0
    final_marks = 0.0

    for question_number in range(1, total_questions + 1):
        correct_option = (verified_answers.get(question_number) or "").upper()
        response = student_responses.get(question_number) or {}
        selected_option = response.get("selected_option")
        detection_status = response.get("detection_status", "BLANK")

        if detection_status == "BLANK" or not selected_option:
            status = "Unanswered"
            marks = 0.0
            blank_count += 1
        elif detection_status == "INVALID":
            status = "Invalid"
            marks = 0.0
            invalid_count += 1
        else:  # DETECTED
            if selected_option.strip().upper() == correct_option:
                status = "Correct"
                marks = marks_per_correct
                correct_count += 1
            else:
                status = "Wrong"
                marks = -negative_marks
                wrong_count += 1

        final_marks += marks

        question_results.append({
            "question_number": question_number,
            "selected_option": selected_option,
            "correct_option": correct_option,
            "status": status,
            "marks": round(marks, 2),
        })

    max_marks = round(total_questions * marks_per_correct, 2)
    final_marks = round(final_marks, 2)
    # Percentage is clamped at 0 even if negative marking drove final
    # marks below zero -- final_marks itself is left uncapped (it's
    # still shown as-is), only the percentage is never negative.
    percentage = round((max(0.0, final_marks) / max_marks) * 100, 2) if max_marks > 0 else 0.0

    summary = {
        "correct_count": correct_count,
        "wrong_count": wrong_count,
        "blank_count": blank_count,
        "invalid_count": invalid_count,
        "final_marks": final_marks,
        "max_marks": max_marks,
        "percentage": percentage,
    }

    return question_results, summary
