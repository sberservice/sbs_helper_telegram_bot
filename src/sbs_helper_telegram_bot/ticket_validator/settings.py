"""
Настройки модуля валидации заявок

Параметры конфигурации для валидации заявок.
"""

from typing import Final, List

from src.common.messages import BUTTON_MAIN_MENU as COMMON_BUTTON_MAIN_MENU

# Метаданные модуля
MODULE_NAME: Final[str] = "Валидация заявок"
MODULE_DESCRIPTION: Final[str] = "Проверка заявок на соответствие требованиям"
MODULE_VERSION: Final[str] = "1.0.0"
MODULE_AUTHOR: Final[str] = "SberService"

# Кнопка главного меню для этого модуля
MENU_BUTTON_TEXT: Final[str] = "✅ Валидация заявок"

# Тексты кнопок подменю
BUTTON_VALIDATE_TICKET: Final[str] = "📋 Проверить заявку"
BUTTON_FILE_VALIDATION: Final[str] = "📁 Валидация файла"
BUTTON_HELP_VALIDATION: Final[str] = "ℹ️ Помощь по валидации"

# Тексты кнопок админ-подменю
BUTTON_TEST_TEMPLATES: Final[str] = "🧪 Тест шаблонов"
BUTTON_ADMIN_PANEL: Final[str] = "🔐 Админ панель"
BUTTON_ADMIN_MENU: Final[str] = "🔙 Админ меню"

# Конфигурация кнопок подменю
SUBMENU_BUTTONS: Final[List[List[str]]] = [
    [BUTTON_VALIDATE_TICKET, BUTTON_FILE_VALIDATION],
    [BUTTON_HELP_VALIDATION],
    [COMMON_BUTTON_MAIN_MENU]
]

# Админ-подменю (включает админ-панель и тестовые шаблоны)
ADMIN_SUBMENU_BUTTONS: Final[List[List[str]]] = [
    [BUTTON_VALIDATE_TICKET, BUTTON_FILE_VALIDATION],
    [BUTTON_TEST_TEMPLATES, BUTTON_HELP_VALIDATION],
    [BUTTON_ADMIN_PANEL, COMMON_BUTTON_MAIN_MENU]
]

# Кнопки меню админ-панели
ADMIN_MENU_BUTTONS: Final[List[List[str]]] = [
    ["📋 Список правил", "➕ Создать правило"],
    ["📁 Типы заявок", "🧪 Тест шаблоны"],
    [" Тест regex"],
    [COMMON_BUTTON_MAIN_MENU]
]

# Подменю управления правилами админа
ADMIN_RULES_BUTTONS: Final[List[List[str]]] = [
    ["📋 Все правила", "🔍 Найти правило"],
    ["➕ Создать правило", "🔬 Тест regex"],
    [BUTTON_ADMIN_MENU, COMMON_BUTTON_MAIN_MENU]
]

# Подменю управления тестовыми шаблонами админа
ADMIN_TEMPLATES_BUTTONS: Final[List[List[str]]] = [
    ["📋 Все шаблоны", "➕ Создать шаблон"],
    ["▶️ Запустить все тесты"],
    [BUTTON_ADMIN_MENU, COMMON_BUTTON_MAIN_MENU]
]

# Ключи user_data
DEBUG_MODE_KEY: Final[str] = 'validator_debug_mode'

# Настройки валидации
MAX_TICKET_LENGTH: Final[int] = 10000  # Максимум символов в тексте заявки
MIN_TICKET_LENGTH: Final[int] = 20     # Минимум символов для валидной заявки

# Настройки загрузки файлов
MAX_FILE_SIZE_MB: Final[int] = 20  # Максимальный размер файла в МБ
SUPPORTED_FILE_EXTENSIONS: Final[List[str]] = ['.xls', '.xlsx']

# Клавиатура загрузки файла
FILE_UPLOAD_BUTTONS: Final[List[List[str]]] = [
    ["❌ Отмена"]
]

# Настройки проверки адреса по ФИАС
# Провайдер для проверок ФИАС: "dadata" (по умолчанию) или кастомный провайдер
FIAS_PROVIDER: Final[str] = "dadata"
# Шаблон regex по умолчанию для извлечения адреса из текста заявки
FIAS_DEFAULT_ADDRESS_PATTERN: Final[str] = r"Адрес установки POS-терминала:\s*([\s\S]*?)(?=Тип пакета:|$)"
