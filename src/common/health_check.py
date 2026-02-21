"""
Утилиты проверки доступности сервиса налоговой.

Хранит статус здоровья и календарь плановых работ (UTC, секунды).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional
import logging
import time
from zoneinfo import ZoneInfo

import src.common.database as database

logger = logging.getLogger(__name__)

HEALTH_STATUS_HEALTHY = "healthy"
HEALTH_STATUS_BROKEN = "broken"

# ─────────────────────────────────────────────────────────────
# TTL-кеш для строк статуса здоровья (главное меню)
# ─────────────────────────────────────────────────────────────
# Данные здоровья обновляются фоновым чекером раз в несколько минут,
# поэтому кешируем на 60 секунд — достаточно для снижения нагрузки
# без потери актуальности.
_HEALTH_CACHE_TTL = 60
_health_lines_cache: Optional[tuple[list[str], float]] = None


def _get_cached_health_lines() -> Optional[list[str]]:
    """Получить кешированные строки статуса, если не протухли."""
    global _health_lines_cache
    if _health_lines_cache is not None:
        lines, cached_at = _health_lines_cache
        if time.monotonic() - cached_at < _HEALTH_CACHE_TTL:
            return lines
        _health_lines_cache = None
    return None


def _set_cached_health_lines(lines: list[str]) -> None:
    """Сохранить строки статуса в кеш."""
    global _health_lines_cache
    _health_lines_cache = (lines, time.monotonic())


def clear_health_cache() -> None:
    """Сбросить кеш статуса здоровья (вызывается при обновлении статуса)."""
    global _health_lines_cache
    _health_lines_cache = None

OUTAGE_TYPE_BLUE_SHORT = "blue_short"
OUTAGE_TYPE_BLUE_LONG = "blue_long"
OUTAGE_TYPE_RED = "red"

OUTAGE_TYPE_LABELS = {
    OUTAGE_TYPE_BLUE_SHORT: "22:00-01:00",
    OUTAGE_TYPE_BLUE_LONG: "22:00-05:00",
    OUTAGE_TYPE_RED: "20:00-20:00",
}

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
    last_broken_started_at: Optional[int]


@dataclass(frozen=True)
class PlannedOutage:
    outage_id: int
    outage_date: date
    outage_type: str
    start_timestamp: int
    end_timestamp: int


def _safe_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _escape_markdown_v2(text: str) -> str:
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text


def _get_outage_window(outage_date: date, outage_type: str) -> tuple[datetime, datetime]:
    if outage_type == OUTAGE_TYPE_BLUE_SHORT:
        start_dt = datetime.combine(outage_date, datetime.min.time(), tzinfo=MOSCOW_TZ).replace(hour=22, minute=0)
        end_dt = start_dt + timedelta(hours=3)
        return start_dt, end_dt
    if outage_type == OUTAGE_TYPE_BLUE_LONG:
        start_dt = datetime.combine(outage_date, datetime.min.time(), tzinfo=MOSCOW_TZ).replace(hour=22, minute=0)
        end_dt = start_dt + timedelta(hours=7)
        return start_dt, end_dt
    start_dt = datetime.combine(outage_date, datetime.min.time(), tzinfo=MOSCOW_TZ).replace(hour=20, minute=0)
    end_dt = start_dt + timedelta(hours=24)
    return start_dt, end_dt


def _format_outage_window(start_ts: int, end_ts: int, outage_type: str) -> str:
    start_dt = datetime.fromtimestamp(start_ts, tz=MOSCOW_TZ)
    end_dt = datetime.fromtimestamp(end_ts, tz=MOSCOW_TZ)
    if outage_type == OUTAGE_TYPE_RED:
        return (
            f"с {start_dt.strftime('%H:%M')} {start_dt.strftime('%d.%m')}"
            f" по {end_dt.strftime('%H:%M')} {end_dt.strftime('%d.%m.%Y')} МСК"
        )
    time_range = f"{start_dt.strftime('%H:%M')}–{end_dt.strftime('%H:%M')} МСК"
    return f"{time_range} ({start_dt.strftime('%d.%m.%Y')})"


def create_planned_outage(outage_date: date, outage_type: str, admin_id: Optional[int]) -> None:
    start_dt, end_dt = _get_outage_window(outage_date, outage_type)
    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(
                """
                INSERT INTO tax_service_planned_outages
                    (outage_date, outage_type, start_timestamp, end_timestamp, created_by_userid, updated_by_userid,
                     created_timestamp, updated_timestamp)
                VALUES (%s, %s, %s, %s, %s, %s, UNIX_TIMESTAMP(), UNIX_TIMESTAMP())
                ON DUPLICATE KEY UPDATE
                    start_timestamp = VALUES(start_timestamp),
                    end_timestamp = VALUES(end_timestamp),
                    updated_by_userid = VALUES(updated_by_userid),
                    updated_timestamp = UNIX_TIMESTAMP()
                """,
                (
                    outage_date.strftime("%Y-%m-%d"),
                    outage_type,
                    start_ts,
                    end_ts,
                    admin_id,
                    admin_id,
                ),
            )


def list_planned_outages(limit: int = 30, include_past: bool = False) -> list[PlannedOutage]:
    now_ts = int(time.time())
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            if include_past:
                cursor.execute(
                    """
                    SELECT id, outage_date, outage_type, start_timestamp, end_timestamp
                    FROM tax_service_planned_outages
                    ORDER BY outage_date DESC, start_timestamp DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
            else:
                cursor.execute(
                    """
                    SELECT id, outage_date, outage_type, start_timestamp, end_timestamp
                    FROM tax_service_planned_outages
                    WHERE end_timestamp >= %s
                    ORDER BY outage_date ASC, start_timestamp ASC
                    LIMIT %s
                    """,
                    (now_ts, limit),
                )
            rows = cursor.fetchall()

    outages: list[PlannedOutage] = []
    for row in rows or []:
        outages.append(
            PlannedOutage(
                outage_id=row["id"],
                outage_date=row["outage_date"],
                outage_type=row["outage_type"],
                start_timestamp=_safe_int(row["start_timestamp"]) or 0,
                end_timestamp=_safe_int(row["end_timestamp"]) or 0,
            )
        )
    return outages


def delete_planned_outage(outage_id: int) -> None:
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(
                "DELETE FROM tax_service_planned_outages WHERE id = %s",
                (outage_id,),
            )


def get_planned_outage_by_id(outage_id: int) -> Optional[PlannedOutage]:
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(
                """
                SELECT id, outage_date, outage_type, start_timestamp, end_timestamp
                FROM tax_service_planned_outages
                WHERE id = %s
                """,
                (outage_id,),
            )
            row = cursor.fetchone()

    if not row:
        return None
    return PlannedOutage(
        outage_id=row["id"],
        outage_date=row["outage_date"],
        outage_type=row["outage_type"],
        start_timestamp=_safe_int(row["start_timestamp"]) or 0,
        end_timestamp=_safe_int(row["end_timestamp"]) or 0,
    )


def _get_red_outage_ranges(now_ts: int) -> list[tuple[int, int]]:
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(
                """
                SELECT outage_date, start_timestamp, end_timestamp
                FROM tax_service_planned_outages
                WHERE outage_type = %s AND end_timestamp >= %s
                ORDER BY outage_date ASC
                """,
                (OUTAGE_TYPE_RED, now_ts),
            )
            rows = cursor.fetchall()

    ranges: list[tuple[int, int]] = []
    current_start = None
    current_end = None
    current_date = None
    for row in rows or []:
        row_date = row["outage_date"]
        start_ts = _safe_int(row["start_timestamp"]) or 0
        end_ts = _safe_int(row["end_timestamp"]) or 0
        if current_start is None:
            current_start = start_ts
            current_end = end_ts
            current_date = row_date
            continue
        if current_date and row_date == current_date + timedelta(days=1):
            current_end = end_ts
            current_date = row_date
            continue
        ranges.append((current_start, current_end))
        current_start = start_ts
        current_end = end_ts
        current_date = row_date
    if current_start is not None and current_end is not None:
        ranges.append((current_start, current_end))
    return ranges


def _find_current_outage(now_ts: int) -> Optional[tuple[str, int, int]]:
    for start_ts, end_ts in _get_red_outage_ranges(now_ts):
        if start_ts <= now_ts < end_ts:
            return OUTAGE_TYPE_RED, start_ts, end_ts

    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(
                """
                SELECT outage_type, start_timestamp, end_timestamp
                FROM tax_service_planned_outages
                WHERE outage_type IN (%s, %s)
                  AND start_timestamp <= %s AND end_timestamp > %s
                ORDER BY start_timestamp ASC
                LIMIT 1
                """,
                (OUTAGE_TYPE_BLUE_SHORT, OUTAGE_TYPE_BLUE_LONG, now_ts, now_ts),
            )
            row = cursor.fetchone()
    if not row:
        return None
    return row["outage_type"], _safe_int(row["start_timestamp"]) or 0, _safe_int(row["end_timestamp"]) or 0


def _find_next_outages(after_ts: int, limit: int = 2) -> list[tuple[str, int, int]]:
    next_red: list[tuple[str, int, int]] = []
    for start_ts, end_ts in _get_red_outage_ranges(after_ts):
        if start_ts > after_ts:
            next_red.append((OUTAGE_TYPE_RED, start_ts, end_ts))
            if len(next_red) >= limit:
                break

    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(
                """
                SELECT outage_type, start_timestamp, end_timestamp
                FROM tax_service_planned_outages
                WHERE outage_type IN (%s, %s)
                  AND start_timestamp > %s
                ORDER BY start_timestamp ASC
                LIMIT %s
                """,
                (OUTAGE_TYPE_BLUE_SHORT, OUTAGE_TYPE_BLUE_LONG, after_ts, limit * 2),
            )
            rows = cursor.fetchall()

    next_blue: list[tuple[str, int, int]] = []
    for row in rows or []:
        next_blue.append(
            (
                row["outage_type"],
                _safe_int(row["start_timestamp"]) or 0,
                _safe_int(row["end_timestamp"]) or 0,
            )
        )

    candidates = [*next_red, *next_blue]
    if not candidates:
        return []
    candidates.sort(key=lambda item: item[1])
    return candidates[:limit]


def get_planned_outage_status_lines() -> list[str]:
    now_ts = int(time.time())
    lines: list[str] = []
    current_outage = _find_current_outage(now_ts)
    next_outages: list[tuple[str, int, int]] = []
    if current_outage:
        outage_type, start_ts, end_ts = current_outage
        current_text = _format_outage_window(start_ts, end_ts, outage_type)
        lines.append(f"*Идут плановые работы:*🟠 {_escape_markdown_v2(f'сейчас {current_text}')}" )
        next_outages = _find_next_outages(end_ts)
    else:
        next_outages = _find_next_outages(now_ts)

    if next_outages:
        next_texts = []
        for outage_type, start_ts, end_ts in next_outages:
            next_texts.append(_format_outage_window(start_ts, end_ts, outage_type))
        lines.append(f"*Следующие плановые работы:* {_escape_markdown_v2('; '.join(next_texts))}")

    return lines


def record_health_status(is_healthy: bool, checked_at: int) -> None:
    """
    Сохранить статус здоровья и временные метки в настройках бота.

    Args:
        is_healthy: True, если сервис доступен.
        checked_at: Временная метка UTC (секунды).
    """
    status_value = HEALTH_STATUS_HEALTHY if is_healthy else HEALTH_STATUS_BROKEN
    last_healthy_at = checked_at if is_healthy else None
    last_broken_at = checked_at if not is_healthy else None
    last_broken_started_at = None
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(
                """
                SELECT last_status, last_broken_started_at
                FROM tax_service_health
                WHERE id = 1
                """
            )
            row = cursor.fetchone()
            prev_status = row.get("last_status") if row else None
            prev_broken_started_at = _safe_int(row.get("last_broken_started_at")) if row else None
            if status_value == HEALTH_STATUS_BROKEN:
                if prev_status != HEALTH_STATUS_BROKEN or not prev_broken_started_at:
                    last_broken_started_at = checked_at
                else:
                    last_broken_started_at = prev_broken_started_at
            else:
                last_broken_started_at = prev_broken_started_at
            cursor.execute(
                """
                INSERT INTO tax_service_health
                    (id, last_status, last_checked_at, last_healthy_at, last_broken_at, last_broken_started_at,
                     updated_timestamp)
                VALUES (1, %s, %s, %s, %s, %s, UNIX_TIMESTAMP())
                ON DUPLICATE KEY UPDATE
                    last_status = VALUES(last_status),
                    last_checked_at = VALUES(last_checked_at),
                    last_healthy_at = COALESCE(VALUES(last_healthy_at), last_healthy_at),
                    last_broken_at = COALESCE(VALUES(last_broken_at), last_broken_at),
                    last_broken_started_at = COALESCE(VALUES(last_broken_started_at), last_broken_started_at),
                    updated_timestamp = UNIX_TIMESTAMP()
                """,
                (status_value, checked_at, last_healthy_at, last_broken_at, last_broken_started_at),
            )
    # Сбрасываем кеш, чтобы новый статус отобразился немедленно
    clear_health_cache()


def get_health_status_snapshot() -> HealthStatusSnapshot:
    """Прочитать текущий снимок статуса из настроек."""
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(
                """
                SELECT last_status, last_checked_at, last_healthy_at, last_broken_at, last_broken_started_at
                FROM tax_service_health
                WHERE id = 1
                """
            )
            row = cursor.fetchone()

    if not row:
        return HealthStatusSnapshot(
            status=None,
            last_checked_at=None,
            last_healthy_at=None,
            last_broken_at=None,
            last_broken_started_at=None,
        )

    return HealthStatusSnapshot(
        status=row.get("last_status"),
        last_checked_at=_safe_int(row.get("last_checked_at")),
        last_healthy_at=_safe_int(row.get("last_healthy_at")),
        last_broken_at=_safe_int(row.get("last_broken_at")),
        last_broken_started_at=_safe_int(row.get("last_broken_started_at")),
    )


def format_moscow_time(timestamp: Optional[int]) -> str:
    if not timestamp:
        return "нет данных"
    dt = datetime.fromtimestamp(timestamp, tz=MOSCOW_TZ)
    now = datetime.now(tz=MOSCOW_TZ)
    if dt.date() == now.date():
        return dt.strftime("%H:%M") + " МСК"
    if dt.date() == (now.date() - timedelta(days=1)):
        return dt.strftime("%H:%M") + " МСК (вчера)"
    return dt.strftime("%d.%m.%Y %H:%M") + " МСК"


def _format_duration_hm(seconds: Optional[int]) -> Optional[str]:
    if seconds is None or seconds < 0:
        return "нет данных"
    if seconds == 0:
        return None
    minutes_total = seconds // 60
    hours = minutes_total // 60
    minutes = minutes_total % 60
    return f"{hours} ч {minutes} мин"


def get_tax_health_status_lines() -> list[str]:
    """
    Сформировать строки статуса для главного меню.

    Результат кешируется на _HEALTH_CACHE_TTL секунд, чтобы
    не создавать 3 DB-соединения при каждом показе главного меню.
    """
    cached = _get_cached_health_lines()
    if cached is not None:
        return cached

    snapshot = get_health_status_snapshot()
    now_ts = int(time.time())
    checked_at = format_moscow_time(snapshot.last_checked_at)
    last_healthy = format_moscow_time(snapshot.last_healthy_at)
    last_broken = format_moscow_time(snapshot.last_broken_at)

    lines: list[str] = []
    if snapshot.status == HEALTH_STATUS_HEALTHY:
        last_outage_seconds = None
        if snapshot.last_broken_at and snapshot.last_broken_started_at:
            last_outage_seconds = snapshot.last_broken_at - snapshot.last_broken_started_at
        last_outage_text = _format_duration_hm(last_outage_seconds)
        lines = [
            f"*Статус налоговой:* {_escape_markdown_v2(f'🟢 работает {checked_at}')}",
            f"*Последний сбой:* {_escape_markdown_v2(last_broken)}",
        ]
        if last_outage_text is not None:
            lines.append(f"*Длительность последнего сбоя:* {_escape_markdown_v2(last_outage_text)}")
    elif snapshot.status == HEALTH_STATUS_BROKEN:
        ongoing_seconds = None
        if snapshot.last_broken_started_at:
            ongoing_seconds = now_ts - snapshot.last_broken_started_at
        ongoing_text = _format_duration_hm(ongoing_seconds)
        lines = [
            f"*Статус налоговой:* {_escape_markdown_v2(f'🔴 проблемы {checked_at}')}",
            f"*Последняя работоспособность:* {_escape_markdown_v2(last_healthy)}",
        ]
        if ongoing_text is not None:
            lines.append(f"*Длительность текущего сбоя:* {_escape_markdown_v2(ongoing_text)}")
    else:
        lines = [f"*Статус налоговой:* {_escape_markdown_v2(f'нет данных {checked_at}')}" ]

    planned_lines = get_planned_outage_status_lines()
    if planned_lines:
        lines.extend(planned_lines)

    _set_cached_health_lines(lines)
    return lines
