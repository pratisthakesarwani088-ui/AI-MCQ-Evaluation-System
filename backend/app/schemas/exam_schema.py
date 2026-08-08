"""
exam_schema.py
--------------
Pydantic models used for validating "Create Exam" requests and for
shaping the JSON returned to the frontend.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator

VALID_EXAM_TYPES = {"AI", "OMR"}


class ExamCreate(BaseModel):
    """Data the teacher submits when creating a new exam."""

    exam_name: str = Field(..., min_length=1, max_length=255)
    subject: Optional[str] = Field(None, max_length=255)
    exam_type: str = Field(..., description="Either 'AI' or 'OMR'")
    total_questions: int = Field(..., gt=0, le=500)
    # NOTE: field name kept as "marks_per_correct" for API/backend
    # compatibility, even though the Create Exam form now labels
    # this "Marks per Question".
    marks_per_correct: float = Field(..., gt=0)
    negative_marks: float = Field(0, ge=0)

    @field_validator("exam_type")
    @classmethod
    def exam_type_must_be_valid(cls, value: str):
        value = value.strip().upper()
        if value not in VALID_EXAM_TYPES:
            raise ValueError("exam_type must be either 'AI' or 'OMR'.")
        return value

    @field_validator("exam_name")
    @classmethod
    def exam_name_must_not_be_blank(cls, value: str):
        value = value.strip()
        if not value:
            raise ValueError("Exam name cannot be empty or just whitespace.")
        return value

    @field_validator("subject")
    @classmethod
    def subject_strip(cls, value: Optional[str]):
        if value is None:
            return value
        value = value.strip()
        return value or None


class ExamOut(BaseModel):
    """Shape of an exam as returned by the API."""

    exam_id: int
    exam_name: str
    subject: Optional[str] = None
    exam_type: str
    total_questions: int
    marks_per_correct: float
    negative_marks: float
    created_at: datetime

    class Config:
        from_attributes = True  # allows creating this from an ORM object directly
