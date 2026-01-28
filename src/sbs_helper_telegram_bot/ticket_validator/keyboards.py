"""
Ticket Validator Module Keyboards

Telegram keyboard builders for the ticket validation module.
"""

from telegram import ReplyKeyboardMarkup
from . import settings


def get_submenu_keyboard() -> ReplyKeyboardMarkup:
    """
    Build ticket validator submenu keyboard for regular users.
    
    Returns:
        ReplyKeyboardMarkup for validator submenu
    """
    return ReplyKeyboardMarkup(
        settings.SUBMENU_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_admin_submenu_keyboard() -> ReplyKeyboardMarkup:
    """
    Build ticket validator submenu keyboard with admin panel button.
    
    Returns:
        ReplyKeyboardMarkup for admin validator submenu
    """
    return ReplyKeyboardMarkup(
        settings.ADMIN_SUBMENU_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_admin_menu_keyboard() -> ReplyKeyboardMarkup:
    """
    Build admin panel main menu keyboard.
    
    Returns:
        ReplyKeyboardMarkup for admin menu
    """
    return ReplyKeyboardMarkup(
        settings.ADMIN_MENU_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_admin_rules_keyboard() -> ReplyKeyboardMarkup:
    """
    Build admin rules management keyboard.
    
    Returns:
        ReplyKeyboardMarkup for rules management
    """
    return ReplyKeyboardMarkup(
        settings.ADMIN_RULES_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_admin_templates_keyboard() -> ReplyKeyboardMarkup:
    """
    Build admin test templates management keyboard.
    
    Returns:
        ReplyKeyboardMarkup for template management
    """
    return ReplyKeyboardMarkup(
        settings.ADMIN_TEMPLATES_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )

