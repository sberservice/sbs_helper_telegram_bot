from typing import Final, List
import os
from src.common.messages import BUTTON_MAIN_MENU as COMMON_BUTTON_MAIN_MENU
from dotenv import load_dotenv

load_dotenv()

# =============================================
# GLOBAL SETTINGS
# Settings that apply to the entire application
# =============================================

DEBUG: Final[bool] = os.getenv("DEBUG", "0") == "1"
INVITES_PER_NEW_USER: Final[int] = int(os.getenv("INVITES_PER_NEW_USER", "2"))

# Telegram API network settings
TELEGRAM_HTTP_MAX_RETRIES: Final[int] = int(os.getenv("TELEGRAM_HTTP_MAX_RETRIES", "3"))
TELEGRAM_HTTP_RETRY_BACKOFF_SECONDS: Final[int] = int(
    os.getenv("TELEGRAM_HTTP_RETRY_BACKOFF_SECONDS", "2")
)
TELEGRAM_SEND_MSG_CONNECT_TIMEOUT_SECONDS: Final[int] = int(
    os.getenv("TELEGRAM_SEND_MSG_CONNECT_TIMEOUT_SECONDS", "30")
)
TELEGRAM_SEND_MSG_READ_TIMEOUT_SECONDS: Final[int] = int(
    os.getenv("TELEGRAM_SEND_MSG_READ_TIMEOUT_SECONDS", "20")
)
TELEGRAM_SEND_DOC_CONNECT_TIMEOUT_SECONDS: Final[int] = int(
    os.getenv("TELEGRAM_SEND_DOC_CONNECT_TIMEOUT_SECONDS", "120")
)
TELEGRAM_SEND_DOC_READ_TIMEOUT_SECONDS: Final[int] = int(
    os.getenv("TELEGRAM_SEND_DOC_READ_TIMEOUT_SECONDS", "180")
)

# =============================================
# DEPRECATED: Module-specific settings below
# These are kept for backwards compatibility but
# should be imported from respective module settings:
# - src.sbs_helper_telegram_bot.ticket_validator.settings
# - src.sbs_helper_telegram_bot.vyezd_byl.settings
# =============================================

# Image processing settings (use vyezd_byl.settings instead)
MAX_SCREENSHOT_SIZE_BYTES: Final[int] = int(os.getenv("MAX_SCREENSHOT_SIZE_BYTES", "4000000"))
MIN_UPLOADED_IMAGE_HEIGHT = 100
MIN_UPLOADED_IMAGE_WIDTH = 100

# Pixel color detection (use vyezd_byl.settings instead)
DARK_PIXEL_COLOR = (150, 5, 5)
LIGHT_PIXEL_COLOR = (245, 5, 5)
DARK_LOCATION_ICON_COLOR = (95, 139, 52)
LIGHT_LOCATION_ICON_COLOR = (145, 225, 67)
DARK_TRIANGLE_ICON_COLOR = (129, 77, 5)
LIGHT_TRIANGLE_ICON_COLOR = (214, 126, 5)
FRAME_BORDER_COLOR = (17, 29, 41)
TASKS_BORDER_COLOR = (238, 238, 238)

# Detection algorithm parameters (use vyezd_byl.settings instead)
FAKE_ICON_DEVIATION_FROM_CENTER_PERCENTAGE = 0.1
ALLOWED_COLOR_INTENSITY_DEVIATION = 5
MIN_HEIGHT_TO_START_LOOKING_FOR_GOOD_PIXEL = 150
MAX_HEIGHT_TO_END_LOOK_FOR_GOOD_PIXEL = 400
COLUMN_TO_SCAN_FOR_FRAME_BORDER_COLOR = 1
COLUMN_TO_SCAN_FOR_TASKS_BORDER_COLOR = 1

# Menu button configurations (use module settings instead)
VALIDATOR_SUBMENU_BUTTONS = [
    ["📋 Проверить заявку", "📜 История проверок"],
    ["ℹ️ Помощь по валидации"],
    [COMMON_BUTTON_MAIN_MENU]
]

ADMIN_VALIDATOR_SUBMENU_BUTTONS = [
    ["📋 Проверить заявку", "📜 История проверок"],
    ["🧪 Тест шаблонов", "ℹ️ Помощь по валидации"],
    ["🔐 Админ панель", COMMON_BUTTON_MAIN_MENU]
]

IMAGE_MENU_BUTTONS = [
    ["📸 Отправить скриншот"],
    ["❓ Помощь по скриншотам"],
    [COMMON_BUTTON_MAIN_MENU]
]

ADMIN_MENU_BUTTONS = [
    ["📋 Список правил", "➕ Создать правило"],
    ["📁 Типы заявок", "🧪 Тест шаблоны"],
    ["🔬 Тест regex", COMMON_BUTTON_MAIN_MENU]
]

ADMIN_RULES_BUTTONS = [
    ["📋 Все правила", "🔍 Найти правило"],
    ["➕ Создать правило", "🔬 Тест regex"],
    ["🔙 Админ меню", COMMON_BUTTON_MAIN_MENU]
]

ADMIN_TEMPLATES_BUTTONS = [
    ["📋 Все шаблоны", "➕ Создать шаблон"],
    ["▶️ Запустить все тесты"],
    ["🔙 Админ меню", COMMON_BUTTON_MAIN_MENU]
]
