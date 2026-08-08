"""
evaluation_result.py
----------------------
ORM model for the "evaluation_results" table. Stores the final
computed summary (marks, correct/wrong/blank/invalid counts) for
one student answer sheet.
"""

from sqlalchemy import Column, Integer, Float, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship

from app.database import Base


class EvaluationResult(Base):
    __tablename__ = "evaluation_results"

    result_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    sheet_id = Column(Integer, ForeignKey("student_answer_sheets.sheet_id", ondelete="CASCADE"), nullable=False)
    exam_id = Column(Integer, ForeignKey("exams.exam_id", ondelete="CASCADE"), nullable=False)
    correct_count = Column(Integer, default=0)
    wrong_count = Column(Integer, default=0)
    blank_count = Column(Integer, default=0)
    invalid_count = Column(Integer, default=0)
    final_marks = Column(Float, default=0)
    max_marks = Column(Float, default=0)
    percentage = Column(Float, default=0)
    # Optional AI-generated performance analysis (weak topics, tips,
    # etc.) from the AI Assistant's "Analyze Results" feature.
    ai_analysis = Column(Text, nullable=True)
    evaluated_at = Column(DateTime, server_default=func.now())

    sheet = relationship("StudentAnswerSheet", back_populates="result")
    exam = relationship("Exam", back_populates="evaluation_results")
