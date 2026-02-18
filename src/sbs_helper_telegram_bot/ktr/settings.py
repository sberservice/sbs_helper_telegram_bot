"""
Настройки модуля КТР

Конфигурация модуля для поиска кодов КТР (Коэффициент Трудозатрат).
"""

from typing import Final, List

from src.common.messages import BUTTON_MAIN_MENU as COMMON_BUTTON_MAIN_MENU

# Метаданные модуля
MODULE_NAME: Final[str] = "КТР"
MODULE_DESCRIPTION: Final[str] = "Поиск кодов КТР и значений трудозатрат в минутах"
MODULE_VERSION: Final[str] = "1.0.0"
MODULE_AUTHOR: Final[str] = "SberService"

# Кнопка главного меню для этого модуля
MENU_BUTTON_TEXT: Final[str] = "⏱️ КТР"

# Подписи кнопок подменю
BUTTON_FIND_CODE: Final[str] = "🔍 Найти код КТР"
BUTTON_POPULAR_CODES: Final[str] = "📊 Популярные коды"
BUTTON_ACHIEVEMENTS: Final[str] = "🎖️ Достижения"
BUTTON_ADMIN_PANEL: Final[str] = "🔐 Админ КТР"
BUTTON_ADMIN_BACK: Final[str] = "🔙 Админ КТР"

# Подписи кнопок админ-меню
BUTTON_ADMIN_LIST_CODES: Final[str] = "📋 Список кодов"
BUTTON_ADMIN_ADD_CODE: Final[str] = "➕ Добавить код"
BUTTON_ADMIN_SEARCH_CODE: Final[str] = "🔍 Найти код"
BUTTON_ADMIN_CATEGORIES: Final[str] = "📁 Категории"
BUTTON_ADMIN_UNKNOWN_CODES: Final[str] = "❓ Неизвестные коды"
BUTTON_ADMIN_STATS: Final[str] = "📈 Статистика"
BUTTON_ADMIN_IMPORT_CSV: Final[str] = "📥 Импорт CSV"
BUTTON_ADMIN_SET_LAST_UPDATE_DATE: Final[str] = "📅 Дата обновления КТР"
BUTTON_ADMIN_BACK_TO_KTR: Final[str] = "🔙 Назад в КТР"

# Ключ настройки в bot_settings для даты последнего обновления общего файла КТР
KTR_LAST_UPDATE_SETTING_KEY: Final[str] = "ktr_last_update_date"

# Подписи кнопок подменю категорий/кодов (админ)
BUTTON_ADMIN_ALL_CATEGORIES: Final[str] = "📋 Все категории"
BUTTON_ADMIN_ADD_CATEGORY: Final[str] = "➕ Добавить категорию"
BUTTON_ADMIN_ALL_CODES: Final[str] = "📋 Все коды"

# Конфигурация кнопок подменю (обычные пользователи)
SUBMENU_BUTTONS: Final[List[List[str]]] = [
    [BUTTON_POPULAR_CODES, BUTTON_ACHIEVEMENTS],
    [COMMON_BUTTON_MAIN_MENU]
]

# Админское подменю (включает кнопку админ-панели)
ADMIN_SUBMENU_BUTTONS: Final[List[List[str]]] = [
    [BUTTON_POPULAR_CODES, BUTTON_ACHIEVEMENTS],
    [BUTTON_ADMIN_PANEL, COMMON_BUTTON_MAIN_MENU]
]

# Кнопки меню админ-панели
ADMIN_MENU_BUTTONS: Final[List[List[str]]] = [
    [BUTTON_ADMIN_LIST_CODES, BUTTON_ADMIN_SEARCH_CODE],
    [BUTTON_ADMIN_ADD_CODE, BUTTON_ADMIN_CATEGORIES],
    [BUTTON_ADMIN_UNKNOWN_CODES, BUTTON_ADMIN_STATS],
    [BUTTON_ADMIN_IMPORT_CSV, BUTTON_ADMIN_SET_LAST_UPDATE_DATE],
    [BUTTON_ADMIN_BACK_TO_KTR]
]

# Подменю управления категориями (админ)
ADMIN_CATEGORIES_BUTTONS: Final[List[List[str]]] = [
    [BUTTON_ADMIN_ALL_CATEGORIES, BUTTON_ADMIN_ADD_CATEGORY],
    [BUTTON_ADMIN_BACK, COMMON_BUTTON_MAIN_MENU]
]

# Подменю управления кодами КТР (админ)
ADMIN_CODES_BUTTONS: Final[List[List[str]]] = [
    [BUTTON_ADMIN_ALL_CODES, BUTTON_ADMIN_SEARCH_CODE],
    [BUTTON_ADMIN_ADD_CODE],
    [BUTTON_ADMIN_BACK, COMMON_BUTTON_MAIN_MENU]
]

# Настройки пагинации
CODES_PER_PAGE: Final[int] = 10
CATEGORIES_PER_PAGE: Final[int] = 10
UNKNOWN_CODES_PER_PAGE: Final[int] = 15

# Количество популярных кодов для отображения
TOP_POPULAR_COUNT: Final[int] = 10
