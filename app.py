from __future__ import annotations

import io
import os
import re
import unicodedata
from pathlib import Path
from typing import Any

from flask import Flask, current_app, redirect, render_template, request, send_file
from PIL import Image, ImageDraw, ImageFont


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_TEMPLATE_IMAGE = BASE_DIR / "static" / "certificate-template.png"
DEFAULT_BUNDLED_FONT = BASE_DIR / "static" / "fonts" / "NotoSans-Regular.ttf"

NAME_BOX = (472, 592, 1532, 688)
NAME_COLOR = (0, 100, 158)
MAX_FONT_SIZE = 92
MIN_FONT_SIZE = 40
FONT_CANDIDATES = [
    os.environ.get("CERTIFICATE_FONT_PATH", "").strip(),
    str(DEFAULT_BUNDLED_FONT),
    r"C:\Windows\Fonts\calibri.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    "/usr/share/fonts/truetype/msttcorefonts/Calibri.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def normalize_name(raw_name: str) -> str:
    name = collapse_whitespace(raw_name)
    if len(name) < 2:
        raise ValueError("Please enter at least two characters for the recipient name.")
    if len(name) > 80:
        raise ValueError("Please keep the recipient name under 80 characters.")
    if not any(char.isalpha() for char in name):
        raise ValueError("The recipient name must contain letters.")

    allowed_punctuation = {" ", "-", "'", ".", ","}
    invalid = [
        char
        for char in name
        if not (char.isalpha() or char in allowed_punctuation)
    ]
    if invalid:
        raise ValueError("Use letters, spaces, hyphens, apostrophes, commas, or periods only.")

    return name


def slugify_filename(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", normalized).strip("-").lower()
    return slug or "recipient"


def resolve_font_path() -> str | None:
    for candidate in FONT_CANDIDATES:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    app = Flask(__name__)
    app.config.update(
        TEMPLATE_IMAGE=str(DEFAULT_TEMPLATE_IMAGE),
        FONT_PATH=resolve_font_path(),
        PDF_RESOLUTION=200.0,
    )

    if test_config:
        app.config.update(test_config)

    @app.context_processor
    def inject_template_helpers() -> dict[str, Any]:
        return {
            "name_box_style": build_name_box_style(),
        }

    @app.route("/", methods=["GET", "POST"])
    @app.route("/claim", methods=["GET", "POST"])
    def claim_page():
        current_name = "Recipient Name"
        error_message: str | None = None

        if request.method == "POST":
            raw_name = request.form.get("name", "")
            current_name = collapse_whitespace(raw_name) or "Recipient Name"

            try:
                recipient_name = normalize_name(raw_name)
            except ValueError as exc:
                return render_template(
                    "claim.html",
                    page_title="Claim Certificate",
                    current_name=current_name,
                    error_message=str(exc),
                ), 400

            pdf_bytes = build_certificate_pdf(recipient_name)
            download_name = f"AI-In-Action-Certificate-{slugify_filename(recipient_name)}.pdf"
            return send_file(
                io.BytesIO(pdf_bytes),
                mimetype="application/pdf",
                as_attachment=True,
                download_name=download_name,
            )

        return render_template(
            "claim.html",
            page_title="Claim Certificate",
            current_name=current_name,
            error_message=error_message,
        )

    @app.get("/admin")
    @app.get("/admin/login")
    @app.get("/admin/codes.csv")
    def legacy_admin_redirect():
        return redirect("/")

    @app.post("/admin/logout")
    def legacy_admin_logout():
        return redirect("/")

    @app.get("/healthz")
    def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    @app.errorhandler(404)
    def handle_not_found(_error: Exception):
        return render_template(
            "error.html",
            page_title="Page Not Found",
            title="This page does not exist",
            message="Check the address and try again, or open the certificate page and enter the recipient name there.",
        ), 404

    return app


def build_name_box_style() -> str:
    template_path = Path(current_app.config["TEMPLATE_IMAGE"])
    with Image.open(template_path) as image:
        width, height = image.size

    left, top, right, bottom = NAME_BOX
    values = {
        "left": left / width * 100,
        "top": top / height * 100,
        "width": (right - left) / width * 100,
        "height": (bottom - top) / height * 100,
    }
    return "; ".join(
        [
            f"--name-left:{values['left']:.3f}%",
            f"--name-top:{values['top']:.3f}%",
            f"--name-width:{values['width']:.3f}%",
            f"--name-height:{values['height']:.3f}%",
        ]
    )


def build_certificate_pdf(recipient_name: str) -> bytes:
    template_path = Path(current_app.config["TEMPLATE_IMAGE"])
    if not template_path.exists():
        raise FileNotFoundError(f"Certificate template not found: {template_path}")

    with Image.open(template_path) as template_image:
        image = template_image.convert("RGB")

    draw = ImageDraw.Draw(image)
    font = fit_text_font(draw, recipient_name, current_app.config["FONT_PATH"], NAME_BOX)
    text_box = draw.textbbox((0, 0), recipient_name, font=font)
    text_width = text_box[2] - text_box[0]
    text_height = text_box[3] - text_box[1]

    left, top, right, bottom = NAME_BOX
    x = left + ((right - left) - text_width) / 2 - text_box[0]
    y = top + ((bottom - top) - text_height) / 2 - text_box[1] - 2
    draw.text((x, y), recipient_name, fill=NAME_COLOR, font=font)

    buffer = io.BytesIO()
    image.save(buffer, format="PDF", resolution=current_app.config["PDF_RESOLUTION"])
    return buffer.getvalue()


def fit_text_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_path: str | None,
    box: tuple[int, int, int, int],
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    max_width = box[2] - box[0]
    max_height = box[3] - box[1]

    for font_size in range(MAX_FONT_SIZE, MIN_FONT_SIZE - 1, -1):
        font = load_font(font_path, font_size)
        text_box = draw.textbbox((0, 0), text, font=font)
        text_width = text_box[2] - text_box[0]
        text_height = text_box[3] - text_box[1]
        if text_width <= max_width and text_height <= max_height:
            return font

    return load_font(font_path, MIN_FONT_SIZE)


def load_font(font_path: str | None, font_size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if font_path:
        try:
            return ImageFont.truetype(font_path, font_size)
        except OSError:
            pass
    return ImageFont.load_default()


app = create_app()


if __name__ == "__main__":
    host = os.environ.get("CERTIFICATE_HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", os.environ.get("CERTIFICATE_PORT", "5050")))
    app.run(host=host, port=port, debug=False)
