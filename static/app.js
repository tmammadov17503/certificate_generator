const nameInput = document.querySelector("[data-name-input]");
const namePreview = document.querySelector("[data-name-preview]");
const claimForm = document.querySelector("[data-claim-form]");

if (nameInput && namePreview) {
  const placeholder = namePreview.dataset.placeholder || "Recipient Name";
  const syncPreview = () => {
    const value = nameInput.value.trim();
    namePreview.textContent = value || placeholder;
  };

  syncPreview();
  nameInput.addEventListener("input", syncPreview);
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
