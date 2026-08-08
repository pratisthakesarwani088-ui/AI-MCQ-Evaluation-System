"""
config.py
---------
Central place for all application settings.

Reads database credentials from a ".env" file (see .env.example in the
project root). This keeps secrets out of the source code.
"""

import os
from dotenv import load_dotenv

# Load variables from the ".env" file into the environment.
# If ".env" is missing, sensible defaults are used instead.
load_dotenv()

# ---------------------------------------------------------------
# Database settings
# ---------------------------------------------------------------
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "mcq_evaluation_system")

# ---------------------------------------------------------------
# AI Assistant (Gemini) settings
# ---------------------------------------------------------------
# NOTE: this is the one part of the system that requires internet
# access -- AI-Based Evaluation and the AI Assistant panel call the
# Gemini API. OMR Evaluation and everything else remain fully local.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
GEMINI_ENABLED = bool(GEMINI_API_KEY)

# SQLAlchemy connection URL for MySQL using the PyMySQL driver.
DATABASE_URL = (
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

# ---------------------------------------------------------------
# Folder paths (all local, no cloud storage)
# ---------------------------------------------------------------
# BASE_DIR = .../MCQ-Evaluation-System/backend/app
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# PROJECT_ROOT = .../MCQ-Evaluation-System
PROJECT_ROOT = os.path.dirname(os.path.dirname(BASE_DIR))

UPLOADS_DIR = os.path.join(PROJECT_ROOT, "uploads")
EXAMS_DIR = os.path.join(UPLOADS_DIR, "exams")
REPORTS_DIR = os.path.join(PROJECT_ROOT, "reports")
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")

# Make sure the core folders exist at startup.
os.makedirs(EXAMS_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)

# ---------------------------------------------------------------
# Upload restrictions
# ---------------------------------------------------------------
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
ALLOWED_DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".txt"}
MAX_UPLOAD_SIZE_MB = 15
