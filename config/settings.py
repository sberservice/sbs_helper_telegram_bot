"""
settings.py — общие настройки Telegram-бота.

Содержит глобальные параметры приложения и сетевые настройки
Telegram API. Для AI/RAG настроек см. config/ai_settings.py,
для настроек БД — config/database_settings.py.
"""

from typing import Final
import os
from dotenv import load_dotenv

load_dotenv()

# =============================================
# GLOBAL SETTINGS
# Общие настройки приложения
# =============================================

DEBUG: Final[bool] = os.getenv("DEBUG", "0") == "1"
INVITES_PER_NEW_USER: Final[int] = int(os.getenv("INVITES_PER_NEW_USER", "2"))

# =============================================
# Telegram API network settings
# Сетевые настройки для взаимодействия с Telegram Bot API
# =============================================

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
# Настройки обработки изображений (vyezd_byl)
# =============================================

MAX_SCREENSHOT_SIZE_BYTES: Final[int] = int(os.getenv("MAX_SCREENSHOT_SIZE_BYTES", "4000000"))
MIN_UPLOADED_IMAGE_HEIGHT: Final[int] = 100
MIN_UPLOADED_IMAGE_WIDTH: Final[int] = 100

# Пороги цветов для детекции пикселей.
DARK_PIXEL_COLOR = (150, 5, 5)
LIGHT_PIXEL_COLOR = (245, 5, 5)
DARK_LOCATION_ICON_COLOR = (95, 139, 52)
LIGHT_LOCATION_ICON_COLOR = (145, 225, 67)
DARK_TRIANGLE_ICON_COLOR = (129, 77, 5)
LIGHT_TRIANGLE_ICON_COLOR = (214, 126, 5)
FRAME_BORDER_COLOR = (17, 29, 41)
TASKS_BORDER_COLOR = (238, 238, 238)

# Параметры алгоритма детекции.
FAKE_ICON_DEVIATION_FROM_CENTER_PERCENTAGE: Final[float] = 0.1
ALLOWED_COLOR_INTENSITY_DEVIATION: Final[int] = 5
MIN_HEIGHT_TO_START_LOOKING_FOR_GOOD_PIXEL: Final[int] = 150
MAX_HEIGHT_TO_END_LOOK_FOR_GOOD_PIXEL: Final[int] = 400
COLUMN_TO_SCAN_FOR_FRAME_BORDER_COLOR: Final[int] = 1
COLUMN_TO_SCAN_FOR_TASKS_BORDER_COLOR: Final[int] = 1
