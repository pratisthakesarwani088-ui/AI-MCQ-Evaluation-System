"""
report.py
-----------
ORM model for the "reports" table. Stores metadata about generated
PDF reports (student report, exam report, highest/lowest/average
marks summary) so previously generated reports can be listed and
re-downloaded without regenerating them.
"""

from sqlalchemy import Column, Integer, String, DateTime, Enum, ForeignKey, func
from sqlalchemy.orm import relationship

from app.database import Base
import enum


class ReportType(str, enum.Enum):
    STUDENT = "STUDENT"
    EXAM = "EXAM"
    HIGHEST = "HIGHEST"
    LOWEST = "LOWEST"
    AVERAGE = "AVERAGE"


class Report(Base):
    __tablename__ = "reports"

    report_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    exam_id = Column(Integer, ForeignKey("exams.exam_id", ondelete="CASCADE"), nullable=True)
    sheet_id = Column(Integer, ForeignKey("student_answer_sheets.sheet_id", ondelete="CASCADE"), nullable=True)
    report_type = Column(Enum(ReportType), nullable=False)
    file_path = Column(String(500), nullable=False)
    generated_at = Column(DateTime, server_default=func.now())

    exam = relationship("Exam", back_populates="reports")
    sheet = relationship("StudentAnswerSheet", back_populates="reports")
