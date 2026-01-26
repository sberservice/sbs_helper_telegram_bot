"""
UPOS Error Module Settings

Module-specific configuration settings for UPOS error code lookup.
"""

from typing import Final, List

# Module metadata
MODULE_NAME: Final[str] = "UPOS Ошибки"
MODULE_DESCRIPTION: Final[str] = "Поиск кодов ошибок UPOS и рекомендаций по их устранению"
MODULE_VERSION: Final[str] = "1.0.0"
MODULE_AUTHOR: Final[str] = "SberService"

# Main menu button for this module
MENU_BUTTON_TEXT: Final[str] = "🔢 UPOS Ошибки"

# Submenu button configuration (regular users)
SUBMENU_BUTTONS: Final[List[List[str]]] = [
    ["🔍 Найти код ошибки"],
    ["📊 Популярные ошибки"],
    ["🏠 Главное меню"]
]

# Admin submenu (includes admin panel button)
ADMIN_SUBMENU_BUTTONS: Final[List[List[str]]] = [
    ["🔍 Найти код ошибки"],
    ["📊 Популярные ошибки"],
    ["🔐 Админ UPOS", "🏠 Главное меню"]
]

# Admin panel menu buttons
ADMIN_MENU_BUTTONS: Final[List[List[str]]] = [
    ["📋 Список ошибок", "➕ Добавить ошибку"],
    ["📁 Категории", "❓ Неизвестные коды"],
    ["� Импорт CSV", "📈 Статистика"],
    ["🔙 Назад в UPOS"]
]

# Admin categories management submenu
ADMIN_CATEGORIES_BUTTONS: Final[List[List[str]]] = [
    ["📋 Все категории", "➕ Добавить категорию"],
    ["🔙 Админ UPOS", "🏠 Главное меню"]
]

# Admin error codes management submenu
ADMIN_ERRORS_BUTTONS: Final[List[List[str]]] = [
    ["📋 Все ошибки", "🔍 Найти ошибку"],
    ["➕ Добавить ошибку"],
    ["🔙 Админ UPOS", "🏠 Главное меню"]
]

# Pagination settings
ERRORS_PER_PAGE: Final[int] = 10
CATEGORIES_PER_PAGE: Final[int] = 10
UNKNOWN_CODES_PER_PAGE: Final[int] = 15

# Top popular errors to show
TOP_POPULAR_COUNT: Final[int] = 10
