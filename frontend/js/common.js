/* ============================================================
   common.js
   Shared helper functions used by every page's JavaScript file.
   Kept dependency-free (no frameworks) per project requirements.
============================================================ */

// Base URL for the API. Since the frontend is served by the same
// FastAPI app, a relative path works perfectly.
const API_BASE = "/api";

/**
 * Shows a message box (success / error / info) inside the given
 * element id. Automatically un-hides it and applies the right
 * color style.
 */
function showAlert(elementId, message, type = "error") {
  const el = document.getElementById(elementId);
  if (!el) return;
  el.textContent = message;
  el.className = `alert show alert-${type}`;
}

/**
 * Hides a previously shown alert box.
 */
function hideAlert(elementId) {
  const el = document.getElementById(elementId);
  if (!el) return;
  el.className = "alert";
}

/**
 * Wrapper around fetch() that:
 *  - Prefixes the API base URL
 *  - Parses the JSON response
 *  - Throws a readable Error with the backend's error message if
 *    the request failed, so callers can just use try/catch.
 */
async function apiRequest(path, options = {}) {
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, options);
  } catch (networkError) {
    throw new Error(
      "Could not reach the server. Please make sure the backend is running."
    );
  }

  let data;
  try {
    data = await response.json();
  } catch (parseError) {
    throw new Error("Unexpected response from the server.");
  }

  if (!response.ok || data.success === false) {
    throw new Error(data.message || data.detail || "Something went wrong.");
  }

  return data;
}

/**
 * Reads the exam_id stored in the browser session (set when the
 * teacher creates or selects an exam) so later pages know which
 * exam they are working with.
 */
function getCurrentExamId() {
  return sessionStorage.getItem("current_exam_id");
}

function setCurrentExamId(examId) {
  sessionStorage.setItem("current_exam_id", examId);
}

/**
 * Remembers which pipeline (AI or OMR) the currently selected exam
 * uses, so pages can show/hide the right steps without an extra
 * API call.
 */
function getCurrentExamType() {
  return sessionStorage.getItem("current_exam_type");
}

function setCurrentExamType(examType) {
  sessionStorage.setItem("current_exam_type", examType);
}

/**
 * Same idea as the exam_id helpers above, but for the student
 * sheet currently being processed / evaluated / viewed.
 */
function getCurrentSheetId() {
  return sessionStorage.getItem("current_sheet_id");
}

function setCurrentSheetId(sheetId) {
  sessionStorage.setItem("current_sheet_id", sheetId);
}

/**
 * Highlights the active nav link based on the current page path.
 * Called from every page's inline script.
 */
function highlightActiveNav() {
  const path = window.location.pathname;
  document.querySelectorAll(".navbar nav a").forEach((link) => {
    if (link.getAttribute("href") === path) {
      link.classList.add("active");
    }
  });
}

document.addEventListener("DOMContentLoaded", highlightActiveNav);
