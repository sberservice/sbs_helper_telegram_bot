"""
Gamification Module Keyboards

Telegram keyboard builders for the gamification/achievement system.
"""

from typing import List, Optional, Dict
from telegram import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from . import settings


# ===== REPLY KEYBOARDS =====

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


# ===== INLINE KEYBOARDS =====

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
    Obfuscate user name for button display.
    Shows first letter + dots for remaining characters.
    
    Args:
        first_name: User's first name
        last_name: User's last name (optional)
    
    Returns:
        Obfuscated name like "И... Г..."
    """
    if not first_name:
        return "???"
    
    # First name: first letter + dots for remaining characters
    first_dots = "." * min(len(first_name) - 1, 3)
    obfuscated = first_name[0] + first_dots
    
    # Last name: first letter + dots for remaining characters
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
    Build inline keyboard for ranking list with pagination and user selection.
    
    Args:
        ranking_type: 'score' or 'achievements'
        period: Period type
        page: Current page number
        total_pages: Total pages
        entries: List of ranking entries (for user buttons)
        obfuscate: Whether to obfuscate names in buttons
    
    Returns:
        InlineKeyboardMarkup with pagination and user buttons
    """
    keyboard = []
    
    # User buttons (2 per row)
    user_buttons = []
    for entry in entries:
        userid = entry.get('userid')
        first_name = entry.get('first_name', 'User')
        last_name = entry.get('last_name')
        rank = entry.get('rank', 0)
        
        # Get display name (obfuscated or normal)
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
    
    # Add user buttons in pairs
    for i in range(0, len(user_buttons), 2):
        row = user_buttons[i:i+2]
        keyboard.append(row)
    
    # Pagination row
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
    
    # Search button
    keyboard.append([
        InlineKeyboardButton(
            "🔍 Найти пользователя",
            callback_data=f"{settings.CALLBACK_PREFIX_RANKING}_search"
        )
    ])
    
    # Period selection button
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
    Build inline keyboard for viewing user profile.
    
    Args:
        from_ranking: Whether viewing from rankings (show back button)
    
    Returns:
        InlineKeyboardMarkup with profile actions
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
    Build inline keyboard for achievements view with module filter.
    
    Args:
        modules: List of module names that have achievements
        selected_module: Currently selected module filter (None = all)
        page: Current page
        total_pages: Total pages
    
    Returns:
        InlineKeyboardMarkup with module filters and pagination
    """
    keyboard = []
    
    # Module filter buttons
    filter_row = [
        InlineKeyboardButton(
            "📋 Все" if selected_module else "✅ Все",
            callback_data=f"{settings.CALLBACK_PREFIX_ACHIEVEMENT}_filter_all"
        )
    ]
    
    for module in modules[:3]:  # Limit to 3 modules per row
        is_selected = selected_module == module
        display = f"✅ {module}" if is_selected else module
        filter_row.append(
            InlineKeyboardButton(
                display,
                callback_data=f"{settings.CALLBACK_PREFIX_ACHIEVEMENT}_filter_{module}"
            )
        )
    
    keyboard.append(filter_row)
    
    # Additional modules on second row if needed
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
    
    # Pagination
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
    Build inline keyboard with single "View achievements" button for integration into modules.
    
    Args:
        module_name: Name of the module
    
    Returns:
        InlineKeyboardMarkup with achievements button
    """
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                settings.MODULE_ACHIEVEMENTS_BUTTON,
                callback_data=f"{settings.CALLBACK_PREFIX_ACHIEVEMENT}_module_{module_name}"
            )
        ]
    ])


# ===== ADMIN KEYBOARDS =====

def get_admin_score_config_keyboard(
    configs: List[Dict],
    page: int = 1,
    total_pages: int = 1
) -> InlineKeyboardMarkup:
    """
    Build inline keyboard for admin score configuration.
    
    Args:
        configs: List of score config entries
        page: Current page
        total_pages: Total pages
    
    Returns:
        InlineKeyboardMarkup with config edit buttons
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
    
    # Pagination
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
    Build inline keyboard for user search results.
    
    Args:
        users: List of user dicts with userid, first_name, last_name
    
    Returns:
        InlineKeyboardMarkup with user selection buttons
    """
    keyboard = []
    
    for user in users[:10]:  # Limit to 10 results
        userid = user.get('userid')
        first_name = user.get('first_name', 'User')
        last_name = user.get('last_name', '')
        
        display_name = first_name
        if last_name:
            display_name += f" {last_name}"
        
        # Truncate if too long
        if len(display_name) > 25:
            display_name = display_name[:22] + "..."
        
        keyboard.append([
            InlineKeyboardButton(
                display_name,
                callback_data=f"{settings.CALLBACK_PREFIX_PROFILE}_view_{userid}"
            )
        ])
    
    # Cancel button
    keyboard.append([
        InlineKeyboardButton(
            "❌ Отмена",
            callback_data=f"{settings.CALLBACK_PREFIX_RANKING}_return"
        )
    ])
    
    return InlineKeyboardMarkup(keyboard)
