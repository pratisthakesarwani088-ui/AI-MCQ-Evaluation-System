# AI Assistant for MCQ Evaluation System

**Evaluate Smarter with AI**

A locally-run web application that helps teachers create exams, generate or scan answer keys, evaluate student MCQ answer sheets (via OCR/OpenCV or Google Gemini AI), and produce detailed reports — all from one dashboard.

---


## 🚀 Project Demo
🎥 Demo Video: https://www.linkedin.com/posts/pratisthaa-kesharwaniii-87260430a_python-fastapi-ai-activity-7491559299308011520-c6-3?utm_source=social_share_send&utm_medium=android_app&rcm=ACoAAE7Bh9YBKu90-pWQC9YXaTczbFda4_Imiw8&utm_campaign=copy_link
💻 GitHub: https://github.com/pratisthakesarwani088-ui/AI-MCQ-Evaluation-System  


____
## Table of Contents

- [Project Description](#project-description)
- [Features](#features)
- [Technology Stack](#technology-stack)
- [Folder Structure](#folder-structure)
- [Installation Guide](#installation-guide)
- [MySQL Setup](#mysql-setup)
- [Gemini API Setup](#gemini-api-setup)
- [Running the Project](#running-the-project)
- [Screenshots](#screenshots)
- [API Overview](#api-overview)
- [Database Tables](#database-tables)
- [Project Workflow](#project-workflow)
- [Future Scope](#future-scope)
- [License](#license)

---

## Project Description

Teachers can create an exam, choose between two evaluation pipelines, and get from a stack of scanned papers to a graded, analyzed, downloadable report in a few steps:

- **AI-Based Evaluation** — upload a question paper (PDF/DOCX/TXT) or enter questions manually, let **Gemini AI** generate and explain the answer key, then verify it before scoring student sheets.
- **OMR Evaluation** — upload a printed answer key image and student OMR (bubble) sheets; **OpenCV** handles perspective/rotation correction and bubble detection fully offline, with no internet required.

Both pipelines converge on the same evaluation engine, the same Result page, the same Reports module, and the same AI Assistant — so once a sheet is scored, everything downstream (statistics, PDF reports, AI performance analysis) works identically regardless of which pipeline produced it.

## Features

- **Dashboard** with quick access to every module
- **Create Exam**: name, subject, exam type (AI/OMR), question count, marks per question, negative marking — with automatic upload-folder creation
- **AI-Based Evaluation**: question paper upload (PDF/DOCX/TXT) with automatic question extraction, manual question entry (add/edit/delete), Gemini-generated answer keys with optional explanations, an editable verify-and-save table, and student sheet upload with automatic OCR answer extraction
- **OMR Evaluation**: question paper upload (with OCR for scanned images), answer-key image upload with OCR extraction, student OMR sheet upload, and fully offline OpenCV bubble detection (perspective correction, rotation correction, blank-bubble and multiple-bubble detection)
- **Evaluation Engine**: exact correct/wrong/blank/invalid scoring with configurable negative marking, final marks, and percentage (never negative, even if marks go negative) — shared identically by both pipelines
- **Result Page**: student details, question-wise breakdown, and on-demand AI Performance Analysis (strong topics, weak topics, suggestions) via Gemini
- **Previous Exams & Student Records**: search/filter/sort exams, view full exam details and evaluated student lists, view any student's result, permanently delete a student record (with confirmation and activity logging) or an entire exam
- **Reports**: Student Report and Exam Report PDFs (project-branded, including AI analysis when available), auto-computed statistics (highest/lowest/average marks, pass/fail counts and percentages), and a history of previously generated reports
- **AI Assistant panel**: generate an answer key, explain any answer (why it's right and others are wrong), generate brand-new MCQs on any topic/difficulty (with save-to-exam or text-file download), and analyze a student's results for strengths, weaknesses, and study suggestions
- Friendly error handling throughout: invalid files, empty/unreadable documents, missing or invalid Gemini API keys, network failures, and OCR/bubble-detection failures all surface as clear messages, never a crash

## Technology Stack

| Layer | Technology |
|---|---|
| Frontend | HTML5, CSS3, vanilla JavaScript (no framework) |
| Backend | Python 3, FastAPI, Uvicorn |
| Database | MySQL, SQLAlchemy ORM |
| Image processing | OpenCV, NumPy |
| OCR | PaddleOCR |
| Document parsing | pypdf, python-docx |
| AI | Google Gemini API (`google-generativeai`) |
| PDF generation | ReportLab |
| Validation | Pydantic |

## Folder Structure

```
MCQ-Evaluation-System/
├── backend/
│   └── app/
│       ├── main.py              # FastAPI app, page routes, router registration
│       ├── config.py            # Settings (DB, Gemini, uploads) — reads .env
│       ├── database.py          # SQLAlchemy engine/session setup
│       ├── models/              # SQLAlchemy ORM models (one file per table)
│       ├── schemas/             # Pydantic request/response validation models
│       ├── routers/             # FastAPI routers (one file per feature area)
│       ├── services/            # Business logic (OCR, OMR, Gemini, PDF, stats...)
│       └── utils/               # Shared helpers (file upload/validation)
├── frontend/
│   ├── *.html                   # One page per feature area
│   ├── css/style.css            # Shared stylesheet
│   └── js/*.js                  # One script per page, plus common.js
├── uploads/                      # Local file storage (created automatically per exam)
│   └── exams/{exam_id}/{question_papers,answer_key,student_sheets}/
├── reports/                      # Generated PDF reports (created automatically per exam)
├── database.sql                  # Full MySQL schema (10 tables)
├── requirements.txt               # Python dependencies
├── .env.example                   # Configuration template
├── TESTING.md                     # What was tested, how, and a manual checklist
├── LICENSE                         # MIT
└── README.md
```

> **Note on this structure vs. a generic Flask/Django-style layout:** this project doesn't use separate top-level `config/`, `models/`, `routers/`, `services/`, `static/`, or `templates/` folders. Those concepts all exist, organized under `backend/app/` (`config.py`, `models/`, `routers/`, `services/`) for a cohesive FastAPI package. There's no separate `static/` folder either — `frontend/` itself is mounted at `/static` by `main.py`. There's no `templates/` folder because the frontend is static HTML served directly (via `FileResponse`), not server-rendered Jinja2 templates.

## Installation Guide

**Prerequisites:** Python 3.9–3.12, MySQL 8.0+, pip.

1. Clone or extract the project, then move into it:
   ```bash
   cd MCQ-Evaluation-System
   ```
2. (Recommended) create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate        # Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
   > PaddleOCR/PaddlePaddle downloads its OCR model files on first use — this requires internet access the first time you run an OCR-dependent feature (answer key upload, student sheet upload), even though the app runs fully offline afterward.

## MySQL Setup

1. Make sure MySQL is installed and running.
2. Create the database and all tables by running the provided schema:
   ```bash
   mysql -u root -p < database.sql
   ```
   This creates the `mcq_evaluation_system` database and all 10 tables (with indexes and foreign keys) in one step. It's safe to re-run — every statement uses `CREATE TABLE IF NOT EXISTS`.
3. Copy the environment template and fill in your MySQL credentials:
   ```bash
   cp .env.example .env
   ```
   Edit `.env`:
   ```
   DB_HOST=localhost
   DB_PORT=3306
   DB_USER=root
   DB_PASSWORD=your_mysql_password
   DB_NAME=mcq_evaluation_system
   ```

## Gemini API Setup

Gemini powers **AI-Based Evaluation** and the **AI Assistant** panel. **OMR Evaluation and everything else work fully offline without it.**

1. Get a free API key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey).
2. Add it to your `.env` file:
   ```
   GEMINI_API_KEY=your_gemini_api_key
   GEMINI_MODEL=gemini-3.6-flash
   ```
3. If this key is missing, AI-dependent features return a clear "AI Assistant is not configured" message instead of failing silently — the rest of the app is unaffected.

## Running the Project

From the `backend` folder:

```bash
cd backend
uvicorn app.main:app --reload
```

Then open **http://localhost:8000** in your browser. The dashboard, all pages, and the API are all served from this single address (the API lives under `/api/...`).

To confirm everything is connected, check the "System Status" card on the dashboard, or visit `http://localhost:8000/api/ping`.

## Screenshots

> Screenshots are not included in this package. Once you have the app running, capture and add your own here:

| Page | Screenshot |
|---|---|
| Dashboard | _add screenshot_ |
| Create Exam | _add screenshot_ |
| AI-Based Evaluation | _add screenshot_ |
| OMR Evaluation | _add screenshot_ |
| Result Page | _add screenshot_ |
| Reports | _add screenshot_ |
| AI Assistant | _add screenshot_ |

## API Overview

All endpoints are prefixed with `/api`. Full interactive docs are available at `http://localhost:8000/docs` (FastAPI's auto-generated Swagger UI) once the server is running.

| Router | Prefix | Purpose |
|---|---|---|
| `exam_router` | `/api/exams` | Create/list (search, filter, sort)/get/delete exams |
| `answer_key_router` | `/api/answer-key` | OMR answer-key image upload (OCR), verify, save |
| `student_sheet_router` | `/api/student-sheet` | Student sheet upload, sheet-type detection + OCR/OMR processing |
| `ai_evaluation_router` | `/api/ai-evaluation` | Question paper upload/extraction, manual questions (CRUD), Gemini answer-key generation, verify |
| `omr_router` | `/api/omr-evaluation` | OMR question paper upload (OCR-capable) |
| `evaluation_router` | `/api/evaluation` | Run/fetch evaluation, generate AI Performance Analysis |
| `previous_exams_router` | `/api/previous-exams` | Evaluated student list per exam, delete a student record |
| `reports_router` | `/api/reports` | Student/Exam Report data + PDF generation/download |
| `ai_assistant_router` | `/api/ai-assistant` | Explain Answers, Generate MCQs, Save Generated MCQs |

## Database Tables

| Table | Purpose |
|---|---|
| `exams` | Exam name, subject, type (AI/OMR), question count, marking scheme |
| `question_papers` | Uploaded question paper / answer-key documents and their extracted text |
| `questions` | Individual MCQ questions (manual or extracted), with options |
| `ai_responses` | Log of every Gemini call (prompt + response) by request type |
| `verified_answer_keys` | The single source of truth for correct answers, per question |
| `student_answer_sheets` | Uploaded student sheet metadata (name, roll number, detected sheet type) |
| `student_responses` | Detected answer per question per sheet, before scoring |
| `evaluation_results` | Final computed score, percentage, and AI analysis per sheet |
| `reports` | Metadata for every generated PDF report |
| `activity_logs` | Audit trail of notable actions (e.g. student record deletions) |

See `database.sql` for full column definitions, indexes, and foreign keys (all cascading deletes are handled at the database level).

## Project Workflow

```
Create Exam ──┬── AI-Based Evaluation ──┐
              │   (question paper/manual  │
              │    entry → Gemini answer   ├──► Student Sheet Upload
              │    key → verify)           │    (OCR / OpenCV)
              └── OMR Evaluation ─────────┘              │
                  (question paper →                       ▼
                   answer key image/OCR →          Evaluation Engine
                   verify)                       (correct/wrong/blank/
                                                   invalid, marks, %)
                                                          │
                                                          ▼
                                                    Result Page
                                              (+ AI Performance Analysis)
                                                          │
                              ┌───────────────────────────┼───────────────────┐
                              ▼                           ▼                   ▼
                      Previous Exams              Reports (PDF)         AI Assistant
                   (search/filter/sort,        (Student/Exam report,   (explain answers,
                    view/delete students)        statistics)            generate MCQs, etc.)
```

## Future Scope

- Configurable per-exam passing marks (currently a fixed 40% threshold)
- Bulk student sheet upload (batch processing multiple sheets at once)
- Support for additional AI providers alongside Gemini
- Exporting Previous Exams / Reports data to CSV/Excel
- Role-based accounts (currently a single-teacher, no-login local tool by design)
- OCR support for scanned/image-only PDFs without a separate image upload step

## License

MIT — see [LICENSE](LICENSE).
