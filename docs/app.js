const TEMPLATE_WIDTH = 1999;
const TEMPLATE_HEIGHT = 1545;
const NAME_BOX = { left: 472, top: 600, right: 1532, bottom: 710 };
const NAME_COLOR = "rgb(0, 100, 158)";

const form = document.querySelector("#certificate-form");
const nameInput = document.querySelector("#recipient-name");
const namePreview = document.querySelector("#name-preview");
const templateImage = document.querySelector("#certificate-template");
const message = document.querySelector("#form-message");
const downloadButton = document.querySelector("#download-button");

function normalizeName(rawValue) {
  const name = rawValue.trim().replace(/\s+/g, " ");
  if (name.length < 2) {
    throw new Error("Please enter at least two characters for the recipient name.");
  }
  if (name.length > 80) {
    throw new Error("Please keep the recipient name under 80 characters.");
  }
  if (!/[\p{L}]/u.test(name) || /[^\p{L}\s.,'-]/u.test(name)) {
    throw new Error("Use letters, spaces, hyphens, apostrophes, commas, or periods only.");
  }
  return name;
}

function setPreview() {
  namePreview.textContent = nameInput.value.trim().replace(/\s+/g, " ") || "Recipient Name";
}

function chooseFontSize(context, name) {
  const availableWidth = NAME_BOX.right - NAME_BOX.left - 30;
  for (let size = 92; size >= 40; size -= 1) {
    context.font = `${size}px "Noto Sans Local", sans-serif`;
    if (context.measureText(name).width <= availableWidth) {
      return size;
    }
  }
  return 40;
}

function fileSlug(name) {
  return name.normalize("NFKD").replace(/[^\w]+/g, "-").replace(/^-|-$/g, "").toLowerCase() || "recipient";
}

async function createPdf(name) {
  await document.fonts.ready;
  const canvas = document.createElement("canvas");
  canvas.width = TEMPLATE_WIDTH;
  canvas.height = TEMPLATE_HEIGHT;
  const context = canvas.getContext("2d");
  context.drawImage(templateImage, 0, 0, TEMPLATE_WIDTH, TEMPLATE_HEIGHT);
  const fontSize = chooseFontSize(context, name);
  context.fillStyle = NAME_COLOR;
  context.textAlign = "center";
  context.textBaseline = "middle";
  context.font = `${fontSize}px "Noto Sans Local", sans-serif`;
  context.fillText(name, TEMPLATE_WIDTH / 2, (NAME_BOX.top + NAME_BOX.bottom) / 2);

  const { jsPDF } = window.jspdf;
  const pdf = new jsPDF({
    orientation: "landscape",
    unit: "px",
    format: [TEMPLATE_WIDTH, TEMPLATE_HEIGHT],
    hotfixes: ["px_scaling"],
    compress: true,
  });
  pdf.addImage(canvas.toDataURL("image/png"), "PNG", 0, 0, TEMPLATE_WIDTH, TEMPLATE_HEIGHT, undefined, "FAST");
  pdf.save(`IEEE-Certificate-of-Appreciation-${fileSlug(name)}.pdf`);
}

nameInput.addEventListener("input", setPreview);

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  message.textContent = "";
  let name;
  try {
    name = normalizeName(nameInput.value);
  } catch (error) {
    message.textContent = error.message;
    return;
  }
  if (!window.jspdf || !templateImage.complete) {
    message.textContent = "The certificate is still loading. Please try again in a moment.";
    return;
  }
  downloadButton.disabled = true;
  downloadButton.textContent = "Preparing PDF...";
  try {
    await createPdf(name);
  } catch (error) {
    message.textContent = "The PDF could not be created. Please refresh the page and try again.";
    console.error(error);
  } finally {
    downloadButton.disabled = false;
    downloadButton.textContent = "Download PDF";
  }
});
