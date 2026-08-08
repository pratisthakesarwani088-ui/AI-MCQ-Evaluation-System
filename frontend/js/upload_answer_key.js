/* ============================================================
   upload_answer_key.js
   Handles image preview and uploading the answer-key image to the
   backend for OCR extraction. On success, redirects to the
   "Verify Answer Key" page.
============================================================ */

document.addEventListener("DOMContentLoaded", () => {
  const examId = getCurrentExamId();

  if (!examId) {
    document.getElementById("no-exam-warning").style.display = "block";
    document.getElementById("upload-card").style.display = "none";
    return;
  }

  const fileInput = document.getElementById("answer_key_file");
  const previewImage = document.getElementById("preview-image");
  const form = document.getElementById("upload-form");
  const uploadBtn = document.getElementById("upload-btn");

  // Show a live preview of the chosen image before uploading.
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

    uploadBtn.disabled = true;
    uploadBtn.innerHTML = '<span class="spinner"></span> Extracting text from image (this may take a few seconds)...';

    try {
      const data = await apiRequest(`/answer-key/upload/${examId}`, {
        method: "POST",
        body: formData, // No Content-Type header: browser sets the multipart boundary automatically.
      });

      showAlert("form-alert", `${data.message} Redirecting to verify the extracted answers...`, "success");

      setTimeout(() => {
        window.location.href = "/verify-answer-key";
      }, 1500);
    } catch (err) {
      showAlert("form-alert", err.message);
    } finally {
      uploadBtn.disabled = false;
      uploadBtn.textContent = "Upload & Extract Answer Key";
    }
  });
});
