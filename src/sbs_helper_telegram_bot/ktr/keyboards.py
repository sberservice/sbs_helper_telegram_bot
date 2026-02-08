"""
KTR Module Keyboards

Telegram keyboard builders for the KTR (Коэффициент Трудозатрат) code lookup module.
"""

from typing import List, Optional
from telegram import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from . import settings
from . import messages


def get_submenu_keyboard() -> ReplyKeyboardMarkup:
    """
    Build KTR submenu keyboard for regular users.
    
    Returns:
        ReplyKeyboardMarkup for KTR submenu
    """
    return ReplyKeyboardMarkup(
        settings.SUBMENU_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_admin_submenu_keyboard() -> ReplyKeyboardMarkup:
    """
    Build KTR submenu keyboard with admin panel button.
    
    Returns:
        ReplyKeyboardMarkup for admin KTR submenu
    """
    return ReplyKeyboardMarkup(
        settings.ADMIN_SUBMENU_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_admin_menu_keyboard() -> ReplyKeyboardMarkup:
    """
    Build KTR admin panel main menu keyboard.
    
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


def get_admin_codes_keyboard() -> ReplyKeyboardMarkup:
    """
    Build admin KTR codes management keyboard.
    
    Returns:
        ReplyKeyboardMarkup for KTR codes management
    """
    return ReplyKeyboardMarkup(
        settings.ADMIN_CODES_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_codes_inline_keyboard(
    codes: List[dict],
    page: int = 1,
    total_pages: int = 1,
    action_prefix: str = "ktr_view"
) -> InlineKeyboardMarkup:
    """
    Build inline keyboard with KTR codes for selection.
    
    Args:
        codes: List of code dicts with 'id', 'code', 'description', 'minutes'
        page: Current page number
        total_pages: Total number of pages
        action_prefix: Callback data prefix for actions
        
    Returns:
        InlineKeyboardMarkup with code buttons
    """
    keyboard = []
    
    for ktr in codes:
        code_id = ktr['id']
        code = ktr['code']
        minutes = ktr['minutes']
        desc = ktr.get('description', '')[:25]
        
        keyboard.append([
            InlineKeyboardButton(
                f"{code} - {desc}... ({minutes} мин.)",
                callback_data=f"{action_prefix}_{code_id}"
            )
        ])
    
    # Pagination buttons
    nav_buttons = []
    if page > 1:
        nav_buttons.append(
            InlineKeyboardButton(messages.BUTTON_BACK, callback_data=f"ktr_page_{page-1}")
        )
    if page < total_pages:
        nav_buttons.append(
            InlineKeyboardButton(messages.BUTTON_FORWARD, callback_data=f"ktr_page_{page+1}")
        )
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # Back button
    keyboard.append([
        InlineKeyboardButton(messages.BUTTON_BACK_TO_MENU, callback_data="ktr_admin_menu")
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
        for_selection: If True, used for category selection when creating code
        
    Returns:
        InlineKeyboardMarkup with category buttons
    """
    keyboard = []
    
    prefix = "ktr_cat_select" if for_selection else "ktr_cat_view"
    
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
            InlineKeyboardButton("⏭️ Пропустить", callback_data="ktr_cat_skip")
        ])
    
    # Pagination buttons
    nav_buttons = []
    if page > 1:
        nav_buttons.append(
            InlineKeyboardButton(messages.BUTTON_BACK, callback_data=f"ktr_cat_page_{page-1}")
        )
    if page < total_pages:
        nav_buttons.append(
            InlineKeyboardButton(messages.BUTTON_FORWARD, callback_data=f"ktr_cat_page_{page+1}")
        )
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # Back button (not for selection mode)
    if not for_selection:
        keyboard.append([
            InlineKeyboardButton(messages.BUTTON_BACK_TO_MENU, callback_data="ktr_admin_menu")
        ])
    
    return InlineKeyboardMarkup(keyboard)


def get_code_detail_keyboard(code_id: int, is_active: bool = True) -> InlineKeyboardMarkup:
    """
    Build inline keyboard for KTR code detail view (admin).
    
    Args:
        code_id: KTR code ID
        is_active: Whether the code is currently active
        
    Returns:
        InlineKeyboardMarkup with edit/delete options
    """
    keyboard = [
        [
            InlineKeyboardButton("📝 Описание", callback_data=f"ktr_edit_desc_{code_id}"),
            InlineKeyboardButton("⏱️ Минуты", callback_data=f"ktr_edit_minutes_{code_id}")
        ],
        [
            InlineKeyboardButton("📁 Категория", callback_data=f"ktr_edit_cat_{code_id}")
        ]
    ]
    
    if is_active:
        keyboard.append([
            InlineKeyboardButton("🚫 Деактивировать", callback_data=f"ktr_deactivate_{code_id}")
        ])
    else:
        keyboard.append([
            InlineKeyboardButton("✅ Активировать", callback_data=f"ktr_activate_{code_id}")
        ])
    
    keyboard.append([
        InlineKeyboardButton("🗑️ Удалить", callback_data=f"ktr_delete_{code_id}")
    ])
    
    keyboard.append([
        InlineKeyboardButton("🔙 К списку", callback_data="ktr_codes_list")
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
            InlineKeyboardButton("📝 Изменить название", callback_data=f"ktr_cat_edit_name_{category_id}"),
        ],
        [
            InlineKeyboardButton("📋 Изменить описание", callback_data=f"ktr_cat_edit_desc_{category_id}")
        ],
        [
            InlineKeyboardButton("🗑️ Удалить", callback_data=f"ktr_cat_delete_{category_id}")
        ],
        [
            InlineKeyboardButton("🔙 К категориям", callback_data="ktr_categories_list")
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
        code = code_info['code']
        times = code_info['times_requested']
        
        keyboard.append([
            InlineKeyboardButton(
                f"➕ {code} ({times}x)",
                callback_data=f"ktr_add_unknown_{code_info['id']}"
            )
        ])
    
    # Pagination buttons
    nav_buttons = []
    if page > 1:
        nav_buttons.append(
            InlineKeyboardButton(messages.BUTTON_BACK, callback_data=f"ktr_unknown_page_{page-1}")
        )
    if page < total_pages:
        nav_buttons.append(
            InlineKeyboardButton(messages.BUTTON_FORWARD, callback_data=f"ktr_unknown_page_{page+1}")
        )
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([
        InlineKeyboardButton(messages.BUTTON_BACK_TO_MENU, callback_data="ktr_admin_menu")
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
        item_type: Type of item ('code' or 'category')
        item_id: Item ID
        
    Returns:
        InlineKeyboardMarkup with confirm/cancel buttons
    """
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "⚠️ Да, удалить",
                callback_data=f"ktr_confirm_delete_{item_type}_{item_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "❌ Отмена",
                callback_data=f"ktr_{item_type}s_list"
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
            [settings.BUTTON_ADMIN_BACK]
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
                callback_data="ktr_csv_import_skip"
            )
        ],
        [
            InlineKeyboardButton(
                "🔄 Импортировать (обновить существующие)",
                callback_data="ktr_csv_import_update"
            )
        ],
        [
            InlineKeyboardButton(
                "❌ Отмена",
                callback_data="ktr_csv_cancel"
            )
        ]
    ])
