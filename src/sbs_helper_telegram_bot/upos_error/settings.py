"""
UPOS Error Module Settings

Module-specific configuration settings for UPOS error code lookup.
"""

from typing import Final, List

from src.common.messages import BUTTON_MAIN_MENU

# Module metadata
MODULE_NAME: Final[str] = "UPOS Ошибки"
MODULE_DESCRIPTION: Final[str] = "Поиск кодов ошибок UPOS и рекомендаций по их устранению"
MODULE_VERSION: Final[str] = "1.0.0"
MODULE_AUTHOR: Final[str] = "SberService"

# Main menu button for this module
MENU_BUTTON_TEXT: Final[str] = "🔢 UPOS Ошибки"

# Submenu button texts
BUTTON_FIND_ERROR: Final[str] = "🔍 Найти код ошибки"
BUTTON_POPULAR_ERRORS: Final[str] = "📊 Популярные ошибки"
BUTTON_ADMIN_PANEL: Final[str] = "🔐 Админ UPOS"
BUTTON_ADMIN_BACK: Final[str] = "🔙 Админ UPOS"

# Admin menu button texts
BUTTON_ADMIN_LIST_ERRORS: Final[str] = "📋 Список ошибок"
BUTTON_ADMIN_FIND_ERROR: Final[str] = "🔍 Найти ошибку"
BUTTON_ADMIN_ADD_ERROR: Final[str] = "➕ Добавить ошибку"
BUTTON_ADMIN_CATEGORIES: Final[str] = "📁 Категории"
BUTTON_ADMIN_UNKNOWN: Final[str] = "❓ Неизвестные коды"
BUTTON_ADMIN_STATS: Final[str] = "📈 Статистика"
BUTTON_ADMIN_IMPORT_CSV: Final[str] = "📥 Импорт CSV"
BUTTON_ADMIN_BACK_TO_UPOS: Final[str] = "🔙 Назад в UPOS"

# Admin categories/errors management button texts
BUTTON_ADMIN_ALL_CATEGORIES: Final[str] = "📋 Все категории"
BUTTON_ADMIN_ADD_CATEGORY: Final[str] = "➕ Добавить категорию"
BUTTON_ADMIN_ALL_ERRORS: Final[str] = "📋 Все ошибки"

# Submenu button configuration (regular users)
SUBMENU_BUTTONS: Final[List[List[str]]] = [
    [BUTTON_FIND_ERROR],
    [BUTTON_POPULAR_ERRORS],
    [BUTTON_MAIN_MENU]
]

# Admin submenu (includes admin panel button)
ADMIN_SUBMENU_BUTTONS: Final[List[List[str]]] = [
    [BUTTON_FIND_ERROR],
    [BUTTON_POPULAR_ERRORS],
    [BUTTON_ADMIN_PANEL, BUTTON_MAIN_MENU]
]

# Admin panel menu buttons
ADMIN_MENU_BUTTONS: Final[List[List[str]]] = [
    [BUTTON_ADMIN_LIST_ERRORS, BUTTON_ADMIN_FIND_ERROR],
    [BUTTON_ADMIN_ADD_ERROR, BUTTON_ADMIN_CATEGORIES],
    [BUTTON_ADMIN_UNKNOWN, BUTTON_ADMIN_STATS],
    [BUTTON_ADMIN_IMPORT_CSV, BUTTON_ADMIN_BACK_TO_UPOS]
]

# Admin categories management submenu
ADMIN_CATEGORIES_BUTTONS: Final[List[List[str]]] = [
    [BUTTON_ADMIN_ALL_CATEGORIES, BUTTON_ADMIN_ADD_CATEGORY],
    [BUTTON_ADMIN_BACK, BUTTON_MAIN_MENU]
]

# Admin error codes management submenu
ADMIN_ERRORS_BUTTONS: Final[List[List[str]]] = [
    [BUTTON_ADMIN_ALL_ERRORS, BUTTON_ADMIN_FIND_ERROR],
    [BUTTON_ADMIN_ADD_ERROR],
    [BUTTON_ADMIN_BACK, BUTTON_MAIN_MENU]
]

# Pagination settings
ERRORS_PER_PAGE: Final[int] = 10
CATEGORIES_PER_PAGE: Final[int] = 10
UNKNOWN_CODES_PER_PAGE: Final[int] = 15

# Top popular errors to show
TOP_POPULAR_COUNT: Final[int] = 10
