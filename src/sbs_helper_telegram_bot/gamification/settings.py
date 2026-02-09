"""
Настройки модуля геймификации

Параметры конфигурации для системы геймификации и достижений.
"""

from typing import Final, List, Dict

from src.common.messages import BUTTON_MAIN_MENU as COMMON_BUTTON_MAIN_MENU

# Метаданные модуля
MODULE_NAME: Final[str] = "Геймификация"
MODULE_DESCRIPTION: Final[str] = "Система достижений, рейтингов и цифровых профилей пользователей"
MODULE_VERSION: Final[str] = "1.0.0"
MODULE_AUTHOR: Final[str] = "SberService"

# Кнопка главного меню для этого модуля
MENU_BUTTON_TEXT: Final[str] = "🏆 Достижения"

# Конфигурация кнопок подменю (обычные пользователи)
SUBMENU_BUTTONS: Final[List[List[str]]] = [
    ["🎖️ Мои достижения", "📊 Рейтинги"],
    [COMMON_BUTTON_MAIN_MENU]
]

# Подменю администратора (включает кнопку админ-панели)
ADMIN_SUBMENU_BUTTONS: Final[List[List[str]]] = [
    ["🎖️ Мои достижения", "📊 Рейтинги"],
    ["🔐 Админ профилей", COMMON_BUTTON_MAIN_MENU]
]

# Кнопки меню админ-панели
ADMIN_MENU_BUTTONS: Final[List[List[str]]] = [
    ["🔍 Найти профиль"],
    ["⚙️ Настройки очков", "📋 Все достижения"],
    ["📈 Статистика системы", "🔒 Скрытие имён"],
    ["🔙 Назад в профиль"]
]

# Кнопки для просмотра профиля другого пользователя
VIEW_PROFILE_BUTTONS: Final[List[List[str]]] = [
    ["🔙 Назад к рейтингу"]
]

# Тексты кнопок (для regex-сопоставления)
BUTTON_MY_PROFILE: Final[str] = "👤 Мой профиль"
BUTTON_MY_ACHIEVEMENTS: Final[str] = "🎖️ Мои достижения"
BUTTON_RANKINGS: Final[str] = "📊 Рейтинги"
BUTTON_ADMIN_PANEL: Final[str] = "🔐 Админ профилей"
BUTTON_BACK_TO_PROFILE: Final[str] = "🔙 Назад в профиль"
BUTTON_BACK_TO_RANKING: Final[str] = "🔙 Назад к рейтингу"
BUTTON_MAIN_MENU: Final[str] = COMMON_BUTTON_MAIN_MENU

# Кнопки администратора
BUTTON_ADMIN_FIND_PROFILE: Final[str] = "🔍 Найти профиль"
BUTTON_ADMIN_SCORE_SETTINGS: Final[str] = "⚙️ Настройки очков"
BUTTON_ADMIN_ALL_ACHIEVEMENTS: Final[str] = "📋 Все достижения"
BUTTON_ADMIN_STATS: Final[str] = "📈 Статистика системы"
BUTTON_ADMIN_OBFUSCATE: Final[str] = "🔒 Скрытие имён"

# Настройки пагинации
RANKINGS_PER_PAGE: Final[int] = 10
ACHIEVEMENTS_PER_PAGE: Final[int] = 6

# Состояния диалога для пользователя
(
    STATE_SUBMENU,
    STATE_VIEW_PROFILE,
    STATE_VIEW_ACHIEVEMENTS,
    STATE_VIEW_RANKINGS,
    STATE_VIEW_USER_PROFILE,
    STATE_SEARCH_USER,
) = range(6)

# Состояния диалога для администратора (начиная с 100)
(
    STATE_ADMIN_MENU,
    STATE_ADMIN_FIND_PROFILE,
    STATE_ADMIN_VIEW_PROFILE,
    STATE_ADMIN_SCORE_SETTINGS,
    STATE_ADMIN_EDIT_SCORE,
    STATE_ADMIN_VIEW_ACHIEVEMENTS,
    STATE_ADMIN_STATS,
) = range(100, 107)

# Ключи контекста для user_data
CONTEXT_CURRENT_PAGE: Final[str] = "gamification_current_page"
CONTEXT_RANKING_TYPE: Final[str] = "gamification_ranking_type"
CONTEXT_RANKING_PERIOD: Final[str] = "gamification_ranking_period"
CONTEXT_VIEW_USERID: Final[str] = "gamification_view_userid"
CONTEXT_SEARCH_QUERY: Final[str] = "gamification_search_query"
CONTEXT_MODULE_FILTER: Final[str] = "gamification_module_filter"
CONTEXT_ADMIN_EDITING_CONFIG: Final[str] = "gamification_admin_editing_config"

# Типы рейтинга
RANKING_TYPE_SCORE: Final[str] = "score"
RANKING_TYPE_ACHIEVEMENTS: Final[str] = "achievements"

# Периоды рейтинга
RANKING_PERIOD_MONTHLY: Final[str] = "monthly"
RANKING_PERIOD_YEARLY: Final[str] = "yearly"
RANKING_PERIOD_ALL_TIME: Final[str] = "all_time"

# Уровни достижений
ACHIEVEMENT_LEVEL_BRONZE: Final[int] = 1
ACHIEVEMENT_LEVEL_SILVER: Final[int] = 2
ACHIEVEMENT_LEVEL_GOLD: Final[int] = 3

# Информация об отображении уровней
ACHIEVEMENT_LEVEL_INFO: Final[Dict[int, Dict[str, str]]] = {
    ACHIEVEMENT_LEVEL_BRONZE: {"name": "Бронза", "icon": "🥉"},
    ACHIEVEMENT_LEVEL_SILVER: {"name": "Серебро", "icon": "🥈"},
    ACHIEVEMENT_LEVEL_GOLD: {"name": "Золото", "icon": "🥇"},
}

# Конфигурация рангов по умолчанию (используется как запасная)
DEFAULT_RANKS: Final[List[Dict]] = [
    {"level": 1, "name": "Новичок", "icon": "🌱", "threshold": 0},
    {"level": 2, "name": "Специалист", "icon": "📘", "threshold": 100},
    {"level": 3, "name": "Эксперт", "icon": "⭐", "threshold": 500},
    {"level": 4, "name": "Мастер", "icon": "🏅", "threshold": 2000},
    {"level": 5, "name": "Легенда", "icon": "👑", "threshold": 5000},
]

# Ключи настроек в базе данных
DB_SETTING_OBFUSCATE_NAMES: Final[str] = "obfuscate_names"
DB_SETTING_RANKINGS_PER_PAGE: Final[str] = "rankings_per_page"

# Префиксы callback-данных
CALLBACK_PREFIX_RANKING: Final[str] = "gf_rank"
CALLBACK_PREFIX_PROFILE: Final[str] = "gf_profile"
CALLBACK_PREFIX_ACHIEVEMENT: Final[str] = "gf_achv"
CALLBACK_PREFIX_PAGE: Final[str] = "gf_page"
CALLBACK_PREFIX_PERIOD: Final[str] = "gf_period"
CALLBACK_PREFIX_ADMIN: Final[str] = "gf_admin"
CALLBACK_PREFIX_OBFUSCATE: Final[str] = "gf_obfuscate"

# Текст кнопки достижений модуля (для интеграции в другие модули)
MODULE_ACHIEVEMENTS_BUTTON: Final[str] = "🎖️ Достижения модуля"
