/* ============================================================
   ai_assistant.js
   ----------------------------------------------------------
   Full AI Assistant panel, wired to the backend. Reuses existing
   endpoints wherever the underlying capability already exists
   elsewhere in the app:
     - Generate Answer Key -> /api/ai-evaluation/generate-answer-key
     - Analyze Results / Weak Topics / Strong Topics / Suggestions
       -> /api/evaluation/analyze/{sheet_id} (one Gemini call already
          returns all three; this panel just displays different
          parts of that same cached response per tab)
     - Exam/student pickers -> /api/exams, /api/previous-exams/{id}/students
   Only Explain Answers and Generate MCQs are genuinely new backend
   endpoints (/api/ai-assistant/...).
============================================================ */

let activeAction = "generate-answer-key";

// Caches so switching tabs / re-rendering doesn't refetch unnecessarily.
let aiExamsCache = null;          // AI-type exams, for Generate Answer Key / Explain Answers / Save MCQs
let allExamsCache = null;         // every exam, for the student-analysis tabs
let studentsByExamCache = {};     // examId -> students list
let lastAnalysis = null;          // { sheetId, summary, analysis }
let lastGeneratedMCQs = null;     // [{question_text, option_a..d, correct_option, explanation}]

const ANALYSIS_TABS = ["analyze-results", "weak-topics", "strong-topics", "suggestions"];

document.addEventListener("DOMContentLoaded", () => {
  const actionButtons = document.querySelectorAll(".ai-action-btn");
  actionButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      actionButtons.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      activeAction = btn.dataset.action;
      renderContextPanel();
    });
  });

  renderContextPanel();
});

async function renderContextPanel() {
  const panel = document.getElementById("ai-context-panel");

  if (activeAction === "generate-answer-key") {
    panel.innerHTML = generateAnswerKeyTemplate();
    await populateExamSelect("gak-exam-select", { aiOnly: true });
    document.getElementById("gak-run-btn").addEventListener("click", runGenerateAnswerKey);
  } else if (activeAction === "explain-answer") {
    panel.innerHTML = explainAnswerTemplate();
    await populateExamSelect("ea-exam-select", { aiOnly: true });
    document.getElementById("ea-run-btn").addEventListener("click", runExplainAnswer);
  } else if (activeAction === "generate-mcqs") {
    panel.innerHTML = generateMcqsTemplate();
    document.getElementById("gm-run-btn").addEventListener("click", runGenerateMcqs);
    if (lastGeneratedMCQs) {
      renderGeneratedMcqs(lastGeneratedMCQs);
      await populateExamSelect("gm-save-exam-select", { aiOnly: true });
    }
  } else if (ANALYSIS_TABS.includes(activeAction)) {
    panel.innerHTML = analysisTemplate();
    await populateExamSelect("an-exam-select", { aiOnly: false });
    document.getElementById("an-exam-select").addEventListener("change", onAnalysisExamChange);
    document.getElementById("an-run-btn").addEventListener("click", runAnalysis);
    if (lastAnalysis) {
      renderAnalysisOutput();
    }
  }
}

/* ============================================================
   Shared helpers
============================================================ */

async function populateExamSelect(selectId, { aiOnly }) {
  const select = document.getElementById(selectId);
  if (!select) return;

  try {
    if (aiOnly) {
      if (!aiExamsCache) {
        const data = await apiRequest("/exams?exam_type=AI");
        aiExamsCache = data.exams;
      }
      renderExamOptions(select, aiExamsCache, "No AI-Based Evaluation exams found. Create one first.");
    } else {
      if (!allExamsCache) {
        const data = await apiRequest("/exams");
        allExamsCache = data.exams;
      }
      renderExamOptions(select, allExamsCache, "No exams found. Create one first.");
    }
  } catch (err) {
    select.innerHTML = `<option value="">Could not load exams</option>`;
  }
}

function renderExamOptions(select, exams, emptyLabel) {
  if (!exams.length) {
    select.innerHTML = `<option value="">${emptyLabel}</option>`;
    return;
  }
  let html = '<option value="">-- Select an exam --</option>';
  exams.forEach((e) => {
    html += `<option value="${e.exam_id}">${escapeHtml(e.exam_name)} (${e.exam_type})</option>`;
  });
  select.innerHTML = html;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

/* ============================================================
   1. Generate Answer Key
============================================================ */

function generateAnswerKeyTemplate() {
  return `
    <h2 style="margin-top:0;">Generate Answer Key</h2>
    <p style="color:#6b7280;margin-top:-6px;">Gemini reads every question in the selected exam and suggests a correct answer for each.</p>

    <label for="gak-exam-select">Exam</label>
    <select id="gak-exam-select"><option value="">Loading exams...</option></select>

    <label style="display:flex; align-items:center; gap:8px; font-weight:400; margin-top:14px;">
      <input type="checkbox" id="gak-include-explanations" style="width:auto;">
      Also generate a short explanation for each answer
    </label>

    <button type="button" class="btn btn-primary" id="gak-run-btn">Generate Answer Key</button>
    <div class="ai-output-box" id="gak-output">Output will appear here once you run this action.</div>
  `;
}

async function runGenerateAnswerKey() {
  const examId = document.getElementById("gak-exam-select").value;
  const includeExplanations = document.getElementById("gak-include-explanations").checked;
  const output = document.getElementById("gak-output");
  const btn = document.getElementById("gak-run-btn");

  if (!examId) {
    output.textContent = "Please select an exam first.";
    return;
  }

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Asking Gemini AI...';
  output.textContent = "";

  try {
    const data = await apiRequest(`/ai-evaluation/generate-answer-key/${examId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ include_explanations: includeExplanations }),
    });
    output.innerHTML = `${escapeHtml(data.message)}<br><br><a href="/ai-evaluation" onclick="setCurrentExamId(${examId}); setCurrentExamType('AI');">Review &amp; verify this answer key on the AI-Based Evaluation page &rarr;</a>`;
  } catch (err) {
    output.textContent = err.message;
  } finally {
    btn.disabled = false;
    btn.textContent = "Generate Answer Key";
  }
}

/* ============================================================
   2. Explain Answers
============================================================ */

function explainAnswerTemplate() {
  return `
    <h2 style="margin-top:0;">Explain Answers</h2>
    <p style="color:#6b7280;margin-top:-6px;">Pick any question with a verified answer and Gemini will explain why it's correct (and why the other options aren't).</p>

    <label for="ea-exam-select">Exam</label>
    <select id="ea-exam-select"><option value="">Loading exams...</option></select>

    <label for="ea-question-number">Question Number</label>
    <input type="number" id="ea-question-number" min="1" placeholder="e.g. 3" style="max-width:160px;">

    <button type="button" class="btn btn-primary" id="ea-run-btn">Explain This Answer</button>
    <div class="ai-output-box" id="ea-output">Output will appear here once you run this action.</div>
  `;
}

async function runExplainAnswer() {
  const examId = document.getElementById("ea-exam-select").value;
  const questionNumber = parseInt(document.getElementById("ea-question-number").value, 10);
  const output = document.getElementById("ea-output");
  const btn = document.getElementById("ea-run-btn");

  if (!examId) {
    output.textContent = "Please select an exam first.";
    return;
  }
  if (!questionNumber || questionNumber < 1) {
    output.textContent = "Please enter a valid question number.";
    return;
  }

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Asking Gemini AI...';
  output.textContent = "";

  try {
    const data = await apiRequest("/ai-assistant/explain-answer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ exam_id: parseInt(examId, 10), question_number: questionNumber }),
    });
    output.innerHTML = `<strong>Correct answer: ${data.correct_option}</strong><br><br>${escapeHtml(data.explanation)}`;
  } catch (err) {
    output.textContent = err.message;
  } finally {
    btn.disabled = false;
    btn.textContent = "Explain This Answer";
  }
}

/* ============================================================
   3. Generate New MCQs
============================================================ */

function generateMcqsTemplate() {
  return `
    <h2 style="margin-top:0;">Generate New MCQs</h2>
    <p style="color:#6b7280;margin-top:-6px;">Describe a topic and Gemini will draft brand-new multiple-choice questions.</p>

    <label for="gm-subject">Subject <span style="font-weight:400;color:#6b7280;">(optional)</span></label>
    <input type="text" id="gm-subject" placeholder="e.g. Computer Science">

    <label for="gm-topic">Topic</label>
    <input type="text" id="gm-topic" placeholder="e.g. Binary Search Trees">

    <div class="grid" style="grid-template-columns: 1fr 1fr;">
      <div>
        <label for="gm-difficulty">Difficulty</label>
        <select id="gm-difficulty">
          <option value="Easy">Easy</option>
          <option value="Medium" selected>Medium</option>
          <option value="Hard">Hard</option>
        </select>
      </div>
      <div>
        <label for="gm-count">Number of Questions</label>
        <input type="number" id="gm-count" min="1" max="20" value="5">
      </div>
    </div>

    <button type="button" class="btn btn-primary" id="gm-run-btn">Generate MCQs</button>
    <div class="ai-output-box" id="gm-output">Output will appear here once you run this action.</div>

    <div id="gm-results-section" style="display:none; margin-top:16px;">
      <h3>Generated Questions</h3>
      <div id="gm-mcq-list"></div>

      <button type="button" class="btn btn-secondary" id="gm-download-btn">Download as Text File</button>

      <h3 style="margin-top:20px;">Save to an Exam</h3>
      <label for="gm-save-exam-select">Exam (AI-Based Evaluation only)</label>
      <select id="gm-save-exam-select"><option value="">Loading exams...</option></select>
      <button type="button" class="btn btn-success" id="gm-save-btn">Save These Questions</button>
      <div class="alert" id="gm-save-alert"></div>
    </div>
  `;
}

async function runGenerateMcqs() {
  const subject = document.getElementById("gm-subject").value.trim();
  const topic = document.getElementById("gm-topic").value.trim();
  const difficulty = document.getElementById("gm-difficulty").value;
  const count = parseInt(document.getElementById("gm-count").value, 10) || 5;
  const output = document.getElementById("gm-output");
  const btn = document.getElementById("gm-run-btn");

  if (!topic) {
    output.textContent = "Please enter a topic first.";
    return;
  }

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Generating questions with Gemini AI...';
  output.textContent = "";
  document.getElementById("gm-results-section").style.display = "none";

  try {
    const data = await apiRequest("/ai-assistant/generate-mcqs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ subject: subject || null, topic, difficulty, count }),
    });
    lastGeneratedMCQs = data.mcqs;
    output.textContent = data.message;
    renderGeneratedMcqs(data.mcqs);
    await populateExamSelect("gm-save-exam-select", { aiOnly: true });
  } catch (err) {
    output.textContent = err.message;
  } finally {
    btn.disabled = false;
    btn.textContent = "Generate MCQs";
  }
}

function renderGeneratedMcqs(mcqs) {
  const listEl = document.getElementById("gm-mcq-list");
  const sectionEl = document.getElementById("gm-results-section");
  if (!listEl || !sectionEl) return;

  let html = "";
  mcqs.forEach((mcq, index) => {
    html += `
      <div class="card" style="margin-bottom:10px;">
        <strong>Q${index + 1}. ${escapeHtml(mcq.question_text)}</strong>
        <ul style="margin:8px 0 0;padding-left:20px;">
          <li>A) ${escapeHtml(mcq.option_a)}</li>
          <li>B) ${escapeHtml(mcq.option_b)}</li>
          <li>C) ${escapeHtml(mcq.option_c)}</li>
          <li>D) ${escapeHtml(mcq.option_d)}</li>
        </ul>
        <p style="margin:8px 0 0;"><strong>Correct answer:</strong> ${mcq.correct_option}</p>
        ${mcq.explanation ? `<p style="margin:4px 0 0;color:#6b7280;">${escapeHtml(mcq.explanation)}</p>` : ""}
      </div>
    `;
  });
  listEl.innerHTML = html;
  sectionEl.style.display = "block";

  document.getElementById("gm-download-btn").onclick = () => downloadMcqsAsText(mcqs);
  document.getElementById("gm-save-btn").onclick = saveMcqsToExam;
}

function downloadMcqsAsText(mcqs) {
  let text = "Generated MCQs\n================\n\n";
  mcqs.forEach((mcq, index) => {
    text += `Q${index + 1}. ${mcq.question_text}\n`;
    text += `A) ${mcq.option_a}\nB) ${mcq.option_b}\nC) ${mcq.option_c}\nD) ${mcq.option_d}\n`;
    text += `Correct answer: ${mcq.correct_option}\n`;
    if (mcq.explanation) text += `Explanation: ${mcq.explanation}\n`;
    text += "\n";
  });

  const blob = new Blob([text], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "generated_mcqs.txt";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

async function saveMcqsToExam() {
  const examId = document.getElementById("gm-save-exam-select").value;
  const btn = document.getElementById("gm-save-btn");
  hideAlert("gm-save-alert");

  if (!examId) {
    showAlert("gm-save-alert", "Please select an exam to save these questions to.");
    return;
  }
  if (!lastGeneratedMCQs || !lastGeneratedMCQs.length) {
    showAlert("gm-save-alert", "No generated questions to save.");
    return;
  }

  btn.disabled = true;
  btn.textContent = "Saving...";

  try {
    const data = await apiRequest(`/ai-assistant/save-mcqs/${examId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mcqs: lastGeneratedMCQs }),
    });
    showAlert("gm-save-alert", data.message, "success");
  } catch (err) {
    showAlert("gm-save-alert", err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Save These Questions";
  }
}

/* ============================================================
   4. Analyze Results / Weak Topics / Strong Topics / Suggestions
   (share one exam+student picker and one cached Gemini call)
============================================================ */

const ANALYSIS_TITLES = {
  "analyze-results": {
    title: "Analyze Student Results",
    description: "Get an AI summary of this student's overall performance.",
  },
  "weak-topics": {
    title: "Identify Weak Topics",
    description: "See which topics/questions this student struggled with most.",
  },
  "strong-topics": {
    title: "Identify Strong Topics",
    description: "See which topics/questions this student answered well.",
  },
  "suggestions": {
    title: "Study Suggestions",
    description: "Get personalized improvement suggestions for this student.",
  },
};

function analysisTemplate() {
  const config = ANALYSIS_TITLES[activeAction];
  return `
    <h2 style="margin-top:0;">${config.title}</h2>
    <p style="color:#6b7280;margin-top:-6px;">${config.description}</p>

    <label for="an-exam-select">Exam</label>
    <select id="an-exam-select"><option value="">Loading exams...</option></select>

    <label for="an-student-select">Student</label>
    <select id="an-student-select"><option value="">-- Select an exam first --</option></select>

    <button type="button" class="btn btn-primary" id="an-run-btn">Run Analysis</button>
    <div class="ai-output-box" id="an-output">Output will appear here once you run this action.</div>
  `;
}

async function onAnalysisExamChange() {
  const examId = document.getElementById("an-exam-select").value;
  const studentSelect = document.getElementById("an-student-select");

  if (!examId) {
    studentSelect.innerHTML = '<option value="">-- Select an exam first --</option>';
    return;
  }

  studentSelect.innerHTML = '<option value="">Loading students...</option>';

  try {
    if (!studentsByExamCache[examId]) {
      const data = await apiRequest(`/previous-exams/${examId}/students`);
      studentsByExamCache[examId] = data.students;
    }
    const students = studentsByExamCache[examId];

    if (!students.length) {
      studentSelect.innerHTML = '<option value="">No evaluated students for this exam</option>';
      return;
    }

    let html = '<option value="">-- Select a student --</option>';
    students.forEach((s) => {
      const label = s.student_name || s.roll_number || `Sheet #${s.sheet_id}`;
      html += `<option value="${s.sheet_id}">${escapeHtml(label)}</option>`;
    });
    studentSelect.innerHTML = html;
  } catch (err) {
    studentSelect.innerHTML = `<option value="">Could not load students</option>`;
  }
}

async function runAnalysis() {
  const sheetId = document.getElementById("an-student-select").value;
  const output = document.getElementById("an-output");
  const btn = document.getElementById("an-run-btn");

  if (!sheetId) {
    output.textContent = "Please select an exam and a student first.";
    return;
  }

  // Reuse the cached analysis if we already ran it for this exact student.
  if (lastAnalysis && String(lastAnalysis.sheetId) === String(sheetId)) {
    renderAnalysisOutput();
    return;
  }

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Analyzing with Gemini AI...';
  output.textContent = "";

  try {
    const summaryData = await apiRequest(`/evaluation/${sheetId}`).catch(() =>
      apiRequest(`/evaluation/evaluate/${sheetId}`, { method: "POST" })
    );
    const analysisData = await apiRequest(`/evaluation/analyze/${sheetId}`, { method: "POST" });

    lastAnalysis = {
      sheetId,
      summary: summaryData.summary,
      studentName: summaryData.student_name,
      examName: summaryData.exam_name,
      strongTopics: analysisData.strong_topics,
      weakTopics: analysisData.weak_topics,
      suggestions: analysisData.suggestions,
    };
    renderAnalysisOutput();
  } catch (err) {
    output.textContent = err.message;
  } finally {
    btn.disabled = false;
    btn.textContent = "Run Analysis";
  }
}

function renderAnalysisOutput() {
  const output = document.getElementById("an-output");
  if (!output || !lastAnalysis) return;

  const { summary, studentName, examName, strongTopics, weakTopics, suggestions } = lastAnalysis;

  if (activeAction === "analyze-results") {
    output.innerHTML = `
      <strong>${escapeHtml(studentName || "Student")} — ${escapeHtml(examName)}</strong><br><br>
      Correct: ${summary.correct_count} &nbsp; Wrong: ${summary.wrong_count} &nbsp;
      Blank: ${summary.blank_count} &nbsp; Invalid: ${summary.invalid_count}<br>
      Final Marks: ${summary.final_marks} / ${summary.max_marks} (${summary.percentage}%)
    `;
  } else if (activeAction === "weak-topics") {
    output.innerHTML = weakTopics.length
      ? `<ul style="margin:0;padding-left:20px;">${weakTopics.map((t) => `<li>${escapeHtml(t)}</li>`).join("")}</ul>`
      : "No specific weak topics were identified.";
  } else if (activeAction === "strong-topics") {
    output.innerHTML = strongTopics.length
      ? `<ul style="margin:0;padding-left:20px;">${strongTopics.map((t) => `<li>${escapeHtml(t)}</li>`).join("")}</ul>`
      : "No specific strong topics were identified.";
  } else if (activeAction === "suggestions") {
    output.textContent = suggestions || "No suggestions were generated.";
  }
}
