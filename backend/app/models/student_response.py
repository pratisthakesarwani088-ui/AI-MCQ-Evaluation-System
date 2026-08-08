"""
student_response.py
---------------------
ORM model for the "student_responses" table. Stores the detected
answer (before scoring) for every question of a student's sheet.
"""

from sqlalchemy import (
    Column, Integer, String, Float, Enum, ForeignKey,
    UniqueConstraint
)
from sqlalchemy.orm import relationship

from app.database import Base
import enum


class DetectionStatus(str, enum.Enum):
    DETECTED = "DETECTED"
    BLANK = "BLANK"
    INVALID = "INVALID"


class StudentResponse(Base):
    __tablename__ = "student_responses"
    __table_args__ = (
        UniqueConstraint("sheet_id", "question_number", name="unique_sheet_question"),
    )

    response_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    sheet_id = Column(Integer, ForeignKey("student_answer_sheets.sheet_id", ondelete="CASCADE"), nullable=False)
    question_number = Column(Integer, nullable=False)
    # Holds "B" normally, or "B,C" when multiple options were marked (=> INVALID)
    selected_option = Column(String(20), nullable=True)
    detection_status = Column(Enum(DetectionStatus), nullable=False, default=DetectionStatus.BLANK)
    confidence = Column(Float, nullable=True)

    sheet = relationship("StudentAnswerSheet", back_populates="responses")
