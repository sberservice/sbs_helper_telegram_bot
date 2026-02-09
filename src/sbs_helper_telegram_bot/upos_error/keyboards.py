"""
Клавиатуры модуля ошибок UPOS

Сборщики клавиатур Telegram для модуля поиска кодов ошибок UPOS.
"""

from typing import List, Optional
from telegram import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from . import settings
from . import messages


def get_submenu_keyboard() -> ReplyKeyboardMarkup:
    """
    Собрать клавиатуру подменю ошибок UPOS для обычных пользователей.

    Returns:
        ReplyKeyboardMarkup для подменю ошибок UPOS.
    """
    return ReplyKeyboardMarkup(
        settings.SUBMENU_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_admin_submenu_keyboard() -> ReplyKeyboardMarkup:
    """
    Собрать клавиатуру подменю ошибок UPOS с кнопкой админ-панели.

    Returns:
        ReplyKeyboardMarkup для админского подменю ошибок UPOS.
    """
    return ReplyKeyboardMarkup(
        settings.ADMIN_SUBMENU_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_admin_menu_keyboard() -> ReplyKeyboardMarkup:
    """
    Собрать клавиатуру главного меню админ-панели UPOS.

    Returns:
        ReplyKeyboardMarkup для админ-меню.
    """
    return ReplyKeyboardMarkup(
        settings.ADMIN_MENU_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_admin_categories_keyboard() -> ReplyKeyboardMarkup:
    """
    Собрать клавиатуру управления категориями (админ).

    Returns:
        ReplyKeyboardMarkup для управления категориями.
    """
    return ReplyKeyboardMarkup(
        settings.ADMIN_CATEGORIES_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_admin_errors_keyboard() -> ReplyKeyboardMarkup:
    """
    Собрать клавиатуру управления кодами ошибок (админ).

    Returns:
        ReplyKeyboardMarkup для управления кодами ошибок.
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
    Собрать inline-клавиатуру с кодами ошибок для выбора.

    Args:
        error_codes: Список словарей с ключами 'id', 'error_code', 'description'.
        page: Текущая страница.
        total_pages: Общее число страниц.
        action_prefix: Префикс callback-данных для действий.

    Returns:
        InlineKeyboardMarkup с кнопками кодов ошибок.
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
    
    # Кнопки пагинации
    nav_buttons = []
    if page > 1:
        nav_buttons.append(
            InlineKeyboardButton(messages.BUTTON_BACK, callback_data=f"upos_page_{page-1}")
        )
    if page < total_pages:
        nav_buttons.append(
            InlineKeyboardButton(messages.BUTTON_FORWARD, callback_data=f"upos_page_{page+1}")
        )
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # Кнопка назад
    keyboard.append([
        InlineKeyboardButton(messages.BUTTON_BACK_TO_MENU, callback_data="upos_admin_menu")
    ])
    
    return InlineKeyboardMarkup(keyboard)


def get_categories_inline_keyboard(
    categories: List[dict],
    page: int = 1,
    total_pages: int = 1,
    for_selection: bool = False
) -> InlineKeyboardMarkup:
    """
    Собрать inline-клавиатуру с категориями.

    Args:
        categories: Список словарей категорий с ключами 'id', 'name'.
        page: Текущая страница.
        total_pages: Общее число страниц.
        for_selection: Если True, используется при выборе категории при создании ошибки.

    Returns:
        InlineKeyboardMarkup с кнопками категорий.
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
    
    # Кнопка пропуска при выборе категории
    if for_selection:
        keyboard.append([
            InlineKeyboardButton("⏭️ Пропустить", callback_data="upos_cat_skip")
        ])
    
    # Кнопки пагинации
    nav_buttons = []
    if page > 1:
        nav_buttons.append(
            InlineKeyboardButton(messages.BUTTON_BACK, callback_data=f"upos_cat_page_{page-1}")
        )
    if page < total_pages:
        nav_buttons.append(
            InlineKeyboardButton(messages.BUTTON_FORWARD, callback_data=f"upos_cat_page_{page+1}")
        )
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # Кнопка назад (не для режима выбора)
    if not for_selection:
        keyboard.append([
            InlineKeyboardButton(messages.BUTTON_BACK_TO_MENU, callback_data="upos_admin_menu")
        ])
    
    return InlineKeyboardMarkup(keyboard)


def get_error_detail_keyboard(error_id: int, is_active: bool = True) -> InlineKeyboardMarkup:
    """
    Собрать inline-клавиатуру для просмотра деталей кода ошибки (админ).

    Args:
        error_id: ID кода ошибки.
        is_active: Активен ли код ошибки сейчас.

    Returns:
        InlineKeyboardMarkup с опциями редактирования/удаления.
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
    Собрать inline-клавиатуру для просмотра категории (админ).

    Args:
        category_id: ID категории.

    Returns:
        InlineKeyboardMarkup с опциями редактирования/удаления.
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
    Собрать inline-клавиатуру с неизвестными кодами для быстрого добавления.

    Args:
        unknown_codes: Список словарей с неизвестными кодами.
        page: Текущая страница.
        total_pages: Общее число страниц.

    Returns:
        InlineKeyboardMarkup с кнопками неизвестных кодов.
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
    
    # Кнопки пагинации
    nav_buttons = []
    if page > 1:
        nav_buttons.append(
            InlineKeyboardButton(messages.BUTTON_BACK, callback_data=f"upos_unknown_page_{page-1}")
        )
    if page < total_pages:
        nav_buttons.append(
            InlineKeyboardButton(messages.BUTTON_FORWARD, callback_data=f"upos_unknown_page_{page+1}")
        )
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([
        InlineKeyboardButton(messages.BUTTON_BACK_TO_MENU, callback_data="upos_admin_menu")
    ])
    
    return InlineKeyboardMarkup(keyboard)


def get_yes_no_keyboard(action_prefix: str, item_id: Optional[int] = None) -> InlineKeyboardMarkup:
    """
    Собрать клавиатуру подтверждения Да/Нет.

    Args:
        action_prefix: Префикс callback-данных.
        item_id: Необязательный ID элемента для включения в callback.

    Returns:
        InlineKeyboardMarkup с кнопками Да/Нет.
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
    Собрать клавиатуру подтверждения удаления.

    Args:
        item_type: Тип элемента ('error' или 'category').
        item_id: ID элемента.

    Returns:
        InlineKeyboardMarkup с кнопками подтверждения/отмены.
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
    Собрать клавиатуру для режима ожидания импорта CSV.

    Returns:
        ReplyKeyboardMarkup для импорта CSV.
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
    Собрать клавиатуру подтверждения импорта CSV.

    Returns:
        InlineKeyboardMarkup с вариантами импорта.
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
