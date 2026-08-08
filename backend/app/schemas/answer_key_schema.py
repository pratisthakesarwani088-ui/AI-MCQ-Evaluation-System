"""
answer_key_schema.py
----------------------
Pydantic models for the answer-key upload / verification endpoints.
"""

import re
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator

VALID_OPTION_PATTERN = re.compile(r"^[A-E]$")


class AnswerKeyRow(BaseModel):
    """One row of the answer key: a question number and its correct option."""

    question_number: int = Field(..., gt=0)
    correct_option: str = Field(..., min_length=1, max_length=5)

    @field_validator("correct_option")
    @classmethod
    def option_must_be_valid(cls, value: str):
        value = value.strip().upper()
        if not VALID_OPTION_PATTERN.match(value):
            raise ValueError(
                f"'{value}' is not a valid option. Only single letters A-E are allowed."
            )
        return value


class VerifyAnswerKeyRequest(BaseModel):
    """Body sent by the frontend when the teacher clicks 'Save Verified Answer Key'."""

    answers: List[AnswerKeyRow]


class AnswerKeyRowOut(BaseModel):
    question_number: int
    correct_option: Optional[str] = None
    is_verified: bool

    class Config:
        from_attributes = True
