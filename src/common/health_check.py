"""
Утилиты проверки доступности сервиса налоговой.

Хранит статус и временные метки в bot_settings (UTC, секунды).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from src.common import bot_settings

SETTING_TAX_HEALTH_LAST_STATUS = "tax_health_last_status"
SETTING_TAX_HEALTH_LAST_CHECKED_AT = "tax_health_last_checked_at"
SETTING_TAX_HEALTH_LAST_HEALTHY_AT = "tax_health_last_healthy_at"
SETTING_TAX_HEALTH_LAST_BROKEN_AT = "tax_health_last_broken_at"

HEALTH_STATUS_HEALTHY = "healthy"
HEALTH_STATUS_BROKEN = "broken"

try:
    MOSCOW_TZ = ZoneInfo("Europe/Moscow")
except Exception:  # noqa: BLE001
    MOSCOW_TZ = timezone(timedelta(hours=3))


@dataclass(frozen=True)
class HealthStatusSnapshot:
    status: Optional[str]
    last_checked_at: Optional[int]
    last_healthy_at: Optional[int]
    last_broken_at: Optional[int]


def _safe_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def record_health_status(is_healthy: bool, checked_at: int) -> None:
    """
    Сохранить статус здоровья и временные метки в настройках бота.

    Args:
        is_healthy: True, если сервис доступен.
        checked_at: Временная метка UTC (секунды).
    """
    status_value = HEALTH_STATUS_HEALTHY if is_healthy else HEALTH_STATUS_BROKEN
    bot_settings.set_setting(SETTING_TAX_HEALTH_LAST_STATUS, status_value)
    bot_settings.set_setting(SETTING_TAX_HEALTH_LAST_CHECKED_AT, str(checked_at))
    if is_healthy:
        bot_settings.set_setting(SETTING_TAX_HEALTH_LAST_HEALTHY_AT, str(checked_at))
    else:
        bot_settings.set_setting(SETTING_TAX_HEALTH_LAST_BROKEN_AT, str(checked_at))


def get_health_status_snapshot() -> HealthStatusSnapshot:
    """Прочитать текущий снимок статуса из настроек."""
    status = bot_settings.get_setting(SETTING_TAX_HEALTH_LAST_STATUS)
    last_checked_at = _safe_int(bot_settings.get_setting(SETTING_TAX_HEALTH_LAST_CHECKED_AT))
    last_healthy_at = _safe_int(bot_settings.get_setting(SETTING_TAX_HEALTH_LAST_HEALTHY_AT))
    last_broken_at = _safe_int(bot_settings.get_setting(SETTING_TAX_HEALTH_LAST_BROKEN_AT))

    return HealthStatusSnapshot(
        status=status,
        last_checked_at=last_checked_at,
        last_healthy_at=last_healthy_at,
        last_broken_at=last_broken_at,
    )


def format_moscow_time(timestamp: Optional[int]) -> str:
    if not timestamp:
        return "нет данных"
    return datetime.fromtimestamp(timestamp, tz=MOSCOW_TZ).strftime("%H:%M") + " МСК"


def get_tax_health_status_lines() -> list[str]:
    """Сформировать строки статуса для главного меню."""
    snapshot = get_health_status_snapshot()
    checked_at = format_moscow_time(snapshot.last_checked_at)
    last_healthy = format_moscow_time(snapshot.last_healthy_at)
    last_broken = format_moscow_time(snapshot.last_broken_at)

    if snapshot.status == HEALTH_STATUS_HEALTHY:
        return [
            f"Статус налоговой: работает. Время проверки: {checked_at}",
            f"Последний сбой: {last_broken}",
        ]
    if snapshot.status == HEALTH_STATUS_BROKEN:
        return [
            f"Статус налоговой: проблемы. Время проверки: {checked_at}",
            f"Последний успех: {last_healthy}",
        ]

    return [f"Статус налоговой: нет данных. Время проверки: {checked_at}"]
