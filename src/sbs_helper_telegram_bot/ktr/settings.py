"""
KTR Module Settings

Module-specific configuration settings for KTR (Коэффициент Трудозатрат) code lookup.
"""

from typing import Final, List

# Module metadata
MODULE_NAME: Final[str] = "КТР"
MODULE_DESCRIPTION: Final[str] = "Поиск кодов КТР и значений трудозатрат в минутах"
MODULE_VERSION: Final[str] = "1.0.0"
MODULE_AUTHOR: Final[str] = "SberService"

# Main menu button for this module
MENU_BUTTON_TEXT: Final[str] = "⏱️ КТР"

# Submenu button configuration (regular users)
SUBMENU_BUTTONS: Final[List[List[str]]] = [
    ["🔍 Найти код КТР"],
    ["📊 Популярные коды"],
    ["🏠 Главное меню"]
]

# Admin submenu (includes admin panel button)
ADMIN_SUBMENU_BUTTONS: Final[List[List[str]]] = [
    ["🔍 Найти код КТР"],
    ["📊 Популярные коды"],
    ["🔐 Админ КТР", "🏠 Главное меню"]
]

# Admin panel menu buttons
ADMIN_MENU_BUTTONS: Final[List[List[str]]] = [
    ["📋 Список кодов", "🔍 Найти код"],
    ["➕ Добавить код", "📁 Категории"],
    ["❓ Неизвестные коды", "📈 Статистика"],
    ["📥 Импорт CSV", "🔙 Назад в КТР"]
]

# Admin categories management submenu
ADMIN_CATEGORIES_BUTTONS: Final[List[List[str]]] = [
    ["📋 Все категории", "➕ Добавить категорию"],
    ["🔙 Админ КТР", "🏠 Главное меню"]
]

# Admin KTR codes management submenu
ADMIN_CODES_BUTTONS: Final[List[List[str]]] = [
    ["📋 Все коды", "🔍 Найти код"],
    ["➕ Добавить код"],
    ["🔙 Админ КТР", "🏠 Главное меню"]
]

# Pagination settings
CODES_PER_PAGE: Final[int] = 10
CATEGORIES_PER_PAGE: Final[int] = 10
UNKNOWN_CODES_PER_PAGE: Final[int] = 15

# Top popular codes to show
TOP_POPULAR_COUNT: Final[int] = 10
