"""Утилиты маскировки чувствительных данных в текстах логов."""

from __future__ import annotations

import re

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+7|7|8)?[\s\-()]*?(?:\d[\s\-()]*){10,11}(?!\d)")
_INN_RE = re.compile(r"(?<!\d)(?:\d{10}|\d{12})(?!\d)")
_SNILS_RE = re.compile(r"(?<!\d)\d{3}-\d{3}-\d{3}\s?\d{2}(?!\d)")


def mask_sensitive_data(value: str) -> str:
    """Замаскировать чувствительные данные (email, телефон, ИНН, СНИЛС)."""
    text = str(value or "")
    if not text:
        return ""

    masked = _EMAIL_RE.sub("[EMAIL_REDACTED]", text)
    masked = _SNILS_RE.sub("[SNILS_REDACTED]", masked)
    masked = _INN_RE.sub("[INN_REDACTED]", masked)
    masked = _PHONE_RE.sub("[PHONE_REDACTED]", masked)
    return masked
