"""
Настройки модуля администрирования бота

Параметры конфигурации для глобального администрирования бота.
"""

from typing import Final, List

from src.common.messages import BUTTON_MAIN_MENU as COMMON_BUTTON_MAIN_MENU

# Метаданные модуля
MODULE_NAME: Final[str] = "Администрирование бота"
MODULE_DESCRIPTION: Final[str] = "Управление пользователями и настройками бота"

# Кнопка входа в админ-меню бота
BUTTON_BOT_ADMIN: Final[str] = "🛠️ Админ бота"

# Тексты кнопок админ-меню
BUTTON_USERS: Final[str] = "👥 Пользователи"
BUTTON_PREINVITES: Final[str] = "👤 Пре-инвайты"
BUTTON_MANUAL_USERS: Final[str] = "➕ Ручные пользователи"
BUTTON_STATS: Final[str] = "📊 Статистика"
BUTTON_INVITES: Final[str] = "🎫 Инвайты"
BUTTON_BOT_SETTINGS: Final[str] = "⚙️ Настройки бота"
BUTTON_BACK_ADMIN: Final[str] = "🔙 Админ бота"
BUTTON_BACK_SETTINGS: Final[str] = "🔙 Настройки бота"

# Тексты кнопок управления пользователями
BUTTON_USER_LIST: Final[str] = "📋 Список пользователей"
BUTTON_USER_SEARCH: Final[str] = "🔍 Поиск пользователя"
BUTTON_ADMINS_LIST: Final[str] = "👑 Список админов"

# Тексты кнопок управления пре-инвайтами
BUTTON_PREINVITE_LIST: Final[str] = "📋 Список пре-инвайтов"
BUTTON_PREINVITE_ADD: Final[str] = "➕ Добавить пользователя"

# Тексты кнопок управления ручными пользователями
BUTTON_MANUAL_LIST: Final[str] = "📋 Список ручных пользователей"
BUTTON_MANUAL_ADD: Final[str] = "➕ Добавить ручного пользователя"

# Тексты кнопок статистики
BUTTON_STATS_TOTAL: Final[str] = "📈 Общая статистика"
BUTTON_STATS_PERIOD: Final[str] = "📅 Статистика за период"

# Тексты кнопок управления инвайтами
BUTTON_INVITES_ALL: Final[str] = "📋 Все инвайты"
BUTTON_INVITES_ISSUE: Final[str] = "🎁 Выдать инвайты"

# Тексты кнопок настроек бота
BUTTON_INVITE_SYSTEM: Final[str] = "🔐 Инвайт-система"
BUTTON_MODULES: Final[str] = "🧩 Модули"
BUTTON_PLANNED_OUTAGES: Final[str] = "🗓️ Плановые работы"
BUTTON_AI_MODEL: Final[str] = "🧠 AI модель"

# Тексты кнопок плановых работ
BUTTON_OUTAGE_LIST: Final[str] = "📋 Список дат"
BUTTON_OUTAGE_ADD: Final[str] = "➕ Добавить дату"
BUTTON_OUTAGE_TYPE_BLUE_SHORT: Final[str] = "🟦 22:00-01:00"
BUTTON_OUTAGE_TYPE_BLUE_LONG: Final[str] = "🟦_ 22:00-05:00"
BUTTON_OUTAGE_TYPE_RED: Final[str] = "🟥 20:00-20:00"

# Кнопки главного админ-меню бота
ADMIN_MENU_BUTTONS: Final[List[List[str]]] = [
    [BUTTON_USERS, BUTTON_PREINVITES],
    [BUTTON_MANUAL_USERS],
    [BUTTON_STATS, BUTTON_INVITES],
    [BUTTON_BOT_SETTINGS],
    [COMMON_BUTTON_MAIN_MENU]
]

# Подменю управления пользователями
USER_MANAGEMENT_BUTTONS: Final[List[List[str]]] = [
    [BUTTON_USER_LIST],
    [BUTTON_USER_SEARCH],
    [BUTTON_ADMINS_LIST],
    [BUTTON_BACK_ADMIN, COMMON_BUTTON_MAIN_MENU]
]

# Подменю управления пре-инвайтами
PREINVITE_BUTTONS: Final[List[List[str]]] = [
    [BUTTON_PREINVITE_LIST],
    [BUTTON_PREINVITE_ADD],
    [BUTTON_BACK_ADMIN, COMMON_BUTTON_MAIN_MENU]
]

# Подменю управления ручными пользователями
MANUAL_USERS_BUTTONS: Final[List[List[str]]] = [
    [BUTTON_MANUAL_LIST],
    [BUTTON_MANUAL_ADD],
    [BUTTON_BACK_ADMIN, COMMON_BUTTON_MAIN_MENU]
]

# Подменю статистики
STATISTICS_BUTTONS: Final[List[List[str]]] = [
    [BUTTON_STATS_TOTAL],
    [BUTTON_STATS_PERIOD],
    [BUTTON_BACK_ADMIN, COMMON_BUTTON_MAIN_MENU]
]

# Подменю управления инвайтами
INVITE_MANAGEMENT_BUTTONS: Final[List[List[str]]] = [
    [BUTTON_INVITES_ALL],
    [BUTTON_INVITES_ISSUE],
    [BUTTON_BACK_ADMIN, COMMON_BUTTON_MAIN_MENU]
]

# Подменю настроек бота
BOT_SETTINGS_BUTTONS: Final[List[List[str]]] = [
    [BUTTON_INVITE_SYSTEM],
    [BUTTON_AI_MODEL],
    [BUTTON_MODULES],
    [BUTTON_PLANNED_OUTAGES],
    [BUTTON_BACK_ADMIN, COMMON_BUTTON_MAIN_MENU]
]

# Подменю управления модулями
MODULES_MANAGEMENT_BUTTONS: Final[List[List[str]]] = [
    [BUTTON_BACK_SETTINGS, COMMON_BUTTON_MAIN_MENU]
]

# Подменю плановых работ
PLANNED_OUTAGES_BUTTONS: Final[List[List[str]]] = [
    [BUTTON_OUTAGE_LIST],
    [BUTTON_OUTAGE_ADD],
    [BUTTON_BACK_SETTINGS, COMMON_BUTTON_MAIN_MENU]
]

# Кнопки выбора типа работ
PLANNED_OUTAGE_TYPE_BUTTONS: Final[List[List[str]]] = [
    [BUTTON_OUTAGE_TYPE_BLUE_SHORT],
    [BUTTON_OUTAGE_TYPE_BLUE_LONG],
    [BUTTON_OUTAGE_TYPE_RED],
    [BUTTON_BACK_SETTINGS, COMMON_BUTTON_MAIN_MENU]
]

# Настройки пагинации
USERS_PER_PAGE: Final[int] = 10
INVITES_PER_PAGE: Final[int] = 15
