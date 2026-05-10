function setupFilePicker() {
  const picker = document.querySelector("[data-file-picker]");
  if (!picker) return;

  const input = picker.querySelector("input[type=file]");
  const label = picker.querySelector("[data-file-name]");

  input.addEventListener("change", () => {
    label.textContent = input.files.length ? input.files[0].name : "支持普通二进制、.a、.lib 文件";
  });

  ["dragenter", "dragover"].forEach((eventName) => {
    picker.addEventListener(eventName, () => picker.classList.add("is-dragging"));
  });

  ["dragleave", "drop"].forEach((eventName) => {
    picker.addEventListener(eventName, () => picker.classList.remove("is-dragging"));
  });
}

function setupJobPolling() {
  const view = document.querySelector("[data-job-status-url]");
  if (!view) return;

  const statusUrl = view.dataset.jobStatusUrl;
  const statusLabel = view.querySelector("[data-status-label]");
  const message = view.querySelector("[data-message]");
  const progressText = view.querySelector("[data-progress-text]");
  const progressBar = view.querySelector("[data-progress-bar]");
  const errorBox = view.querySelector("[data-error]");
  const download = view.querySelector("[data-download]");

  async function refresh() {
    const response = await fetch(statusUrl, {
      headers: { Accept: "application/json" },
      credentials: "same-origin",
    });
    if (!response.ok) return;

    const data = await response.json();
    statusLabel.textContent = data.status_label;
    statusLabel.className = `status-chip status-${data.status}`;
    message.textContent = data.message || "";
    progressText.textContent = data.progress;
    progressBar.style.width = `${data.progress}%`;

    if (data.error) {
      errorBox.textContent = data.error;
      errorBox.classList.remove("is-hidden");
    }

    if (data.status === "success") {
      download.href = data.download_url;
      download.classList.remove("is-disabled");
      return;
    }

    if (data.status === "failed" || data.status === "cleaned") {
      return;
    }

    window.setTimeout(refresh, 1400);
  }

  refresh();
}

document.addEventListener("DOMContentLoaded", () => {
  setupFilePicker();
  setupJobPolling();
});
