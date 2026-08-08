/* ============================================================
   ai_evaluation.js
   ----------------------------------------------------------
   Full AI-Based Evaluation workflow, wired to the backend:
     1. Upload a question paper (PDF/DOCX/TXT) and auto-extract
        questions, OR add/edit/delete questions manually.
     2. Generate an answer key (with optional explanations) using
        Gemini AI.
     3. Review, edit, and save the verified answer key.
============================================================ */

let editingQuestionId = null; // set while editing an existing question

document.addEventListener("DOMContentLoaded", () => {
  const examId = getCurrentExamId();
  const examType = getCurrentExamType();

  if (!examId || examType !== "AI") {
    document.querySelectorAll(".container > .card").forEach((el) => (el.style.display = "none"));
    document.getElementById("no-exam-warning").style.display = "block";
    return;
  }

  const tabUploadBtn = document.getElementById("tab-upload-btn");
  const tabManualBtn = document.getElementById("tab-manual-btn");
  const uploadPanel = document.getElementById("upload-paper-panel");
  const manualPanel = document.getElementById("manual-entry-panel");

  tabUploadBtn.addEventListener("click", () => {
    tabUploadBtn.classList.replace("btn-secondary", "btn-primary");
    tabManualBtn.classList.replace("btn-primary", "btn-secondary");
    uploadPanel.style.display = "block";
    manualPanel.style.display = "none";
  });

  tabManualBtn.addEventListener("click", () => {
    tabManualBtn.classList.replace("btn-secondary", "btn-primary");
    tabUploadBtn.classList.replace("btn-primary", "btn-secondary");
    manualPanel.style.display = "block";
    uploadPanel.style.display = "none";
  });

  document.getElementById("extract-questions-btn").addEventListener("click", () => uploadQuestionPaper(examId));
  document.getElementById("add-question-btn").addEventListener("click", () => submitManualQuestion(examId));
  document.getElementById("cancel-edit-btn").addEventListener("click", cancelEdit);
  document.getElementById("generate-answer-key-btn").addEventListener("click", () => generateAnswerKey(examId));
  document.getElementById("save-verified-key-btn").addEventListener("click", () => saveVerifiedKey(examId));

  setupSheetPreview();
  document.getElementById("ai-upload-sheet-btn").addEventListener("click", () => uploadStudentSheet(examId));

  loadQuestions(examId);
  loadAnswerKey(examId);
  loadStudentSheets(examId);
});

/* ---------------------- Step 1: Question Paper Upload ---------------------- */

async function uploadQuestionPaper(examId) {
  const fileInput = document.getElementById("question_paper_file");
  const btn = document.getElementById("extract-questions-btn");
  hideAlert("questions-alert");

  const file = fileInput.files[0];
  if (!file) {
    showAlert("questions-alert", "Please choose a PDF, DOCX, or TXT file first.");
    return;
  }

  const validExtensions = [".pdf", ".docx", ".txt"];
  const lowerName = file.name.toLowerCase();
  if (!validExtensions.some((ext) => lowerName.endsWith(ext))) {
    showAlert("questions-alert", "Unsupported file type. Only PDF, DOCX, and TXT files are allowed.");
    return;
  }

  const formData = new FormData();
  formData.append("file", file);

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Extracting text...';

  try {
    const uploadData = await apiRequest(`/ai-evaluation/upload-paper/${examId}`, {
      method: "POST",
      body: formData,
    });

    btn.innerHTML = '<span class="spinner"></span> Parsing questions...';
    const extractData = await apiRequest(`/ai-evaluation/extract-questions/${uploadData.paper_id}`, {
      method: "POST",
    });

    showAlert("questions-alert", extractData.message, "success");
    fileInput.value = "";
    await loadQuestions(examId);
  } catch (err) {
    showAlert("questions-alert", err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Upload & Extract Questions";
  }
}

/* ---------------------- Manual Question Entry (Add/Edit) ---------------------- */

function readManualForm() {
  return {
    question_text: document.getElementById("manual_question_text").value.trim(),
    option_a: document.getElementById("manual_option_a").value.trim(),
    option_b: document.getElementById("manual_option_b").value.trim(),
    option_c: document.getElementById("manual_option_c").value.trim(),
    option_d: document.getElementById("manual_option_d").value.trim(),
    option_e: document.getElementById("manual_option_e").value.trim() || null,
  };
}

function clearManualForm() {
  document.getElementById("manual_question_text").value = "";
  document.getElementById("manual_option_a").value = "";
  document.getElementById("manual_option_b").value = "";
  document.getElementById("manual_option_c").value = "";
  document.getElementById("manual_option_d").value = "";
  document.getElementById("manual_option_e").value = "";
}

async function submitManualQuestion(examId) {
  hideAlert("questions-alert");
  const data = readManualForm();

  if (!data.question_text) {
    showAlert("questions-alert", "Please enter the question text.");
    return;
  }
  if (!data.option_a || !data.option_b || !data.option_c || !data.option_d) {
    showAlert("questions-alert", "Please fill in at least Options A, B, C, and D.");
    return;
  }

  const addBtn = document.getElementById("add-question-btn");
  addBtn.disabled = true;

  try {
    if (editingQuestionId) {
      await apiRequest(`/ai-evaluation/questions/${editingQuestionId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      showAlert("questions-alert", "Question updated.", "success");
      cancelEdit();
    } else {
      await apiRequest(`/ai-evaluation/questions/${examId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      showAlert("questions-alert", "Question added.", "success");
      clearManualForm();
    }
    await loadQuestions(examId);
  } catch (err) {
    showAlert("questions-alert", err.message);
  } finally {
    addBtn.disabled = false;
  }
}

function startEditQuestion(question) {
  editingQuestionId = question.question_id;
  document.getElementById("manual_question_text").value = question.question_text;
  document.getElementById("manual_option_a").value = question.option_a || "";
  document.getElementById("manual_option_b").value = question.option_b || "";
  document.getElementById("manual_option_c").value = question.option_c || "";
  document.getElementById("manual_option_d").value = question.option_d || "";
  document.getElementById("manual_option_e").value = question.option_e || "";

  document.getElementById("add-question-btn").textContent = "Update Question";
  document.getElementById("cancel-edit-btn").style.display = "inline-block";

  document.getElementById("tab-manual-btn").click();
  document.getElementById("manual_question_text").scrollIntoView({ behavior: "smooth", block: "center" });
}

function cancelEdit() {
  editingQuestionId = null;
  clearManualForm();
  document.getElementById("add-question-btn").textContent = "Add Question";
  document.getElementById("cancel-edit-btn").style.display = "none";
}

async function deleteQuestion(questionId, examId) {
  try {
    await apiRequest(`/ai-evaluation/questions/${questionId}`, { method: "DELETE" });
    showAlert("questions-alert", "Question deleted.", "success");
    await loadQuestions(examId);
  } catch (err) {
    showAlert("questions-alert", err.message);
  }
}

let currentQuestions = [];

async function loadQuestions(examId) {
  const tbody = document.getElementById("questions-tbody");
  try {
    const data = await apiRequest(`/ai-evaluation/questions/${examId}`);
    currentQuestions = data.questions;

    if (!currentQuestions.length) {
      tbody.innerHTML = '<tr><td colspan="4" class="empty-state">No questions added yet. Upload a question paper or add questions manually above.</td></tr>';
      return;
    }

    let html = "";
    currentQuestions.forEach((q) => {
      const options = [q.option_a, q.option_b, q.option_c, q.option_d, q.option_e]
        .filter((opt) => opt)
        .map((opt, i) => `${String.fromCharCode(65 + i)}) ${escapeHtml(opt)}`)
        .join("<br>");

      html += `
        <tr>
          <td>${q.question_number}</td>
          <td>${escapeHtml(q.question_text)}</td>
          <td>${options}</td>
          <td>
            <button class="btn btn-secondary" style="margin-top:0;" onclick='startEditQuestion(${JSON.stringify(q)})'>Edit</button>
            <button class="btn btn-secondary" style="margin-top:0;" onclick="deleteQuestion(${q.question_id}, ${examId})">Remove</button>
          </td>
        </tr>
      `;
    });
    tbody.innerHTML = html;
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="4" class="empty-state">Could not load questions: ${escapeHtml(err.message)}</td></tr>`;
  }
}

/* ---------------------- Step 2: Generate Answer Key ---------------------- */

async function generateAnswerKey(examId) {
  hideAlert("generate-alert");
  const btn = document.getElementById("generate-answer-key-btn");
  const includeExplanations = document.getElementById("include_explanations").checked;

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Asking Gemini AI...';

  try {
    const data = await apiRequest(`/ai-evaluation/generate-answer-key/${examId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ include_explanations: includeExplanations }),
    });
    showAlert("generate-alert", data.message, "success");
    await loadAnswerKey(examId);
  } catch (err) {
    showAlert("generate-alert", err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Generate Answer Key using Gemini AI";
  }
}

/* ---------------------- Step 3: Verify & Edit Answer Key ---------------------- */

async function loadAnswerKey(examId) {
  const tbody = document.getElementById("answer-key-tbody");
  try {
    const data = await apiRequest(`/ai-evaluation/answer-key/${examId}`);

    if (!data.answers.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="empty-state">Add questions and generate an answer key above to review it here.</td></tr>';
      return;
    }

    let html = "";
    data.answers.forEach((row) => {
      html += `
        <tr>
          <td>${row.question_number}</td>
          <td>${escapeHtml(row.question_text)}</td>
          <td>
            <input type="text" maxlength="1" class="ak-answer-input" data-qnum="${row.question_number}" value="${row.correct_option || ""}" placeholder="A-E" style="width:60px;text-transform:uppercase;">
          </td>
          <td>
            <textarea class="ak-explanation-input" data-qnum="${row.question_number}" rows="2" style="width:100%;" placeholder="No explanation available.">${escapeHtml(row.explanation || "")}</textarea>
          </td>
          <td style="text-align:center;">
            <input type="checkbox" class="ak-verified-checkbox" data-qnum="${row.question_number}" ${row.is_verified ? "checked" : ""}>
          </td>
        </tr>
      `;
    });
    tbody.innerHTML = html;

    document.querySelectorAll(".ak-answer-input").forEach((input) => {
      input.addEventListener("input", () => {
        input.value = input.value.toUpperCase();
      });
    });
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty-state">Could not load the answer key: ${escapeHtml(err.message)}</td></tr>`;
  }
}

async function saveVerifiedKey(examId) {
  hideAlert("verify-alert");
  const btn = document.getElementById("save-verified-key-btn");

  const answerInputs = document.querySelectorAll(".ak-answer-input");
  if (!answerInputs.length) {
    showAlert("verify-alert", "Generate the answer key above before saving.");
    return;
  }

  const VALID_OPTIONS = ["A", "B", "C", "D", "E"];
  const answers = [];
  const emptyQuestions = [];
  const invalidQuestions = [];

  answerInputs.forEach((input) => {
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
    showAlert("verify-alert", `Please fill in an answer for question(s): ${emptyQuestions.join(", ")}.`);
    return;
  }
  if (invalidQuestions.length) {
    showAlert("verify-alert", `Question(s) ${invalidQuestions.join(", ")} must have a valid option (A-E).`);
    return;
  }

  btn.disabled = true;
  btn.textContent = "Saving...";

  try {
    const data = await apiRequest(`/ai-evaluation/verify-answer-key/${examId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answers }),
    });
    showAlert("verify-alert", data.message, "success");
    await loadAnswerKey(examId);
  } catch (err) {
    showAlert("verify-alert", err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Save Verified Answer Key";
  }
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

/* ---------------------- Step 4: Upload Student Answer Sheet ---------------------- */
/* Reuses the existing /api/student-sheet endpoints (upload + auto
   OCR/OMR processing) that already power the OMR Evaluation flow --
   no new backend logic needed here, just wiring this page to it. */

function setupSheetPreview() {
  const input = document.getElementById("ai_student_sheet_file");
  const preview = document.getElementById("ai-sheet-preview");
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

async function uploadStudentSheet(examId) {
  hideAlert("ai-sheet-alert");
  const fileInput = document.getElementById("ai_student_sheet_file");
  const btn = document.getElementById("ai-upload-sheet-btn");

  const file = fileInput.files[0];
  if (!file) {
    showAlert("ai-sheet-alert", "Please choose an answer sheet image first.");
    return;
  }

  const validExtensions = [".jpg", ".jpeg", ".png"];
  const lowerName = file.name.toLowerCase();
  if (!validExtensions.some((ext) => lowerName.endsWith(ext))) {
    showAlert("ai-sheet-alert", "Unsupported file type. Only JPG, JPEG, and PNG images are allowed.");
    return;
  }

  const formData = new FormData();
  formData.append("file", file);
  formData.append("student_name", document.getElementById("ai_student_name").value.trim());
  formData.append("roll_number", document.getElementById("ai_roll_number").value.trim());

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Uploading...';

  try {
    const uploadData = await apiRequest(`/student-sheet/upload/${examId}`, {
      method: "POST",
      body: formData,
    });

    const sheetId = uploadData.sheet.sheet_id;
    setCurrentSheetId(sheetId);

    btn.innerHTML = '<span class="spinner"></span> Extracting answers with OCR...';
    const processData = await apiRequest(`/student-sheet/process/${sheetId}`, { method: "POST" });

    showAlert(
      "ai-sheet-alert",
      `${uploadData.message} ${processData.message} Go to the Result page to see the evaluated marks.`,
      "success"
    );
    fileInput.value = "";
    document.getElementById("ai-sheet-preview").style.display = "none";
    await loadStudentSheets(examId);
  } catch (err) {
    showAlert("ai-sheet-alert", err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Upload & Extract Answers";
  }
}

async function loadStudentSheets(examId) {
  const tbody = document.getElementById("ai-sheets-tbody");
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
          <td><button class="btn btn-secondary" style="margin-top:0;" onclick="viewSheetResult(${sheet.sheet_id})">View Result</button></td>
        </tr>
      `;
    });
    tbody.innerHTML = html;
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty-state">Could not load student sheets: ${escapeHtml(err.message)}</td></tr>`;
  }
}

function viewSheetResult(sheetId) {
  setCurrentSheetId(sheetId);
  window.location.href = "/result";
}
