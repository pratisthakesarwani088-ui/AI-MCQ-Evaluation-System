/* ============================================================
   omr_evaluation.js
   ----------------------------------------------------------
   Full OMR Evaluation workflow, wired to the backend. This reuses
   already-built, already-tested endpoints wherever possible:
     - /api/omr-evaluation/upload-paper  (new: reference question paper)
     - /api/answer-key/...               (existing: OCR + verify)
     - /api/student-sheet/...            (existing: upload + OpenCV
                                           bubble detection with
                                           perspective/rotation
                                           correction, blank/multi
                                           bubble handling)
     - /api/evaluation/...               (existing: automatic scoring)
============================================================ */

document.addEventListener("DOMContentLoaded", () => {
  const examId = getCurrentExamId();
  const examType = getCurrentExamType();

  if (!examId || examType !== "OMR") {
    document.querySelectorAll(".container > .card").forEach((el) => (el.style.display = "none"));
    document.getElementById("no-exam-warning").style.display = "block";
    return;
  }

  setupPreview("omr_answer_key_file", "omr-key-preview");
  setupPreview("omr_student_sheet_file", "omr-sheet-preview");

  document.getElementById("omr-upload-paper-btn").addEventListener("click", () => uploadQuestionPaper(examId));
  document.getElementById("omr-upload-key-btn").addEventListener("click", () => uploadAnswerKey(examId));
  document.getElementById("omr-save-key-btn").addEventListener("click", () => saveAnswerKey(examId));
  document.getElementById("omr-upload-sheet-btn").addEventListener("click", () => uploadStudentSheet(examId));
  document.getElementById("omr-run-evaluation-btn").addEventListener("click", () => evaluateSelectedSheet(examId));

  loadAnswerKey(examId);
  loadStudentSheets(examId);
});

function setupPreview(inputId, previewId) {
  const input = document.getElementById(inputId);
  const preview = document.getElementById(previewId);
  input.addEventListener("change", () => {
    const file = input.files[0];
    if (!file) {
      preview.style.display = "none";
      return;
    }
    const reader = new FileReader();
    reader.onload = (e) => {
      preview.src = e.target.result;
      preview.style.display = "block";
    };
    reader.readAsDataURL(file);
  });
}

/* ---------------------- Step 1: Upload Question Paper ---------------------- */

async function uploadQuestionPaper(examId) {
  hideAlert("omr-paper-alert");
  const fileInput = document.getElementById("omr_question_paper_file");
  const btn = document.getElementById("omr-upload-paper-btn");

  const file = fileInput.files[0];
  if (!file) {
    showAlert("omr-paper-alert", "Please choose a file first.");
    return;
  }
  const validExtensions = [".pdf", ".docx", ".txt", ".jpg", ".jpeg", ".png"];
  if (!validExtensions.some((ext) => file.name.toLowerCase().endsWith(ext))) {
    showAlert("omr-paper-alert", "Unsupported file type. Only PDF, DOCX, TXT, JPG, JPEG, and PNG files are allowed.");
    return;
  }

  const formData = new FormData();
  formData.append("file", file);

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Uploading...';

  try {
    const data = await apiRequest(`/omr-evaluation/upload-paper/${examId}`, {
      method: "POST",
      body: formData,
    });
    showAlert("omr-paper-alert", data.message, "success");
    fileInput.value = "";
  } catch (err) {
    showAlert("omr-paper-alert", err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Upload Question Paper";
  }
}

/* ---------------------- Step 2: Upload Answer Key (OCR) ---------------------- */

async function uploadAnswerKey(examId) {
  hideAlert("omr-key-alert");
  const fileInput = document.getElementById("omr_answer_key_file");
  const btn = document.getElementById("omr-upload-key-btn");

  const file = fileInput.files[0];
  if (!file) {
    showAlert("omr-key-alert", "Please choose an answer-key image first.");
    return;
  }
  const validExtensions = [".jpg", ".jpeg", ".png"];
  if (!validExtensions.some((ext) => file.name.toLowerCase().endsWith(ext))) {
    showAlert("omr-key-alert", "Unsupported file type. Only JPG, JPEG, and PNG images are allowed.");
    return;
  }

  const formData = new FormData();
  formData.append("file", file);

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Extracting text from image...';

  try {
    const data = await apiRequest(`/answer-key/upload/${examId}`, {
      method: "POST",
      body: formData,
    });
    showAlert("omr-key-alert", data.message, "success");
    fileInput.value = "";
    await loadAnswerKey(examId);
  } catch (err) {
    showAlert("omr-key-alert", err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Upload & Extract Answer Key";
  }
}

/* ---------------------- Step 3: Verify Answer Key ---------------------- */

const VALID_OPTIONS = ["A", "B", "C", "D", "E"];

async function loadAnswerKey(examId) {
  const tbody = document.getElementById("omr-answer-key-tbody");
  try {
    const data = await apiRequest(`/answer-key/${examId}`);

    if (!data.answers.length) {
      tbody.innerHTML = '<tr><td colspan="2" class="empty-state">Upload an answer key above to review it here.</td></tr>';
      return;
    }

    let html = "";
    data.answers.forEach((row) => {
      html += `
        <tr>
          <td>Question ${row.question_number}</td>
          <td>
            <input type="text" maxlength="1" class="omr-answer-input" data-qnum="${row.question_number}" value="${row.correct_option || ""}" placeholder="A-E" style="width:70px;text-transform:uppercase;">
          </td>
        </tr>
      `;
    });
    tbody.innerHTML = html;

    document.querySelectorAll(".omr-answer-input").forEach((input) => {
      input.addEventListener("input", () => {
        input.value = input.value.toUpperCase();
      });
    });
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="2" class="empty-state">Could not load the answer key: ${escapeHtml(err.message)}</td></tr>`;
  }
}

async function saveAnswerKey(examId) {
  hideAlert("omr-verify-alert");
  const btn = document.getElementById("omr-save-key-btn");
  const inputs = document.querySelectorAll(".omr-answer-input");

  if (!inputs.length) {
    showAlert("omr-verify-alert", "Upload an answer key above to build the table first.");
    return;
  }

  const answers = [];
  const emptyQuestions = [];
  const invalidQuestions = [];

  inputs.forEach((input) => {
    const questionNumber = parseInt(input.dataset.qnum, 10);
    const value = input.value.trim().toUpperCase();
    if (!value) {
      emptyQuestions.push(questionNumber);
    } else if (!VALID_OPTIONS.includes(value)) {
      invalidQuestions.push(questionNumber);
    } else {
      answers.push({ question_number: questionNumber, correct_option: value });
    }
  });

  if (emptyQuestions.length) {
    showAlert("omr-verify-alert", `Please fill in an answer for question(s): ${emptyQuestions.join(", ")}.`);
    return;
  }
  if (invalidQuestions.length) {
    showAlert("omr-verify-alert", `Question(s) ${invalidQuestions.join(", ")} must have a valid option (A-E).`);
    return;
  }

  btn.disabled = true;
  btn.textContent = "Saving...";

  try {
    const data = await apiRequest(`/answer-key/verify/${examId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answers }),
    });
    showAlert("omr-verify-alert", data.message, "success");
  } catch (err) {
    showAlert("omr-verify-alert", err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Save Verified Answer Key";
  }
}

/* ---------------------- Step 4: Upload Student OMR Sheet ---------------------- */

async function uploadStudentSheet(examId) {
  hideAlert("omr-sheet-alert");
  const fileInput = document.getElementById("omr_student_sheet_file");
  const btn = document.getElementById("omr-upload-sheet-btn");

  const file = fileInput.files[0];
  if (!file) {
    showAlert("omr-sheet-alert", "Please choose a student sheet image first.");
    return;
  }
  const validExtensions = [".jpg", ".jpeg", ".png"];
  if (!validExtensions.some((ext) => file.name.toLowerCase().endsWith(ext))) {
    showAlert("omr-sheet-alert", "Unsupported file type. Only JPG, JPEG, and PNG images are allowed.");
    return;
  }

  const formData = new FormData();
  formData.append("file", file);
  formData.append("student_name", document.getElementById("omr_student_name").value.trim());
  formData.append("roll_number", document.getElementById("omr_roll_number").value.trim());

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Uploading...';

  try {
    const uploadData = await apiRequest(`/student-sheet/upload/${examId}`, {
      method: "POST",
      body: formData,
    });

    const sheetId = uploadData.sheet.sheet_id;
    setCurrentSheetId(sheetId);

    btn.innerHTML = '<span class="spinner"></span> Running bubble detection...';
    const processData = await apiRequest(`/student-sheet/process/${sheetId}`, { method: "POST" });

    updateDetectionBadges(processData.sheet_type, true);

    showAlert("omr-sheet-alert", `${uploadData.message} ${processData.message}`, "success");
    fileInput.value = "";
    document.getElementById("omr-sheet-preview").style.display = "none";
    await loadStudentSheets(examId);
  } catch (err) {
    showAlert("omr-sheet-alert", err.message);
    updateDetectionBadges(null, false);
  } finally {
    btn.disabled = false;
    btn.textContent = "Upload Student Sheet";
  }
}

async function loadStudentSheets(examId) {
  const tbody = document.getElementById("omr-sheets-tbody");
  try {
    const data = await apiRequest(`/student-sheet/exam/${examId}`);

    if (!data.sheets.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No student sheets uploaded yet for this exam.</td></tr>';
      return;
    }

    let html = "";
    data.sheets.forEach((sheet) => {
      const uploadedDate = new Date(sheet.uploaded_at).toLocaleString();
      html += `
        <tr>
          <td>${escapeHtml(sheet.student_name || "—")}</td>
          <td>${escapeHtml(sheet.roll_number || "—")}</td>
          <td><span class="badge badge-blank">${sheet.sheet_type}</span></td>
          <td>${uploadedDate}</td>
          <td><button class="btn btn-secondary" style="margin-top:0;" onclick="selectSheetForEvaluation(${sheet.sheet_id}, '${sheet.sheet_type}')">Select</button></td>
        </tr>
      `;
    });
    tbody.innerHTML = html;
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty-state">Could not load student sheets: ${escapeHtml(err.message)}</td></tr>`;
  }
}

function selectSheetForEvaluation(sheetId, sheetType) {
  setCurrentSheetId(sheetId);
  updateDetectionBadges(sheetType, true);
  document.getElementById("omr-run-evaluation-btn").scrollIntoView({ behavior: "smooth", block: "center" });
}

function updateDetectionBadges(sheetType, success) {
  const typeBadge = document.getElementById("omr-sheet-type-badge");
  const bubbleBadge = document.getElementById("omr-bubble-status-badge");

  if (success) {
    typeBadge.textContent = sheetType || "Unknown";
    typeBadge.className = "badge badge-correct";
    bubbleBadge.textContent = "Complete";
    bubbleBadge.className = "badge badge-correct";
  } else {
    typeBadge.textContent = "Detection failed";
    typeBadge.className = "badge badge-invalid";
    bubbleBadge.textContent = "Failed";
    bubbleBadge.className = "badge badge-invalid";
  }
}

/* ---------------------- Step 5: Evaluate Selected Sheet ---------------------- */

async function evaluateSelectedSheet(examId) {
  hideAlert("omr-evaluate-alert");
  const sheetId = getCurrentSheetId();

  if (!sheetId) {
    showAlert("omr-evaluate-alert", "Please upload or select a student sheet in Step 4 first.");
    return;
  }

  const btn = document.getElementById("omr-run-evaluation-btn");
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Evaluating...';

  try {
    const data = await apiRequest(`/evaluation/evaluate/${sheetId}`, { method: "POST" });
    renderResultSummary(data.summary);
    showAlert("omr-evaluate-alert", data.message, "success");
    document.getElementById("omr-view-result-btn").style.display = "inline-block";
  } catch (err) {
    showAlert("omr-evaluate-alert", err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Evaluate Selected Sheet";
  }
}

function renderResultSummary(summary) {
  document.getElementById("omr-correct-count").textContent = summary.correct_count;
  document.getElementById("omr-wrong-count").textContent = summary.wrong_count;
  document.getElementById("omr-blank-count").textContent = summary.blank_count;
  document.getElementById("omr-invalid-count").textContent = summary.invalid_count;
  document.getElementById("omr-final-marks").textContent = summary.final_marks;
  document.getElementById("omr-max-marks").textContent = summary.max_marks;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}
