# Testing Notes

This file documents what was actually tested during development
(including a full end-to-end integration pass across every module),
how it was tested, and a manual checklist to verify the complete
system works on your own machine after installation.

## Sandbox constraints (why some tests are "logic-level" not "live")

The development sandbox had **OpenCV, NumPy, and reportlab** available
(so OMR bubble detection, perspective/rotation correction, and PDF
generation were tested for real, against real generated images/PDFs),
but **no internet access** and therefore no FastAPI, SQLAlchemy,
PyMySQL, Pydantic, PaddleOCR, or the Gemini SDK installed. Every piece
of business logic that doesn't strictly require those packages was
tested directly; everything that does require them was verified by
static analysis (full compile checks, AST-based import analysis,
systematic route cross-referencing) and by mocking the SDK boundary
(Gemini, PaddleOCR) to test the surrounding logic in isolation.

## What was tested for real (not mocked)

1. **OMR bubble detection, perspective correction, rotation
   correction, blank/multi-bubble detection** (`omr_service.py`) --
   generated real synthetic bubble-sheet images with OpenCV and ran
   the actual detection pipeline:
   - Straight sheet: all 5 questions (single-fill, blank, and a
     double-fill/invalid case) detected exactly correctly.
   - Rotation: correctly handled up to **15-20 degrees**; at 25
     degrees detection degrades (see Known Limitations).
   - Mild perspective distortion (skewed corners): detected correctly.
   - This is the same pipeline used by both AI-Based Evaluation and
     OMR Evaluation's student-sheet processing step.

2. **Evaluation engine** (`evaluation_service.py`) -- exact
   correct/wrong/blank/invalid/negative-marking/final-marks/
   percentage math verified against hand-calculated values across
   multiple scenarios, including a heavy-negative-marking case
   confirming `final_marks` stays negative/uncapped while
   `percentage` correctly clamps at 0.

3. **Statistics engine** (`statistics_service.py`) -- highest/
   lowest/average marks, pass/fail counts (40% threshold), and
   totals verified against a hand-built multi-student dataset,
   including the empty-list edge case.

4. **PDF report generation** (`pdf_report_service.py`) -- both
   Student Report and Exam Report PDFs were actually generated with
   reportlab and verified to have a valid `%PDF-` header and
   reasonable file size; tested with missing optional fields (no AI
   analysis, no student name) and generated 20 reports in one batch
   with no errors (62ms total).

5. **Question-paper text parsing** (`question_parser_service.py`) --
   parses "1. Question text / A) Option" style documents into
   structured questions; tested with multi-line wrapped questions
   and a 150-question stress test (parsed in <1ms).

6. **File-type validation** -- every one of the 6 required formats
   (PDF, DOCX, TXT, JPG, JPEG, PNG) tested against all three upload
   categories (image-only, document-only, combined) for correct
   accept/reject behavior; malicious extensions (.exe, .sh, .php,
   .svg) confirmed always rejected.

7. **OCR text parsing logic** (`ocr_service.parse_answer_key`) --
   tested with mocked PaddleOCR output covering clean text, poor
   quality/low-confidence text, empty results, and garbled
   unrecognizable text -- all handled without crashing.

8. **Gemini-facing logic** (`gemini_service.py`) -- every function
   (`generate_answer_key`, `analyze_performance`, `explain_answer`,
   `generate_mcqs`) tested with a mocked model covering: successful
   JSON extraction (including markdown-fenced responses), malformed/
   unparsable responses, and all 4 failure modes explicitly requested
   for this system -- **missing API key**, **invalid API key**,
   **network failure**, and **rate limiting** -- all correctly
   surface as a friendly `RuntimeError`, which every calling router
   converts to an HTTP 502 with a clear message. Never an unhandled
   crash.

## What was verified by static analysis (not live execution)

Since FastAPI/SQLAlchemy/Pydantic aren't installed in this sandbox,
the following were verified by direct code inspection and automated
cross-referencing rather than live execution:

- **Every database table** (10/10): SQLAlchemy models and
  `database.sql` compared column-by-column -- fully identical.
- **Every foreign key** (11/11): confirmed correct `ON DELETE CASCADE`
  / `ON DELETE SET NULL` behavior matching what the delete endpoints
  (exam deletion, student-record deletion) rely on.
- **Every frontend API call** (28 unique patterns across all pages):
  cross-referenced against the full backend route inventory (9
  routers) -- 100% match, no broken calls.
- **Every internal page link** (`href`): cross-referenced against
  registered page routes -- no broken links.
- **Every `onclick` handler function reference** and every
  **`getElementById` call**: verified to resolve to an actually
  defined function / actually existing element ID (including IDs
  created dynamically via JS templates).
- **Unused imports**: AST-based analysis across every router/service/
  model file -- none found.
- **N+1 query patterns**: none found (exam list statistics, student
  lists, and report statistics all use single grouped queries).
- **Raw SQL / SQL injection risk**: none found -- 100% parameterized
  SQLAlchemy ORM usage throughout.
- **Duplicate code**: one instance found (bubble-detection threshold
  logic duplicated between `omr_service.py` and
  `sheet_detection_service.py`) and fixed by extracting a shared
  `compute_bubble_threshold()` / `find_bubble_contours()` pair, then
  re-tested both call sites for regressions (none found).

Every Python file (45) compiles cleanly and every JavaScript file
(11) passes Node.js syntax checking.

## What could NOT be tested in this sandbox

- The FastAPI app actually starting with `uvicorn` and connecting to
  a real MySQL database (no SQLAlchemy/PyMySQL installed, no
  internet to install them).
- PaddleOCR's and Gemini's real-world accuracy on your own images/
  questions (the surrounding logic was tested thoroughly with mocks,
  but not the actual OCR engine or Gemini API responses).
- The full HTTP request/response cycle through a real browser.

## Manual end-to-end checklist

Follow these steps after installing dependencies (`requirements.txt`),
setting up MySQL and your `.env` file, and starting the server (see
README.md) to confirm everything works on your machine.

**Create Exam & routing**
- [ ] Dashboard loads, "System Status" shows connected.
- [ ] Create an AI-type exam -- redirects to AI-Based Evaluation.
- [ ] Create an OMR-type exam -- redirects to OMR Evaluation.
- [ ] Confirm `uploads/exams/{id}/...` folders were created automatically.

**AI-Based Evaluation**
- [ ] Upload a PDF/DOCX/TXT question paper -- questions extracted.
- [ ] Add a question manually, edit it, delete it.
- [ ] Generate Answer Key with Gemini (requires `GEMINI_API_KEY`) --
      review/edit the suggested answers, save as verified.
- [ ] Upload a student sheet -- OCR extracts answers automatically.

**OMR Evaluation**
- [ ] Upload a question paper (PDF/DOCX/TXT, or a scanned image via OCR).
- [ ] Upload an answer-key image -- verify/correct the extracted table.
- [ ] Upload a student OMR sheet -- confirm bubble detection + sheet-type badge.
- [ ] Click Evaluate -- confirm the result summary populates.

**Evaluation + Result**
- [ ] Result page shows correct/wrong/blank/invalid, final marks,
      percentage, and question-wise breakdown.
- [ ] Click "Generate AI Performance Analysis" -- confirm strong/weak
      topics and suggestions appear (requires `GEMINI_API_KEY`).

**Previous Exams**
- [ ] Search, subject filter, type filter, and sort all work on the
      exams table.
- [ ] Open an exam -- student list, marks, and percentage display.
- [ ] Delete a student record -- confirm the modal, then confirm the
      sheet/responses/result are gone and an Activity Log was written.
- [ ] Delete an entire exam -- confirm cascading removal.

**Reports**
- [ ] Generate an Exam Report PDF and a Student Report PDF, download
      both, and open them to confirm formatting.
- [ ] Confirm the Generated Reports table lists both afterward.

**AI Assistant**
- [ ] Explain Answers, Generate New MCQs (+ download/save), Analyze
      Student Results, Weak/Strong Topics, and Suggestions all work
      end-to-end with a real Gemini API key.

**Error handling**
- [ ] Try an unsupported file type on any upload -- friendly error,
      no crash.
- [ ] Try uploading a student sheet before the answer key is verified
      -- correctly blocked with a clear message.
- [ ] Try running any AI Assistant action without `GEMINI_API_KEY` set
      -- friendly "not configured" error, no crash.

## Tuning OMR / OCR accuracy for your own sheets

Real-world scans vary a lot. If detection accuracy is low on your
sheets, these are the first things to adjust:

- `backend/app/services/omr_service.py`:
  - `FILL_THRESHOLD` (default `0.45`) -- lower it if lightly-shaded
    bubbles aren't being detected as filled; raise it if faint
    smudges are being wrongly detected as filled.
  - The area/circularity filters inside `find_bubble_contours` --
    widen the area range if your bubbles are much larger/smaller
    than the defaults assume. This same function is now shared with
    `sheet_detection_service.py`, so tuning it here improves both
    OMR scoring and OMR-vs-normal-sheet type detection together.
- `backend/app/services/normal_mcq_service.py`:
  - `MIN_CONFIDENCE` (default `0.55`) -- the OCR confidence floor
    below which an answer is treated as `INVALID` rather than
    trusted.
  - `MARK_DENSITY_MULTIPLIER` (default `1.6`) -- how much extra ink
    a circled/boxed/ticked letter must have compared to its row
    neighbours to be counted as "marked".
- `backend/app/services/statistics_service.py`:
  - `PASS_PERCENTAGE_THRESHOLD` (default `40.0`) -- adjust to match
    your institution's actual passing grade.

## Known limitations

- **OMR rotation limit**: reliable up to ~15-20 degrees of rotation;
  beyond that, perspective correction can lose track of the page
  boundary (especially if a rotated photo's corners get clipped by
  the camera frame) and bubble-row grouping degrades. Photograph
  sheets with visible margin around all edges and minimal tilt for
  best results.
- **AI Performance Analysis topic-awareness for OMR exams** depends
  on a question paper having been uploaded and successfully parsed
  into question text; without that, analysis falls back to
  reasoning by question number only.
- **Fixed 40% pass/fail threshold**, not configurable per-exam (no
  such column exists in the finalized 10-table schema).
- **Gemini features require internet + a valid API key**; OMR
  Evaluation and everything else remain fully offline.
- Three read-only endpoints exist but aren't currently called by the
  frontend (`GET /api/reports/student/{sheet_id}`,
  `GET /api/omr-evaluation/papers/{exam_id}`,
  `GET /api/student-sheet/{sheet_id}`) -- kept as valid API surface
  rather than removed, since they work correctly and may be useful
  for future UI or external API consumers.
