"""
Vyezd Byl (Image Processing) Module Keyboards

Telegram keyboard builders for the image processing module.
"""

from telegram import ReplyKeyboardMarkup
from . import settings


def get_submenu_keyboard() -> ReplyKeyboardMarkup:
    """
    Build image processing module menu keyboard.
    
    Returns:
        ReplyKeyboardMarkup for image processing menu
    """
    return ReplyKeyboardMarkup(
        settings.SUBMENU_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False
    )
