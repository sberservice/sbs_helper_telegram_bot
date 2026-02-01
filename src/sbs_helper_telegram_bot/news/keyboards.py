"""
News Module Keyboards

Keyboard builders for reply and inline keyboards.
"""

from typing import List, Optional
from telegram import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton

from . import settings


def get_submenu_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    """
    Get the news submenu keyboard.
    
    Args:
        is_admin: Whether to show admin buttons
        
    Returns:
        Reply keyboard markup
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
    Get the admin panel menu keyboard.
    
    Returns:
        Reply keyboard markup
    """
    return ReplyKeyboardMarkup(
        settings.ADMIN_MENU_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_admin_category_keyboard() -> ReplyKeyboardMarkup:
    """
    Get the admin category management keyboard.
    
    Returns:
        Reply keyboard markup
    """
    return ReplyKeyboardMarkup(
        settings.ADMIN_CATEGORY_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """
    Get a keyboard with just a cancel button.
    
    Returns:
        Reply keyboard markup
    """
    return ReplyKeyboardMarkup(
        [[settings.BUTTON_CANCEL]],
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_skip_cancel_keyboard() -> ReplyKeyboardMarkup:
    """
    Get a keyboard with skip and cancel buttons.
    
    Returns:
        Reply keyboard markup
    """
    return ReplyKeyboardMarkup(
        [["⏭️ Пропустить"], [settings.BUTTON_CANCEL]],
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_back_keyboard() -> ReplyKeyboardMarkup:
    """
    Get a keyboard with just a back button.
    
    Returns:
        Reply keyboard markup
    """
    return ReplyKeyboardMarkup(
        [[settings.BUTTON_BACK]],
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_article_view_keyboard() -> ReplyKeyboardMarkup:
    """
    Get a keyboard for viewing articles with Back and Main Menu buttons.
    
    Returns:
        Reply keyboard markup
    """
    return ReplyKeyboardMarkup(
        [[settings.BUTTON_BACK, settings.BUTTON_MAIN_MENU]],
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


# ===== INLINE KEYBOARDS =====


def get_reaction_keyboard(news_id: int, reactions: dict, user_reaction: Optional[str] = None) -> InlineKeyboardMarkup:
    """
    Build inline keyboard with reaction buttons and counts.
    
    Args:
        news_id: Article ID
        reactions: Dict with like/love/dislike counts
        user_reaction: Current user's reaction type (to highlight)
        
    Returns:
        Inline keyboard markup
    """
    like_count = reactions.get('like', 0)
    love_count = reactions.get('love', 0)
    dislike_count = reactions.get('dislike', 0)
    
    # Add highlight if user has reacted
    like_text = f"{'✓' if user_reaction == 'like' else ''}👍 {like_count}" if like_count > 0 else "👍"
    love_text = f"{'✓' if user_reaction == 'love' else ''}❤️ {love_count}" if love_count > 0 else "❤️"
    dislike_text = f"{'✓' if user_reaction == 'dislike' else ''}👎 {dislike_count}" if dislike_count > 0 else "👎"
    
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(like_text, callback_data=f"{settings.CALLBACK_REACT_PREFIX}{news_id}_like"),
            InlineKeyboardButton(love_text, callback_data=f"{settings.CALLBACK_REACT_PREFIX}{news_id}_love"),
            InlineKeyboardButton(dislike_text, callback_data=f"{settings.CALLBACK_REACT_PREFIX}{news_id}_dislike"),
        ]
    ])


def get_mandatory_ack_keyboard(news_id: int) -> InlineKeyboardMarkup:
    """
    Build keyboard for mandatory news acknowledgment.
    
    Args:
        news_id: Article ID
        
    Returns:
        Inline keyboard markup
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Принято", callback_data=f"{settings.CALLBACK_ACK_PREFIX}{news_id}")]
    ])


def get_pagination_keyboard(
    page: int,
    total_pages: int,
    prefix: str = settings.CALLBACK_PAGE_PREFIX
) -> List[InlineKeyboardButton]:
    """
    Build pagination row for inline keyboards.
    
    Args:
        page: Current page (0-indexed)
        total_pages: Total number of pages
        prefix: Callback data prefix
        
    Returns:
        List of inline keyboard buttons for pagination
    """
    nav_row = []
    
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️", callback_data=f"{prefix}{page - 1}"))
    
    nav_row.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data=settings.CALLBACK_NOOP))
    
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("➡️", callback_data=f"{prefix}{page + 1}"))
    
    return nav_row


def get_news_list_keyboard(
    articles: List[dict],
    page: int,
    total_pages: int,
    prefix: str = settings.CALLBACK_ARTICLE_PREFIX,
    page_prefix: str = settings.CALLBACK_PAGE_PREFIX
) -> InlineKeyboardMarkup:
    """
    Build inline keyboard for news article list with pagination.
    
    Args:
        articles: List of article dicts with 'id', 'title', 'category_emoji'
        page: Current page (0-indexed)
        total_pages: Total number of pages
        prefix: Callback data prefix for article selection
        page_prefix: Callback data prefix for pagination
        
    Returns:
        Inline keyboard markup
    """
    keyboard = []
    
    for article in articles:
        emoji = article.get('category_emoji', '📰')
        title = article.get('title', 'Без названия')
        # Truncate title if too long
        if len(title) > 35:
            title = title[:32] + "..."
        article_id = article.get('id', 0)
        
        keyboard.append([
            InlineKeyboardButton(
                f"{emoji} {title}",
                callback_data=f"{prefix}{article_id}"
            )
        ])
    
    # Add pagination if needed
    if total_pages > 1:
        keyboard.append(get_pagination_keyboard(page, total_pages, page_prefix))
    
    return InlineKeyboardMarkup(keyboard)


def get_category_keyboard(categories: List[dict]) -> InlineKeyboardMarkup:
    """
    Build inline keyboard for category selection.
    
    Args:
        categories: List of category dicts with 'id', 'name', 'emoji'
        
    Returns:
        Inline keyboard markup
    """
    keyboard = []
    
    for cat in categories:
        emoji = cat.get('emoji', '📝')
        name = cat.get('name', 'Unknown')
        cat_id = cat.get('id', 0)
        keyboard.append([
            InlineKeyboardButton(
                f"{emoji} {name}",
                callback_data=f"{settings.CALLBACK_ADMIN_CATEGORY_PREFIX}{cat_id}"
            )
        ])
    
    # Add cancel button
    keyboard.append([
        InlineKeyboardButton("❌ Отмена", callback_data=settings.CALLBACK_CANCEL)
    ])
    
    return InlineKeyboardMarkup(keyboard)


def get_publish_mode_keyboard() -> InlineKeyboardMarkup:
    """
    Build keyboard for selecting publish mode (silent/notify).
    
    Returns:
        Inline keyboard markup
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔕 Тихая публикация", callback_data=f"{settings.CALLBACK_ADMIN_ACTION_PREFIX}silent")],
        [InlineKeyboardButton("📢 С уведомлением", callback_data=f"{settings.CALLBACK_ADMIN_ACTION_PREFIX}notify")],
        [InlineKeyboardButton("❌ Отмена", callback_data=settings.CALLBACK_CANCEL)]
    ])


def get_mandatory_mode_keyboard() -> InlineKeyboardMarkup:
    """
    Build keyboard for selecting mandatory mode.
    
    Returns:
        Inline keyboard markup
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚨 Обязательная", callback_data=f"{settings.CALLBACK_ADMIN_ACTION_PREFIX}mandatory")],
        [InlineKeyboardButton("📰 Обычная", callback_data=f"{settings.CALLBACK_ADMIN_ACTION_PREFIX}normal")],
        [InlineKeyboardButton("❌ Отмена", callback_data=settings.CALLBACK_CANCEL)]
    ])


def get_confirm_keyboard(action: str = "publish") -> InlineKeyboardMarkup:
    """
    Build confirmation keyboard (yes/no).
    
    Args:
        action: Action being confirmed
        
    Returns:
        Inline keyboard markup
    """
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Да", callback_data=f"{settings.CALLBACK_ADMIN_CONFIRM_PREFIX}yes_{action}"),
            InlineKeyboardButton("❌ Нет", callback_data=f"{settings.CALLBACK_ADMIN_CONFIRM_PREFIX}no_{action}")
        ]
    ])


def get_admin_article_actions_keyboard(article_id: int, status: str) -> InlineKeyboardMarkup:
    """
    Build keyboard with admin actions for an article.
    
    Args:
        article_id: Article ID
        status: Current article status
        
    Returns:
        Inline keyboard markup
    """
    keyboard = []
    
    if status == settings.STATUS_DRAFT:
        # Draft actions
        keyboard.append([
            InlineKeyboardButton("👁️ Превью", callback_data=f"{settings.CALLBACK_ADMIN_ACTION_PREFIX}preview_{article_id}"),
            InlineKeyboardButton("📢 Опубликовать", callback_data=f"{settings.CALLBACK_ADMIN_ACTION_PREFIX}publish_{article_id}")
        ])
        keyboard.append([
            InlineKeyboardButton("✏️ Заголовок", callback_data=f"{settings.CALLBACK_ADMIN_EDIT_PREFIX}title_{article_id}"),
            InlineKeyboardButton("✏️ Текст", callback_data=f"{settings.CALLBACK_ADMIN_EDIT_PREFIX}content_{article_id}")
        ])
        keyboard.append([
            InlineKeyboardButton("🖼️ Изображение", callback_data=f"{settings.CALLBACK_ADMIN_EDIT_PREFIX}image_{article_id}"),
            InlineKeyboardButton("📎 Файл", callback_data=f"{settings.CALLBACK_ADMIN_EDIT_PREFIX}file_{article_id}")
        ])
        keyboard.append([
            InlineKeyboardButton("📂 Категория", callback_data=f"{settings.CALLBACK_ADMIN_EDIT_PREFIX}category_{article_id}"),
            InlineKeyboardButton("🔔 Режим", callback_data=f"{settings.CALLBACK_ADMIN_EDIT_PREFIX}mode_{article_id}")
        ])
        keyboard.append([
            InlineKeyboardButton("🗑️ Удалить", callback_data=f"{settings.CALLBACK_ADMIN_ACTION_PREFIX}delete_{article_id}")
        ])
    elif status == settings.STATUS_PUBLISHED:
        # Published article actions
        keyboard.append([
            InlineKeyboardButton("📤 Повторная рассылка", callback_data=f"{settings.CALLBACK_ADMIN_ACTION_PREFIX}rebroadcast_{article_id}")
        ])
        keyboard.append([
            InlineKeyboardButton("📂 В архив", callback_data=f"{settings.CALLBACK_ADMIN_ACTION_PREFIX}archive_{article_id}"),
            InlineKeyboardButton("🗑️ Удалить", callback_data=f"{settings.CALLBACK_ADMIN_ACTION_PREFIX}delete_{article_id}")
        ])
    
    # Back button
    keyboard.append([
        InlineKeyboardButton("◀️ Назад", callback_data=f"{settings.CALLBACK_ADMIN_ACTION_PREFIX}back")
    ])
    
    return InlineKeyboardMarkup(keyboard)


def get_admin_category_list_keyboard(categories: List[dict], page: int = 0, total_pages: int = 1) -> InlineKeyboardMarkup:
    """
    Build keyboard for admin category list.
    
    Args:
        categories: List of category dicts
        page: Current page
        total_pages: Total pages
        
    Returns:
        Inline keyboard markup
    """
    keyboard = []
    
    for cat in categories:
        emoji = cat.get('emoji', '📝')
        name = cat.get('name', 'Unknown')
        cat_id = cat.get('id', 0)
        count = cat.get('article_count', 0)
        active = "✓" if cat.get('active', True) else "✗"
        
        keyboard.append([
            InlineKeyboardButton(
                f"{emoji} {name} ({count}) {active}",
                callback_data=f"{settings.CALLBACK_ADMIN_CATEGORY_PREFIX}edit_{cat_id}"
            )
        ])
    
    # Add pagination if needed
    if total_pages > 1:
        keyboard.append(get_pagination_keyboard(page, total_pages, f"{settings.CALLBACK_ADMIN_CATEGORY_PREFIX}page_"))
    
    return InlineKeyboardMarkup(keyboard)


def get_admin_category_edit_keyboard(category_id: int, is_active: bool) -> InlineKeyboardMarkup:
    """
    Build keyboard for category editing.
    
    Args:
        category_id: Category ID
        is_active: Whether category is currently active
        
    Returns:
        Inline keyboard markup
    """
    toggle_text = "🔴 Деактивировать" if is_active else "🟢 Активировать"
    toggle_action = "deactivate" if is_active else "activate"
    
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✏️ Название", callback_data=f"{settings.CALLBACK_ADMIN_CATEGORY_PREFIX}name_{category_id}"),
            InlineKeyboardButton("😀 Эмодзи", callback_data=f"{settings.CALLBACK_ADMIN_CATEGORY_PREFIX}emoji_{category_id}")
        ],
        [
            InlineKeyboardButton(toggle_text, callback_data=f"{settings.CALLBACK_ADMIN_CATEGORY_PREFIX}{toggle_action}_{category_id}")
        ],
        [
            InlineKeyboardButton("🗑️ Удалить", callback_data=f"{settings.CALLBACK_ADMIN_CATEGORY_PREFIX}delete_{category_id}")
        ],
        [
            InlineKeyboardButton("◀️ Назад", callback_data=f"{settings.CALLBACK_ADMIN_CATEGORY_PREFIX}back")
        ]
    ])
