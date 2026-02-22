"""
bot_settings.py

Утилиты управления настройками бота.

Функции:
- get_setting(key) -> str | None: Получить значение настройки по ключу.
- set_setting(key, value, updated_by) -> bool: Установить значение настройки.
- is_invite_system_enabled() -> bool: Проверить, включена ли инвайт-система.
- set_invite_system_enabled(enabled, updated_by) -> bool: Включить/выключить инвайт-систему.
- is_module_enabled(module_key) -> bool: Проверить, включён ли модуль.
- set_module_enabled(module_key, enabled, updated_by) -> bool: Включить/выключить модуль.
- get_all_module_states() -> dict: Получить состояние всех модулей (вкл/выкл).
- clear_settings_cache() -> None: Очистить кеш настроек (вызывается при set_setting).
"""

import logging
import time
from typing import Optional, Dict, List
import src.common.database as database

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# TTL-кеш для настроек (избегаем повторных обращений к БД)
# ─────────────────────────────────────────────────────────────
# Время жизни кеша в секундах. Настройки модулей меняются редко (админ-переключение),
# поэтому 60 секунд — приемлемая задержка. При записи кеш сбрасывается немедленно.
_SETTINGS_CACHE_TTL = 60

# Кеш: ключ -> (значение, время_записи)
_settings_cache: Dict[str, tuple] = {}


def _cache_get(key: str) -> Optional[str]:
    """
    Получить значение из кеша, если оно ещё не протухло.

    Returns:
        Значение настройки или _CACHE_MISS-sentinel, если кеш пуст/протух.
    """
    entry = _settings_cache.get(key)
    if entry is not None:
        value, cached_at = entry
        if time.monotonic() - cached_at < _SETTINGS_CACHE_TTL:
            return value
        # Протухло — удаляем
        del _settings_cache[key]
    return _CACHE_MISS


# Sentinel-объект, отличающийся от None (None — допустимое значение «настройка не найдена»)
_CACHE_MISS = object()


def _cache_put(key: str, value: Optional[str]) -> None:
    """Сохранить значение в кеш."""
    _settings_cache[key] = (value, time.monotonic())


def clear_settings_cache() -> None:
    """
    Очистить весь кеш настроек.

    Вызывается автоматически при set_setting(), чтобы изменения
    применялись немедленно в текущем процессе.
    """
    _settings_cache.clear()

# Ключи настроек
SETTING_INVITE_SYSTEM_ENABLED = 'invite_system_enabled'

# Конфигурация модулей
# Каждый модуль содержит:
# - key: уникальный идентификатор модуля
# - setting_key: ключ настройки в БД для вкл/выкл
# - button_label: текст кнопки модуля
# - order: порядок отображения (меньше — раньше)
# - columns: число кнопок в строке (1 или 2)
# - show_in_modules_menu: показывать ли модуль в меню «⚡ Начать работу»
MODULE_CONFIG = [
    {
        'key': 'certification',
        'setting_key': 'module_certification_enabled',
        'button_label': '📝 Аттестация',
        'order': 1,
        'columns': 2
    },
    {
        'key': 'screenshot',
        'setting_key': 'module_screenshot_enabled',
        'button_label': '📸 Обработать скриншот',
        'order': 2,
        'columns': 2
    },
    {
        'key': 'upos_errors',
        'setting_key': 'module_upos_errors_enabled',
        'button_label': '🔢 UPOS Ошибки',
        'order': 3,
        'columns': 2
    },
    {
        'key': 'ticket_validator',
        'setting_key': 'module_ticket_validator_enabled',
        'button_label': '✅ Валидация заявок',
        'order': 4,
        'columns': 2
    },
    {
        'key': 'ktr',
        'setting_key': 'module_ktr_enabled',
        'button_label': '⏱️ КТР',
        'order': 5,
        'columns': 2
    },
    {
        'key': 'feedback',
        'setting_key': 'module_feedback_enabled',
        'button_label': '📬 Обратная связь',
        'order': 6,
        'columns': 2
    },
    {
        'key': 'ai_router',
        'setting_key': 'module_ai_router_enabled',
        'button_label': '🤖 AI Роутер',
        'order': 7,
        'columns': 2,
        'show_in_modules_menu': False
    },
    {
        'key': 'news',
        'setting_key': 'module_news_enabled',
        'button_label': '📰 Новости',
        'order': 8,
        'columns': 2
    },
]

# Формируем MODULE_KEYS из MODULE_CONFIG для обратной совместимости
MODULE_KEYS = {module['key']: module['setting_key'] for module in MODULE_CONFIG}

# Формируем MODULE_NAMES из MODULE_CONFIG для обратной совместимости
MODULE_NAMES = {module['key']: module['button_label'] for module in MODULE_CONFIG}


def get_setting(key: str) -> Optional[str]:
    """
    Получить значение настройки по ключу.

    Args:
        key: Ключ настройки для получения.

    Returns:
        Значение настройки в виде строки или None, если не найдено.
    """
    cached_value = _cache_get(key)
    if cached_value is not _CACHE_MISS:
        return cached_value

    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(
                "SELECT setting_value FROM bot_settings WHERE setting_key = %s",
                (key,)
            )
            result = cursor.fetchone()
            value = result['setting_value'] if result else None
            _cache_put(key, value)
            return value


def set_setting(key: str, value: str, updated_by: Optional[int] = None) -> bool:
    """
    Установить значение настройки (вставка или обновление).

    Args:
        key: Ключ настройки.
        value: Значение настройки в виде строки.
        updated_by: ID администратора, вносящего изменения (опционально).

    Returns:
        True при успехе, иначе False.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(
                """
                INSERT INTO bot_settings (setting_key, setting_value, updated_timestamp, updated_by_userid)
                VALUES (%s, %s, UNIX_TIMESTAMP(), %s)
                ON DUPLICATE KEY UPDATE 
                    setting_value = VALUES(setting_value),
                    updated_timestamp = UNIX_TIMESTAMP(),
                    updated_by_userid = VALUES(updated_by_userid)
                """,
                (key, value, updated_by)
            )
            clear_settings_cache()
            return True


def is_invite_system_enabled() -> bool:
    """
    Проверить, включена ли инвайт-система.

    Когда включена: пользователи, вошедшие по инвайту, имеют доступ.
    Когда выключена: доступ есть только у пользователей из chat_members (Telegram-группа).

    Returns:
        True если инвайт-система включена, иначе False.
        По умолчанию True, если настройка не найдена.
    """
    value = get_setting(SETTING_INVITE_SYSTEM_ENABLED)
    # По умолчанию считаем включённой, если настройка не задана
    if value is None:
        return True
    return value == '1'


def set_invite_system_enabled(enabled: bool, updated_by: Optional[int] = None) -> bool:
    """
    Включить или выключить инвайт-систему.

    Args:
        enabled: True — включить, False — выключить.
        updated_by: ID администратора, вносящего изменения (опционально).

    Returns:
        True при успехе.
    """
    return set_setting(SETTING_INVITE_SYSTEM_ENABLED, '1' if enabled else '0', updated_by)


def is_module_enabled(module_key: str) -> bool:
    """
    Проверить, включён ли конкретный модуль.

    Args:
        module_key: Ключ модуля (например, 'ticket_validator', 'screenshot' и т. п.).

    Returns:
        True если модуль включён, иначе False.
        По умолчанию True, если настройка не найдена.
    """
    if module_key not in MODULE_KEYS:
        return True  # Неизвестные модули считаются включёнными по умолчанию
    
    setting_key = MODULE_KEYS[module_key]
    value = get_setting(setting_key)
    # По умолчанию считаем включённым, если настройка не задана
    if value is None:
        return True
    return value == '1'


def set_module_enabled(module_key: str, enabled: bool, updated_by: Optional[int] = None) -> bool:
    """
    Включить или выключить конкретный модуль.

    Args:
        module_key: Ключ модуля (например, 'ticket_validator', 'screenshot' и т. п.).
        enabled: True — включить, False — выключить.
        updated_by: ID администратора, вносящего изменения (опционально).

    Returns:
        True при успехе, False если ключ модуля некорректен.
    """
    if module_key not in MODULE_KEYS:
        return False
    
    setting_key = MODULE_KEYS[module_key]
    return set_setting(setting_key, '1' if enabled else '0', updated_by)


def get_all_module_states() -> Dict[str, bool]:
    """
    Получить состояние (вкл/выкл) для всех модулей.

    Returns:
        Словарь соответствий module_key -> состояние (True/False).
    """
    module_pairs = [(key, setting_key) for key, setting_key in MODULE_KEYS.items()]
    if not module_pairs:
        return {}

    cache_keys = [setting_key for _, setting_key in module_pairs]
    cached_values: Dict[str, Optional[str]] = {}
    missing_keys: List[str] = []

    for cache_key in cache_keys:
        cached_value = _cache_get(cache_key)
        if cached_value is _CACHE_MISS:
            missing_keys.append(cache_key)
        else:
            cached_values[cache_key] = cached_value

    if missing_keys:
        placeholders = ", ".join(["%s"] * len(missing_keys))
        query = (
            "SELECT setting_key, setting_value "
            "FROM bot_settings "
            f"WHERE setting_key IN ({placeholders})"
        )

        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(query, tuple(missing_keys))
                rows = cursor.fetchall() or []

        values_from_db = {row['setting_key']: row['setting_value'] for row in rows}
        for key in missing_keys:
            value = values_from_db.get(key)
            _cache_put(key, value)
            cached_values[key] = value

    states: Dict[str, bool] = {}
    for module_key, setting_key in module_pairs:
        value = cached_values.get(setting_key)
        states[module_key] = True if value is None else value == '1'

    return states


def get_enabled_modules() -> List[str]:
    """
    Получить список ключей включённых модулей.

    Returns:
        Список ключей модулей, которые сейчас включены.
    """
    return [key for key, enabled in get_all_module_states().items() if enabled]


def get_modules_config(
    enabled_only: bool = True,
    visible_in_modules_menu_only: bool = False,
) -> List[Dict[str, any]]:
    """
    Получить конфигурацию модулей в порядке отображения.

    Args:
        enabled_only: Если True, вернуть только включённые модули. Если False, вернуть все.
        visible_in_modules_menu_only: Если True, вернуть только модули,
            помеченные как видимые в меню модулей.

    Returns:
        Список словарей конфигурации, отсортированный по полю order.
        Каждый словарь содержит: key, setting_key, button_label, order, columns.
    """
    # Сортируем модули по полю order
    sorted_modules = sorted(MODULE_CONFIG, key=lambda x: x['order'])

    module_states = get_all_module_states() if enabled_only else None

    if enabled_only and module_states is not None:
        sorted_modules = [
            module
            for module in sorted_modules
            if module_states.get(module['key'], True)
        ]

    if visible_in_modules_menu_only:
        sorted_modules = [
            module for module in sorted_modules
            if module.get('show_in_modules_menu', True)
        ]
    
    return sorted_modules


def check_if_user_from_invite(telegram_id: int) -> bool:
    """
    Проверить, получил ли пользователь доступ через инвайт-систему (не пред-добавлен).

    Пользователь считается "по инвайту", если:
    1. Он использовал инвайт-код, И
    2. Его нет в таблице chat_members (пред-добавленные).

    Args:
        telegram_id: Telegram ID пользователя.

    Returns:
        True, если пользователь только из инвайт-системы, иначе False.
    """
    # Проверяем, использовал ли пользователь инвайт
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(
                "SELECT COUNT(*) as count FROM invites WHERE consumed_userid = %s",
                (telegram_id,)
            )
            result = cursor.fetchone()
            has_consumed_invite = result['count'] > 0

    # Проверяем, является ли пользователь пред-добавленным (таблица chat_members)
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(
                "SELECT COUNT(*) as count FROM chat_members WHERE telegram_id = %s",
                (telegram_id,)
            )
            result = cursor.fetchone()
            is_pre_invited = result['count'] > 0
    
    # Пользователь "по инвайту", если использовал инвайт И не пред-добавлен
    return has_consumed_invite and not is_pre_invited
