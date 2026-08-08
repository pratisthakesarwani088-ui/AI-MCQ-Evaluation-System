"""
verified_answer_key.py
-----------------------
ORM model for the "verified_answer_keys" table. This holds the
FINAL correct answer for each question, after the teacher has
reviewed and (if needed) corrected the OCR output. Only rows with
is_verified=True are used during evaluation.
"""

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey,
    UniqueConstraint, func
)
from sqlalchemy.orm import relationship

from app.database import Base


class VerifiedAnswerKey(Base):
    __tablename__ = "verified_answer_keys"
    __table_args__ = (
        UniqueConstraint("exam_id", "question_number", name="unique_exam_question"),
    )

    key_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    exam_id = Column(Integer, ForeignKey("exams.exam_id", ondelete="CASCADE"), nullable=False)
    question_number = Column(Integer, nullable=False)
    correct_option = Column(String(5), nullable=False)  # e.g. "A", "B", "C", "D", "E"
    is_verified = Column(Boolean, default=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    exam = relationship("Exam", back_populates="verified_answer_keys")
