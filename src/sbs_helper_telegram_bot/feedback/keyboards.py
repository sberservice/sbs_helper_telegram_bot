"""
Клавиатуры модуля обратной связи

Сборщики reply- и inline-клавиатур.
"""

from typing import List
from telegram import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton

from . import settings


def get_submenu_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    """
    Получить клавиатуру подменю обратной связи.
    
    Args:
        is_admin: Показывать ли админские кнопки
        
    Returns:
        Разметка reply-клавиатуры
    """
    buttons = settings.ADMIN_SUBMENU_BUTTONS if is_admin else settings.SUBMENU_BUTTONS
    return ReplyKeyboardMarkup(
        buttons,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_admin_menu_keyboard() -> ReplyKeyboardMarkup:
    """
    Получить клавиатуру меню админ-панели.
    
    Returns:
        Разметка reply-клавиатуры
    """
    return ReplyKeyboardMarkup(
        settings.ADMIN_MENU_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """
    Получить клавиатуру только с кнопкой отмены.
    
    Returns:
        Разметка reply-клавиатуры
    """
    return ReplyKeyboardMarkup(
        [[settings.BUTTON_CANCEL]],
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_category_keyboard(categories: List[dict]) -> InlineKeyboardMarkup:
    """
    Собрать inline-клавиатуру для выбора категории.
    
    Args:
        categories: Список словарей категорий с ключами 'id', 'name', 'emoji'
        
    Returns:
        Разметка inline-клавиатуры
    """
    keyboard = []
    for cat in categories:
        emoji = cat.get('emoji', '📝')
        name = cat.get('name', 'Unknown')
        cat_id = cat.get('id', 0)
        keyboard.append([
            InlineKeyboardButton(
                f"{emoji} {name}",
                callback_data=f"{settings.CALLBACK_CATEGORY_PREFIX}{cat_id}"
            )
        ])
    
    # Добавляем кнопку отмены
    keyboard.append([
        InlineKeyboardButton(
            "❌ Отмена",
            callback_data=settings.CALLBACK_CANCEL
        )
    ])
    
    return InlineKeyboardMarkup(keyboard)


def get_confirm_keyboard() -> InlineKeyboardMarkup:
    """
    Собрать inline-клавиатуру подтверждения (Да/Нет).
    
    Returns:
        Разметка inline-клавиатуры
    """
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Да, отправить", callback_data=settings.CALLBACK_CONFIRM_YES),
            InlineKeyboardButton("❌ Нет, отменить", callback_data=settings.CALLBACK_CONFIRM_NO)
        ]
    ])


def get_my_feedback_keyboard(
    entries: List[dict],
    page: int = 0,
    total_pages: int = 1
) -> InlineKeyboardMarkup:
    """
    Собрать постраничную inline-клавиатуру для списка обращений пользователя.
    
    Args:
        entries: Список словарей записей с ключами 'id', 'category', 'status', 'date'
        page: Текущая страница (с 0)
        total_pages: Общее количество страниц
        
    Returns:
        Разметка inline-клавиатуры
    """
    keyboard = []
    
    for entry in entries:
        entry_id = entry.get('id', 0)
        status_emoji = _get_status_emoji(entry.get('status', 'new'))
        date = entry.get('date', '')
        category = entry.get('category', '')
        
        # Формат: "🆕 #123 | Ошибка | 01.01.2026"
        button_text = f"{status_emoji} #{entry_id} | {category} | {date}"
        keyboard.append([
            InlineKeyboardButton(
                button_text,
                callback_data=f"{settings.CALLBACK_ENTRY_PREFIX}{entry_id}"
            )
        ])
    
    # Кнопки пагинации
    pagination_row = []
    if page > 0:
        pagination_row.append(
            InlineKeyboardButton("◀️ Назад", callback_data=f"{settings.CALLBACK_PAGE_PREFIX}{page - 1}")
        )
    if page < total_pages - 1:
        pagination_row.append(
            InlineKeyboardButton("Вперёд ▶️", callback_data=f"{settings.CALLBACK_PAGE_PREFIX}{page + 1}")
        )
    
    if pagination_row:
        keyboard.append(pagination_row)
    
    return InlineKeyboardMarkup(keyboard)


def get_feedback_detail_keyboard(entry_id: int) -> InlineKeyboardMarkup:  # pylint: disable=unused-argument
    """
    Собрать inline-клавиатуру для просмотра деталей обращения (пользователь).
    
    Args:
        entry_id: ID обращения (зарезервировано для будущего использования)
        
    Returns:
        Разметка inline-клавиатуры
    """
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("◀️ К списку", callback_data=f"{settings.CALLBACK_PAGE_PREFIX}0")
        ]
    ])


# ===== АДМИНСКИЕ КЛАВИАТУРЫ =====


def get_admin_entries_keyboard(
    entries: List[dict],
    page: int = 0,
    total_pages: int = 1
) -> InlineKeyboardMarkup:
    """
    Собрать постраничную inline-клавиатуру для списка обращений (админ).
    
    Args:
        entries: Список словарей записей с ключами 'id', 'user_id', 'status', 'date'
        page: Текущая страница (с 0)
        total_pages: Общее количество страниц
        
    Returns:
        Разметка inline-клавиатуры
    """
    keyboard = []
    
    for entry in entries:
        entry_id = entry.get('id', 0)
        status_emoji = _get_status_emoji(entry.get('status', 'new'))
        date = entry.get('date', '')
        category = entry.get('category', '')
        
        # Формат: "🆕 #123 | Ошибка | 01.01.2026"
        button_text = f"{status_emoji} #{entry_id} | {category} | {date}"
        keyboard.append([
            InlineKeyboardButton(
                button_text,
                callback_data=f"{settings.CALLBACK_ADMIN_ENTRY_PREFIX}{entry_id}"
            )
        ])
    
    # Кнопки пагинации
    pagination_row = []
    if page > 0:
        pagination_row.append(
            InlineKeyboardButton("◀️", callback_data=f"{settings.CALLBACK_ADMIN_PAGE_PREFIX}{page - 1}")
        )
    if page < total_pages - 1:
        pagination_row.append(
            InlineKeyboardButton("▶️", callback_data=f"{settings.CALLBACK_ADMIN_PAGE_PREFIX}{page + 1}")
        )
    
    if pagination_row:
        keyboard.append(pagination_row)
    
    # Кнопка назад
    keyboard.append([
        InlineKeyboardButton("◀️ Назад", callback_data=settings.CALLBACK_ADMIN_BACK)
    ])
    
    return InlineKeyboardMarkup(keyboard)


def get_admin_entry_detail_keyboard(entry_id: int, current_status: str) -> InlineKeyboardMarkup:  # pylint: disable=unused-argument
    """
    Собрать inline-клавиатуру для просмотра деталей обращения (админ).
    
    Args:
        entry_id: ID обращения (зарезервировано для будущего использования)
        current_status: Текущий статус обращения (зарезервировано для будущего использования)
        
    Returns:
        Разметка inline-клавиатуры
    """
    keyboard = [
        [
            InlineKeyboardButton("✏️ Ответить", callback_data=settings.CALLBACK_ADMIN_REPLY),
            InlineKeyboardButton("📊 Статус", callback_data=settings.CALLBACK_ADMIN_STATUS)
        ],
        [
            InlineKeyboardButton("◀️ К списку", callback_data=settings.CALLBACK_ADMIN_BACK)
        ]
    ]
    
    return InlineKeyboardMarkup(keyboard)


def get_admin_status_keyboard(current_status: str) -> InlineKeyboardMarkup:
    """
    Build inline keyboard for status selection.
    
    Args:
        current_status: Current status (to highlight/exclude)
        
    Returns:
        Inline keyboard markup
    """
    keyboard = []
    
    for status, name in settings.STATUS_NAMES.items():
        if status != current_status:
            keyboard.append([
                InlineKeyboardButton(
                    name,
                    callback_data=f"{settings.CALLBACK_STATUS_PREFIX}{status}"
                )
            ])
    
    keyboard.append([
        InlineKeyboardButton("❌ Отмена", callback_data=settings.CALLBACK_CANCEL)
    ])
    
    return InlineKeyboardMarkup(keyboard)


def get_admin_category_keyboard(categories: List[dict]) -> InlineKeyboardMarkup:
    """
    Build inline keyboard for category filter selection (admin).
    
    Args:
        categories: List of category dicts with 'id', 'name', 'emoji', 'count' keys
        
    Returns:
        Inline keyboard markup
    """
    keyboard = []
    
    for cat in categories:
        emoji = cat.get('emoji', '📝')
        name = cat.get('name', 'Unknown')
        cat_id = cat.get('id', 0)
        count = cat.get('count', 0)
        
        button_text = f"{emoji} {name} ({count})"
        keyboard.append([
            InlineKeyboardButton(
                button_text,
                callback_data=f"{settings.CALLBACK_CATEGORY_PREFIX}{cat_id}"
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton("◀️ Назад", callback_data=settings.CALLBACK_ADMIN_BACK)
    ])
    
    return InlineKeyboardMarkup(keyboard)


def get_admin_confirm_reply_keyboard() -> InlineKeyboardMarkup:
    """
    Build inline keyboard for admin reply confirmation.
    
    Returns:
        Inline keyboard markup
    """
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Отправить", callback_data=settings.CALLBACK_CONFIRM_YES),
            InlineKeyboardButton("❌ Отменить", callback_data=settings.CALLBACK_CONFIRM_NO)
        ]
    ])


# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====


def _get_status_emoji(status: str) -> str:
    """
    Get emoji for a status.
    
    Args:
        status: Status string
        
    Returns:
        Emoji string
    """
    status_emojis = {
        settings.STATUS_NEW: "🆕",
        settings.STATUS_IN_PROGRESS: "⏳",
        settings.STATUS_RESOLVED: "✅",
        settings.STATUS_CLOSED: "🔒",
    }
    return status_emojis.get(status, "📝")
