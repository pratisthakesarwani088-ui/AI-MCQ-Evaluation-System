"""
models package
---------------
Importing this package registers all ORM models with SQLAlchemy's
Base metadata, so that `Base.metadata.create_all(engine)` in main.py
knows about every table.
"""

from app.models.exam import Exam
from app.models.question_paper import QuestionPaper
from app.models.question import Question
from app.models.ai_response import AIResponse
from app.models.verified_answer_key import VerifiedAnswerKey
from app.models.student_sheet import StudentAnswerSheet
from app.models.student_response import StudentResponse
from app.models.evaluation_result import EvaluationResult
from app.models.report import Report
from app.models.activity_log import ActivityLog

__all__ = [
    "Exam",
    "QuestionPaper",
    "Question",
    "AIResponse",
    "VerifiedAnswerKey",
    "StudentAnswerSheet",
    "StudentResponse",
    "EvaluationResult",
    "Report",
    "ActivityLog",
]
