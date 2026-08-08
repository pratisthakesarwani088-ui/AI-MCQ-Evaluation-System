"""
database.py
-----------
Sets up the SQLAlchemy engine, session factory, and declarative base.

Every router uses `get_db()` (a FastAPI dependency) to obtain a
database session for a single request, and the session is always
closed afterwards -- even if an error occurs.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import DATABASE_URL

# The "engine" manages the actual connection pool to MySQL.
# pool_pre_ping=True automatically checks that a connection is still
# alive before using it (helpful for long-running local servers).
engine = create_engine(DATABASE_URL, pool_pre_ping=True, echo=False)

# SessionLocal is a factory that creates new Session objects.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class that all ORM models inherit from.
Base = declarative_base()


def get_db():
    """
    FastAPI dependency that yields a database session and guarantees
    it is closed after the request finishes, whether it succeeded or
    raised an exception.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
