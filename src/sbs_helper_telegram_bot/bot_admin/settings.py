"""
Bot Admin Module Settings

Configuration settings for bot-wide administration.
"""

from typing import Final, List

# Module metadata
MODULE_NAME: Final[str] = "Администрирование бота"
MODULE_DESCRIPTION: Final[str] = "Управление пользователями и настройками бота"

# Main bot admin menu button
BUTTON_BOT_ADMIN: Final[str] = "🛠️ Админ бота"

# Bot admin main menu buttons
ADMIN_MENU_BUTTONS: Final[List[List[str]]] = [
    ["👥 Пользователи", "👤 Пре-инвайты"],
    ["📊 Статистика", "🎫 Инвайты"],
    ["⚙️ Настройки бота"],
    ["🏠 Главное меню"]
]

# User management submenu
USER_MANAGEMENT_BUTTONS: Final[List[List[str]]] = [
    ["📋 Список пользователей"],
    ["🔍 Поиск пользователя"],
    ["👑 Список админов"],
    ["🔙 Админ бота", "🏠 Главное меню"]
]

# Pre-invite management submenu
PREINVITE_BUTTONS: Final[List[List[str]]] = [
    ["📋 Список пре-инвайтов"],
    ["➕ Добавить пользователя"],
    ["🔙 Админ бота", "🏠 Главное меню"]
]

# Statistics submenu
STATISTICS_BUTTONS: Final[List[List[str]]] = [
    ["📈 Общая статистика"],
    ["📅 Статистика за период"],
    ["🔙 Админ бота", "🏠 Главное меню"]
]

# Invite management submenu
INVITE_MANAGEMENT_BUTTONS: Final[List[List[str]]] = [
    ["📋 Все инвайты"],
    ["🎁 Выдать инвайты"],
    ["🔙 Админ бота", "🏠 Главное меню"]
]

# Bot settings submenu
BOT_SETTINGS_BUTTONS: Final[List[List[str]]] = [
    ["🔐 Инвайт-система"],
    ["🔙 Админ бота", "🏠 Главное меню"]
]

# Pagination settings
USERS_PER_PAGE: Final[int] = 10
INVITES_PER_PAGE: Final[int] = 15
