from __future__ import annotations

import csv
import io
import os
import re
import secrets
import sqlite3
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import (
    Flask,
    Response,
    current_app,
    g,
    has_request_context,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from PIL import Image, ImageDraw, ImageFont


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_TEMPLATE_IMAGE = BASE_DIR / "static" / "certificate-template.png"

NAME_BOX = (472, 592, 1532, 688)
NAME_COLOR = (0, 100, 158)
MAX_FONT_SIZE = 92
MIN_FONT_SIZE = 40
CLAIM_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
FONT_CANDIDATES = [
    os.environ.get("CERTIFICATE_FONT_PATH", "").strip(),
    r"C:\Windows\Fonts\calibri.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    "/usr/share/fonts/truetype/msttcorefonts/Calibri.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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


def normalize_label(raw_label: str) -> str:
    return collapse_whitespace(raw_label)[:120]


def normalize_code_input(raw_code: str) -> str:
    code = re.sub(r"[^A-Za-z0-9]", "", raw_code or "").upper()
    if not code:
        raise ValueError("Enter your one-time code.")
    expected_length = int(current_app.config["CLAIM_CODE_LENGTH"])
    if len(code) != expected_length:
        raise ValueError(f"Enter the full {expected_length}-character code.")
    return code


def format_code_for_display(code: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9]", "", code or "").upper()
    return "-".join(clean[index:index + 4] for index in range(0, len(clean), 4))


def slugify_filename(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", normalized).strip("-").lower()
    return slug or "recipient"


def resolve_font_path() -> str | None:
    for candidate in FONT_CANDIDATES:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def format_timestamp(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return value
    return parsed.astimezone().strftime("%Y-%m-%d %H:%M %Z")


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    data_dir = Path(os.environ.get("CERTIFICATE_DATA_DIR", str(BASE_DIR / "instance")))
    default_db_path = data_dir / "certificates.db"
    default_output_dir = data_dir / "output"

    app = Flask(__name__, instance_path=str(BASE_DIR / "instance"))
    app.config.update(
        SECRET_KEY=os.environ.get("CERTIFICATE_APP_SECRET", "certificate-claim-app"),
        DATABASE=str(default_db_path),
        OUTPUT_DIR=str(default_output_dir),
        TEMPLATE_IMAGE=str(DEFAULT_TEMPLATE_IMAGE),
        FONT_PATH=resolve_font_path(),
        BASE_URL=os.environ.get("CERTIFICATE_BASE_URL", "").rstrip("/"),
        ADMIN_PASSWORD=os.environ.get("CERTIFICATE_ADMIN_PASSWORD", ""),
        MAX_CREATE_QUANTITY=500,
        CLAIM_CODE_LENGTH=8,
        PDF_RESOLUTION=200.0,
    )

    if test_config:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    Path(app.config["OUTPUT_DIR"]).mkdir(parents=True, exist_ok=True)

    with app.app_context():
        init_db()

    @app.teardown_appcontext
    def close_db(_error: BaseException | None) -> None:
        db = g.pop("db", None)
        if db is not None:
            db.close()

    @app.context_processor
    def inject_template_helpers() -> dict[str, Any]:
        return {
            "name_box_style": build_name_box_style(),
        }

    @app.route("/", methods=["GET", "POST"])
    @app.route("/claim", methods=["GET", "POST"])
    def claim_page():
        current_name = "Recipient Name"
        current_code = ""
        error_message: str | None = None
        code_details: dict[str, Any] | None = None

        if request.method == "POST":
            raw_code = request.form.get("code", "")
            raw_name = request.form.get("name", "")
            current_name = collapse_whitespace(raw_name) or "Recipient Name"
            current_code = format_code_for_display(raw_code)

            try:
                code = normalize_code_input(raw_code)
            except ValueError as exc:
                error_message = str(exc)
                return render_template(
                    "claim.html",
                    page_title="Claim Certificate",
                    public_claim_url=build_public_claim_url(),
                    current_name=current_name,
                    current_code=current_code,
                    error_message=error_message,
                    code_details=None,
                ), 400

            code_row = get_code(code)
            if code_row is None:
                error_message = "This code is invalid. Check it and try again."
                return render_template(
                    "claim.html",
                    page_title="Claim Certificate",
                    public_claim_url=build_public_claim_url(),
                    current_name=current_name,
                    current_code=current_code,
                    error_message=error_message,
                    code_details=None,
                ), 400

            code_details = serialize_code(code_row)
            if code_row["used_at"]:
                return render_template(
                    "used.html",
                    page_title="Code Already Used",
                    code=code_details,
                ), 410

            try:
                recipient_name = normalize_name(raw_name)
            except ValueError as exc:
                return render_template(
                    "claim.html",
                    page_title="Claim Certificate",
                    public_claim_url=build_public_claim_url(),
                    current_name=current_name,
                    current_code=current_code,
                    error_message=str(exc),
                    code_details=code_details,
                ), 400

            pdf_bytes = build_certificate_pdf(recipient_name)
            used_at = utc_now_iso()
            output_filename = f"{code.lower()}-{slugify_filename(recipient_name)}.pdf"
            updated = mark_code_used(
                code=code,
                recipient_name=recipient_name,
                used_at=used_at,
                used_ip=request.headers.get("X-Forwarded-For", request.remote_addr or ""),
                user_agent=request.user_agent.string or "",
                output_filename=output_filename,
            )
            if not updated:
                latest_code = get_code(code)
                return render_template(
                    "used.html",
                    page_title="Code Already Used",
                    code=serialize_code(latest_code) if latest_code else None,
                ), 410

            archive_certificate(output_filename, pdf_bytes)
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
            public_claim_url=build_public_claim_url(),
            current_name=current_name,
            current_code=current_code,
            error_message=error_message,
            code_details=code_details,
        )

    @app.route("/admin", methods=["GET", "POST"])
    def admin_dashboard() -> str:
        if not is_admin_authenticated():
            return redirect(url_for("admin_login"))

        generated_codes: list[sqlite3.Row] = []
        form_error: str | None = None

        if request.method == "POST":
            try:
                quantity = parse_quantity(
                    request.form.get("quantity", "1"),
                    current_app.config["MAX_CREATE_QUANTITY"],
                )
                label = normalize_label(request.form.get("label", ""))
                generated_codes = create_codes(quantity, label)
            except ValueError as exc:
                form_error = str(exc)

        codes = [serialize_code(row) for row in list_codes()]
        generated = [serialize_code(row) for row in generated_codes]
        return render_template(
            "dashboard.html",
            page_title="Certificate Code Studio",
            codes=codes,
            generated_codes=generated,
            form_error=form_error,
            public_claim_url=build_public_claim_url(),
            summary=count_codes(),
        )

    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login() -> str:
        if not admin_auth_enabled():
            return redirect(url_for("admin_dashboard"))
        if session.get("admin_authenticated"):
            return redirect(url_for("admin_dashboard"))

        error_message: str | None = None
        if request.method == "POST":
            password = request.form.get("password", "")
            if password == current_app.config["ADMIN_PASSWORD"]:
                session["admin_authenticated"] = True
                return redirect(url_for("admin_dashboard"))
            error_message = "Incorrect admin password."

        return render_template(
            "login.html",
            page_title="Admin Login",
            error_message=error_message,
        )

    @app.post("/admin/logout")
    def admin_logout():
        session.pop("admin_authenticated", None)
        return redirect(url_for("admin_login"))

    @app.get("/admin/codes.csv")
    def export_codes_csv() -> Response:
        if not is_admin_authenticated():
            return redirect(url_for("admin_login"))

        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(["Code", "Label", "Status", "Used Name", "Created At", "Used At", "Public Claim URL"])
        for row in list_codes():
            code = serialize_code(row)
            writer.writerow(
                [
                    code["display_code"],
                    code["label"],
                    code["status_label"],
                    code["used_name"] or "",
                    code["created_at"],
                    code["used_at"] or "",
                    build_public_claim_url(),
                ]
            )

        return Response(
            stream.getvalue(),
            mimetype="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=certificate-codes.csv"
            },
        )

    @app.get("/healthz")
    def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    @app.errorhandler(404)
    def handle_not_found(_error: Exception):
        return render_template(
            "error.html",
            page_title="Page Not Found",
            title="This page does not exist",
            message="Check the address and try again, or use the shared certificate page link from the organizer.",
        ), 404

    return app


def parse_quantity(raw_value: str, max_value: int) -> int:
    try:
        quantity = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Quantity must be a whole number.") from exc
    if quantity < 1:
        raise ValueError("Create at least one code.")
    if quantity > max_value:
        raise ValueError(f"Create no more than {max_value} codes at once.")
    return quantity


def admin_auth_enabled() -> bool:
    return bool(current_app.config.get("ADMIN_PASSWORD"))


def is_admin_authenticated() -> bool:
    if not admin_auth_enabled():
        return True
    return bool(session.get("admin_authenticated"))


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


def build_public_claim_url() -> str:
    configured = current_app.config.get("BASE_URL", "")
    if configured:
        return configured
    if has_request_context():
        return request.url_root.rstrip("/")
    return ""


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        connection = sqlite3.connect(current_app.config["DATABASE"])
        connection.row_factory = sqlite3.Row
        g.db = connection
    return g.db


def init_db() -> None:
    db = get_db()
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS claim_codes (
            code TEXT PRIMARY KEY,
            label TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            used_at TEXT,
            used_name TEXT,
            used_ip TEXT,
            used_user_agent TEXT,
            output_filename TEXT
        )
        """
    )
    db.commit()


def create_codes(quantity: int, label: str) -> list[sqlite3.Row]:
    db = get_db()
    created_codes: list[sqlite3.Row] = []
    code_length = int(current_app.config["CLAIM_CODE_LENGTH"])

    for _ in range(quantity):
        created_at = utc_now_iso()
        while True:
            code = "".join(secrets.choice(CLAIM_CODE_ALPHABET) for _ in range(code_length))
            try:
                db.execute(
                    "INSERT INTO claim_codes (code, label, created_at) VALUES (?, ?, ?)",
                    (code, label, created_at),
                )
                created_codes.append(
                    db.execute("SELECT * FROM claim_codes WHERE code = ?", (code,)).fetchone()
                )
                break
            except sqlite3.IntegrityError:
                continue

    db.commit()
    return created_codes


def list_codes() -> list[sqlite3.Row]:
    db = get_db()
    return db.execute(
        """
        SELECT code, label, created_at, used_at, used_name, output_filename
        FROM claim_codes
        ORDER BY datetime(created_at) DESC, code DESC
        """
    ).fetchall()


def count_codes() -> dict[str, int]:
    db = get_db()
    row = db.execute(
        """
        SELECT
            COUNT(*) AS total_count,
            SUM(CASE WHEN used_at IS NULL THEN 1 ELSE 0 END) AS unused_count,
            SUM(CASE WHEN used_at IS NOT NULL THEN 1 ELSE 0 END) AS used_count
        FROM claim_codes
        """
    ).fetchone()
    total = int(row["total_count"] or 0)
    unused = int(row["unused_count"] or 0)
    used = int(row["used_count"] or 0)
    return {
        "total": total,
        "unused": unused,
        "used": used,
    }


def get_code(code: str) -> sqlite3.Row | None:
    db = get_db()
    return db.execute(
        """
        SELECT code, label, created_at, used_at, used_name, output_filename
        FROM claim_codes
        WHERE code = ?
        """,
        (code,),
    ).fetchone()


def mark_code_used(
    *,
    code: str,
    recipient_name: str,
    used_at: str,
    used_ip: str,
    user_agent: str,
    output_filename: str,
) -> bool:
    db = get_db()
    cursor = db.execute(
        """
        UPDATE claim_codes
        SET used_at = ?, used_name = ?, used_ip = ?, used_user_agent = ?, output_filename = ?
        WHERE code = ? AND used_at IS NULL
        """,
        (used_at, recipient_name, used_ip, user_agent, output_filename, code),
    )
    db.commit()
    return cursor.rowcount == 1


def serialize_code(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    used = bool(row["used_at"])
    return {
        "code": row["code"],
        "display_code": format_code_for_display(row["code"]),
        "label": row["label"],
        "created_at": row["created_at"],
        "created_at_display": format_timestamp(row["created_at"]),
        "used_at": row["used_at"],
        "used_at_display": format_timestamp(row["used_at"]),
        "used_name": row["used_name"],
        "output_filename": row["output_filename"],
        "status_label": "Used" if used else "Unused",
        "status_class": "claimed" if used else "unused",
    }


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


def archive_certificate(output_filename: str, pdf_bytes: bytes) -> None:
    output_dir = Path(current_app.config["OUTPUT_DIR"])
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        (output_dir / output_filename).write_bytes(pdf_bytes)
    except OSError:
        return


app = create_app()


if __name__ == "__main__":
    host = os.environ.get("CERTIFICATE_HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", os.environ.get("CERTIFICATE_PORT", "5050")))
    app.run(host=host, port=port, debug=False)
