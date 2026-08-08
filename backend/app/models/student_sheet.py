"""
student_sheet.py
------------------
ORM model for the "student_answer_sheets" table. Stores metadata
about a single uploaded student answer sheet image.
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum, func
from sqlalchemy.orm import relationship

from app.database import Base
import enum


class SheetType(str, enum.Enum):
    OMR = "OMR"
    NORMAL = "NORMAL"
    UNKNOWN = "UNKNOWN"


class StudentAnswerSheet(Base):
    __tablename__ = "student_answer_sheets"

    sheet_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    exam_id = Column(Integer, ForeignKey("exams.exam_id", ondelete="CASCADE"), nullable=False)
    student_name = Column(String(255), nullable=True)
    roll_number = Column(String(100), nullable=True)
    image_path = Column(String(500), nullable=False)
    sheet_type = Column(Enum(SheetType), default=SheetType.UNKNOWN)
    uploaded_at = Column(DateTime, server_default=func.now())

    exam = relationship("Exam", back_populates="student_sheets")
    responses = relationship(
        "StudentResponse", back_populates="sheet", cascade="all, delete-orphan"
    )
    result = relationship(
        "EvaluationResult", back_populates="sheet", uselist=False,
        cascade="all, delete-orphan"
    )
    reports = relationship(
        "Report", back_populates="sheet", cascade="all, delete-orphan"
    )
