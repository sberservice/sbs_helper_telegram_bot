"""
Тесты шаблона и рендера изображения СООС.
"""

from datetime import datetime
from io import BytesIO
from zoneinfo import ZoneInfo

from PIL import Image

from src.sbs_helper_telegram_bot.soos import settings
from src.sbs_helper_telegram_bot.soos.soos_renderer import render_terminal_receipt_image
from src.sbs_helper_telegram_bot.soos.soos_template import (
    build_soos_cancel_receipt_text,
    build_soos_payment_receipt_text,
    build_soos_receipt_text,
)


def test_build_soos_receipt_text_shape_and_content():
    """Строит чек фиксированной ширины и с ожидаемыми полями."""
    fields = {
        "merchant_name": "MOCHI & BUBBLE TEA",
        "address": "Островцы, Раменское, ул. Баулинская, дом 3",
        "phone": "79629355081",
        "tid": "12345678",
        "merchant_id": "123456789012",
    }

    now = datetime(2026, 2, 26, 11, 38, tzinfo=ZoneInfo("Europe/Moscow"))
    receipt_text = build_soos_receipt_text(fields, now=now)
    lines = receipt_text.splitlines()

    assert len(lines) > 20
    assert all(len(line) <= settings.RECEIPT_WIDTH_CHARS for line in lines)
    assert "Т: 12345678" in receipt_text
    assert "М:123456789012" in receipt_text
    assert "26.02.26" in receipt_text
    assert "11:38" in receipt_text
    assert "\nИтоги совпали\n" in receipt_text


def test_address_split_preserves_order():
    """Разбиение адреса на две строки сохраняет исходный порядок частей."""
    fields = {
        "merchant_name": "TEST",
        "address": "Московская область обл, г Лыткарино, кв-л 3А, дом 8",
        "phone": "79990000000",
        "tid": "12345678",
        "merchant_id": "851000345678",
    }

    now = datetime(2026, 2, 26, 11, 38, tzinfo=ZoneInfo("Europe/Moscow"))
    receipt_text = build_soos_receipt_text(fields, now=now)

    idx_region = receipt_text.find("Московская область обл")
    idx_city = receipt_text.find("г Лыткарино")
    idx_block = receipt_text.find("кв-л 3А")
    idx_house = receipt_text.find("дом 8")

    assert idx_region != -1
    assert idx_city != -1
    assert idx_block != -1
    assert idx_house != -1
    assert idx_region < idx_city < idx_block < idx_house


def test_long_address_truncates_without_ellipsis():
    """Слишком длинный адрес обрезается без добавления многоточия."""
    fields = {
        "merchant_name": "TEST",
        "address": "Московская область обл, г Лыткарино, кв-л 3А, дом 8, подъезд 2, этаж 5, помещение 123, дополнительная очень длинная часть адреса",
        "phone": "79990000000",
        "tid": "12345678",
        "merchant_id": "851000345678",
    }

    now = datetime(2026, 2, 26, 11, 38, tzinfo=ZoneInfo("Europe/Moscow"))
    receipt_text = build_soos_receipt_text(fields, now=now)

    assert "…" not in receipt_text


def test_render_terminal_receipt_image_png():
    """Рендерит PNG-изображение из текста чека."""
    receipt_text = "Тест\n" + ("-" * settings.RECEIPT_WIDTH_CHARS)
    image_bytes = render_terminal_receipt_image(receipt_text, image_format="PNG")

    assert image_bytes.startswith(b"\x89PNG\r\n\x1a\n")

    image = Image.open(BytesIO(image_bytes))
    assert image.width > 0
    assert image.height > 0
    assert image.mode == "RGB"


def test_build_soos_payment_receipt_text_contains_required_blocks():
    """Строит первый шаблон чека оплаты с ключевыми блоками из макета."""
    fields = {
        "merchant_name": "Машенька",
        "address": "Жуковский, Московская область, ул. Чкалова, дом 4Г",
        "phone": "79150583838",
        "tid": "34623408",
        "merchant_id": "851000623408",
    }

    now = datetime(2026, 2, 26, 12, 41, tzinfo=ZoneInfo("Europe/Moscow"))
    receipt_text = build_soos_payment_receipt_text(fields, now=now)

    assert "ЧЕК   0001" in receipt_text
    assert "ПАО СБЕРБАНК" in receipt_text
    assert "Оплата" in receipt_text
    assert "ОДОБРЕНО" in receipt_text
    assert "RRN:" in receipt_text


def test_build_soos_cancel_receipt_text_contains_required_blocks():
    """Строит дополнительный шаблон чека отмены с ключевыми блоками."""
    fields = {
        "merchant_name": "Машенька",
        "address": "Жуковский, Московская область, ул. Чкалова, дом 4Г",
        "phone": "79150583838",
        "tid": "34623408",
        "merchant_id": "851000612408",
    }

    now = datetime(2026, 2, 26, 12, 41, tzinfo=ZoneInfo("Europe/Moscow"))
    receipt_text = build_soos_cancel_receipt_text(fields, now=now)

    assert "ЧЕК   0001" in receipt_text
    assert "ПАО СБЕРБАНК" in receipt_text
    assert "Отмена" in receipt_text
    assert "ОДОБРЕНО" in receipt_text
    assert "26C22D1BF6A07DDFD96459CEF05920DF" in receipt_text
