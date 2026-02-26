"""
Шаблонизатор чека СООС.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from . import settings

MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def _truncate(text: str, width: int) -> str:
    """
    Обрезать строку до заданной длины.

    Args:
        text: Исходный текст.
        width: Максимальная длина.

    Returns:
        Обрезанная строка.
    """
    if len(text) <= width:
        return text
    if width <= 1:
        return text[:width]
    return text[: width - 1] + "…"


def _truncate_hard(text: str, width: int) -> str:
    """
    Жёстко обрезать строку до заданной длины без многоточия.

    Args:
        text: Исходный текст.
        width: Максимальная длина.

    Returns:
        Обрезанная строка без добавления дополнительных символов.
    """
    if width <= 0:
        return ""
    return text[:width]


def _center(text: str, width: int) -> str:
    """
    Выровнять строку по центру.

    Args:
        text: Исходный текст.
        width: Ширина строки.

    Returns:
        Строка фиксированной ширины.
    """
    return _truncate(text, width).center(width)


def _left_right(left: str, right: str, width: int) -> str:
    """
    Сформировать строку с левым и правым выравниванием.

    Args:
        left: Левая часть.
        right: Правая часть.
        width: Общая ширина.

    Returns:
        Строка фиксированной ширины.
    """
    left = _truncate(left, width)
    right = _truncate(right, width)
    if len(left) + len(right) >= width:
        allowed_left = max(0, width - len(right) - 1)
        left = _truncate(left, allowed_left)
    spaces = " " * max(0, width - len(left) - len(right))
    return f"{left}{spaces}{right}"


def _split_address_to_two_lines(address: str, width: int) -> tuple[str, str]:
    """
    Разбить адрес на две строки фиксированной ширины.

    Args:
        address: Исходный адрес.
        width: Ширина строки.

    Returns:
        Кортеж из двух строк адреса.
    """
    normalized = " ".join(address.split())
    if len(normalized) <= width:
        return normalized, ""

    split_index = normalized.rfind(",", 0, width + 1)
    if split_index == -1:
        split_index = normalized.rfind(" ", 0, width + 1)

    if split_index == -1:
        first_line = normalized[:width]
        second_line = normalized[width:]
    else:
        first_line = normalized[:split_index]
        second_line = normalized[split_index + 1:]

    first_line = first_line.strip(" ,")
    second_line = second_line.strip(" ,")
    return _truncate_hard(first_line, width), _truncate_hard(second_line, width)


def build_soos_receipt_text(fields: dict[str, str | None], now: datetime | None = None) -> str:
    """
    Собрать текст чека сверки по шаблону СООС.

    Args:
        fields: Извлечённые поля тикета.
        now: Временная метка для даты/времени чека.

    Returns:
        Готовый многострочный текст чека.
    """
    width = settings.RECEIPT_WIDTH_CHARS

    now_msk = now.astimezone(MOSCOW_TZ) if now else datetime.now(MOSCOW_TZ)
    date_value = now_msk.strftime("%d.%m.%y")
    time_value = now_msk.strftime("%H:%M")

    merchant_name = (fields.get("merchant_name") or "").strip()
    address = (fields.get("address") or "").strip()
    phone = (fields.get("phone") or "").strip()
    tid = (fields.get("tid") or "").strip()
    merchant_id = (fields.get("merchant_id") or "").strip()

    address_line_1, address_line_2 = _split_address_to_two_lines(address, width)

    lines = [
        _center(merchant_name, width),
        _center(address_line_1, width),
        _center(address_line_2, width),
        _center(f"т. {phone}", width),
        _left_right(date_value, time_value, width),
        _left_right("ПАО СБЕРБАНК", "Сверка итогов", width),
        _left_right(f"Т: {tid}", f"М:{merchant_id}", width),
        "-" * width,
        _truncate("Итоги совпали", width),
        "-" * width,
        "",
        _left_right("Валюта   :", "Руб", width),
        "",
        _truncate(" Отмена", width),
        _left_right(" Всего операций:", "1", width),
        _left_right("   На сумму:", "1.00", width),
        _truncate(" " + "-" * (width - 1), width),
        "",
        _left_right(" Количество оплат:", "0", width),
        _left_right("  На сумму:", "0.00", width),
        "",
        _left_right(" Количество отмен:", "1", width),
        _left_right("  На сумму:", "1.00", width),
        "",
        _left_right(" Количество возвратов:", "0", width),
        _left_right("  На сумму:", "0.00", width),
        "",
        "-" * width,
        _center("*******  Отчет закончен  *******", width),
        _center("База знаний кассира", width),
        _center("Оплата-картой.рф", width),
        "*" * width,
    ]

    return "\n".join(lines)


def build_soos_payment_receipt_text(fields: dict[str, str | None], now: datetime | None = None) -> str:
    """
    Собрать текст чека оплаты по первому шаблону СООС.

    Args:
        fields: Извлечённые поля тикета.
        now: Временная метка для даты/времени чека.

    Returns:
        Готовый многострочный текст чека.
    """
    width = settings.RECEIPT_WIDTH_CHARS

    now_msk = now.astimezone(MOSCOW_TZ) if now else datetime.now(MOSCOW_TZ)
    date_value = now_msk.strftime("%d.%m.%y")
    time_value = now_msk.strftime("%H:%M")

    merchant_name = (fields.get("merchant_name") or "").strip()
    address = (fields.get("address") or "").strip()
    phone = (fields.get("phone") or "").strip()
    tid = (fields.get("tid") or "").strip()
    merchant_id = (fields.get("merchant_id") or "").strip()

    address_line_1, address_line_2 = _split_address_to_two_lines(address, width)

    card_suffix = tid[-4:].rjust(4, "0") if tid else "5709"
    auth_code = "016180"
    rrn_code = "426809548769"
    aid = "A0000000031010"
    terminal_hash = "A1433D67233DF4A2A6BEF5E4929C0738"

    lines = [
        _center(merchant_name, width),
        _center(address_line_1, width),
        _center(address_line_2, width),
        _center(f"т. {phone}", width),
        _left_right(f"{date_value}    {time_value}", "ЧЕК   0001", width),
        _left_right("ПАО СБЕРБАНК", "Оплата", width),
        _left_right(f"Т:{tid}", f"М:{merchant_id}", width),
        _left_right("VISA", aid, width),
        _left_right("Карта:(E1)", f"************{card_suffix}", width),
        _left_right("Сумма (Руб):", "1.00", width),
        _truncate("Комиссия за операцию — 0 Руб.", width),
        _center("ОДОБРЕНО", width),
        _left_right(f"К/А: {auth_code}", f"RRN: {rrn_code}", width),
        _truncate("Подпись клиента не требуется", width),
        _truncate(terminal_hash, width),
        "=" * width,
    ]

    return "\n".join(lines)


def build_soos_cancel_receipt_text(fields: dict[str, str | None], now: datetime | None = None) -> str:
    """
    Собрать текст чека отмены по дополнительному шаблону СООС.

    Args:
        fields: Извлечённые поля тикета.
        now: Временная метка для даты/времени чека.

    Returns:
        Готовый многострочный текст чека.
    """
    width = settings.RECEIPT_WIDTH_CHARS

    now_msk = now.astimezone(MOSCOW_TZ) if now else datetime.now(MOSCOW_TZ)
    date_value = now_msk.strftime("%d.%m.%y")
    time_value = now_msk.strftime("%H:%M")

    merchant_name = (fields.get("merchant_name") or "").strip()
    address = (fields.get("address") or "").strip()
    phone = (fields.get("phone") or "").strip()
    tid = (fields.get("tid") or "").strip()
    merchant_id = (fields.get("merchant_id") or "").strip()

    address_line_1, address_line_2 = _split_address_to_two_lines(address, width)

    card_suffix = tid[-4:].rjust(4, "0") if tid else "5709"
    auth_code = "016180"
    rrn_code = "426809548769"
    aid = "A0000000031010"
    terminal_hash = "26C22D1BF6A07DDFD96459CEF05920DF"

    lines = [
        _center(merchant_name, width),
        _center(address_line_1, width),
        _center(address_line_2, width),
        _center(f"т. {phone}", width),
        _left_right(f"{date_value}    {time_value}", "ЧЕК   0001", width),
        _left_right("ПАО СБЕРБАНК", "Отмена", width),
        _left_right(f"Т: {tid}", f"М:{merchant_id}", width),
        _left_right("VISA", aid, width),
        _left_right("Карта:(E1)", f"************{card_suffix}", width),
        _left_right("Сумма (Руб):", "1.00", width),
        _truncate("Комиссия за операцию — 0 Руб.", width),
        _center("ОДОБРЕНО", width),
        _left_right(f"К/А: {auth_code}", f"RRN: {rrn_code}", width),
        _truncate(terminal_hash, width),
        "=" * width,
    ]

    return "\n".join(lines)
