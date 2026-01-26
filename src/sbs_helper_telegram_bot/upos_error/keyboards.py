"""
UPOS Error Module Keyboards

Telegram keyboard builders for the UPOS error code lookup module.
"""

from typing import List, Optional
from telegram import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from . import settings


def get_submenu_keyboard() -> ReplyKeyboardMarkup:
    """
    Build UPOS error submenu keyboard for regular users.
    
    Returns:
        ReplyKeyboardMarkup for UPOS error submenu
    """
    return ReplyKeyboardMarkup(
        settings.SUBMENU_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_admin_submenu_keyboard() -> ReplyKeyboardMarkup:
    """
    Build UPOS error submenu keyboard with admin panel button.
    
    Returns:
        ReplyKeyboardMarkup for admin UPOS error submenu
    """
    return ReplyKeyboardMarkup(
        settings.ADMIN_SUBMENU_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_admin_menu_keyboard() -> ReplyKeyboardMarkup:
    """
    Build UPOS error admin panel main menu keyboard.
    
    Returns:
        ReplyKeyboardMarkup for admin menu
    """
    return ReplyKeyboardMarkup(
        settings.ADMIN_MENU_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_admin_categories_keyboard() -> ReplyKeyboardMarkup:
    """
    Build admin categories management keyboard.
    
    Returns:
        ReplyKeyboardMarkup for categories management
    """
    return ReplyKeyboardMarkup(
        settings.ADMIN_CATEGORIES_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_admin_errors_keyboard() -> ReplyKeyboardMarkup:
    """
    Build admin error codes management keyboard.
    
    Returns:
        ReplyKeyboardMarkup for error codes management
    """
    return ReplyKeyboardMarkup(
        settings.ADMIN_ERRORS_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_error_codes_inline_keyboard(
    error_codes: List[dict],
    page: int = 1,
    total_pages: int = 1,
    action_prefix: str = "upos_view"
) -> InlineKeyboardMarkup:
    """
    Build inline keyboard with error codes for selection.
    
    Args:
        error_codes: List of error code dicts with 'id', 'error_code', 'description'
        page: Current page number
        total_pages: Total number of pages
        action_prefix: Callback data prefix for actions
        
    Returns:
        InlineKeyboardMarkup with error code buttons
    """
    keyboard = []
    
    for error in error_codes:
        error_id = error['id']
        code = error['error_code']
        desc = error.get('description', '')[:30]
        
        keyboard.append([
            InlineKeyboardButton(
                f"{code} - {desc}...",
                callback_data=f"{action_prefix}_{error_id}"
            )
        ])
    
    # Pagination buttons
    nav_buttons = []
    if page > 1:
        nav_buttons.append(
            InlineKeyboardButton("⬅️ Назад", callback_data=f"upos_page_{page-1}")
        )
    if page < total_pages:
        nav_buttons.append(
            InlineKeyboardButton("Вперёд ➡️", callback_data=f"upos_page_{page+1}")
        )
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # Back button
    keyboard.append([
        InlineKeyboardButton("🔙 Назад в меню", callback_data="upos_admin_menu")
    ])
    
    return InlineKeyboardMarkup(keyboard)


def get_categories_inline_keyboard(
    categories: List[dict],
    page: int = 1,
    total_pages: int = 1,
    for_selection: bool = False
) -> InlineKeyboardMarkup:
    """
    Build inline keyboard with categories.
    
    Args:
        categories: List of category dicts with 'id', 'name'
        page: Current page number
        total_pages: Total number of pages
        for_selection: If True, used for category selection when creating error
        
    Returns:
        InlineKeyboardMarkup with category buttons
    """
    keyboard = []
    
    prefix = "upos_cat_select" if for_selection else "upos_cat_view"
    
    for cat in categories:
        cat_id = cat['id']
        name = cat['name']
        
        keyboard.append([
            InlineKeyboardButton(
                name,
                callback_data=f"{prefix}_{cat_id}"
            )
        ])
    
    # Skip button for category selection
    if for_selection:
        keyboard.append([
            InlineKeyboardButton("⏭️ Пропустить", callback_data="upos_cat_skip")
        ])
    
    # Pagination buttons
    nav_buttons = []
    if page > 1:
        nav_buttons.append(
            InlineKeyboardButton("⬅️ Назад", callback_data=f"upos_cat_page_{page-1}")
        )
    if page < total_pages:
        nav_buttons.append(
            InlineKeyboardButton("Вперёд ➡️", callback_data=f"upos_cat_page_{page+1}")
        )
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # Back button (not for selection mode)
    if not for_selection:
        keyboard.append([
            InlineKeyboardButton("🔙 Назад в меню", callback_data="upos_admin_menu")
        ])
    
    return InlineKeyboardMarkup(keyboard)


def get_error_detail_keyboard(error_id: int, is_active: bool = True) -> InlineKeyboardMarkup:
    """
    Build inline keyboard for error code detail view (admin).
    
    Args:
        error_id: Error code ID
        is_active: Whether the error code is currently active
        
    Returns:
        InlineKeyboardMarkup with edit/delete options
    """
    keyboard = [
        [
            InlineKeyboardButton("📝 Описание", callback_data=f"upos_edit_desc_{error_id}"),
            InlineKeyboardButton("💡 Рекомендации", callback_data=f"upos_edit_actions_{error_id}")
        ],
        [
            InlineKeyboardButton("📁 Категория", callback_data=f"upos_edit_cat_{error_id}")
        ]
    ]
    
    if is_active:
        keyboard.append([
            InlineKeyboardButton("🚫 Деактивировать", callback_data=f"upos_deactivate_{error_id}")
        ])
    else:
        keyboard.append([
            InlineKeyboardButton("✅ Активировать", callback_data=f"upos_activate_{error_id}")
        ])
    
    keyboard.append([
        InlineKeyboardButton("🗑️ Удалить", callback_data=f"upos_delete_{error_id}")
    ])
    
    keyboard.append([
        InlineKeyboardButton("🔙 К списку", callback_data="upos_errors_list")
    ])
    
    return InlineKeyboardMarkup(keyboard)


def get_category_detail_keyboard(category_id: int) -> InlineKeyboardMarkup:
    """
    Build inline keyboard for category detail view (admin).
    
    Args:
        category_id: Category ID
        
    Returns:
        InlineKeyboardMarkup with edit/delete options
    """
    keyboard = [
        [
            InlineKeyboardButton("📝 Изменить название", callback_data=f"upos_cat_edit_name_{category_id}"),
        ],
        [
            InlineKeyboardButton("📋 Изменить описание", callback_data=f"upos_cat_edit_desc_{category_id}")
        ],
        [
            InlineKeyboardButton("🗑️ Удалить", callback_data=f"upos_cat_delete_{category_id}")
        ],
        [
            InlineKeyboardButton("🔙 К категориям", callback_data="upos_categories_list")
        ]
    ]
    
    return InlineKeyboardMarkup(keyboard)


def get_unknown_codes_inline_keyboard(
    unknown_codes: List[dict],
    page: int = 1,
    total_pages: int = 1
) -> InlineKeyboardMarkup:
    """
    Build inline keyboard with unknown codes for quick addition.
    
    Args:
        unknown_codes: List of unknown code dicts
        page: Current page number
        total_pages: Total number of pages
        
    Returns:
        InlineKeyboardMarkup with unknown code buttons
    """
    keyboard = []
    
    for code_info in unknown_codes:
        code = code_info['error_code']
        times = code_info['times_requested']
        
        keyboard.append([
            InlineKeyboardButton(
                f"➕ {code} ({times}x)",
                callback_data=f"upos_add_unknown_{code_info['id']}"
            )
        ])
    
    # Pagination buttons
    nav_buttons = []
    if page > 1:
        nav_buttons.append(
            InlineKeyboardButton("⬅️ Назад", callback_data=f"upos_unknown_page_{page-1}")
        )
    if page < total_pages:
        nav_buttons.append(
            InlineKeyboardButton("Вперёд ➡️", callback_data=f"upos_unknown_page_{page+1}")
        )
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([
        InlineKeyboardButton("🔙 Назад в меню", callback_data="upos_admin_menu")
    ])
    
    return InlineKeyboardMarkup(keyboard)


def get_yes_no_keyboard(action_prefix: str, item_id: Optional[int] = None) -> InlineKeyboardMarkup:
    """
    Build Yes/No confirmation keyboard.
    
    Args:
        action_prefix: Prefix for callback data
        item_id: Optional item ID to include in callback
        
    Returns:
        InlineKeyboardMarkup with Yes/No buttons
    """
    suffix = f"_{item_id}" if item_id else ""
    
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Да", callback_data=f"{action_prefix}_yes{suffix}"),
            InlineKeyboardButton("❌ Нет", callback_data=f"{action_prefix}_no{suffix}")
        ]
    ])


def get_confirm_delete_keyboard(item_type: str, item_id: int) -> InlineKeyboardMarkup:
    """
    Build delete confirmation keyboard.
    
    Args:
        item_type: Type of item ('error' or 'category')
        item_id: Item ID
        
    Returns:
        InlineKeyboardMarkup with confirm/cancel buttons
    """
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "⚠️ Да, удалить",
                callback_data=f"upos_confirm_delete_{item_type}_{item_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "❌ Отмена",
                callback_data=f"upos_{item_type}s_list"
            )
        ]
    ])


def get_csv_import_keyboard() -> ReplyKeyboardMarkup:
    """
    Build keyboard for CSV import waiting state.
    
    Returns:
        ReplyKeyboardMarkup for CSV import
    """
    return ReplyKeyboardMarkup(
        [
            ["❌ Отмена"],
            ["🔙 Админ UPOS"]
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_csv_confirm_keyboard() -> InlineKeyboardMarkup:
    """
    Build keyboard for CSV import confirmation.
    
    Returns:
        InlineKeyboardMarkup with import options
    """
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ Импортировать (пропустить существующие)",
                callback_data="upos_csv_import_skip"
            )
        ],
        [
            InlineKeyboardButton(
                "🔄 Импортировать (обновить существующие)",
                callback_data="upos_csv_import_update"
            )
        ],
        [
            InlineKeyboardButton(
                "❌ Отмена",
                callback_data="upos_csv_cancel"
            )
        ]
    ])
