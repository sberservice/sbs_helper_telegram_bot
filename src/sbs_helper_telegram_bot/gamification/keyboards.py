"""
Gamification Module Keyboards

Telegram keyboard builders for the gamification/achievement system.
"""

from typing import List, Optional, Dict
from telegram import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from . import settings


# ===== ОТВЕТНЫЕ КЛАВИАТУРЫ =====

def get_submenu_keyboard() -> ReplyKeyboardMarkup:
    """
    Build gamification submenu keyboard for regular users.
    
    Returns:
        ReplyKeyboardMarkup for gamification submenu
    """
    return ReplyKeyboardMarkup(
        settings.SUBMENU_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_admin_submenu_keyboard() -> ReplyKeyboardMarkup:
    """
    Build gamification submenu keyboard with admin panel button.
    
    Returns:
        ReplyKeyboardMarkup for admin submenu
    """
    return ReplyKeyboardMarkup(
        settings.ADMIN_SUBMENU_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_admin_menu_keyboard() -> ReplyKeyboardMarkup:
    """
    Build gamification admin panel main menu keyboard.
    
    Returns:
        ReplyKeyboardMarkup for admin menu
    """
    return ReplyKeyboardMarkup(
        settings.ADMIN_MENU_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_view_profile_keyboard() -> ReplyKeyboardMarkup:
    """
    Build keyboard for viewing another user's profile.
    
    Returns:
        ReplyKeyboardMarkup with back button
    """
    return ReplyKeyboardMarkup(
        settings.VIEW_PROFILE_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


# ===== ВСТРОЕННЫЕ КЛАВИАТУРЫ =====

def get_rankings_type_keyboard() -> InlineKeyboardMarkup:
    """
    Build inline keyboard for selecting ranking type.
    
    Returns:
        InlineKeyboardMarkup with score/achievements options
    """
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "💎 По очкам",
                callback_data=f"{settings.CALLBACK_PREFIX_RANKING}_type_{settings.RANKING_TYPE_SCORE}"
            ),
            InlineKeyboardButton(
                "🎖️ По достижениям",
                callback_data=f"{settings.CALLBACK_PREFIX_RANKING}_type_{settings.RANKING_TYPE_ACHIEVEMENTS}"
            ),
        ]
    ])


def get_rankings_period_keyboard(ranking_type: str) -> InlineKeyboardMarkup:
    """
    Build inline keyboard for selecting ranking period.
    
    Args:
        ranking_type: 'score' or 'achievements'
    
    Returns:
        InlineKeyboardMarkup with period options
    """
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📅 Месяц",
                callback_data=f"{settings.CALLBACK_PREFIX_PERIOD}_{ranking_type}_{settings.RANKING_PERIOD_MONTHLY}"
            ),
            InlineKeyboardButton(
                "📆 Год",
                callback_data=f"{settings.CALLBACK_PREFIX_PERIOD}_{ranking_type}_{settings.RANKING_PERIOD_YEARLY}"
            ),
            InlineKeyboardButton(
                "🌐 Всё время",
                callback_data=f"{settings.CALLBACK_PREFIX_PERIOD}_{ranking_type}_{settings.RANKING_PERIOD_ALL_TIME}"
            ),
        ],
        [
            InlineKeyboardButton(
                "🔙 Назад",
                callback_data=f"{settings.CALLBACK_PREFIX_RANKING}_back"
            ),
        ]
    ])


def _obfuscate_name_for_button(first_name: str, last_name: Optional[str]) -> str:
    """
    Скрыть имя пользователя для отображения на кнопке.
    Показывает первую букву и точки вместо остальных символов.
    
    Args:
        first_name: Имя пользователя
        last_name: Фамилия пользователя (необязательно)
    
    Returns:
        Маскированное имя вида "И... Г..."
    """
    if not first_name:
        return "???"
    
    # Имя: первая буква и точки вместо остальных символов
    first_dots = "." * min(len(first_name) - 1, 3)
    obfuscated = first_name[0] + first_dots
    
    # Фамилия: первая буква и точки вместо остальных символов
    if last_name:
        last_dots = "." * min(len(last_name) - 1, 3)
        obfuscated += f" {last_name[0]}{last_dots}"
    
    return obfuscated


def get_ranking_list_keyboard(
    ranking_type: str,
    period: str,
    page: int,
    total_pages: int,
    entries: List[Dict],
    obfuscate: bool = False
) -> InlineKeyboardMarkup:
    """
    Собрать inline-клавиатуру для списка рейтинга с пагинацией и выбором пользователя.
    
    Args:
        ranking_type: 'score' или 'achievements'
        period: Тип периода
        page: Текущая страница
        total_pages: Всего страниц
        entries: Список записей рейтинга (для пользовательских кнопок)
        obfuscate: Нужно ли скрывать имена на кнопках
    
    Returns:
        InlineKeyboardMarkup с пагинацией и пользовательскими кнопками
    """
    keyboard = []
    
    # Кнопки пользователей (по 2 в строке)
    user_buttons = []
    for entry in entries:
        userid = entry.get('userid')
        first_name = entry.get('first_name', 'User')
        last_name = entry.get('last_name')
        rank = entry.get('rank', 0)
        
        # Получаем отображаемое имя (скрытое или обычное)
        if obfuscate:
            display_name = _obfuscate_name_for_button(first_name, last_name)
        else:
            display_name = first_name[:15] + "..." if len(first_name) > 15 else first_name
        
        user_buttons.append(
            InlineKeyboardButton(
                f"{rank}. {display_name}",
                callback_data=f"{settings.CALLBACK_PREFIX_PROFILE}_view_{userid}"
            )
        )
    
    # Добавляем кнопки пользователей парами
    for i in range(0, len(user_buttons), 2):
        row = user_buttons[i:i+2]
        keyboard.append(row)
    
    # Строка пагинации
    pagination_row = []
    if page > 1:
        pagination_row.append(
            InlineKeyboardButton(
                "◀️ Назад",
                callback_data=f"{settings.CALLBACK_PREFIX_PAGE}_{ranking_type}_{period}_{page-1}"
            )
        )
    
    pagination_row.append(
        InlineKeyboardButton(
            f"{page}/{total_pages}",
            callback_data="noop"
        )
    )
    
    if page < total_pages:
        pagination_row.append(
            InlineKeyboardButton(
                "Вперёд ▶️",
                callback_data=f"{settings.CALLBACK_PREFIX_PAGE}_{ranking_type}_{period}_{page+1}"
            )
        )
    
    if pagination_row:
        keyboard.append(pagination_row)
    
    # Кнопка поиска
    keyboard.append([
        InlineKeyboardButton(
            "🔍 Найти пользователя",
            callback_data=f"{settings.CALLBACK_PREFIX_RANKING}_search"
        )
    ])
    
    # Кнопка выбора периода
    keyboard.append([
        InlineKeyboardButton(
            "📅 Изменить период",
            callback_data=f"{settings.CALLBACK_PREFIX_RANKING}_type_{ranking_type}"
        ),
        InlineKeyboardButton(
            "🔙 Тип рейтинга",
            callback_data=f"{settings.CALLBACK_PREFIX_RANKING}_back"
        )
    ])
    
    return InlineKeyboardMarkup(keyboard)


def get_user_profile_keyboard(from_ranking: bool = False) -> InlineKeyboardMarkup:
    """
    Собрать inline-клавиатуру для просмотра профиля пользователя.
    
    Args:
        from_ranking: Просмотр из рейтинга (показывать кнопку назад)
    
    Returns:
        InlineKeyboardMarkup с действиями профиля
    """
    keyboard = []
    
    if from_ranking:
        keyboard.append([
            InlineKeyboardButton(
                "🔙 Назад к рейтингу",
                callback_data=f"{settings.CALLBACK_PREFIX_RANKING}_return"
            )
        ])
    
    return InlineKeyboardMarkup(keyboard)


def get_achievements_keyboard(
    modules: List[str],
    selected_module: Optional[str] = None,
    page: int = 1,
    total_pages: int = 1
) -> InlineKeyboardMarkup:
    """
    Собрать inline-клавиатуру для просмотра достижений с фильтром по модулю.
    
    Args:
        modules: Список модулей с достижениями
        selected_module: Выбранный фильтр по модулю (None = все)
        page: Текущая страница
        total_pages: Всего страниц
    
    Returns:
        InlineKeyboardMarkup с фильтрами по модулю и пагинацией
    """
    keyboard = []
    
    # Кнопки фильтра по модулю
    filter_row = [
        InlineKeyboardButton(
            "📋 Все" if selected_module else "✅ Все",
            callback_data=f"{settings.CALLBACK_PREFIX_ACHIEVEMENT}_filter_all"
        )
    ]
    
    for module in modules[:3]:  # Ограничиваем до 3 модулей в строке
        is_selected = selected_module == module
        display = f"✅ {module}" if is_selected else module
        filter_row.append(
            InlineKeyboardButton(
                display,
                callback_data=f"{settings.CALLBACK_PREFIX_ACHIEVEMENT}_filter_{module}"
            )
        )
    
    keyboard.append(filter_row)
    
    # Дополнительные модули во второй строке при необходимости
    if len(modules) > 3:
        extra_row = []
        for module in modules[3:6]:
            is_selected = selected_module == module
            display = f"✅ {module}" if is_selected else module
            extra_row.append(
                InlineKeyboardButton(
                    display,
                    callback_data=f"{settings.CALLBACK_PREFIX_ACHIEVEMENT}_filter_{module}"
                )
            )
        keyboard.append(extra_row)
    
    # Пагинация
    if total_pages > 1:
        pagination_row = []
        if page > 1:
            pagination_row.append(
                InlineKeyboardButton(
                    "◀️",
                    callback_data=f"{settings.CALLBACK_PREFIX_ACHIEVEMENT}_page_{page-1}"
                )
            )
        
        pagination_row.append(
            InlineKeyboardButton(
                f"{page}/{total_pages}",
                callback_data="noop"
            )
        )
        
        if page < total_pages:
            pagination_row.append(
                InlineKeyboardButton(
                    "▶️",
                    callback_data=f"{settings.CALLBACK_PREFIX_ACHIEVEMENT}_page_{page+1}"
                )
            )
        
        keyboard.append(pagination_row)
    
    return InlineKeyboardMarkup(keyboard)


def get_module_achievements_button(module_name: str) -> InlineKeyboardMarkup:
    """
    Собрать inline-клавиатуру с одной кнопкой «Посмотреть достижения» для интеграции в модули.
    
    Args:
        module_name: Название модуля
    
    Returns:
        InlineKeyboardMarkup с кнопкой достижений
    """
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                settings.MODULE_ACHIEVEMENTS_BUTTON,
                callback_data=f"{settings.CALLBACK_PREFIX_ACHIEVEMENT}_module_{module_name}"
            )
        ]
    ])


# ===== КЛАВИАТУРЫ АДМИНА =====

def get_admin_score_config_keyboard(
    configs: List[Dict],
    page: int = 1,
    total_pages: int = 1
) -> InlineKeyboardMarkup:
    """
    Собрать inline-клавиатуру для настройки очков в админ-панели.
    
    Args:
        configs: Список записей конфигурации очков
        page: Текущая страница
        total_pages: Всего страниц
    
    Returns:
        InlineKeyboardMarkup с кнопками редактирования конфигурации
    """
    keyboard = []
    
    for config in configs:
        config_id = config.get('id')
        module = config.get('module', '')
        action = config.get('action', '')
        points = config.get('points', 0)
        
        keyboard.append([
            InlineKeyboardButton(
                f"{module}: {action} ({points} очков)",
                callback_data=f"{settings.CALLBACK_PREFIX_ADMIN}_edit_score_{config_id}"
            )
        ])
    
    # Пагинация
    if total_pages > 1:
        pagination_row = []
        if page > 1:
            pagination_row.append(
                InlineKeyboardButton(
                    "◀️",
                    callback_data=f"{settings.CALLBACK_PREFIX_ADMIN}_score_page_{page-1}"
                )
            )
        
        pagination_row.append(
            InlineKeyboardButton(
                f"{page}/{total_pages}",
                callback_data="noop"
            )
        )
        
        if page < total_pages:
            pagination_row.append(
                InlineKeyboardButton(
                    "▶️",
                    callback_data=f"{settings.CALLBACK_PREFIX_ADMIN}_score_page_{page+1}"
                )
            )
        
        keyboard.append(pagination_row)
    
    return InlineKeyboardMarkup(keyboard)


def get_search_results_keyboard(
    users: List[Dict]
) -> InlineKeyboardMarkup:
    """
    Собрать inline-клавиатуру для результатов поиска пользователей.
    
    Args:
        users: Список словарей пользователей с userid, first_name, last_name
    
    Returns:
        InlineKeyboardMarkup с кнопками выбора пользователя
    """
    keyboard = []
    
    for user in users[:10]:  # Ограничиваем до 10 результатов
        userid = user.get('userid')
        first_name = user.get('first_name', 'User')
        last_name = user.get('last_name', '')
        
        display_name = first_name
        if last_name:
            display_name += f" {last_name}"
        
        # Обрезаем, если слишком длинно
        if len(display_name) > 25:
            display_name = display_name[:22] + "..."
        
        keyboard.append([
            InlineKeyboardButton(
                display_name,
                callback_data=f"{settings.CALLBACK_PREFIX_PROFILE}_view_{userid}"
            )
        ])
    
    # Кнопка отмены
    keyboard.append([
        InlineKeyboardButton(
            "❌ Отмена",
            callback_data=f"{settings.CALLBACK_PREFIX_RANKING}_return"
        )
    ])
    
    return InlineKeyboardMarkup(keyboard)
