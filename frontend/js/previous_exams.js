/* ============================================================
   previous_exams.js
   ----------------------------------------------------------
   Full Previous Exams + Student Records workflow, wired to the
   backend:
     - Lists exams with search / subject filter / type filter / sort
     - Opens an exam to show its full details + evaluated student list
     - View Result (reuses the existing Result page)
     - Delete Student Record (with confirmation modal), which
       permanently removes the sheet + responses + evaluation
       result (via DB cascade) and the uploaded file, and logs the
       action to Activity Logs.
============================================================ */

let allExams = [];       // last-loaded exam list, used to populate the subject filter
let currentExamId = null;
let pendingDeleteSheetId = null;
let pendingDeleteType = null; // "student" or "exam"

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("exam-search").addEventListener("input", debounce(loadExams, 300));
  document.getElementById("exam-subject-filter").addEventListener("change", loadExams);
  document.getElementById("exam-type-filter").addEventListener("change", loadExams);
  document.getElementById("exam-sort").addEventListener("change", loadExams);

  document.getElementById("delete-modal-cancel").addEventListener("click", closeDeleteModal);
  document.getElementById("delete-modal-confirm").addEventListener("click", confirmDelete);
  document.getElementById("delete-exam-btn").addEventListener("click", openDeleteExamModal);

  loadExams();
});

/**
 * Small debounce helper so typing in the search box doesn't fire a
 * request on every keystroke.
 */
function debounce(fn, delayMs) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delayMs);
  };
}

/* ---------------------- All Exams ---------------------- */

async function loadExams() {
  const loadingEl = document.getElementById("exams-loading");
  const tableEl = document.getElementById("exams-table");
  const emptyEl = document.getElementById("exams-empty");
  const errorEl = document.getElementById("exams-error");

  hideAlert("exams-error");
  loadingEl.style.display = "block";
  tableEl.style.display = "none";
  emptyEl.style.display = "none";

  const search = document.getElementById("exam-search").value.trim();
  const subject = document.getElementById("exam-subject-filter").value;
  const examType = document.getElementById("exam-type-filter").value;
  const sort = document.getElementById("exam-sort").value;

  const params = new URLSearchParams();
  if (search) params.set("search", search);
  if (subject) params.set("subject", subject);
  if (examType) params.set("exam_type", examType);
  if (sort) params.set("sort", sort);

  try {
    const data = await apiRequest(`/exams?${params.toString()}`);
    allExams = data.exams;
    populateSubjectFilter(allExams);

    loadingEl.style.display = "none";

    if (!allExams.length) {
      emptyEl.style.display = "block";
      return;
    }

    renderExamsTable(allExams);
    tableEl.style.display = "table";
  } catch (err) {
    loadingEl.style.display = "none";
    showAlert("exams-error", err.message);
  }
}

/**
 * Fills the Subject filter dropdown with the distinct subjects
 * found in the currently loaded exam list, preserving the
 * currently selected value if it's still present.
 */
function populateSubjectFilter(exams) {
  const select = document.getElementById("exam-subject-filter");
  const currentValue = select.value;

  const subjects = [...new Set(exams.map((e) => e.subject).filter(Boolean))].sort();

  let html = '<option value="">All Subjects</option>';
  subjects.forEach((s) => {
    html += `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`;
  });
  select.innerHTML = html;

  if (subjects.includes(currentValue)) {
    select.value = currentValue;
  }
}

function renderExamsTable(exams) {
  const tbody = document.getElementById("exams-tbody");
  let html = "";

  exams.forEach((exam) => {
    const createdDate = new Date(exam.created_at).toLocaleDateString(undefined, {
      year: "numeric", month: "short", day: "numeric",
    });
    const typeBadgeClass = exam.exam_type === "AI" ? "badge-correct" : "badge-blank";

    html += `
      <tr>
        <td>${escapeHtml(exam.exam_name)}</td>
        <td>${escapeHtml(exam.subject || "—")}</td>
        <td><span class="badge ${typeBadgeClass}">${exam.exam_type}</span></td>
        <td>${exam.total_questions}</td>
        <td>${exam.evaluated_count}</td>
        <td>${createdDate}</td>
        <td><button class="btn btn-primary" style="margin-top:0;" onclick="openExam(${exam.exam_id})">View</button></td>
      </tr>
    `;
  });

  tbody.innerHTML = html;
}

/* ---------------------- Exam Details + Student List ---------------------- */

async function openExam(examId) {
  currentExamId = examId;

  document.getElementById("exam-details-card").style.display = "block";
  document.getElementById("student-list-card").style.display = "block";
  document.getElementById("exam-details-card").scrollIntoView({ behavior: "smooth", block: "start" });

  await Promise.all([loadExamDetails(examId), loadStudentList(examId)]);
}

async function loadExamDetails(examId) {
  try {
    const data = await apiRequest(`/exams/${examId}`);
    const exam = data.exam;

    document.getElementById("d-exam-name").textContent = exam.exam_name;
    document.getElementById("d-subject").textContent = exam.subject || "Not specified";
    document.getElementById("d-exam-type").textContent = exam.exam_type === "AI" ? "AI-Based Evaluation" : "OMR Evaluation";
    document.getElementById("d-total-questions").textContent = exam.total_questions;
    document.getElementById("d-marks-per-question").textContent = exam.marks_per_correct;
    document.getElementById("d-negative-marks").textContent = exam.negative_marks;
    document.getElementById("d-evaluated-count").textContent = exam.evaluated_count;
    document.getElementById("d-created-at").textContent = new Date(exam.created_at).toLocaleString();
  } catch (err) {
    showAlert("exams-error", `Could not load exam details: ${err.message}`);
  }
}

async function loadStudentList(examId) {
  const loadingEl = document.getElementById("students-loading");
  const tableEl = document.getElementById("students-table");
  const emptyEl = document.getElementById("students-empty");

  hideAlert("students-error");
  loadingEl.style.display = "block";
  tableEl.style.display = "none";
  emptyEl.style.display = "none";

  try {
    const data = await apiRequest(`/previous-exams/${examId}/students`);
    loadingEl.style.display = "none";

    if (!data.students.length) {
      emptyEl.style.display = "block";
      return;
    }

    renderStudentList(data.students);
    tableEl.style.display = "table";
  } catch (err) {
    loadingEl.style.display = "none";
    showAlert("students-error", err.message);
  }
}

function renderStudentList(students) {
  const tbody = document.getElementById("student-list-tbody");
  let html = "";

  students.forEach((student) => {
    const evalDate = student.evaluated_at
      ? new Date(student.evaluated_at).toLocaleString()
      : "—";

    html += `
      <tr>
        <td>${escapeHtml(student.student_name || "—")}</td>
        <td>${escapeHtml(student.roll_number || "—")}</td>
        <td>${student.final_marks} / ${student.max_marks}</td>
        <td>${student.percentage}%</td>
        <td>${evalDate}</td>
        <td>
          <button class="btn btn-secondary" style="margin-top:0;" onclick="viewStudentResult(${student.sheet_id})">View Result</button>
          <button class="btn btn-secondary" style="margin-top:0;background:#fdecec;color:#d33d3d;" onclick="openDeleteModal(${student.sheet_id}, '${escapeHtml(student.student_name || student.roll_number || ('Sheet #' + student.sheet_id)).replace(/'/g, "\\'")}')">Delete</button>
        </td>
      </tr>
    `;
  });

  tbody.innerHTML = html;
}

function viewStudentResult(sheetId) {
  setCurrentSheetId(sheetId);
  window.location.href = "/result";
}

/* ---------------------- Delete Student Record (with confirmation modal) ---------------------- */

function openDeleteModal(sheetId, studentLabel) {
  pendingDeleteSheetId = sheetId;
  pendingDeleteType = "student";
  document.getElementById("delete-modal-text").textContent =
    `Are you sure you want to permanently delete the record for "${studentLabel}"?`;
  document.getElementById("delete-modal-overlay").style.display = "flex";
}

function openDeleteExamModal() {
  if (!currentExamId) return;
  const examName = document.getElementById("d-exam-name").textContent;
  pendingDeleteSheetId = currentExamId;
  pendingDeleteType = "exam";
  document.getElementById("delete-modal-text").textContent =
    `Are you sure you want to permanently delete the exam "${examName}"? This also deletes all of its questions, answer keys, student sheets, results, and reports.`;
  document.getElementById("delete-modal-overlay").style.display = "flex";
}

function closeDeleteModal() {
  pendingDeleteSheetId = null;
  pendingDeleteType = null;
  document.getElementById("delete-modal-overlay").style.display = "none";
}

async function confirmDelete() {
  if (!pendingDeleteSheetId || !pendingDeleteType) return;

  const id = pendingDeleteSheetId;
  const type = pendingDeleteType;
  const confirmBtn = document.getElementById("delete-modal-confirm");
  confirmBtn.disabled = true;
  confirmBtn.textContent = "Deleting...";

  try {
    if (type === "student") {
      await apiRequest(`/previous-exams/students/${id}`, { method: "DELETE" });
      closeDeleteModal();
      if (currentExamId) {
        await Promise.all([loadExamDetails(currentExamId), loadStudentList(currentExamId)]);
      }
      await loadExams();
    } else if (type === "exam") {
      await apiRequest(`/exams/${id}`, { method: "DELETE" });
      closeDeleteModal();
      document.getElementById("exam-details-card").style.display = "none";
      document.getElementById("student-list-card").style.display = "none";
      currentExamId = null;
      await loadExams();
    }
  } catch (err) {
    const errorTarget = type === "exam" ? "exams-error" : "students-error";
    showAlert(errorTarget, err.message);
    closeDeleteModal();
  } finally {
    confirmBtn.disabled = false;
    confirmBtn.textContent = "Delete Permanently";
  }
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}
