"""
question.py
-------------
ORM model for the "questions" table. Stores individual MCQ
questions for an exam -- either extracted from an uploaded question
paper, or entered manually by the teacher (AI-Based Evaluation
flow). The correct option itself is NOT stored here; that lives in
"verified_answer_keys" once Gemini has generated it and the teacher
has verified it, keeping a single source of truth for scoring.
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, Enum, ForeignKey, func
from sqlalchemy.orm import relationship

from app.database import Base
import enum


class QuestionSource(str, enum.Enum):
    MANUAL = "MANUAL"
    EXTRACTED = "EXTRACTED"


class Question(Base):
    __tablename__ = "questions"

    question_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    exam_id = Column(Integer, ForeignKey("exams.exam_id", ondelete="CASCADE"), nullable=False)
    paper_id = Column(Integer, ForeignKey("question_papers.paper_id", ondelete="SET NULL"), nullable=True)
    question_number = Column(Integer, nullable=False)
    question_text = Column(Text, nullable=False)
    option_a = Column(String(500), nullable=True)
    option_b = Column(String(500), nullable=True)
    option_c = Column(String(500), nullable=True)
    option_d = Column(String(500), nullable=True)
    option_e = Column(String(500), nullable=True)
    source = Column(Enum(QuestionSource), nullable=False, default=QuestionSource.MANUAL)
    created_at = Column(DateTime, server_default=func.now())

    exam = relationship("Exam", back_populates="questions")
    paper = relationship("QuestionPaper", back_populates="questions")
