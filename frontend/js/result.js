/* ============================================================
   result.js
   Loads the evaluation result for the currently selected student
   sheet. If it hasn't been evaluated yet, triggers the evaluation
   engine automatically, then renders the summary, the
   question-wise breakdown, and (on request) the AI Performance
   Analysis.
============================================================ */

let currentSheetIdForAnalysis = null;

document.addEventListener("DOMContentLoaded", () => {
  const sheetId = getCurrentSheetId();

  if (!sheetId) {
    document.getElementById("no-sheet-warning").style.display = "block";
    document.getElementById("loading-state").style.display = "none";
    return;
  }

  currentSheetIdForAnalysis = sheetId;
  loadResult(sheetId);

  document.getElementById("generate-analysis-btn").addEventListener("click", () => generateAnalysis(sheetId));
  document.getElementById("regenerate-analysis-btn").addEventListener("click", () => generateAnalysis(sheetId));
});

async function loadResult(sheetId) {
  const loadingState = document.getElementById("loading-state");
  const errorState = document.getElementById("error-state");
  const errorText = document.getElementById("error-text");

  try {
    // First, try to fetch an already-computed result.
    let data;
    try {
      data = await apiRequest(`/evaluation/${sheetId}`);
    } catch (fetchErr) {
      // Not evaluated yet (or any other issue) -- attempt to run
      // the evaluation engine now, then retry rendering.
      data = await apiRequest(`/evaluation/evaluate/${sheetId}`, { method: "POST" });
    }

    renderResult(data);
    loadingState.style.display = "none";
    errorState.style.display = "none";
    document.getElementById("result-content").style.display = "block";
  } catch (err) {
    loadingState.style.display = "none";
    errorText.textContent = err.message;
    errorState.style.display = "block";
  }
}

/**
 * Populates every section of the result page from the API response.
 */
function renderResult(data) {
  document.getElementById("r-exam-name").textContent = data.exam_name;
  document.getElementById("r-student-name").textContent = data.student_name || "Not provided";
  document.getElementById("r-roll-number").textContent = data.roll_number || "Not provided";
  document.getElementById("r-sheet-type").textContent = data.sheet_type;

  const summary = data.summary;
  document.getElementById("r-correct-count").textContent = summary.correct_count;
  document.getElementById("r-wrong-count").textContent = summary.wrong_count;
  document.getElementById("r-blank-count").textContent = summary.blank_count;
  document.getElementById("r-invalid-count").textContent = summary.invalid_count;
  document.getElementById("r-final-marks").textContent = summary.final_marks;
  document.getElementById("r-max-marks").textContent = summary.max_marks;
  document.getElementById("r-percentage").textContent = summary.percentage;

  const badgeClassFor = {
    Correct: "badge-correct",
    Wrong: "badge-wrong",
    Unanswered: "badge-blank",
    Invalid: "badge-invalid",
  };

  let rowsHtml = "";
  data.question_results.forEach((row) => {
    const badgeClass = badgeClassFor[row.status] || "badge-blank";
    const marksDisplay = row.marks > 0 ? `+${row.marks}` : `${row.marks}`;
    rowsHtml += `
      <tr>
        <td>Q${row.question_number}</td>
        <td>${row.selected_option || "—"}</td>
        <td>${row.correct_option || "—"}</td>
        <td><span class="badge ${badgeClass}">${row.status}</span></td>
        <td>${marksDisplay}</td>
      </tr>
    `;
  });

  document.getElementById("question-results-tbody").innerHTML = rowsHtml;

  // If this sheet already has a saved AI Performance Analysis
  // (data.ai_analysis, only present from the GET endpoint), show it
  // directly instead of the "Generate" prompt.
  if (data.ai_analysis) {
    renderStoredAnalysisText(data.ai_analysis);
  }
}

/**
 * Renders a previously saved ai_analysis TEXT blob (from the GET
 * endpoint) by showing it as-is, since the structured strong/weak/
 * suggestions breakdown is only returned by the POST /analyze call
 * itself. This still gives the teacher immediate access to a
 * previously generated analysis without needing to regenerate it.
 */
function renderStoredAnalysisText(formattedText) {
  document.getElementById("ai-analysis-empty").style.display = "none";
  document.getElementById("ai-analysis-content").style.display = "block";
  document.getElementById("ai-analysis-strong").innerHTML = "";
  document.getElementById("ai-analysis-weak").innerHTML = "";
  document.getElementById("ai-analysis-suggestions").innerHTML = `<pre style="white-space:pre-wrap;font-family:inherit;margin:0;">${escapeHtml(formattedText)}</pre>`;
}

async function generateAnalysis(sheetId) {
  hideAlert("ai-analysis-alert");
  const generateBtn = document.getElementById("generate-analysis-btn");
  const regenerateBtn = document.getElementById("regenerate-analysis-btn");

  [generateBtn, regenerateBtn].forEach((btn) => {
    btn.disabled = true;
  });
  const activeBtn = document.getElementById("ai-analysis-content").style.display === "block" ? regenerateBtn : generateBtn;
  const originalText = activeBtn.textContent;
  activeBtn.innerHTML = '<span class="spinner"></span> Analyzing with Gemini...';

  try {
    const data = await apiRequest(`/evaluation/analyze/${sheetId}`, { method: "POST" });

    document.getElementById("ai-analysis-empty").style.display = "none";
    document.getElementById("ai-analysis-content").style.display = "block";

    const strongHtml = data.strong_topics.length
      ? `<h3 style="margin-bottom:6px;color:#1f9d55;">Strong Topics</h3><ul style="margin:0;padding-left:20px;">${data.strong_topics.map((t) => `<li>${escapeHtml(t)}</li>`).join("")}</ul>`
      : "";
    const weakHtml = data.weak_topics.length
      ? `<h3 style="margin-bottom:6px;color:#d33d3d;">Weak Topics</h3><ul style="margin:0;padding-left:20px;">${data.weak_topics.map((t) => `<li>${escapeHtml(t)}</li>`).join("")}</ul>`
      : "";
    const suggestionsHtml = data.suggestions
      ? `<h3 style="margin-bottom:6px;color:#2f5fdc;">Suggestions</h3><p style="margin:0;color:#374151;">${escapeHtml(data.suggestions)}</p>`
      : "";

    document.getElementById("ai-analysis-strong").innerHTML = strongHtml;
    document.getElementById("ai-analysis-weak").innerHTML = weakHtml;
    document.getElementById("ai-analysis-suggestions").innerHTML = suggestionsHtml;

    showAlert("ai-analysis-alert", data.message, "success");
  } catch (err) {
    showAlert("ai-analysis-alert", err.message);
  } finally {
    [generateBtn, regenerateBtn].forEach((btn) => {
      btn.disabled = false;
    });
    activeBtn.textContent = originalText;
  }
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}
