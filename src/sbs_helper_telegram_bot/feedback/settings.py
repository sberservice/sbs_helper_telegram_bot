"""
Настройки модуля обратной связи

Константы конфигурации, ключи контекста и определения меню.
"""

from typing import Final, List

from src.common.messages import BUTTON_MAIN_MENU as COMMON_BUTTON_MAIN_MENU

# ===== МЕТАДАННЫЕ МОДУЛЯ =====

MODULE_NAME: Final[str] = "Обратная связь"
MODULE_DESCRIPTION: Final[str] = "Модуль для отправки отзывов и получения ответов от команды поддержки"
MODULE_VERSION: Final[str] = "1.0.0"
MODULE_AUTHOR: Final[str] = "SBS Archie Team"

# ===== КНОПКИ МЕНЮ =====

MENU_BUTTON_TEXT: Final[str] = "📬 Обратная связь"

# Кнопки подменю пользователя
SUBMENU_BUTTONS: Final[List[List[str]]] = [
    ["📝 Отправить отзыв"],
    ["📋 Мои обращения"],
    [COMMON_BUTTON_MAIN_MENU]
]

# Кнопки подменю администратора (включают админ-панель)
ADMIN_SUBMENU_BUTTONS: Final[List[List[str]]] = [
    ["📝 Отправить отзыв"],
    ["📋 Мои обращения"],
    ["⚙️ Управление отзывами", COMMON_BUTTON_MAIN_MENU]
]

# Тексты кнопок
BUTTON_SUBMIT_FEEDBACK: Final[str] = "📝 Отправить отзыв"
BUTTON_MY_FEEDBACK: Final[str] = "📋 Мои обращения"
BUTTON_ADMIN_PANEL: Final[str] = "⚙️ Управление отзывами"
BUTTON_MAIN_MENU: Final[str] = COMMON_BUTTON_MAIN_MENU
BUTTON_BACK: Final[str] = "◀️ Назад"
BUTTON_CANCEL: Final[str] = "❌ Отмена"

# ===== КНОПКИ АДМИН-ПАНЕЛИ =====

ADMIN_MENU_BUTTONS: Final[List[List[str]]] = [
    ["📥 Новые обращения", "📊 Все обращения"],
    ["📂 По категориям"],
    ["◀️ Назад"]
]

BUTTON_NEW_ENTRIES: Final[str] = "📥 Новые обращения"
BUTTON_ALL_ENTRIES: Final[str] = "📊 Все обращения"
BUTTON_BY_CATEGORY: Final[str] = "📂 По категориям"

# ===== СОСТОЯНИЯ ДИАЛОГА =====

# Состояния пользователя
(
    STATE_SUBMENU,
    STATE_SELECT_CATEGORY,
    STATE_ENTER_MESSAGE,
    STATE_CONFIRM_SUBMIT,
    STATE_VIEW_MY_FEEDBACK,
    STATE_VIEW_FEEDBACK_DETAIL,
) = range(6)

# Состояния администратора (начиная с 100, чтобы избежать конфликтов)
(
    STATE_ADMIN_MENU,
    STATE_ADMIN_VIEW_LIST,
    STATE_ADMIN_VIEW_ENTRY,
    STATE_ADMIN_COMPOSE_REPLY,
    STATE_ADMIN_CONFIRM_REPLY,
    STATE_ADMIN_SELECT_STATUS,
    STATE_ADMIN_BY_CATEGORY,
) = range(100, 107)

# ===== КЛЮЧИ КОНТЕКСТА =====

# Контекст пользователя
CURRENT_CATEGORY_KEY: Final[str] = "feedback_current_category"
CURRENT_MESSAGE_KEY: Final[str] = "feedback_current_message"
CURRENT_ENTRY_ID_KEY: Final[str] = "feedback_current_entry_id"
MY_FEEDBACK_PAGE_KEY: Final[str] = "feedback_my_page"

# Контекст администратора
ADMIN_CURRENT_ENTRY_KEY: Final[str] = "feedback_admin_current_entry"
ADMIN_REPLY_TEXT_KEY: Final[str] = "feedback_admin_reply_text"
ADMIN_LIST_PAGE_KEY: Final[str] = "feedback_admin_list_page"
ADMIN_FILTER_STATUS_KEY: Final[str] = "feedback_admin_filter_status"
ADMIN_FILTER_CATEGORY_KEY: Final[str] = "feedback_admin_filter_category"

# ===== ОГРАНИЧЕНИЕ ЧАСТОТЫ =====

# Минимальный интервал между отправками (в секундах)
# 3600 = 1 час
RATE_LIMIT_SECONDS: Final[int] = 3600

# ===== ПАГИНАЦИЯ =====

ITEMS_PER_PAGE: Final[int] = 5

# ===== ПАТТЕРНЫ ДЛЯ ПОИСКА ССЫЛОК =====

# Regex-паттерны для обнаружения ссылок в сообщениях
# Эти паттерны используются для отклонения сообщений с URL
LINK_PATTERNS: Final[List[str]] = [
    r'https?://[^\s]+',  # http:// или https://
    r'www\.[^\s]+',  # www.
    r't\.me/[^\s]+',  # ссылки Telegram
    r'[a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z]{2,}(?:/[^\s]*)?',  # шаблоны domain.tld
]

# ===== СТАТУСЫ ОБРАТНОЙ СВЯЗИ =====

STATUS_NEW: Final[str] = "new"
STATUS_IN_PROGRESS: Final[str] = "in_progress"
STATUS_RESOLVED: Final[str] = "resolved"
STATUS_CLOSED: Final[str] = "closed"

# Человекочитаемые названия статусов
STATUS_NAMES: Final[dict] = {
    STATUS_NEW: "🆕 Новое",
    STATUS_IN_PROGRESS: "⏳ В работе",
    STATUS_RESOLVED: "✅ Решено",
    STATUS_CLOSED: "🔒 Закрыто",
}

# ===== ПРЕФИКСЫ INLINE CALLBACK =====

CALLBACK_CATEGORY_PREFIX: Final[str] = "fb_cat_"
CALLBACK_ENTRY_PREFIX: Final[str] = "fb_entry_"
CALLBACK_PAGE_PREFIX: Final[str] = "fb_page_"
CALLBACK_STATUS_PREFIX: Final[str] = "fb_status_"
CALLBACK_ADMIN_ENTRY_PREFIX: Final[str] = "fb_adm_entry_"
CALLBACK_ADMIN_PAGE_PREFIX: Final[str] = "fb_adm_page_"
CALLBACK_ADMIN_REPLY: Final[str] = "fb_adm_reply"
CALLBACK_ADMIN_STATUS: Final[str] = "fb_adm_status"
CALLBACK_ADMIN_BACK: Final[str] = "fb_adm_back"
CALLBACK_CONFIRM_YES: Final[str] = "fb_confirm_yes"
CALLBACK_CONFIRM_NO: Final[str] = "fb_confirm_no"
CALLBACK_CANCEL: Final[str] = "fb_cancel"
