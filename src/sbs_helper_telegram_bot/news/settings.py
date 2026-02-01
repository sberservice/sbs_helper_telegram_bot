"""
News Module Settings

Configuration constants, context keys, callback prefixes, and menu definitions.
"""

from typing import Final, List

# ===== MODULE METADATA =====

MODULE_NAME: Final[str] = "Новости"
MODULE_DESCRIPTION: Final[str] = "Модуль публикации новостей и объявлений с поддержкой рассылки"
MODULE_VERSION: Final[str] = "1.0.0"
MODULE_AUTHOR: Final[str] = "SBS Helper Team"

# ===== MENU BUTTONS =====

MENU_BUTTON_TEXT: Final[str] = "📰 Новости"

# User submenu buttons
SUBMENU_BUTTONS: Final[List[List[str]]] = [
    ["📋 Последние новости"],
    ["📂 Архив", "🔍 Поиск"],
    ["🏠 Главное меню"]
]

# Admin submenu buttons (includes admin panel)
ADMIN_SUBMENU_BUTTONS: Final[List[List[str]]] = [
    ["📋 Последние новости"],
    ["📂 Архив", "🔍 Поиск"],
    ["⚙️ Управление новостями", "🏠 Главное меню"]
]

# Button texts
BUTTON_LATEST_NEWS: Final[str] = "📋 Последние новости"
BUTTON_ARCHIVE: Final[str] = "📂 Архив"
BUTTON_SEARCH: Final[str] = "🔍 Поиск"
BUTTON_ADMIN_PANEL: Final[str] = "⚙️ Управление новостями"
BUTTON_MAIN_MENU: Final[str] = "🏠 Главное меню"
BUTTON_BACK: Final[str] = "◀️ Назад"
BUTTON_CANCEL: Final[str] = "❌ Отмена"

# ===== ADMIN PANEL BUTTONS =====

ADMIN_MENU_BUTTONS: Final[List[List[str]]] = [
    ["📝 Создать новость"],
    ["📋 Черновики", "📢 Опубликованные"],
    ["📂 Категории"],
    ["◀️ Назад"]
]

BUTTON_CREATE_NEWS: Final[str] = "📝 Создать новость"
BUTTON_DRAFTS: Final[str] = "📋 Черновики"
BUTTON_PUBLISHED: Final[str] = "📢 Опубликованные"
BUTTON_CATEGORIES: Final[str] = "📂 Категории"

# Category management buttons
ADMIN_CATEGORY_BUTTONS: Final[List[List[str]]] = [
    ["➕ Добавить категорию"],
    ["◀️ Назад"]
]

BUTTON_ADD_CATEGORY: Final[str] = "➕ Добавить категорию"

# ===== CONVERSATION STATES =====

# User states
(
    STATE_SUBMENU,
    STATE_VIEW_NEWS,
    STATE_SEARCH_INPUT,
    STATE_SEARCH_RESULTS,
    STATE_ARCHIVE,
) = range(5)

# Admin states (start at 100 to avoid conflicts)
(
    STATE_ADMIN_MENU,
    STATE_ADMIN_DRAFTS_LIST,
    STATE_ADMIN_PUBLISHED_LIST,
    STATE_ADMIN_VIEW_ARTICLE,
    STATE_ADMIN_CREATE_TITLE,
    STATE_ADMIN_CREATE_CONTENT,
    STATE_ADMIN_CREATE_IMAGE,
    STATE_ADMIN_CREATE_FILE,
    STATE_ADMIN_CREATE_CATEGORY,
    STATE_ADMIN_CREATE_MODE,
    STATE_ADMIN_CREATE_MANDATORY,
    STATE_ADMIN_CONFIRM_PUBLISH,
    STATE_ADMIN_EDIT_FIELD,
    STATE_ADMIN_CATEGORIES_LIST,
    STATE_ADMIN_CATEGORY_CREATE_NAME,
    STATE_ADMIN_CATEGORY_CREATE_EMOJI,
    STATE_ADMIN_CATEGORY_EDIT,
    STATE_ADMIN_BROADCAST_PROGRESS,
) = range(100, 118)

# ===== CONTEXT KEYS =====

# User context
CURRENT_PAGE_KEY: Final[str] = "news_current_page"
SEARCH_QUERY_KEY: Final[str] = "news_search_query"
VIEW_MODE_KEY: Final[str] = "news_view_mode"  # 'latest', 'archive', 'search'

# Admin context
ADMIN_CURRENT_ARTICLE_KEY: Final[str] = "news_admin_current_article"
ADMIN_LIST_PAGE_KEY: Final[str] = "news_admin_list_page"
ADMIN_DRAFT_DATA_KEY: Final[str] = "news_admin_draft_data"
ADMIN_EDIT_FIELD_KEY: Final[str] = "news_admin_edit_field"
ADMIN_CURRENT_CATEGORY_KEY: Final[str] = "news_admin_current_category"

# ===== CALLBACK PREFIXES =====

# User callbacks
CALLBACK_PAGE_PREFIX: Final[str] = "news_page_"
CALLBACK_ARTICLE_PREFIX: Final[str] = "news_art_"
CALLBACK_REACT_PREFIX: Final[str] = "news_react_"
CALLBACK_ACK_PREFIX: Final[str] = "news_ack_"
CALLBACK_SEARCH_PAGE_PREFIX: Final[str] = "news_search_"

# Admin callbacks
CALLBACK_ADMIN_ARTICLE_PREFIX: Final[str] = "news_adm_art_"
CALLBACK_ADMIN_PAGE_PREFIX: Final[str] = "news_adm_page_"
CALLBACK_ADMIN_CATEGORY_PREFIX: Final[str] = "news_adm_cat_"
CALLBACK_ADMIN_ACTION_PREFIX: Final[str] = "news_adm_act_"
CALLBACK_ADMIN_EDIT_PREFIX: Final[str] = "news_adm_edit_"
CALLBACK_ADMIN_CONFIRM_PREFIX: Final[str] = "news_adm_conf_"

# Specific callbacks
CALLBACK_CANCEL: Final[str] = "news_cancel"
CALLBACK_NOOP: Final[str] = "news_noop"
CALLBACK_SKIP: Final[str] = "news_skip"

# ===== REACTION TYPES =====

REACTION_LIKE: Final[str] = "like"
REACTION_LOVE: Final[str] = "love"
REACTION_DISLIKE: Final[str] = "dislike"

# Reaction emojis mapping
REACTION_EMOJIS: Final[dict] = {
    REACTION_LIKE: "👍",
    REACTION_LOVE: "❤️",
    REACTION_DISLIKE: "👎",
}

# ===== BROADCAST SETTINGS =====

# Delay between messages in seconds (0.1 = 10 msg/sec, safe margin for 30/sec limit)
BROADCAST_DELAY_SECONDS: Final[float] = 0.1

# Progress update interval (every N users)
BROADCAST_PROGRESS_INTERVAL: Final[int] = 50

# ===== BOT SETTINGS KEYS =====

SETTING_NEWS_EXPIRY_DAYS: Final[str] = "news_expiry_days"
SETTING_MODULE_ENABLED: Final[str] = "module_news_enabled"

# Default values
DEFAULT_NEWS_EXPIRY_DAYS: Final[int] = 30

# ===== PAGINATION =====

# Max items per page for list views
ITEMS_PER_PAGE: Final[int] = 5

# Max characters per message (Telegram limit is 4096, leave buffer for formatting)
MAX_MESSAGE_LENGTH: Final[int] = 3800

# ===== ARTICLE STATUSES =====

STATUS_DRAFT: Final[str] = "draft"
STATUS_PUBLISHED: Final[str] = "published"
STATUS_ARCHIVED: Final[str] = "archived"
