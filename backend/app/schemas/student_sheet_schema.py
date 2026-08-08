"""
student_sheet_schema.py
-------------------------
Pydantic models for the student answer sheet upload endpoints.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class StudentSheetOut(BaseModel):
    sheet_id: int
    exam_id: int
    student_name: Optional[str] = None
    roll_number: Optional[str] = None
    image_path: str
    sheet_type: str
    uploaded_at: datetime

    class Config:
        from_attributes = True
