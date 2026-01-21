from typing import Final
import os
from dotenv import load_dotenv

load_dotenv()

DEBUG: Final[bool] = os.getenv("DEBUG", "0") == "1"
INVITES_PER_NEW_USER: Final[int] = int(os.getenv("INVITES_PER_NEW_USER", "2"))
MAX_SCREENSHOT_SIZE_BYTES: Final[int] = int(os.getenv("MAX_SCREENSHOT_SIZE_BYTES", "4000000"))

MIN_UPLOADED_IMAGE_HEIGHT = 100
MIN_UPLOADED_IMAGE_WIDTH = 100

# These values describe the color of the red pixel in the first letter of Яндекс карты logo
DARK_PIXEL_COLOR = (150, 5, 5)
LIGHT_PIXEL_COLOR = (245, 5, 5)

# These values describe the color of the round location icon with the letter Я
DARK_LOCATION_ICON_COLOR=(95,139,52)
LIGHT_LOCATION_ICON_COLOR=(145,225,67)

# These values describe the color of the triangle location icon
DARK_TRIANGLE_ICON_COLOR=(129,77,5)
LIGHT_TRIANGLE_ICON_COLOR=(214,126,5)

# These values the navy color of the border of the frame which contains the map
FRAME_BORDER_COLOR=(17,29,41)

# These values the grey color of the border of the frame which contains tasks
TASKS_BORDER_COLOR =(238,238,238)


#########

FAKE_ICON_DEVIATION_FROM_CENTER_PERCENTAGE = 0.1
ALLOWED_COLOR_INTENSITY_DEVIATION = 5
MIN_HEIGHT_TO_START_LOOKING_FOR_GOOD_PIXEL=150
MAX_HEIGHT_TO_END_LOOK_FOR_GOOD_PIXEL=400
COLUMN_TO_SCAN_FOR_FRAME_BORDER_COLOR = 1
COLUMN_TO_SCAN_FOR_TASKS_BORDER_COLOR = 1

#########
# TELEGRAM MENU BUTTONS CONFIGURATION
#########

# Main menu buttons shown to all authorized users
MAIN_MENU_BUTTONS = [
    ["✅ Валидация заявок", "📸 Обработать скриншот"],
    ["🎫 Мои инвайты"]
]

# Ticket validator submenu - shown when user clicks validation button
VALIDATOR_SUBMENU_BUTTONS = [
    ["📋 Проверить заявку", "📜 История проверок"],
    ["📄 Шаблоны заявок", "ℹ️ Помощь по валидации"],
    ["🏠 Главное меню"]
]

# Image processing module menu
IMAGE_MENU_BUTTONS = [
    ["📸 Отправить скриншот"],
    ["🏠 Главное меню"]
]
