"""
Bot Admin Module Settings

Configuration settings for bot-wide administration.
"""

from typing import Final, List

from src.common.messages import BUTTON_MAIN_MENU as COMMON_BUTTON_MAIN_MENU

# Module metadata
MODULE_NAME: Final[str] = "Администрирование бота"
MODULE_DESCRIPTION: Final[str] = "Управление пользователями и настройками бота"

# Main bot admin menu button
BUTTON_BOT_ADMIN: Final[str] = "🛠️ Админ бота"

# Bot admin main menu buttons
ADMIN_MENU_BUTTONS: Final[List[List[str]]] = [
    ["👥 Пользователи", "👤 Пре-инвайты"],
    ["➕ Ручные пользователи"],
    ["📊 Статистика", "🎫 Инвайты"],
    ["⚙️ Настройки бота"],
    [COMMON_BUTTON_MAIN_MENU]
]

# User management submenu
USER_MANAGEMENT_BUTTONS: Final[List[List[str]]] = [
    ["📋 Список пользователей"],
    ["🔍 Поиск пользователя"],
    ["👑 Список админов"],
    ["🔙 Админ бота", COMMON_BUTTON_MAIN_MENU]
]

# Pre-invite management submenu
PREINVITE_BUTTONS: Final[List[List[str]]] = [
    ["📋 Список пре-инвайтов"],
    ["➕ Добавить пользователя"],
    ["🔙 Админ бота", COMMON_BUTTON_MAIN_MENU]
]

# Manual users management submenu
MANUAL_USERS_BUTTONS: Final[List[List[str]]] = [
    ["📋 Список ручных пользователей"],
    ["➕ Добавить ручного пользователя"],
    ["🔙 Админ бота", COMMON_BUTTON_MAIN_MENU]
]

# Statistics submenu
STATISTICS_BUTTONS: Final[List[List[str]]] = [
    ["📈 Общая статистика"],
    ["📅 Статистика за период"],
    ["🔙 Админ бота", COMMON_BUTTON_MAIN_MENU]
]

# Invite management submenu
INVITE_MANAGEMENT_BUTTONS: Final[List[List[str]]] = [
    ["📋 Все инвайты"],
    ["🎁 Выдать инвайты"],
    ["🔙 Админ бота", COMMON_BUTTON_MAIN_MENU]
]

# Bot settings submenu
BOT_SETTINGS_BUTTONS: Final[List[List[str]]] = [
    ["🔐 Инвайт-система"],
    ["🧩 Модули"],
    ["🔙 Админ бота", COMMON_BUTTON_MAIN_MENU]
]

# Modules management submenu
MODULES_MANAGEMENT_BUTTONS: Final[List[List[str]]] = [
    ["🔙 Настройки бота", COMMON_BUTTON_MAIN_MENU]
]

# Pagination settings
USERS_PER_PAGE: Final[int] = 10
INVITES_PER_PAGE: Final[int] = 15
