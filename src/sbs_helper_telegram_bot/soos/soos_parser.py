"""
Парсер тикета для модуля СООС.
"""

from __future__ import annotations

import re
from typing import Final

REQUIRED_FIELD_LABELS: Final[dict[str, str]] = {
    "merchant_name": "Наименование ТСТ",
    "address": "Адрес установки POS-терминала",
    "phone": "Телефон",
    "tid": "TID",
    "merchant_id": "merchant/MID",
}


def _generate_mid_from_tid(tid: str) -> str:
    """
    Сгенерировать merchant ID из TID по правилу СООС.

    Формат: 12 символов, префикс `851000` + последние 6 цифр TID.

    Args:
        tid: Идентификатор терминала.

    Returns:
        Сгенерированный merchant ID.
    """
    tid_digits = re.sub(r"\D", "", tid)
    tid_tail = tid_digits[-6:].zfill(6)
    return f"851000{tid_tail}"


def _normalize_spaces(value: str) -> str:
    """
    Нормализовать пробелы в строке.

    Args:
        value: Исходная строка.

    Returns:
        Строка с нормализованными пробелами.
    """
    return re.sub(r"\s+", " ", value).strip()


def _extract_last_match(patterns: list[str], ticket_text: str) -> str | None:
    """
    Извлечь последнее подходящее значение по набору regex-паттернов.

    Args:
        patterns: Список regex-паттернов с одной группой захвата.
        ticket_text: Текст тикета.

    Returns:
        Значение или None.
    """
    for pattern in patterns:
        matches = re.findall(pattern, ticket_text, re.IGNORECASE | re.MULTILINE)
        if not matches:
            continue
        last_value = matches[-1]
        if isinstance(last_value, tuple):
            last_value = next((x for x in last_value if x), "")
        normalized = _normalize_spaces(str(last_value))
        if normalized:
            return normalized
    return None


def extract_ticket_fields(ticket_text: str) -> dict[str, str | None]:
    """
    Извлечь поля СООС из текста тикета.

    Args:
        ticket_text: Полный текст тикета.

    Returns:
        Словарь извлечённых полей.
    """
    merchant_name = _extract_last_match(
        [r"^\s*Наименование ТСТ\s*:\s*(.+?)\s*$"],
        ticket_text,
    )

    address = _extract_last_match(
        [r"^\s*Адрес установки POS-терминала\s*:\s*(.+?)\s*$"],
        ticket_text,
    )

    phone = _extract_last_match(
        [
            r"^\s*Телефон обратной связи\s*:\s*([+]?\d[\d\s\-()]{7,})\s*$",
            r"^\s*Телефон ТСТ\s*:\s*([+]?\d[\d\s\-()]{7,})\s*$",
            r"^\s*Телефон МПС\s*:\s*([+]?\d[\d\s\-()]{7,})\s*$",
            r"^\s*т\.?\s*([+]?\d[\d\s\-()]{7,})\s*$",
        ],
        ticket_text,
    )

    if phone is not None:
        phone = re.sub(r"[^0-9]", "", phone)

    tid = _extract_last_match(
        [r"^\s*TID\s*:\s*(\d{6,12})\s*$", r"\bT\s*:\s*(\d{6,12})\b"],
        ticket_text,
    )

    merchant_id = _extract_last_match(
        [
            r"^\s*merchant\s*[:=]\s*(\d{8,20})\s*$",
            r"^\s*mid\s*[:=]\s*(\d{8,20})\s*$",
            r"\bМ\s*:\s*(\d{8,20})\b",
        ],
        ticket_text,
    )

    if merchant_id is None and tid:
        merchant_id = _generate_mid_from_tid(tid)

    return {
        "merchant_name": merchant_name,
        "address": address,
        "phone": phone,
        "tid": tid,
        "merchant_id": merchant_id,
    }


def get_missing_required_fields(fields: dict[str, str | None]) -> list[str]:
    """
    Определить список отсутствующих обязательных полей.

    Args:
        fields: Словарь извлечённых полей.

    Returns:
        Список человекочитаемых названий отсутствующих полей.
    """
    missing: list[str] = []
    for key, label in REQUIRED_FIELD_LABELS.items():
        value = fields.get(key)
        if value is None or not str(value).strip():
            missing.append(label)
    return missing
