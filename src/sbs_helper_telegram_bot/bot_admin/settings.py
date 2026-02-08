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

# Admin menu button texts
BUTTON_USERS: Final[str] = "👥 Пользователи"
BUTTON_PREINVITES: Final[str] = "👤 Пре-инвайты"
BUTTON_MANUAL_USERS: Final[str] = "➕ Ручные пользователи"
BUTTON_STATS: Final[str] = "📊 Статистика"
BUTTON_INVITES: Final[str] = "🎫 Инвайты"
BUTTON_BOT_SETTINGS: Final[str] = "⚙️ Настройки бота"
BUTTON_BACK_ADMIN: Final[str] = "🔙 Админ бота"
BUTTON_BACK_SETTINGS: Final[str] = "🔙 Настройки бота"

# User management button texts
BUTTON_USER_LIST: Final[str] = "📋 Список пользователей"
BUTTON_USER_SEARCH: Final[str] = "🔍 Поиск пользователя"
BUTTON_ADMINS_LIST: Final[str] = "👑 Список админов"

# Pre-invite management button texts
BUTTON_PREINVITE_LIST: Final[str] = "📋 Список пре-инвайтов"
BUTTON_PREINVITE_ADD: Final[str] = "➕ Добавить пользователя"

# Manual users management button texts
BUTTON_MANUAL_LIST: Final[str] = "📋 Список ручных пользователей"
BUTTON_MANUAL_ADD: Final[str] = "➕ Добавить ручного пользователя"

# Statistics button texts
BUTTON_STATS_TOTAL: Final[str] = "📈 Общая статистика"
BUTTON_STATS_PERIOD: Final[str] = "📅 Статистика за период"

# Invite management button texts
BUTTON_INVITES_ALL: Final[str] = "📋 Все инвайты"
BUTTON_INVITES_ISSUE: Final[str] = "🎁 Выдать инвайты"

# Bot settings button texts
BUTTON_INVITE_SYSTEM: Final[str] = "🔐 Инвайт-система"
BUTTON_MODULES: Final[str] = "🧩 Модули"

# Bot admin main menu buttons
ADMIN_MENU_BUTTONS: Final[List[List[str]]] = [
    [BUTTON_USERS, BUTTON_PREINVITES],
    [BUTTON_MANUAL_USERS],
    [BUTTON_STATS, BUTTON_INVITES],
    [BUTTON_BOT_SETTINGS],
    [COMMON_BUTTON_MAIN_MENU]
]

# User management submenu
USER_MANAGEMENT_BUTTONS: Final[List[List[str]]] = [
    [BUTTON_USER_LIST],
    [BUTTON_USER_SEARCH],
    [BUTTON_ADMINS_LIST],
    [BUTTON_BACK_ADMIN, COMMON_BUTTON_MAIN_MENU]
]

# Pre-invite management submenu
PREINVITE_BUTTONS: Final[List[List[str]]] = [
    [BUTTON_PREINVITE_LIST],
    [BUTTON_PREINVITE_ADD],
    [BUTTON_BACK_ADMIN, COMMON_BUTTON_MAIN_MENU]
]

# Manual users management submenu
MANUAL_USERS_BUTTONS: Final[List[List[str]]] = [
    [BUTTON_MANUAL_LIST],
    [BUTTON_MANUAL_ADD],
    [BUTTON_BACK_ADMIN, COMMON_BUTTON_MAIN_MENU]
]

# Statistics submenu
STATISTICS_BUTTONS: Final[List[List[str]]] = [
    [BUTTON_STATS_TOTAL],
    [BUTTON_STATS_PERIOD],
    [BUTTON_BACK_ADMIN, COMMON_BUTTON_MAIN_MENU]
]

# Invite management submenu
INVITE_MANAGEMENT_BUTTONS: Final[List[List[str]]] = [
    [BUTTON_INVITES_ALL],
    [BUTTON_INVITES_ISSUE],
    [BUTTON_BACK_ADMIN, COMMON_BUTTON_MAIN_MENU]
]

# Bot settings submenu
BOT_SETTINGS_BUTTONS: Final[List[List[str]]] = [
    [BUTTON_INVITE_SYSTEM],
    [BUTTON_MODULES],
    [BUTTON_BACK_ADMIN, COMMON_BUTTON_MAIN_MENU]
]

# Modules management submenu
MODULES_MANAGEMENT_BUTTONS: Final[List[List[str]]] = [
    [BUTTON_BACK_SETTINGS, COMMON_BUTTON_MAIN_MENU]
]

# Pagination settings
USERS_PER_PAGE: Final[int] = 10
INVITES_PER_PAGE: Final[int] = 15
