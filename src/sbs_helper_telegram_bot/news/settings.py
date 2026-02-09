"""
Настройки модуля новостей.

Константы конфигурации, ключи контекста, префиксы колбэков и меню.
"""

from typing import Final, List

from src.common.messages import BUTTON_MAIN_MENU as COMMON_BUTTON_MAIN_MENU

# ===== МЕТАДАННЫЕ МОДУЛЯ =====

MODULE_NAME: Final[str] = "Новости"
MODULE_DESCRIPTION: Final[str] = "Модуль публикации новостей и объявлений с поддержкой рассылки"
MODULE_VERSION: Final[str] = "1.0.0"
MODULE_AUTHOR: Final[str] = "SBS Helper Team"

# ===== КНОПКИ МЕНЮ =====

MENU_BUTTON_TEXT: Final[str] = "📰 Новости"

# Кнопки подменю пользователя
SUBMENU_BUTTONS: Final[List[List[str]]] = [
    ["📋 Все новости"],
    ["📂 Архив", "🔍 Поиск"],
    [COMMON_BUTTON_MAIN_MENU]
]

# Кнопки подменю админа (включая админ-панель)
ADMIN_SUBMENU_BUTTONS: Final[List[List[str]]] = [
    ["📋 Все новости"],
    ["📂 Архив", "🔍 Поиск"],
    ["⚙️ Управление новостями", COMMON_BUTTON_MAIN_MENU]
]

# Тексты кнопок
BUTTON_LATEST_NEWS: Final[str] = "📋 Все новости"
BUTTON_ARCHIVE: Final[str] = "📂 Архив"
BUTTON_SEARCH: Final[str] = "🔍 Поиск"
BUTTON_ADMIN_PANEL: Final[str] = "⚙️ Управление новостями"
BUTTON_MAIN_MENU: Final[str] = COMMON_BUTTON_MAIN_MENU
BUTTON_BACK: Final[str] = "◀️ Назад"
BUTTON_CANCEL: Final[str] = "❌ Отмена"

# ===== КНОПКИ АДМИН-ПАНЕЛИ =====

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

# Кнопки управления категориями
ADMIN_CATEGORY_BUTTONS: Final[List[List[str]]] = [
    ["➕ Добавить категорию"],
    ["◀️ Назад"]
]

BUTTON_ADD_CATEGORY: Final[str] = "➕ Добавить категорию"

# ===== СОСТОЯНИЯ ДИАЛОГА =====

# Состояния пользователя
(
    STATE_SUBMENU,
    STATE_VIEW_NEWS,
    STATE_SEARCH_INPUT,
    STATE_SEARCH_RESULTS,
    STATE_ARCHIVE,
) = range(5)

# Состояния админа (с 100, чтобы избежать конфликтов)
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

# ===== КЛЮЧИ КОНТЕКСТА =====

# Контекст пользователя
CURRENT_PAGE_KEY: Final[str] = "news_current_page"
SEARCH_QUERY_KEY: Final[str] = "news_search_query"
VIEW_MODE_KEY: Final[str] = "news_view_mode"  # режимы: 'latest', 'archive', 'search'

# Контекст админа
ADMIN_CURRENT_ARTICLE_KEY: Final[str] = "news_admin_current_article"
ADMIN_LIST_PAGE_KEY: Final[str] = "news_admin_list_page"
ADMIN_DRAFT_DATA_KEY: Final[str] = "news_admin_draft_data"
ADMIN_EDIT_FIELD_KEY: Final[str] = "news_admin_edit_field"
ADMIN_CURRENT_CATEGORY_KEY: Final[str] = "news_admin_current_category"

# ===== ПРЕФИКСЫ КОЛБЭКОВ =====

# Колбэки пользователя
CALLBACK_PAGE_PREFIX: Final[str] = "news_page_"
CALLBACK_ARTICLE_PREFIX: Final[str] = "news_art_"
CALLBACK_REACT_PREFIX: Final[str] = "news_react_"
CALLBACK_ACK_PREFIX: Final[str] = "news_ack_"
CALLBACK_SEARCH_PAGE_PREFIX: Final[str] = "news_search_"

# Колбэки админа
CALLBACK_ADMIN_ARTICLE_PREFIX: Final[str] = "news_adm_art_"
CALLBACK_ADMIN_PAGE_PREFIX: Final[str] = "news_adm_page_"
CALLBACK_ADMIN_CATEGORY_PREFIX: Final[str] = "news_adm_cat_"
CALLBACK_ADMIN_ACTION_PREFIX: Final[str] = "news_adm_act_"
CALLBACK_ADMIN_EDIT_PREFIX: Final[str] = "news_adm_edit_"
CALLBACK_ADMIN_CONFIRM_PREFIX: Final[str] = "news_adm_conf_"

# Специальные колбэки
CALLBACK_CANCEL: Final[str] = "news_cancel"
CALLBACK_NOOP: Final[str] = "news_noop"
CALLBACK_SKIP: Final[str] = "news_skip"

# ===== ТИПЫ РЕАКЦИЙ =====

REACTION_LIKE: Final[str] = "like"
REACTION_LOVE: Final[str] = "love"
REACTION_DISLIKE: Final[str] = "dislike"

# Соответствие эмодзи реакций
REACTION_EMOJIS: Final[dict] = {
    REACTION_LIKE: "👍",
    REACTION_LOVE: "❤️",
    REACTION_DISLIKE: "👎",
}

# ===== НАСТРОЙКИ РАССЫЛКИ =====

# Задержка между сообщениями в секундах (0.1 = 10 сообщений/с, запас до лимита 30/с)
BROADCAST_DELAY_SECONDS: Final[float] = 0.1

# Интервал обновления прогресса (каждые N пользователей)
BROADCAST_PROGRESS_INTERVAL: Final[int] = 50

# ===== КЛЮЧИ НАСТРОЕК БОТА =====

SETTING_NEWS_EXPIRY_DAYS: Final[str] = "news_expiry_days"
SETTING_MODULE_ENABLED: Final[str] = "module_news_enabled"

# Значения по умолчанию
DEFAULT_NEWS_EXPIRY_DAYS: Final[int] = 30

# ===== ПАГИНАЦИЯ =====

# Максимум элементов на страницу
ITEMS_PER_PAGE: Final[int] = 5

# Максимум символов в сообщении (лимит Telegram 4096, оставляем запас на форматирование)
MAX_MESSAGE_LENGTH: Final[int] = 3800

# ===== СТАТУСЫ СТАТЕЙ =====

STATUS_DRAFT: Final[str] = "draft"
STATUS_PUBLISHED: Final[str] = "published"
STATUS_ARCHIVED: Final[str] = "archived"
