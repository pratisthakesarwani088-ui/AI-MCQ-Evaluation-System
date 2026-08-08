/* ============================================================
   verify_answer_key.js
   Loads the current (draft or already-verified) answer key into an
   editable table, lets the teacher correct any answers, and saves
   the final verified key back to the server.
============================================================ */

const VALID_OPTIONS = ["A", "B", "C", "D", "E"];

document.addEventListener("DOMContentLoaded", () => {
  const examId = getCurrentExamId();

  if (!examId) {
    document.getElementById("no-exam-warning").style.display = "block";
    document.getElementById("verify-card").style.display = "none";
    return;
  }

  loadAnswerKey(examId);

  document.getElementById("save-btn").addEventListener("click", () => saveAnswerKey(examId));
});

/**
 * Fetches the current answer key rows and renders one editable
 * input per question.
 */
async function loadAnswerKey(examId) {
  const loadingState = document.getElementById("loading-state");
  const tableWrapper = document.getElementById("table-wrapper");
  const tbody = document.getElementById("answer-key-tbody");

  try {
    const data = await apiRequest(`/answer-key/${examId}`);

    if (!data.answers.length) {
      loadingState.textContent = "No answer key found yet. Please upload an answer key image first.";
      return;
    }

    let rowsHtml = "";
    data.answers.forEach((row) => {
      rowsHtml += `
        <tr>
          <td>Question ${row.question_number}</td>
          <td>
            <input
              type="text"
              maxlength="1"
              data-question="${row.question_number}"
              class="answer-input"
              value="${row.correct_option || ""}"
              placeholder="A-E"
              style="text-transform: uppercase; width: 70px;"
            >
          </td>
        </tr>
      `;
    });

    tbody.innerHTML = rowsHtml;
    loadingState.style.display = "none";
    tableWrapper.style.display = "block";

    // Auto-uppercase whatever the teacher types.
    document.querySelectorAll(".answer-input").forEach((input) => {
      input.addEventListener("input", () => {
        input.value = input.value.toUpperCase();
      });
    });
  } catch (err) {
    loadingState.textContent = `Could not load the answer key: ${err.message}`;
  }
}

/**
 * Collects every input's value, validates it client-side, and
 * submits the full verified answer key to the backend.
 */
async function saveAnswerKey(examId) {
  hideAlert("form-alert");
  const saveBtn = document.getElementById("save-btn");
  const inputs = document.querySelectorAll(".answer-input");

  const answers = [];
  const emptyQuestions = [];
  const invalidQuestions = [];

  inputs.forEach((input) => {
    const questionNumber = parseInt(input.dataset.question, 10);
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
    showAlert("form-alert", `Please fill in an answer for question(s): ${emptyQuestions.join(", ")}.`);
    return;
  }
  if (invalidQuestions.length) {
    showAlert("form-alert", `Question(s) ${invalidQuestions.join(", ")} must have a valid option (A-E).`);
    return;
  }

  saveBtn.disabled = true;
  saveBtn.textContent = "Saving...";

  try {
    const data = await apiRequest(`/answer-key/verify/${examId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answers }),
    });

    showAlert("form-alert", `${data.message} Redirecting to upload a student sheet...`, "success");

    setTimeout(() => {
      window.location.href = "/upload-student-sheet";
    }, 1200);
  } catch (err) {
    showAlert("form-alert", err.message);
  } finally {
    saveBtn.disabled = false;
    saveBtn.textContent = "Save Verified Answer Key";
  }
}
