"""
Настройки модуля Vyezd Byl (обработка изображений).

Конфигурация модуля обработки изображений.
"""

from typing import Final, List

from src.common.messages import BUTTON_MAIN_MENU as COMMON_BUTTON_MAIN_MENU
import os
from dotenv import load_dotenv

load_dotenv()

# Метаданные модуля
MODULE_NAME: Final[str] = "Обработка скриншота"
MODULE_DESCRIPTION: Final[str] = "Обработка скриншотов карт"
MODULE_VERSION: Final[str] = "1.0.0"
MODULE_AUTHOR: Final[str] = "SberService"

# Кнопка главного меню для модуля
MENU_BUTTON_TEXT: Final[str] = "📸 Обработать скриншот"

# Подписи кнопок подменю
BUTTON_SEND_SCREENSHOT: Final[str] = "📸 Отправить скриншот"
BUTTON_SCREENSHOT_HELP: Final[str] = "❓ Помощь по скриншотам"

# Конфигурация кнопок подменю
SUBMENU_BUTTONS: Final[List[List[str]]] = [
    [BUTTON_SEND_SCREENSHOT],
    [BUTTON_SCREENSHOT_HELP],
    [COMMON_BUTTON_MAIN_MENU]
]

# Настройки обработки изображений
MAX_SCREENSHOT_SIZE_BYTES: Final[int] = int(os.getenv("MAX_SCREENSHOT_SIZE_BYTES", "4000000"))
MIN_UPLOADED_IMAGE_HEIGHT: Final[int] = 100
MIN_UPLOADED_IMAGE_WIDTH: Final[int] = 100

# Настройки определения цветов для Яндекс.Карт
# Цвет красного пикселя в первой букве логотипа «Яндекс карты»
DARK_PIXEL_COLOR: Final[tuple] = (150, 5, 5)
LIGHT_PIXEL_COLOR: Final[tuple] = (245, 5, 5)

# Цвет круглой иконки локации с буквой «Я»
DARK_LOCATION_ICON_COLOR: Final[tuple] = (95, 139, 52)
LIGHT_LOCATION_ICON_COLOR: Final[tuple] = (145, 225, 67)

# Цвет треугольной иконки локации
DARK_TRIANGLE_ICON_COLOR: Final[tuple] = (129, 77, 5)
LIGHT_TRIANGLE_ICON_COLOR: Final[tuple] = (214, 126, 5)

# Тёмно-синий цвет рамки, содержащей карту
FRAME_BORDER_COLOR: Final[tuple] = (17, 29, 41)

# Серый цвет рамки, содержащей задачи
TASKS_BORDER_COLOR: Final[tuple] = (238, 238, 238)

# Параметры алгоритма детекции
FAKE_ICON_DEVIATION_FROM_CENTER_PERCENTAGE: Final[float] = 0.1
ALLOWED_COLOR_INTENSITY_DEVIATION: Final[int] = 5
MIN_HEIGHT_TO_START_LOOKING_FOR_GOOD_PIXEL: Final[int] = 150
MAX_HEIGHT_TO_END_LOOK_FOR_GOOD_PIXEL: Final[int] = 400
COLUMN_TO_SCAN_FOR_FRAME_BORDER_COLOR: Final[int] = 1
COLUMN_TO_SCAN_FOR_TASKS_BORDER_COLOR: Final[int] = 1
