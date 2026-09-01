from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "assets" / "branding-source.png"
OUTPUT_PATH = ROOT / "static" / "certificate-template.png"
NOTO_FONT = ROOT / "static" / "fonts" / "NotoSans-Regular.ttf"

WIDTH = 1999
HEIGHT = 1545

NAVY = "#073B5C"
INK = "#183142"
TEAL = "#007F9D"
SKY = "#2CA8CC"
GOLD = "#C89B4B"
PAPER = "#FFFEFA"
MIST = "#F1F8F8"


def font(path: str | Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size)


def center_text(draw: ImageDraw.ImageDraw, y: int, text: str, text_font: ImageFont.ImageFont, fill: str) -> None:
    box = draw.textbbox((0, 0), text, font=text_font)
    width = box[2] - box[0]
    draw.text(((WIDTH - width) / 2 - box[0], y - box[1]), text, font=text_font, fill=fill)


def text_centered_at(
    draw: ImageDraw.ImageDraw,
    center_x: int,
    y: int,
    text: str,
    text_font: ImageFont.ImageFont,
    fill: str,
) -> None:
    box = draw.textbbox((0, 0), text, font=text_font)
    draw.text((center_x - (box[2] - box[0]) / 2 - box[0], y - box[1]), text, font=text_font, fill=fill)


def wrapped_center_text(
    draw: ImageDraw.ImageDraw,
    y: int,
    text: str,
    text_font: ImageFont.ImageFont,
    fill: str,
    max_width: int,
    line_gap: int,
) -> int:
    words = text.split()
    lines: list[str] = []
    line = ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if draw.textbbox((0, 0), candidate, font=text_font)[2] <= max_width or not line:
            line = candidate
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)

    current_y = y
    for line in lines:
        center_text(draw, current_y, line, text_font, fill)
        bounds = draw.textbbox((0, 0), line, font=text_font)
        current_y += (bounds[3] - bounds[1]) + line_gap
    return current_y


def non_white_crop(source: Image.Image, crop_box: tuple[int, int, int, int], threshold: int = 238) -> Image.Image:
    crop = source.crop(crop_box).convert("RGBA")
    pixels = crop.load()
    for y in range(crop.height):
        for x in range(crop.width):
            red, green, blue, alpha = pixels[x, y]
            if red >= threshold and green >= threshold and blue >= threshold:
                pixels[x, y] = (red, green, blue, 0)
            else:
                pixels[x, y] = (red, green, blue, alpha)

    alpha_channel = crop.getchannel("A")
    box = alpha_channel.getbbox()
    return crop.crop(box) if box else crop


def paste_contained(canvas: Image.Image, image: Image.Image, box: tuple[int, int, int, int]) -> None:
    target_width = box[2] - box[0]
    target_height = box[3] - box[1]
    ratio = min(target_width / image.width, target_height / image.height)
    size = (max(1, round(image.width * ratio)), max(1, round(image.height * ratio)))
    resized = image.resize(size, Image.Resampling.LANCZOS)
    x = box[0] + (target_width - resized.width) // 2
    y = box[1] + (target_height - resized.height) // 2
    canvas.alpha_composite(resized, (x, y))


def add_corner_geometry(draw: ImageDraw.ImageDraw) -> None:
    for offset in range(0, 520, 58):
        draw.line((0, 330 + offset, 350 + offset, HEIGHT), fill="#D7E8E5", width=2)
        draw.line((WIDTH, 330 + offset, WIDTH - 350 - offset, HEIGHT), fill="#D7E8E5", width=2)
    draw.arc((45, 220, 500, 760), 75, 190, fill="#D3E9E6", width=3)
    draw.arc((WIDTH - 500, 220, WIDTH - 45, 760), -10, 105, fill="#D3E9E6", width=3)


def main() -> None:
    if not SOURCE_PATH.exists():
        raise FileNotFoundError(f"Branding source not found: {SOURCE_PATH}")

    source = Image.open(SOURCE_PATH).convert("RGBA")
    canvas = Image.new("RGBA", (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(canvas)

    draw.rectangle((0, 0, WIDTH, HEIGHT), fill=PAPER)
    draw.rectangle((28, 28, WIDTH - 28, HEIGHT - 28), outline=NAVY, width=6)
    draw.rectangle((48, 48, WIDTH - 48, HEIGHT - 48), outline=GOLD, width=2)

    draw.rectangle((50, 50, WIDTH - 50, 280), fill=NAVY)
    draw.rectangle((50, 274, WIDTH - 50, 284), fill=GOLD)
    for index in range(0, 850, 68):
        draw.line((50 + index, 50, 50 + index + 220, 280), fill="#0C5976", width=3)
        draw.line((WIDTH - 50 - index, 50, WIDTH - 50 - index - 220, 280), fill="#0C5976", width=3)

    add_corner_geometry(draw)

    title_font = font(r"C:\Windows\Fonts\georgiab.ttf", 86)
    subtitle_font = font(r"C:\Windows\Fonts\calibri.ttf", 30)
    heading_font = font(r"C:\Windows\Fonts\georgiab.ttf", 31)
    body_font = font(NOTO_FONT, 35)
    body_emphasis_font = font(r"C:\Windows\Fonts\calibrii.ttf", 34)
    footer_font = font(r"C:\Windows\Fonts\calibri.ttf", 25)

    center_text(draw, 94, "CERTIFICATE", title_font, "#FFFFFF")
    center_text(draw, 185, "OF APPRECIATION", subtitle_font, "#B9E7EB")

    ieee = non_white_crop(source, (80, 235, 530, 510))
    usg = non_white_crop(source, (1580, 250, 1940, 530))
    paste_contained(canvas, ieee, (110, 330, 455, 530))
    paste_contained(canvas, usg, (1560, 320, 1895, 535))

    center_text(draw, 365, "PRESENTED TO", heading_font, TEAL)
    draw.line((770, 420, 1229, 420), fill=GOLD, width=3)
    draw.ellipse((982, 413, 1017, 448), fill=GOLD)

    # This clear field is intentionally left for the app to render the recipient name.
    center_text(draw, 680, "In recognition of your", heading_font, INK)
    next_y = wrapped_center_text(
        draw,
        740,
        "active participation, valuable contributions, and dedicated involvement in the activities and initiatives of IEEE during the 2025-2026 term.",
        body_font,
        INK,
        1370,
        16,
    )
    draw.line((615, next_y + 12, 1384, next_y + 12), fill="#B8D7D6", width=2)
    wrapped_center_text(
        draw,
        next_y + 55,
        "Your commitment, enthusiasm, and contribution to the IEEE community are sincerely appreciated and have played an important role in the success of our activities.",
        body_font,
        "#345161",
        1390,
        15,
    )
    center_text(draw, 1127, "With gratitude and appreciation for your dedication and service.", body_emphasis_font, TEAL)

    signature_left = non_white_crop(source, (300, 1050, 740, 1228), 235)
    signature_right = non_white_crop(source, (1210, 1045, 1680, 1235), 235)
    paste_contained(canvas, signature_left, (225, 1210, 735, 1325))
    paste_contained(canvas, signature_right, (1264, 1208, 1774, 1328))

    draw.line((220, 1337, 750, 1337), fill=INK, width=2)
    draw.line((1249, 1337, 1779, 1337), fill=INK, width=2)
    signer_font = font(r"C:\Windows\Fonts\calibri.ttf", 31)
    signer_role_font = font(r"C:\Windows\Fonts\calibri.ttf", 22)
    text_centered_at(draw, 485, 1352, "Taghi Mammadov", signer_font, INK)
    text_centered_at(draw, 485, 1393, "President of IEEE ADA Club", signer_role_font, "#405968")
    text_centered_at(draw, 1514, 1352, "Murad Orujov", signer_font, INK)
    text_centered_at(draw, 1514, 1393, "USG Future Hub Chair of the Development Center", signer_role_font, "#405968")

    draw.rectangle((50, 1450, WIDTH - 50, HEIGHT - 50), fill=NAVY)
    draw.rectangle((50, 1450, WIDTH - 50, 1458), fill=GOLD)
    center_text(draw, 1472, "IEEE ADA CLUB  |  USG FUTURE HUB  |  2025-2026", footer_font, "#D5F0F0")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(OUTPUT_PATH, format="PNG", optimize=True)
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
