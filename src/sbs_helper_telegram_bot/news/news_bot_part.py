"""
News Module User Handlers

User-facing handlers for viewing news, reactions, search, and archive.
"""

import logging
from datetime import datetime

from telegram import Update, constants
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    CommandHandler,
    filters
)

from src.common.telegram_user import check_if_user_legit, check_if_user_admin
from src.common.messages import BUTTON_MAIN_MENU, get_main_menu_keyboard

from . import settings
from . import messages
from . import keyboards
from . import news_logic

logger = logging.getLogger(__name__)


# ===== ENTRY POINTS =====


async def news_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Entry point for news module.
    Shows submenu and marks all news as read.
    """
    user_id = update.effective_user.id
    
    if not check_if_user_legit(user_id):
        return ConversationHandler.END
    
    # Mark all news as read when entering the module
    news_logic.mark_all_as_read(user_id)
    
    is_admin = check_if_user_admin(user_id)
    keyboard = keyboards.get_submenu_keyboard(is_admin=is_admin)
    
    await update.message.reply_text(
        messages.MESSAGE_SUBMENU,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboard
    )
    
    return settings.STATE_SUBMENU


# ===== VIEW NEWS =====


async def show_latest_news(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Show list of latest (non-expired) published news.
    """
    user_id = update.effective_user.id
    page = context.user_data.get(settings.CURRENT_PAGE_KEY, 0)
    
    # Get news
    articles, total = news_logic.get_published_news(page=page, include_expired=False)
    
    if not articles:
        await update.message.reply_text(
            messages.MESSAGE_NO_NEWS,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return settings.STATE_SUBMENU
    
    # Build message with all articles on current page
    total_pages = (total + settings.ITEMS_PER_PAGE - 1) // settings.ITEMS_PER_PAGE
    
    text = messages.MESSAGE_NEWS_LIST_HEADER
    
    for article in articles:
        text += _format_article_preview(article)
        text += "\n\n" + "─" * 20 + "\n\n"
    
    # Get keyboard with article links
    keyboard = keyboards.get_news_list_keyboard(
        articles, page, total_pages,
        prefix=settings.CALLBACK_ARTICLE_PREFIX,
        page_prefix=settings.CALLBACK_PAGE_PREFIX
    )
    
    # First send reply keyboard so user can navigate
    await update.message.reply_text(
        text,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_article_view_keyboard()
    )
    
    # Then send article list with inline keyboard
    await update.message.reply_text(
        "👆 Выберите новость для просмотра:",
        reply_markup=keyboard
    )
    
    context.user_data[settings.VIEW_MODE_KEY] = 'latest'
    return settings.STATE_VIEW_NEWS


async def handle_news_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle pagination callback for news list.
    """
    query = update.callback_query
    await query.answer()
    
    # Extract page number from callback data
    page = int(query.data.replace(settings.CALLBACK_PAGE_PREFIX, ''))
    context.user_data[settings.CURRENT_PAGE_KEY] = page
    
    view_mode = context.user_data.get(settings.VIEW_MODE_KEY, 'latest')
    
    if view_mode == 'archive':
        articles, total = news_logic.get_published_news(page=page, include_expired=True)
        header = messages.MESSAGE_ARCHIVE_HEADER.format(days=news_logic.get_news_expiry_days())
    elif view_mode == 'search':
        search_query = context.user_data.get(settings.SEARCH_QUERY_KEY, '')
        articles, total = news_logic.search_news(search_query, page=page)
        header = messages.MESSAGE_SEARCH_RESULTS.format(
            query=messages.escape_markdown_v2(search_query),
            count=total
        )
    else:
        articles, total = news_logic.get_published_news(page=page, include_expired=False)
        header = messages.MESSAGE_NEWS_LIST_HEADER
    
    if not articles:
        return settings.STATE_VIEW_NEWS
    
    total_pages = (total + settings.ITEMS_PER_PAGE - 1) // settings.ITEMS_PER_PAGE
    
    text = header
    for article in articles:
        text += _format_article_preview(article)
        text += "\n\n" + "─" * 20 + "\n\n"
    
    keyboard = keyboards.get_news_list_keyboard(
        articles, page, total_pages,
        prefix=settings.CALLBACK_ARTICLE_PREFIX,
        page_prefix=settings.CALLBACK_PAGE_PREFIX
    )
    
    await query.edit_message_text(
        text,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboard
    )
    
    return settings.STATE_VIEW_NEWS


async def handle_article_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle click on a specific article to view it in full.
    """
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    article_id = int(query.data.replace(settings.CALLBACK_ARTICLE_PREFIX, ''))
    
    article = news_logic.get_article_by_id(article_id)
    if not article:
        await query.edit_message_text(
            messages.MESSAGE_ARTICLE_NOT_FOUND,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return settings.STATE_VIEW_NEWS
    
    # Format full article
    text = _format_full_article(article)
    
    # Get reactions and user's reaction
    reactions = news_logic.get_article_reactions(article_id)
    user_reaction = news_logic.get_user_reaction(article_id, user_id)
    
    keyboard = keyboards.get_reaction_keyboard(article_id, reactions, user_reaction)
    reply_keyboard = keyboards.get_article_view_keyboard()
    
    # Send article (with image if present)
    if article.get('image_file_id'):
        await query.message.reply_photo(
            photo=article['image_file_id'],
            caption=text,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboard
        )
        # Send a separate message to update reply keyboard
        await query.message.reply_text(
            "↑ Используйте кнопки под статьёй для реакций",
            reply_markup=reply_keyboard
        )
    else:
        await query.message.reply_text(
            text,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboard
        )
        # Send a separate message to update reply keyboard
        await query.message.reply_text(
            "↑ Используйте кнопки под статьёй для реакций",
            reply_markup=reply_keyboard
        )
    
    # Send attachment if present
    if article.get('attachment_file_id'):
        await query.message.reply_document(
            document=article['attachment_file_id'],
            filename=article.get('attachment_filename'),
            caption="📎 Прикреплённый файл"
        )
    
    return settings.STATE_VIEW_NEWS


# ===== REACTIONS =====


async def handle_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle reaction button click (like/love/dislike).
    """
    query = update.callback_query
    user_id = update.effective_user.id
    
    # Parse callback data: news_react_{article_id}_{reaction_type}
    parts = query.data.replace(settings.CALLBACK_REACT_PREFIX, '').split('_')
    if len(parts) != 2:
        await query.answer("Ошибка")
        return
    
    article_id = int(parts[0])
    reaction_type = parts[1]
    
    if reaction_type not in [settings.REACTION_LIKE, settings.REACTION_LOVE, settings.REACTION_DISLIKE]:
        await query.answer("Неизвестная реакция")
        return
    
    # Toggle reaction
    was_added = news_logic.set_reaction(article_id, user_id, reaction_type)
    
    # Update keyboard with new counts
    reactions = news_logic.get_article_reactions(article_id)
    user_reaction = news_logic.get_user_reaction(article_id, user_id)
    
    keyboard = keyboards.get_reaction_keyboard(article_id, reactions, user_reaction)
    
    try:
        await query.edit_message_reply_markup(reply_markup=keyboard)
        emoji = settings.REACTION_EMOJIS.get(reaction_type, '👍')
        if was_added:
            await query.answer(f"{emoji} Спасибо за реакцию!")
        else:
            await query.answer("Реакция убрана")
    except Exception:
        await query.answer("Готово")


# ===== ARCHIVE =====


async def show_archive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Show archived (expired) news.
    """
    context.user_data[settings.CURRENT_PAGE_KEY] = 0
    context.user_data[settings.VIEW_MODE_KEY] = 'archive'
    
    articles, total = news_logic.get_published_news(page=0, include_expired=True)
    
    if not articles:
        await update.message.reply_text(
            messages.MESSAGE_ARCHIVE_EMPTY,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return settings.STATE_SUBMENU
    
    expiry_days = news_logic.get_news_expiry_days()
    total_pages = (total + settings.ITEMS_PER_PAGE - 1) // settings.ITEMS_PER_PAGE
    
    text = messages.MESSAGE_ARCHIVE_HEADER.format(days=expiry_days)
    
    for article in articles:
        text += _format_article_preview(article)
        text += "\n\n" + "─" * 20 + "\n\n"
    
    keyboard = keyboards.get_news_list_keyboard(
        articles, 0, total_pages,
        prefix=settings.CALLBACK_ARTICLE_PREFIX,
        page_prefix=settings.CALLBACK_PAGE_PREFIX
    )
    
    # First send reply keyboard so user can navigate
    await update.message.reply_text(
        text,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_article_view_keyboard()
    )
    
    # Then send article list with inline keyboard
    await update.message.reply_text(
        "👆 Выберите новость для просмотра:",
        reply_markup=keyboard
    )
    
    return settings.STATE_VIEW_NEWS


# ===== SEARCH =====


async def search_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Show search prompt.
    """
    await update.message.reply_text(
        messages.MESSAGE_SEARCH_PROMPT,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_cancel_keyboard()
    )
    return settings.STATE_SEARCH_INPUT


async def handle_search_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Process search query and show results.
    """
    query = update.message.text.strip()
    
    if not query or len(query) < 2:
        await update.message.reply_text(
            "Введите минимум 2 символа для поиска\\.",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return settings.STATE_SEARCH_INPUT
    
    context.user_data[settings.SEARCH_QUERY_KEY] = query
    context.user_data[settings.CURRENT_PAGE_KEY] = 0
    context.user_data[settings.VIEW_MODE_KEY] = 'search'
    
    articles, total = news_logic.search_news(query, page=0)
    
    is_admin = check_if_user_admin(update.effective_user.id)
    
    if not articles:
        await update.message.reply_text(
            messages.MESSAGE_SEARCH_NO_RESULTS,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_submenu_keyboard(is_admin=is_admin)
        )
        return settings.STATE_SUBMENU
    
    total_pages = (total + settings.ITEMS_PER_PAGE - 1) // settings.ITEMS_PER_PAGE
    
    text = messages.MESSAGE_SEARCH_RESULTS.format(
        query=messages.escape_markdown_v2(query),
        count=total
    )
    
    for article in articles:
        text += _format_article_preview(article)
        text += "\n\n" + "─" * 20 + "\n\n"
    
    keyboard = keyboards.get_news_list_keyboard(
        articles, 0, total_pages,
        prefix=settings.CALLBACK_ARTICLE_PREFIX,
        page_prefix=settings.CALLBACK_SEARCH_PAGE_PREFIX
    )
    
    # First send reply keyboard so user can navigate
    await update.message.reply_text(
        text,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_article_view_keyboard()
    )
    
    # Then send article list with inline keyboard
    await update.message.reply_text(
        "👆 Выберите новость для просмотра:",
        reply_markup=keyboard
    )
    
    return settings.STATE_VIEW_NEWS


# ===== MANDATORY NEWS ACKNOWLEDGMENT =====


async def handle_mandatory_ack(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle acknowledgment of mandatory news.
    """
    query = update.callback_query
    user_id = update.effective_user.id
    
    # Extract news ID
    news_id = int(query.data.replace(settings.CALLBACK_ACK_PREFIX, ''))
    
    # Record acknowledgment
    news_logic.acknowledge_mandatory_news(news_id, user_id)
    
    await query.answer("✅ Принято")
    
    # Check if there are more mandatory news
    next_mandatory = news_logic.get_unacked_mandatory_news(user_id)
    
    if next_mandatory:
        # Show next mandatory news
        text = messages.MESSAGE_MANDATORY_NEWS + "\n\n"
        text += _format_full_article(next_mandatory)
        
        keyboard = keyboards.get_mandatory_ack_keyboard(next_mandatory['id'])
        
        if next_mandatory.get('image_file_id'):
            await query.message.reply_photo(
                photo=next_mandatory['image_file_id'],
                caption=text,
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=keyboard
            )
        else:
            await query.message.reply_text(
                text,
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=keyboard
            )
    else:
        # All mandatory news acknowledged
        is_admin = check_if_user_admin(user_id)
        await query.message.reply_text(
            messages.MESSAGE_MANDATORY_ACKNOWLEDGED,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=get_main_menu_keyboard(is_admin=is_admin)
        )


# ===== NAVIGATION =====


async def back_to_submenu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Return to news submenu.
    """
    user_id = update.effective_user.id
    is_admin = check_if_user_admin(user_id)
    
    # Clear context
    context.user_data.pop(settings.CURRENT_PAGE_KEY, None)
    context.user_data.pop(settings.SEARCH_QUERY_KEY, None)
    context.user_data.pop(settings.VIEW_MODE_KEY, None)
    
    await update.message.reply_text(
        messages.MESSAGE_SUBMENU,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_submenu_keyboard(is_admin=is_admin)
    )
    
    return settings.STATE_SUBMENU


async def back_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Return to main menu.
    """
    user_id = update.effective_user.id
    is_admin = check_if_user_admin(user_id)
    
    # Clear all context
    for key in [settings.CURRENT_PAGE_KEY, settings.SEARCH_QUERY_KEY, settings.VIEW_MODE_KEY]:
        context.user_data.pop(key, None)
    
    from src.common.messages import MESSAGE_MAIN_MENU
    
    await update.message.reply_text(
        MESSAGE_MAIN_MENU,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=get_main_menu_keyboard(is_admin=is_admin)
    )
    
    return ConversationHandler.END


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle /cancel command.
    """
    return await back_to_submenu(update, context)


# ===== HELPER FUNCTIONS =====


def _format_article_preview(article: dict) -> str:
    """
    Format article for list preview (title + truncated content).
    """
    title = messages.escape_markdown_v2(article.get('title', 'Без названия'))
    category_emoji = article.get('category_emoji', '📰')
    category_name = messages.escape_markdown_v2(article.get('category_name', ''))
    
    published_ts = article.get('published_timestamp', 0)
    if published_ts:
        published_date = datetime.fromtimestamp(published_ts).strftime('%d.%m.%Y')
        published_date = messages.escape_markdown_v2(published_date)
    else:
        published_date = ""
    
    # Truncate content for preview
    content = article.get('content', '')
    if len(content) > 200:
        content = content[:197] + "..."
    
    # Escape content for MarkdownV2
    content = messages.escape_markdown_v2(content)
    
    text = f"{category_emoji} *{title}*\n"
    text += f"_{category_name} • {published_date}_\n\n"
    text += content
    
    return text


def _format_full_article(article: dict) -> str:
    """
    Format full article for viewing.
    """
    title = messages.escape_markdown_v2(article.get('title', 'Без названия'))
    content = messages.escape_markdown_v2(article.get('content', ''))
    category_emoji = article.get('category_emoji', '📰')
    category_name = messages.escape_markdown_v2(article.get('category_name', ''))
    
    published_ts = article.get('published_timestamp', 0)
    if published_ts:
        published_date = datetime.fromtimestamp(published_ts).strftime('%d.%m.%Y')
        published_date = messages.escape_markdown_v2(published_date)
    else:
        published_date = ""
    
    reactions = news_logic.get_article_reactions(article['id'])
    
    return messages.format_news_article(
        title=title,
        content=content,
        category_emoji=category_emoji,
        category_name=category_name,
        published_date=published_date,
        reactions=reactions
    )


# ===== CONVERSATION HANDLER =====


def get_news_user_handler() -> ConversationHandler:
    """
    Create and return the news user ConversationHandler.
    """
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(f"^{settings.MENU_BUTTON_TEXT}$"), news_entry),
            MessageHandler(filters.Regex("^📰 Новости"), news_entry),  # With unread count
        ],
        states={
            settings.STATE_SUBMENU: [
                MessageHandler(filters.Regex(f"^{settings.BUTTON_LATEST_NEWS}$"), show_latest_news),
                MessageHandler(filters.Regex(f"^{settings.BUTTON_ARCHIVE}$"), show_archive),
                MessageHandler(filters.Regex(f"^{settings.BUTTON_SEARCH}$"), search_prompt),
                MessageHandler(filters.Regex(f"^{settings.BUTTON_ADMIN_PANEL}$"), _admin_panel_redirect),
                MessageHandler(filters.Regex(f"^{BUTTON_MAIN_MENU}$"), back_to_main_menu),
            ],
            settings.STATE_VIEW_NEWS: [
                CallbackQueryHandler(handle_article_view, pattern=f"^{settings.CALLBACK_ARTICLE_PREFIX}"),
                CallbackQueryHandler(handle_news_pagination, pattern=f"^{settings.CALLBACK_PAGE_PREFIX}"),
                CallbackQueryHandler(handle_news_pagination, pattern=f"^{settings.CALLBACK_SEARCH_PAGE_PREFIX}"),
                CallbackQueryHandler(handle_reaction, pattern=f"^{settings.CALLBACK_REACT_PREFIX}"),
                MessageHandler(filters.Regex(f"^{settings.BUTTON_BACK}$"), back_to_submenu),
                MessageHandler(filters.Regex(f"^{BUTTON_MAIN_MENU}$"), back_to_main_menu),
            ],
            settings.STATE_SEARCH_INPUT: [
                MessageHandler(filters.Regex(f"^{settings.BUTTON_CANCEL}$"), back_to_submenu),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search_query),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_command),
            MessageHandler(filters.Regex(f"^{BUTTON_MAIN_MENU}$"), back_to_main_menu),
        ],
        name="news_user_handler",
        persistent=False
    )


async def _admin_panel_redirect(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Redirect to admin panel (handled by separate handler).
    """
    user_id = update.effective_user.id
    if not check_if_user_admin(user_id):
        await update.message.reply_text(
            messages.MESSAGE_ADMIN_NOT_AUTHORIZED,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return settings.STATE_SUBMENU
    
    # The admin panel handler will take over
    return ConversationHandler.END


# ===== GLOBAL HANDLER FOR MANDATORY NEWS ACK =====


def get_mandatory_ack_handler() -> CallbackQueryHandler:
    """
    Create callback handler for mandatory news acknowledgment.
    This should be registered globally, not in ConversationHandler.
    """
    return CallbackQueryHandler(handle_mandatory_ack, pattern=f"^{settings.CALLBACK_ACK_PREFIX}")
