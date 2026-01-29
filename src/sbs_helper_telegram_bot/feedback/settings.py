"""
Feedback Module Settings

Configuration constants, context keys, and menu definitions.
"""

from typing import Final, List

# ===== MODULE METADATA =====

MODULE_NAME: Final[str] = "Обратная связь"
MODULE_DESCRIPTION: Final[str] = "Модуль для отправки отзывов и получения ответов от команды поддержки"
MODULE_VERSION: Final[str] = "1.0.0"
MODULE_AUTHOR: Final[str] = "SBS Helper Team"

# ===== MENU BUTTONS =====

MENU_BUTTON_TEXT: Final[str] = "📬 Обратная связь"

# User submenu buttons
SUBMENU_BUTTONS: Final[List[List[str]]] = [
    ["📝 Отправить отзыв"],
    ["📋 Мои обращения"],
    ["🏠 Главное меню"]
]

# Admin submenu buttons (includes admin panel)
ADMIN_SUBMENU_BUTTONS: Final[List[List[str]]] = [
    ["📝 Отправить отзыв"],
    ["📋 Мои обращения"],
    ["⚙️ Управление отзывами", "🏠 Главное меню"]
]

# Button texts
BUTTON_SUBMIT_FEEDBACK: Final[str] = "📝 Отправить отзыв"
BUTTON_MY_FEEDBACK: Final[str] = "📋 Мои обращения"
BUTTON_ADMIN_PANEL: Final[str] = "⚙️ Управление отзывами"
BUTTON_MAIN_MENU: Final[str] = "🏠 Главное меню"
BUTTON_BACK: Final[str] = "◀️ Назад"
BUTTON_CANCEL: Final[str] = "❌ Отмена"

# ===== ADMIN PANEL BUTTONS =====

ADMIN_MENU_BUTTONS: Final[List[List[str]]] = [
    ["📥 Новые обращения", "📊 Все обращения"],
    ["📂 По категориям"],
    ["◀️ Назад"]
]

BUTTON_NEW_ENTRIES: Final[str] = "📥 Новые обращения"
BUTTON_ALL_ENTRIES: Final[str] = "📊 Все обращения"
BUTTON_BY_CATEGORY: Final[str] = "📂 По категориям"

# ===== CONVERSATION STATES =====

# User states
(
    STATE_SUBMENU,
    STATE_SELECT_CATEGORY,
    STATE_ENTER_MESSAGE,
    STATE_CONFIRM_SUBMIT,
    STATE_VIEW_MY_FEEDBACK,
    STATE_VIEW_FEEDBACK_DETAIL,
) = range(6)

# Admin states (start at 100 to avoid conflicts)
(
    STATE_ADMIN_MENU,
    STATE_ADMIN_VIEW_LIST,
    STATE_ADMIN_VIEW_ENTRY,
    STATE_ADMIN_COMPOSE_REPLY,
    STATE_ADMIN_CONFIRM_REPLY,
    STATE_ADMIN_SELECT_STATUS,
    STATE_ADMIN_BY_CATEGORY,
) = range(100, 107)

# ===== CONTEXT KEYS =====

# User context
CURRENT_CATEGORY_KEY: Final[str] = "feedback_current_category"
CURRENT_MESSAGE_KEY: Final[str] = "feedback_current_message"
CURRENT_ENTRY_ID_KEY: Final[str] = "feedback_current_entry_id"
MY_FEEDBACK_PAGE_KEY: Final[str] = "feedback_my_page"

# Admin context
ADMIN_CURRENT_ENTRY_KEY: Final[str] = "feedback_admin_current_entry"
ADMIN_REPLY_TEXT_KEY: Final[str] = "feedback_admin_reply_text"
ADMIN_LIST_PAGE_KEY: Final[str] = "feedback_admin_list_page"
ADMIN_FILTER_STATUS_KEY: Final[str] = "feedback_admin_filter_status"
ADMIN_FILTER_CATEGORY_KEY: Final[str] = "feedback_admin_filter_category"

# ===== RATE LIMITING =====

# Minimum time between feedback submissions (in seconds)
# 3600 = 1 hour
RATE_LIMIT_SECONDS: Final[int] = 3600

# ===== PAGINATION =====

ITEMS_PER_PAGE: Final[int] = 5

# ===== LINK DETECTION PATTERNS =====

# Regex patterns to detect links in user messages
# These patterns are used to reject messages containing URLs
LINK_PATTERNS: Final[List[str]] = [
    r'https?://[^\s]+',  # http:// or https://
    r'www\.[^\s]+',  # www.
    r't\.me/[^\s]+',  # Telegram links
    r'[a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z]{2,}(?:/[^\s]*)?',  # domain.tld patterns
]

# ===== FEEDBACK STATUSES =====

STATUS_NEW: Final[str] = "new"
STATUS_IN_PROGRESS: Final[str] = "in_progress"
STATUS_RESOLVED: Final[str] = "resolved"
STATUS_CLOSED: Final[str] = "closed"

# Human-readable status names
STATUS_NAMES: Final[dict] = {
    STATUS_NEW: "🆕 Новое",
    STATUS_IN_PROGRESS: "⏳ В работе",
    STATUS_RESOLVED: "✅ Решено",
    STATUS_CLOSED: "🔒 Закрыто",
}

# ===== INLINE CALLBACK PREFIXES =====

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
