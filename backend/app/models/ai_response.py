"""
ai_response.py
----------------
ORM model for the "ai_responses" table. Every call made to the
Gemini AI Assistant (generate answer key, explain an answer,
generate MCQs, analyze results, find weak topics, suggestions) is
logged here -- both the prompt sent and the response received. This
gives the teacher a history/audit trail of what the AI produced and
lets "AI explanation" text be re-displayed without calling Gemini
again.
"""

from sqlalchemy import Column, Integer, Text, DateTime, Enum, ForeignKey, func
from sqlalchemy.orm import relationship

from app.database import Base
import enum


class AIRequestType(str, enum.Enum):
    GENERATE_ANSWER_KEY = "GENERATE_ANSWER_KEY"
    EXPLAIN_ANSWER = "EXPLAIN_ANSWER"
    GENERATE_MCQS = "GENERATE_MCQS"
    ANALYZE_RESULTS = "ANALYZE_RESULTS"
    FIND_WEAK_TOPICS = "FIND_WEAK_TOPICS"
    SUGGESTIONS = "SUGGESTIONS"


class AIResponse(Base):
    __tablename__ = "ai_responses"

    response_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    exam_id = Column(Integer, ForeignKey("exams.exam_id", ondelete="CASCADE"), nullable=True)
    request_type = Column(Enum(AIRequestType), nullable=False)
    prompt_text = Column(Text, nullable=True)
    response_text = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    exam = relationship("Exam", back_populates="ai_responses")
