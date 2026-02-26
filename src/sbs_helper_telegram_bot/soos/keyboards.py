"""
Клавиатуры модуля СООС.
"""

from telegram import ReplyKeyboardMarkup

from . import settings


def get_submenu_keyboard() -> ReplyKeyboardMarkup:
    """
    Собрать клавиатуру подменю модуля СООС.

    Returns:
        Клавиатура подменю.
    """
    return ReplyKeyboardMarkup(
        settings.SUBMENU_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True,
    )
