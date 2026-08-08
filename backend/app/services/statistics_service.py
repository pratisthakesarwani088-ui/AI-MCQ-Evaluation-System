"""
statistics_service.py
------------------------
Computes exam-wide aggregate statistics (highest/lowest/average
marks, pass/fail counts, totals of correct/wrong/blank/invalid
answers) from a list of EvaluationResult rows. Used by the Reports
module's Exam Report and statistics cards.

Pass/fail threshold: since the Exams table has no dedicated
"passing marks" column, a fixed passing threshold of 40% is used
(a common academic default). This is a deliberate, documented
assumption -- see PASS_PERCENTAGE_THRESHOLD below.
"""

# A student is considered to have passed if their percentage is at
# or above this value. Adjust here if your institution uses a
# different passing threshold.
PASS_PERCENTAGE_THRESHOLD = 40.0


def compute_exam_statistics(evaluation_results: list) -> dict:
    """
    Args:
        evaluation_results: a list of objects with attributes
            final_marks, max_marks, percentage, correct_count,
            wrong_count, blank_count, invalid_count (this matches
            the EvaluationResult ORM model's fields exactly, so ORM
            rows can be passed directly).

    Returns:
        dict with total_students, highest_marks, lowest_marks,
        average_marks, average_percentage, pass_count, fail_count,
        pass_percentage, total_correct, total_wrong, total_blank,
        total_invalid, max_marks (the exam's maximum possible marks,
        taken from any result row since it's the same for every
        student in one exam).
    """
    total_students = len(evaluation_results)

    if total_students == 0:
        return {
            "total_students": 0,
            "highest_marks": 0,
            "lowest_marks": 0,
            "average_marks": 0,
            "average_percentage": 0,
            "max_marks": 0,
            "pass_count": 0,
            "fail_count": 0,
            "pass_percentage": 0,
            "total_correct": 0,
            "total_wrong": 0,
            "total_blank": 0,
            "total_invalid": 0,
        }

    marks_list = [r.final_marks for r in evaluation_results]
    percentages = [r.percentage for r in evaluation_results]

    pass_count = sum(1 for p in percentages if p >= PASS_PERCENTAGE_THRESHOLD)
    fail_count = total_students - pass_count

    return {
        "total_students": total_students,
        "highest_marks": round(max(marks_list), 2),
        "lowest_marks": round(min(marks_list), 2),
        "average_marks": round(sum(marks_list) / total_students, 2),
        "average_percentage": round(sum(percentages) / total_students, 2),
        "max_marks": evaluation_results[0].max_marks,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "pass_percentage": round((pass_count / total_students) * 100, 2),
        "total_correct": sum(r.correct_count for r in evaluation_results),
        "total_wrong": sum(r.wrong_count for r in evaluation_results),
        "total_blank": sum(r.blank_count for r in evaluation_results),
        "total_invalid": sum(r.invalid_count for r in evaluation_results),
    }
