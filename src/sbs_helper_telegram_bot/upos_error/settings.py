"""
Настройки модуля ошибок UPOS

Конфигурация модуля для поиска кодов ошибок UPOS.
"""

from typing import Final, List

from src.common.messages import BUTTON_MAIN_MENU

# Метаданные модуля
MODULE_NAME: Final[str] = "UPOS Ошибки"
MODULE_DESCRIPTION: Final[str] = "Поиск кодов ошибок UPOS и рекомендаций по их устранению"
MODULE_VERSION: Final[str] = "1.0.0"
MODULE_AUTHOR: Final[str] = "SberService"

# Кнопка главного меню для этого модуля
MENU_BUTTON_TEXT: Final[str] = "🔢 UPOS Ошибки"

# Подписи кнопок подменю
BUTTON_FIND_ERROR: Final[str] = "🔍 Найти код ошибки"
BUTTON_POPULAR_ERRORS: Final[str] = "📊 Популярные ошибки"
BUTTON_ADMIN_PANEL: Final[str] = "🔐 Админ UPOS"
BUTTON_ADMIN_BACK: Final[str] = "🔙 Админ UPOS"

# Подписи кнопок админ-меню
BUTTON_ADMIN_LIST_ERRORS: Final[str] = "📋 Список ошибок"
BUTTON_ADMIN_FIND_ERROR: Final[str] = "🔍 Найти ошибку"
BUTTON_ADMIN_ADD_ERROR: Final[str] = "➕ Добавить ошибку"
BUTTON_ADMIN_CATEGORIES: Final[str] = "📁 Категории"
BUTTON_ADMIN_UNKNOWN: Final[str] = "❓ Неизвестные коды"
BUTTON_ADMIN_STATS: Final[str] = "📈 Статистика"
BUTTON_ADMIN_IMPORT_CSV: Final[str] = "📥 Импорт CSV"
BUTTON_ADMIN_BACK_TO_UPOS: Final[str] = "🔙 Назад в UPOS"

# Подписи кнопок управления категориями/ошибками (админ)
BUTTON_ADMIN_ALL_CATEGORIES: Final[str] = "📋 Все категории"
BUTTON_ADMIN_ADD_CATEGORY: Final[str] = "➕ Добавить категорию"
BUTTON_ADMIN_ALL_ERRORS: Final[str] = "📋 Все ошибки"

# Конфигурация кнопок подменю (обычные пользователи)
SUBMENU_BUTTONS: Final[List[List[str]]] = [
    [BUTTON_POPULAR_ERRORS],
    [BUTTON_MAIN_MENU]
]

# Админское подменю (включает кнопку админ-панели)
ADMIN_SUBMENU_BUTTONS: Final[List[List[str]]] = [
    [BUTTON_POPULAR_ERRORS],
    [BUTTON_ADMIN_PANEL, BUTTON_MAIN_MENU]
]

# Кнопки меню админ-панели
ADMIN_MENU_BUTTONS: Final[List[List[str]]] = [
    [BUTTON_ADMIN_LIST_ERRORS, BUTTON_ADMIN_FIND_ERROR],
    [BUTTON_ADMIN_ADD_ERROR, BUTTON_ADMIN_CATEGORIES],
    [BUTTON_ADMIN_UNKNOWN, BUTTON_ADMIN_STATS],
    [BUTTON_ADMIN_IMPORT_CSV, BUTTON_ADMIN_BACK_TO_UPOS]
]

# Подменю управления категориями (админ)
ADMIN_CATEGORIES_BUTTONS: Final[List[List[str]]] = [
    [BUTTON_ADMIN_ALL_CATEGORIES, BUTTON_ADMIN_ADD_CATEGORY],
    [BUTTON_ADMIN_BACK, BUTTON_MAIN_MENU]
]

# Подменю управления кодами ошибок (админ)
ADMIN_ERRORS_BUTTONS: Final[List[List[str]]] = [
    [BUTTON_ADMIN_ALL_ERRORS, BUTTON_ADMIN_FIND_ERROR],
    [BUTTON_ADMIN_ADD_ERROR],
    [BUTTON_ADMIN_BACK, BUTTON_MAIN_MENU]
]

# Настройки пагинации
ERRORS_PER_PAGE: Final[int] = 10
CATEGORIES_PER_PAGE: Final[int] = 10
UNKNOWN_CODES_PER_PAGE: Final[int] = 15

# Количество популярных ошибок для отображения
TOP_POPULAR_COUNT: Final[int] = 10
