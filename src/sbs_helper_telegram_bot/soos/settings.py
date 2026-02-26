"""
Настройки модуля СООС.
"""

from typing import Final, List

from src.common.messages import BUTTON_MAIN_MENU as COMMON_BUTTON_MAIN_MENU

MODULE_NAME: Final[str] = "СООС"
MODULE_DESCRIPTION: Final[str] = "Генерация чека сверки итогов из текста тикета"
MODULE_VERSION: Final[str] = "1.0.0"
MODULE_AUTHOR: Final[str] = "SberService"

MENU_BUTTON_TEXT: Final[str] = "🧾 СООС"
BUTTON_GENERATE_SOOS: Final[str] = "🧾 Сформировать СООС"
BUTTON_SOOS_HELP: Final[str] = "❓ Помощь по СООС"

SUBMENU_BUTTONS: Final[List[List[str]]] = [
    [BUTTON_GENERATE_SOOS],
    [BUTTON_SOOS_HELP],
    [COMMON_BUTTON_MAIN_MENU],
]

RECEIPT_WIDTH_CHARS: Final[int] = 32
RECEIPT_FONT_SIZE: Final[int] = 18
RECEIPT_PADDING_X: Final[int] = 24 #24
RECEIPT_PADDING_Y: Final[int] = 20 #20
RECEIPT_LINE_SPACING: Final[int] = 6

TERMINAL_BG_COLOR: Final[tuple[int, int, int]] = (0, 0, 0)
TERMINAL_TEXT_COLOR: Final[tuple[int, int, int]] = (245, 245, 245)

SOOS_QUEUE_TABLE: Final[str] = "soos_image_queue"
