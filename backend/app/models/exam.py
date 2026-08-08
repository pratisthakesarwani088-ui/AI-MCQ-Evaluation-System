"""
exam.py
-------
ORM model for the "exams" table. Each row represents one exam that
the teacher has created (e.g. "Unit Test 1 - Physics").
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Enum, func
from sqlalchemy.orm import relationship

from app.database import Base
import enum


class ExamType(str, enum.Enum):
    """
    Which evaluation pipeline this exam uses:
      AI  -> AI-Based Evaluation (Gemini generates/assists the answer key)
      OMR -> OMR Evaluation (OpenCV bubble-sheet detection)
    """
    AI = "AI"
    OMR = "OMR"


class Exam(Base):
    __tablename__ = "exams"

    exam_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    exam_name = Column(String(255), nullable=False)
    subject = Column(String(255), nullable=True)
    exam_type = Column(Enum(ExamType), nullable=False, default=ExamType.OMR)
    total_questions = Column(Integer, nullable=False)
    # NOTE: kept as "marks_per_correct" internally (the value awarded
    # per correct answer) even though the UI now labels this field
    # "Marks per Question", to stay compatible with the existing
    # evaluation engine and API contract.
    marks_per_correct = Column(Float, nullable=False)
    negative_marks = Column(Float, nullable=False, default=0)
    created_at = Column(DateTime, server_default=func.now())

    # Relationships let us easily access related rows in Python,
    # e.g. exam.question_papers, exam.student_sheets
    question_papers = relationship(
        "QuestionPaper", back_populates="exam", cascade="all, delete-orphan"
    )
    questions = relationship(
        "Question", back_populates="exam", cascade="all, delete-orphan"
    )
    ai_responses = relationship(
        "AIResponse", back_populates="exam", cascade="all, delete-orphan"
    )
    verified_answer_keys = relationship(
        "VerifiedAnswerKey", back_populates="exam", cascade="all, delete-orphan"
    )
    student_sheets = relationship(
        "StudentAnswerSheet", back_populates="exam", cascade="all, delete-orphan"
    )
    evaluation_results = relationship(
        "EvaluationResult", back_populates="exam", cascade="all, delete-orphan"
    )
    reports = relationship(
        "Report", back_populates="exam", cascade="all, delete-orphan"
    )
