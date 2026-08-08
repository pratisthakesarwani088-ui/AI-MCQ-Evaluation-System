"""
activity_log.py
------------------
ORM model for the "activity_logs" table. A simple, general-purpose
audit trail recording notable actions across the system (exam
created, answer key verified, sheet evaluated, report generated,
AI assistant used, etc.) so a teacher can see a history of what
happened and when.
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, func

from app.database import Base


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    log_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    action = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
