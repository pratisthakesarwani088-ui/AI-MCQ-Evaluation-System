/* ============================================================
   reports.js
   ----------------------------------------------------------
   Full Reports workflow, wired to the backend:
     - Find an exam (search / subject filter / type filter) --
       reuses the same GET /api/exams endpoint as Previous Exams.
     - Exam Report: statistics cards + Download Exam Report PDF.
     - Student Reports: table of evaluated students (reuses the
       same /api/previous-exams/{exam_id}/students endpoint) with
       a Download Student Report PDF button per row.
     - Generated Reports: list of previously generated PDFs for the
       selected exam, each downloadable again without regenerating.
============================================================ */

let allStudents = [];   // last-loaded student list for the selected exam, for client-side search
let currentExamId = null;

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("report-exam-search").addEventListener("input", debounce(loadExams, 300));
  document.getElementById("report-subject-filter").addEventListener("change", loadExams);
  document.getElementById("report-type-filter").addEventListener("change", loadExams);

  document.getElementById("student-report-search").addEventListener("input", () => {
    renderStudentsTable(filterStudents(allStudents, document.getElementById("student-report-search").value));
  });

  document.getElementById("download-exam-report-btn").addEventListener("click", downloadExamReport);

  loadExams();
});

function debounce(fn, delayMs) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delayMs);
  };
}

/* ---------------------- Find Exam ---------------------- */

async function loadExams() {
  const loadingEl = document.getElementById("exams-loading");
  const tableEl = document.getElementById("exams-table");
  const emptyEl = document.getElementById("exams-empty");

  hideAlert("exams-error");
  loadingEl.style.display = "block";
  tableEl.style.display = "none";
  emptyEl.style.display = "none";

  const search = document.getElementById("report-exam-search").value.trim();
  const subject = document.getElementById("report-subject-filter").value;
  const examType = document.getElementById("report-type-filter").value;

  const params = new URLSearchParams();
  if (search) params.set("search", search);
  if (subject) params.set("subject", subject);
  if (examType) params.set("exam_type", examType);

  try {
    const data = await apiRequest(`/exams?${params.toString()}`);
    populateSubjectFilter(data.exams);
    loadingEl.style.display = "none";

    if (!data.exams.length) {
      emptyEl.style.display = "block";
      return;
    }

    renderExamsTable(data.exams);
    tableEl.style.display = "table";
  } catch (err) {
    loadingEl.style.display = "none";
    showAlert("exams-error", err.message);
  }
}

function populateSubjectFilter(exams) {
  const select = document.getElementById("report-subject-filter");
  const currentValue = select.value;
  const subjects = [...new Set(exams.map((e) => e.subject).filter(Boolean))].sort();

  let html = '<option value="">All Subjects</option>';
  subjects.forEach((s) => {
    html += `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`;
  });
  select.innerHTML = html;
  if (subjects.includes(currentValue)) select.value = currentValue;
}

function renderExamsTable(exams) {
  const tbody = document.getElementById("exams-tbody");
  let html = "";
  exams.forEach((exam) => {
    const typeBadgeClass = exam.exam_type === "AI" ? "badge-correct" : "badge-blank";
    html += `
      <tr>
        <td>${escapeHtml(exam.exam_name)}</td>
        <td>${escapeHtml(exam.subject || "—")}</td>
        <td><span class="badge ${typeBadgeClass}">${exam.exam_type}</span></td>
        <td>${exam.evaluated_count}</td>
        <td><button class="btn btn-primary" style="margin-top:0;" onclick="selectExamForReports(${exam.exam_id}, '${escapeHtml(exam.exam_name).replace(/'/g, "\\'")}')">View Reports</button></td>
      </tr>
    `;
  });
  tbody.innerHTML = html;
}

/* ---------------------- Exam Report + Statistics ---------------------- */

async function selectExamForReports(examId, examName) {
  currentExamId = examId;

  document.getElementById("exam-report-card").style.display = "block";
  document.getElementById("student-report-card").style.display = "block";
  document.getElementById("generated-reports-card").style.display = "block";
  document.getElementById("er-exam-name").textContent = examName;
  document.getElementById("exam-report-card").scrollIntoView({ behavior: "smooth", block: "start" });

  await Promise.all([
    loadExamReport(examId),
    loadStudentsForReports(examId),
    loadGeneratedReports(examId),
  ]);
}

async function loadExamReport(examId) {
  const loadingEl = document.getElementById("exam-report-loading");
  const contentEl = document.getElementById("exam-report-content");
  const emptyEl = document.getElementById("exam-report-empty");

  hideAlert("exam-report-alert");
  loadingEl.style.display = "block";
  contentEl.style.display = "none";
  emptyEl.style.display = "none";

  try {
    const data = await apiRequest(`/reports/exam/${examId}`);
    loadingEl.style.display = "none";

    if (data.total_students === 0) {
      emptyEl.style.display = "block";
      return;
    }

    document.getElementById("er-subject").textContent = data.subject || "Not specified";
    document.getElementById("er-exam-type").textContent = data.exam_type === "AI" ? "AI-Based Evaluation" : "OMR Evaluation";
    document.getElementById("er-total-students").textContent = data.total_students;

    document.getElementById("stat-highest-marks").textContent = `${data.highest_marks} / ${data.max_marks}`;
    document.getElementById("stat-lowest-marks").textContent = `${data.lowest_marks} / ${data.max_marks}`;
    document.getElementById("stat-average-marks").textContent = `${data.average_marks} / ${data.max_marks}`;
    document.getElementById("stat-total-students").textContent = data.total_students;
    document.getElementById("stat-pass-count").textContent = data.pass_count;
    document.getElementById("stat-fail-count").textContent = data.fail_count;
    document.getElementById("stat-pass-percentage").textContent = `${data.pass_percentage}%`;
    document.getElementById("stat-average-percentage").textContent = `${data.average_percentage}%`;

    contentEl.style.display = "block";
  } catch (err) {
    loadingEl.style.display = "none";
    showAlert("exam-report-alert", err.message);
  }
}

async function downloadExamReport() {
  if (!currentExamId) return;
  const btn = document.getElementById("download-exam-report-btn");
  hideAlert("exam-report-alert");
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Generating PDF...';

  try {
    const data = await apiRequest(`/reports/exam/${currentExamId}/pdf`, { method: "POST" });
    window.open(`/api/reports/download/${data.report_id}`, "_blank");
    await loadGeneratedReports(currentExamId);
  } catch (err) {
    showAlert("exam-report-alert", err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Download Exam Report PDF";
  }
}

/* ---------------------- Student Reports ---------------------- */

async function loadStudentsForReports(examId) {
  const loadingEl = document.getElementById("students-loading");
  const tableEl = document.getElementById("students-table");
  const emptyEl = document.getElementById("students-empty");

  hideAlert("student-report-alert");
  loadingEl.style.display = "block";
  tableEl.style.display = "none";
  emptyEl.style.display = "none";
  document.getElementById("student-report-search").value = "";

  try {
    const data = await apiRequest(`/previous-exams/${examId}/students`);
    allStudents = data.students;
    loadingEl.style.display = "none";

    if (!allStudents.length) {
      emptyEl.style.display = "block";
      return;
    }

    renderStudentsTable(allStudents);
    tableEl.style.display = "table";
  } catch (err) {
    loadingEl.style.display = "none";
    showAlert("student-report-alert", err.message);
  }
}

function filterStudents(students, query) {
  const q = query.trim().toLowerCase();
  if (!q) return students;
  return students.filter((s) =>
    (s.student_name || "").toLowerCase().includes(q) ||
    (s.roll_number || "").toLowerCase().includes(q)
  );
}

function renderStudentsTable(students) {
  const tbody = document.getElementById("students-tbody");
  const emptyEl = document.getElementById("students-empty");
  const tableEl = document.getElementById("students-table");

  if (!students.length) {
    tableEl.style.display = "none";
    emptyEl.style.display = "block";
    emptyEl.textContent = "No students match your search.";
    return;
  }
  emptyEl.style.display = "none";
  tableEl.style.display = "table";

  let html = "";
  students.forEach((student) => {
    html += `
      <tr>
        <td>${escapeHtml(student.student_name || "—")}</td>
        <td>${escapeHtml(student.roll_number || "—")}</td>
        <td>${student.final_marks} / ${student.max_marks}</td>
        <td>${student.percentage}%</td>
        <td><button class="btn btn-secondary" style="margin-top:0;" onclick="downloadStudentReport(${student.sheet_id}, this)">Download Report PDF</button></td>
      </tr>
    `;
  });
  tbody.innerHTML = html;
}

async function downloadStudentReport(sheetId, btnEl) {
  hideAlert("student-report-alert");
  const originalText = btnEl.textContent;
  btnEl.disabled = true;
  btnEl.innerHTML = '<span class="spinner"></span> Generating...';

  try {
    const data = await apiRequest(`/reports/student/${sheetId}/pdf`, { method: "POST" });
    window.open(`/api/reports/download/${data.report_id}`, "_blank");
    if (currentExamId) await loadGeneratedReports(currentExamId);
  } catch (err) {
    showAlert("student-report-alert", err.message);
  } finally {
    btnEl.disabled = false;
    btnEl.textContent = originalText;
  }
}

/* ---------------------- Generated Reports ---------------------- */

async function loadGeneratedReports(examId) {
  const loadingEl = document.getElementById("generated-reports-loading");
  const tableEl = document.getElementById("generated-reports-table");
  const emptyEl = document.getElementById("generated-reports-empty");

  loadingEl.style.display = "block";
  tableEl.style.display = "none";
  emptyEl.style.display = "none";

  try {
    const data = await apiRequest(`/reports/list/${examId}`);
    loadingEl.style.display = "none";

    if (!data.reports.length) {
      emptyEl.style.display = "block";
      return;
    }

    const labelFor = { STUDENT: "Student Report", EXAM: "Exam Report" };
    let html = "";
    data.reports.forEach((r) => {
      const generatedDate = r.generated_at ? new Date(r.generated_at).toLocaleString() : "—";
      html += `
        <tr>
          <td>${labelFor[r.report_type] || r.report_type}</td>
          <td>${generatedDate}</td>
          <td><button class="btn btn-secondary" style="margin-top:0;" onclick="window.open('/api/reports/download/${r.report_id}', '_blank')">Download</button></td>
        </tr>
      `;
    });
    document.getElementById("generated-reports-tbody").innerHTML = html;
    tableEl.style.display = "table";
  } catch (err) {
    loadingEl.style.display = "none";
    emptyEl.style.display = "block";
    emptyEl.textContent = `Could not load generated reports: ${err.message}`;
  }
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}
