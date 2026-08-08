/* ============================================================
   create_exam.js
   Handles the "Create Exam" form submission and displays the
   list of existing exams (with a "Select" action that stores the
   chosen exam_id in sessionStorage for use on later pages).
============================================================ */

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("create-exam-form");
  const submitBtn = document.getElementById("submit-btn");

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    hideAlert("form-alert");

    const examName = document.getElementById("exam_name").value.trim();
    const subject = document.getElementById("subject").value.trim();
    const examType = document.getElementById("exam_type").value;
    const totalQuestions = parseInt(document.getElementById("total_questions").value, 10);
    const marksPerCorrect = parseFloat(document.getElementById("marks_per_correct").value);
    const negativeMarks = parseFloat(document.getElementById("negative_marks").value || "0");

    // --- Client-side validation (friendly, immediate feedback) ---
    if (!examName) {
      showAlert("form-alert", "Please enter an exam name.");
      return;
    }
    if (!examType) {
      showAlert("form-alert", "Please choose an exam type (AI-Based or OMR Evaluation).");
      return;
    }
    if (!totalQuestions || totalQuestions <= 0) {
      showAlert("form-alert", "Total questions must be a positive number.");
      return;
    }
    if (totalQuestions > 500) {
      showAlert("form-alert", "Total questions cannot be more than 500.");
      return;
    }
    if (!marksPerCorrect || marksPerCorrect <= 0) {
      showAlert("form-alert", "Marks per correct answer must be a positive number.");
      return;
    }
    if (negativeMarks < 0) {
      showAlert("form-alert", "Negative marks cannot be a negative value.");
      return;
    }
    if (negativeMarks > marksPerCorrect) {
      showAlert("form-alert", "Negative marks cannot be greater than marks per correct answer.");
      return;
    }

    submitBtn.disabled = true;
    submitBtn.textContent = "Creating...";

    try {
      const data = await apiRequest("/exams", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          exam_name: examName,
          subject: subject || null,
          exam_type: examType,
          total_questions: totalQuestions,
          marks_per_correct: marksPerCorrect,
          negative_marks: negativeMarks,
        }),
      });

      // Remember this as the "current" exam so the next steps
      // (upload answer key, etc.) know which exam to attach to.
      setCurrentExamId(data.exam.exam_id);
      setCurrentExamType(data.exam.exam_type);

      showAlert("form-alert", `"${data.exam.exam_name}" created successfully! Redirecting...`, "success");
      form.reset();
      document.getElementById("negative_marks").value = "0";

      await loadExams();

      // AI-Based exams generate their answer key via the AI
      // Assistant; OMR exams go to the OMR Evaluation hub.
      const nextPage = data.exam.exam_type === "AI" ? "/ai-evaluation" : "/omr-evaluation";
      setTimeout(() => {
        window.location.href = nextPage;
      }, 1200);
    } catch (err) {
      showAlert("form-alert", err.message);
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "Create Exam";
    }
  });

  loadExams();
});

/**
 * Fetches all existing exams and renders them as a table with a
 * "Select" button so the teacher can resume work on a past exam.
 */
async function loadExams() {
  const container = document.getElementById("exams-list");
  try {
    const data = await apiRequest("/exams");

    if (!data.exams.length) {
      container.innerHTML = '<p class="empty-state">No exams created yet. Use the form above to create your first exam.</p>';
      return;
    }

    let html = `
      <table>
        <thead>
          <tr>
            <th>Exam Name</th>
            <th>Subject</th>
            <th>Type</th>
            <th>Questions</th>
            <th>Marks / Question</th>
            <th>Negative Marks</th>
            <th>Created</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
    `;

    data.exams.forEach((exam) => {
      const createdDate = new Date(exam.created_at).toLocaleString();
      const typeBadgeClass = exam.exam_type === "AI" ? "badge-correct" : "badge-blank";
      html += `
        <tr>
          <td>${escapeHtml(exam.exam_name)}</td>
          <td>${escapeHtml(exam.subject || "—")}</td>
          <td><span class="badge ${typeBadgeClass}">${exam.exam_type}</span></td>
          <td>${exam.total_questions}</td>
          <td>${exam.marks_per_correct}</td>
          <td>${exam.negative_marks}</td>
          <td>${createdDate}</td>
          <td><button class="btn btn-secondary" style="margin-top:0;" onclick="selectExam(${exam.exam_id}, '${exam.exam_type}')">Select</button></td>
        </tr>
      `;
    });

    html += "</tbody></table>";
    container.innerHTML = html;
  } catch (err) {
    container.innerHTML = `<p class="empty-state">Could not load exams: ${escapeHtml(err.message)}</p>`;
  }
}

/**
 * Marks an existing exam as the "current" exam and takes the
 * teacher to the appropriate next step based on its exam type.
 */
function selectExam(examId, examType) {
  setCurrentExamId(examId);
  setCurrentExamType(examType);
  window.location.href = examType === "AI" ? "/ai-evaluation" : "/omr-evaluation";
}

/**
 * Minimal HTML-escaping helper to safely render user-entered text
 * (exam names) inside the table without risking HTML injection.
 */
function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}
