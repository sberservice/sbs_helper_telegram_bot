"""
Ticket Validator Module Settings

Module-specific configuration settings for ticket validation.
"""

from typing import Final, List

# Module metadata
MODULE_NAME: Final[str] = "Валидация заявок"
MODULE_DESCRIPTION: Final[str] = "Проверка заявок на соответствие требованиям"
MODULE_VERSION: Final[str] = "1.0.0"
MODULE_AUTHOR: Final[str] = "SberService"

# Main menu button for this module
MENU_BUTTON_TEXT: Final[str] = "✅ Валидация заявок"

# Submenu button configuration
SUBMENU_BUTTONS: Final[List[List[str]]] = [
    ["📋 Проверить заявку", "📁 Валидация файла"],
    ["ℹ️ Помощь по валидации"],
    ["🏠 Главное меню"]
]

# Admin submenu (includes admin panel and test templates buttons)
ADMIN_SUBMENU_BUTTONS: Final[List[List[str]]] = [
    ["📋 Проверить заявку", "📁 Валидация файла"],
    ["🧪 Тест шаблонов", "ℹ️ Помощь по валидации"],
    ["🔐 Админ панель", "🏠 Главное меню"]
]

# Admin panel menu buttons
ADMIN_MENU_BUTTONS: Final[List[List[str]]] = [
    ["📋 Список правил", "➕ Создать правило"],
    ["📁 Типы заявок", "🧪 Тест шаблоны"],
    [" Тест regex"],
    ["🏠 Главное меню"]
]

# Admin rules management submenu
ADMIN_RULES_BUTTONS: Final[List[List[str]]] = [
    ["📋 Все правила", "🔍 Найти правило"],
    ["➕ Создать правило", "🔬 Тест regex"],
    ["🔙 Админ меню", "🏠 Главное меню"]
]

# Admin test templates management submenu
ADMIN_TEMPLATES_BUTTONS: Final[List[List[str]]] = [
    ["📋 Все шаблоны", "➕ Создать шаблон"],
    ["▶️ Запустить все тесты"],
    ["🔙 Админ меню", "🏠 Главное меню"]
]

# User data keys
DEBUG_MODE_KEY: Final[str] = 'validator_debug_mode'

# Validation settings
MAX_TICKET_LENGTH: Final[int] = 10000  # Maximum characters in ticket text
MIN_TICKET_LENGTH: Final[int] = 20     # Minimum characters for valid ticket

# File upload settings
MAX_FILE_SIZE_MB: Final[int] = 20  # Maximum file size in MB
SUPPORTED_FILE_EXTENSIONS: Final[List[str]] = ['.xls', '.xlsx']

# File upload keyboard
FILE_UPLOAD_BUTTONS: Final[List[List[str]]] = [
    ["❌ Отмена"]
]

# FIAS address validation settings
# Provider to use for FIAS checks: "dadata" (default) or a custom provider
FIAS_PROVIDER: Final[str] = "dadata"
# Default regex pattern to extract the address from ticket text
FIAS_DEFAULT_ADDRESS_PATTERN: Final[str] = r"Адрес установки POS-терминала:\s*([\s\S]*?)(?=Тип пакета:|$)"
