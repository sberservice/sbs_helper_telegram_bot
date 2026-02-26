"""
Рендер изображения СООС в terminal-style.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from src.common.constants.os import ASSETS_DIR
from . import settings


def _load_terminal_font(font_size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """
    Загрузить моноширинный шрифт с fallback.

    Args:
        font_size: Размер шрифта.

    Returns:
        Объект шрифта Pillow.
    """
    font_candidates: list[str] = [
        str(ASSETS_DIR / "fonts" / "CascadiaMono.ttf"),
        str(ASSETS_DIR / "fonts" / "CascadiaCode.ttf"),
        "CascadiaMono.ttf",
        "CascadiaCode.ttf",
        "Cascadia Mono.ttf",
        "Consola.ttf",
        "Consolas.ttf",
        "/Library/Fonts/CascadiaMono.ttf",
        "/Library/Fonts/CascadiaCode.ttf",
        str(Path("~/Library/Fonts/CascadiaMono.ttf").expanduser()),
        str(Path("~/Library/Fonts/CascadiaCode.ttf").expanduser()),
        "DejaVuSansMono.ttf",
        "Menlo.ttc",
        "Courier New.ttf",
        "/System/Library/Fonts/Menlo.ttc",
        "/System/Library/Fonts/Supplemental/Courier New.ttf",
    ]

    for candidate in font_candidates:
        try:
            if candidate.startswith("/") and not Path(candidate).exists():
                continue
            return ImageFont.truetype(candidate, font_size)
        except Exception:
            continue

    return ImageFont.load_default()


def render_terminal_receipt_image(receipt_text: str, image_format: str = "PNG") -> bytes:
    """
    Отрендерить terminal-style изображение из текста чека.

    Args:
        receipt_text: Текст чека.
        image_format: Формат выходного изображения.

    Returns:
        Байты изображения.
    """
    lines = receipt_text.splitlines() or [""]
    font = _load_terminal_font(settings.RECEIPT_FONT_SIZE)

    sample_bbox = font.getbbox("M")
    char_width = max(sample_bbox[2] - sample_bbox[0], 1)
    char_height = max(sample_bbox[3] - sample_bbox[1], 1)

    max_len = max(len(line) for line in lines)
    image_width = settings.RECEIPT_PADDING_X * 2 + char_width * max_len
    line_height = char_height + settings.RECEIPT_LINE_SPACING
    image_height = settings.RECEIPT_PADDING_Y * 2 + line_height * len(lines)

    image = Image.new("RGB", (image_width, image_height), settings.TERMINAL_BG_COLOR)
    draw = ImageDraw.Draw(image)

    y = settings.RECEIPT_PADDING_Y
    for line in lines:
        draw.text(
            (settings.RECEIPT_PADDING_X, y),
            line,
            font=font,
            fill=settings.TERMINAL_TEXT_COLOR,
        )
        y += line_height

    buffer = BytesIO()
    image.save(buffer, format=image_format)
    return buffer.getvalue()
