"""
question_paper.py
-------------------
ORM model for the "question_papers" table.

This table stores every document a teacher uploads for an exam --
both the question paper itself (PDF/DOCX/TXT/image) and, for the
OMR pipeline, the separate answer-key image. `paper_type`
distinguishes the two. `extracted_text` holds whatever text was
pulled out of the file (via PDF/DOCX text extraction or OCR), which
is what the AI-Based Evaluation flow feeds to Gemini.
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, Enum, ForeignKey, func
from sqlalchemy.orm import relationship

from app.database import Base
import enum


class PaperType(str, enum.Enum):
    QUESTION_PAPER = "QUESTION_PAPER"
    ANSWER_KEY = "ANSWER_KEY"


class FileType(str, enum.Enum):
    PDF = "PDF"
    DOCX = "DOCX"
    TXT = "TXT"
    IMAGE = "IMAGE"


class QuestionPaper(Base):
    __tablename__ = "question_papers"

    paper_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    exam_id = Column(Integer, ForeignKey("exams.exam_id", ondelete="CASCADE"), nullable=False)
    paper_type = Column(Enum(PaperType), nullable=False)
    file_path = Column(String(500), nullable=True)  # nullable: manual question entry has no file
    file_type = Column(Enum(FileType), nullable=True)
    extracted_text = Column(Text, nullable=True)
    uploaded_at = Column(DateTime, server_default=func.now())

    exam = relationship("Exam", back_populates="question_papers")
    questions = relationship(
        "Question", back_populates="paper", cascade="all, delete-orphan"
    )
