const nameInput = document.querySelector("[data-name-input]");
const namePreview = document.querySelector("[data-name-preview]");
const claimForm = document.querySelector("[data-claim-form]");
const codeInput = document.querySelector("[data-code-input]");

if (nameInput && namePreview) {
  const placeholder = namePreview.dataset.placeholder || "Recipient Name";
  const syncPreview = () => {
    const value = nameInput.value.trim();
    namePreview.textContent = value || placeholder;
  };

  syncPreview();
  nameInput.addEventListener("input", syncPreview);
}

if (codeInput) {
  const syncCode = () => {
    const clean = codeInput.value.replace(/[^a-zA-Z0-9]/g, "").toUpperCase().slice(0, 8);
    const groups = clean.match(/.{1,4}/g) || [];
    codeInput.value = groups.join("-");
  };

  syncCode();
  codeInput.addEventListener("input", syncCode);
}

if (claimForm) {
  claimForm.addEventListener("submit", () => {
    const button = claimForm.querySelector("button[type='submit']");
    if (!button) {
      return;
    }
    button.disabled = true;
    button.textContent = button.dataset.submitLabel || "Preparing...";
  });
}

document.querySelectorAll("[data-copy-target]").forEach((button) => {
  button.addEventListener("click", async () => {
    const value = button.dataset.copyTarget;
    if (!value) {
      return;
    }

    const originalLabel = button.dataset.originalLabel || button.textContent;
    button.dataset.originalLabel = originalLabel;

    try {
      await navigator.clipboard.writeText(value);
      button.textContent = "Copied";
      window.setTimeout(() => {
        button.textContent = originalLabel;
      }, 1400);
    } catch (_error) {
      button.textContent = "Copy failed";
      window.setTimeout(() => {
        button.textContent = originalLabel;
      }, 1400);
    }
  });
});
