"""
main.py
-------
Entry point of the FastAPI backend.

Responsibilities:
1. Create all MySQL tables (if they don't already exist) on startup.
2. Serve the frontend (HTML/CSS/JS) as static files.
3. Serve uploaded images so the browser can display them (e.g. on
   the "Verify Answer Key" page).
4. Register all API routers.

Run with (from the "backend" folder):
    uvicorn app.main:app --reload
"""

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine, Base
from app.config import FRONTEND_DIR, UPLOADS_DIR
import app.models  # noqa: F401  (import registers all models with Base)

# ---------------------------------------------------------------
# Create the FastAPI application
# ---------------------------------------------------------------
app = FastAPI(
    title="AI Assistant for MCQ Evaluation System",
    description="Evaluate Smarter with AI",
    version="2.0.0",
)

# Allow the frontend (served from the same app, but just in case it
# is opened from a different port/file during development) to call
# the API without CORS errors.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------
# Create database tables on startup
# ---------------------------------------------------------------
@app.on_event("startup")
def on_startup():
    """
    Creates every table defined by our SQLAlchemy models if it does
    not already exist. This means a fresh MySQL database (created
    via database.sql) is automatically populated with the correct
    schema the first time the server runs.
    """
    Base.metadata.create_all(bind=engine)


# ---------------------------------------------------------------
# Global error handler so the app NEVER crashes with a raw 500 page
# ---------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": f"An unexpected server error occurred: {str(exc)}",
        },
    )


# ---------------------------------------------------------------
# Serve uploaded images (answer keys & student sheets) so the
# frontend <img> tags can display them directly.
# ---------------------------------------------------------------
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")


# ---------------------------------------------------------------
# API routers (added module by module)
# ---------------------------------------------------------------
from app.routers import exam_router  # noqa: E402
app.include_router(exam_router.router)

from app.routers import answer_key_router  # noqa: E402
app.include_router(answer_key_router.router)

from app.routers import student_sheet_router  # noqa: E402
app.include_router(student_sheet_router.router)

from app.routers import evaluation_router  # noqa: E402
app.include_router(evaluation_router.router)

from app.routers import ai_evaluation_router  # noqa: E402
app.include_router(ai_evaluation_router.router)

from app.routers import omr_router  # noqa: E402
app.include_router(omr_router.router)

from app.routers import previous_exams_router  # noqa: E402
app.include_router(previous_exams_router.router)

from app.routers import reports_router  # noqa: E402
app.include_router(reports_router.router)

from app.routers import ai_assistant_router  # noqa: E402
app.include_router(ai_assistant_router.router)


# ---------------------------------------------------------------
# Simple health check endpoint
# ---------------------------------------------------------------
@app.get("/api/ping")
def ping():
    return {"success": True, "message": "Server is running."}


# ---------------------------------------------------------------
# Serve the frontend HTML pages
# ---------------------------------------------------------------
@app.get("/")
def serve_dashboard():
    return FileResponse(f"{FRONTEND_DIR}/index.html")


@app.get("/create-exam")
def serve_create_exam():
    return FileResponse(f"{FRONTEND_DIR}/create_exam.html")


@app.get("/upload-answer-key")
def serve_upload_answer_key():
    return FileResponse(f"{FRONTEND_DIR}/upload_answer_key.html")


@app.get("/verify-answer-key")
def serve_verify_answer_key():
    return FileResponse(f"{FRONTEND_DIR}/verify_answer_key.html")


@app.get("/upload-student-sheet")
def serve_upload_student_sheet():
    return FileResponse(f"{FRONTEND_DIR}/upload_student_sheet.html")


@app.get("/result")
def serve_result():
    return FileResponse(f"{FRONTEND_DIR}/result.html")


@app.get("/ai-evaluation")
def serve_ai_evaluation():
    return FileResponse(f"{FRONTEND_DIR}/ai_evaluation.html")


@app.get("/omr-evaluation")
def serve_omr_evaluation():
    return FileResponse(f"{FRONTEND_DIR}/omr_evaluation.html")


@app.get("/previous-exams")
def serve_previous_exams():
    return FileResponse(f"{FRONTEND_DIR}/previous_exams.html")


@app.get("/reports")
def serve_reports():
    return FileResponse(f"{FRONTEND_DIR}/reports.html")


@app.get("/ai-assistant")
def serve_ai_assistant():
    return FileResponse(f"{FRONTEND_DIR}/ai_assistant.html")


# Mount CSS/JS as static assets under /static
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
