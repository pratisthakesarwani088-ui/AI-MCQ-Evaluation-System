/* ============================================================
   upload_student_sheet.js
   Handles uploading a single student's answer sheet image (with
   optional name/roll number), automatically running detection +
   OMR/Normal-MCQ processing on it, and listing sheets already
   uploaded for the current exam (with a way to jump straight to
   their result).
============================================================ */

document.addEventListener("DOMContentLoaded", () => {
  const examId = getCurrentExamId();

  if (!examId) {
    document.getElementById("no-exam-warning").style.display = "block";
    document.getElementById("upload-card").style.display = "none";
    document.getElementById("sheets-list").innerHTML = "";
    return;
  }

  const fileInput = document.getElementById("student_sheet_file");
  const previewImage = document.getElementById("preview-image");
  const form = document.getElementById("upload-form");
  const uploadBtn = document.getElementById("upload-btn");

  fileInput.addEventListener("change", () => {
    const file = fileInput.files[0];
    if (!file) {
      previewImage.style.display = "none";
      return;
    }
    const reader = new FileReader();
    reader.onload = (e) => {
      previewImage.src = e.target.result;
      previewImage.style.display = "block";
    };
    reader.readAsDataURL(file);
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    hideAlert("form-alert");

    const file = fileInput.files[0];
    if (!file) {
      showAlert("form-alert", "Please choose an image file first.");
      return;
    }

    const validExtensions = [".jpg", ".jpeg", ".png"];
    const lowerName = file.name.toLowerCase();
    if (!validExtensions.some((ext) => lowerName.endsWith(ext))) {
      showAlert("form-alert", "Unsupported file type. Only JPG, JPEG, and PNG images are allowed.");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);
    formData.append("student_name", document.getElementById("student_name").value.trim());
    formData.append("roll_number", document.getElementById("roll_number").value.trim());

    uploadBtn.disabled = true;
    uploadBtn.innerHTML = '<span class="spinner"></span> Uploading...';

    try {
      const uploadData = await apiRequest(`/student-sheet/upload/${examId}`, {
        method: "POST",
        body: formData,
      });

      const sheetId = uploadData.sheet.sheet_id;
      setCurrentSheetId(sheetId);

      uploadBtn.innerHTML = '<span class="spinner"></span> Detecting sheet type & reading answers...';
      const processData = await apiRequest(`/student-sheet/process/${sheetId}`, { method: "POST" });

      showAlert(
        "form-alert",
        `${uploadData.message} ${processData.message} Click "View Result" below to evaluate and see the marks.`,
        "success"
      );
      form.reset();
      previewImage.style.display = "none";

      await loadSheets(examId);
    } catch (err) {
      showAlert("form-alert", err.message);
    } finally {
      uploadBtn.disabled = false;
      uploadBtn.textContent = "Upload Student Sheet";
    }
  });

  loadSheets(examId);
});

/**
 * Loads and renders all student sheets uploaded so far for the
 * current exam, each with a "View Result" button.
 */
async function loadSheets(examId) {
  const container = document.getElementById("sheets-list");
  try {
    const data = await apiRequest(`/student-sheet/exam/${examId}`);

    if (!data.sheets.length) {
      container.innerHTML = '<p class="empty-state">No student sheets uploaded yet for this exam.</p>';
      return;
    }

    let html = `
      <table>
        <thead>
          <tr>
            <th>Student</th>
            <th>Roll No.</th>
            <th>Sheet Type</th>
            <th>Uploaded</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
    `;

    data.sheets.forEach((sheet) => {
      const uploadedDate = new Date(sheet.uploaded_at).toLocaleString();
      html += `
        <tr>
          <td>${escapeHtml(sheet.student_name || "—")}</td>
          <td>${escapeHtml(sheet.roll_number || "—")}</td>
          <td><span class="badge badge-blank">${sheet.sheet_type}</span></td>
          <td>${uploadedDate}</td>
          <td><button class="btn btn-secondary" style="margin-top:0;" onclick="viewResult(${sheet.sheet_id})">View Result</button></td>
        </tr>
      `;
    });

    html += "</tbody></table>";
    container.innerHTML = html;
  } catch (err) {
    container.innerHTML = `<p class="empty-state">Could not load sheets: ${escapeHtml(err.message)}</p>`;
  }
}

/**
 * Selects a sheet and takes the teacher to its result page. If the
 * sheet was uploaded but never processed, the result page will
 * automatically trigger evaluation (which itself requires
 * processing) -- to keep this simple, we also (re)run processing
 * here before navigating, so the result page always has responses
 * ready to evaluate.
 */
async function viewResult(sheetId) {
  setCurrentSheetId(sheetId);
  try {
    await apiRequest(`/student-sheet/process/${sheetId}`, { method: "POST" });
  } catch (err) {
    // If processing fails (e.g. unreadable image), still navigate --
    // the result page will show a clear error message explaining why.
  }
  window.location.href = "/result";
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}
