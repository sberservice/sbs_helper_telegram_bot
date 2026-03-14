"""Утилиты хранения общепроектных (не бот-специфичных) настроек."""

from __future__ import annotations

import time
from typing import Dict, Optional

import src.common.database as database

# TTL-кеш для снижения числа обращений к БД.
_SETTINGS_CACHE_TTL = 60
_settings_cache: Dict[str, tuple[Optional[str], float]] = {}
_CACHE_MISS = object()


def _cache_get(key: str):
    """Получить значение из кеша, если оно ещё актуально."""
    entry = _settings_cache.get(key)
    if entry is not None:
        value, cached_at = entry
        if time.monotonic() - cached_at < _SETTINGS_CACHE_TTL:
            return value
        del _settings_cache[key]
    return _CACHE_MISS


def _cache_put(key: str, value: Optional[str]) -> None:
    """Сохранить значение в кеш."""
    _settings_cache[key] = (value, time.monotonic())


def clear_settings_cache() -> None:
    """Очистить кеш настроек."""
    _settings_cache.clear()


def get_setting(key: str) -> Optional[str]:
    """Прочитать значение настройки из таблицы app_settings."""
    cached_value = _cache_get(key)
    if cached_value is not _CACHE_MISS:
        return cached_value

    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(
                "SELECT setting_value FROM app_settings WHERE setting_key = %s",
                (key,),
            )
            row = cursor.fetchone()
            value = row["setting_value"] if row else None
            _cache_put(key, value)
            return value


def set_setting(key: str, value: str, updated_by: Optional[int] = None) -> bool:
    """Создать или обновить настройку в таблице app_settings."""
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(
                """
                INSERT INTO app_settings (setting_key, setting_value, updated_timestamp, updated_by_userid)
                VALUES (%s, %s, UNIX_TIMESTAMP(), %s)
                ON DUPLICATE KEY UPDATE
                    setting_value = VALUES(setting_value),
                    updated_timestamp = UNIX_TIMESTAMP(),
                    updated_by_userid = VALUES(updated_by_userid)
                """,
                (key, value, updated_by),
            )
            clear_settings_cache()
            return True
