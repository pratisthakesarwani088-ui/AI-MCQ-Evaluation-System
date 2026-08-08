"""
question_schema.py
--------------------
Pydantic models for manual question entry (add/edit/list) in the
AI-Based Evaluation module.
"""

from typing import Optional
from pydantic import BaseModel, Field, field_validator


class QuestionCreate(BaseModel):
    """Data submitted when the teacher manually adds a question."""

    question_number: Optional[int] = Field(None, gt=0, le=500)
    question_text: str = Field(..., min_length=1)
    option_a: str = Field(..., min_length=1, max_length=500)
    option_b: str = Field(..., min_length=1, max_length=500)
    option_c: str = Field(..., min_length=1, max_length=500)
    option_d: str = Field(..., min_length=1, max_length=500)
    option_e: Optional[str] = Field(None, max_length=500)

    @field_validator("question_text")
    @classmethod
    def question_text_not_blank(cls, value: str):
        value = value.strip()
        if not value:
            raise ValueError("Question text cannot be empty.")
        return value

    @field_validator("option_a", "option_b", "option_c", "option_d")
    @classmethod
    def required_option_not_blank(cls, value: str):
        value = value.strip()
        if not value:
            raise ValueError("Options A-D cannot be empty.")
        return value

    @field_validator("option_e")
    @classmethod
    def optional_option_strip(cls, value: Optional[str]):
        if value is None:
            return value
        value = value.strip()
        return value or None


class QuestionUpdate(BaseModel):
    """Data submitted when the teacher edits an existing question."""

    question_text: str = Field(..., min_length=1)
    option_a: str = Field(..., min_length=1, max_length=500)
    option_b: str = Field(..., min_length=1, max_length=500)
    option_c: str = Field(..., min_length=1, max_length=500)
    option_d: str = Field(..., min_length=1, max_length=500)
    option_e: Optional[str] = Field(None, max_length=500)

    @field_validator("question_text")
    @classmethod
    def question_text_not_blank(cls, value: str):
        value = value.strip()
        if not value:
            raise ValueError("Question text cannot be empty.")
        return value

    @field_validator("option_a", "option_b", "option_c", "option_d")
    @classmethod
    def required_option_not_blank(cls, value: str):
        value = value.strip()
        if not value:
            raise ValueError("Options A-D cannot be empty.")
        return value

    @field_validator("option_e")
    @classmethod
    def optional_option_strip(cls, value: Optional[str]):
        if value is None:
            return value
        value = value.strip()
        return value or None


class QuestionOut(BaseModel):
    question_id: int
    exam_id: int
    question_number: int
    question_text: str
    option_a: Optional[str] = None
    option_b: Optional[str] = None
    option_c: Optional[str] = None
    option_d: Optional[str] = None
    option_e: Optional[str] = None
    source: str

    class Config:
        from_attributes = True


class GenerateAnswerKeyRequest(BaseModel):
    """Body for triggering Gemini answer-key generation."""

    include_explanations: bool = False
