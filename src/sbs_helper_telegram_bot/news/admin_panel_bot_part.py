"""
News Module Admin Handlers

Admin panel for creating, editing, publishing, and managing news articles and categories.
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

from src.common.telegram_user import check_if_user_admin
from src.common.messages import BUTTON_MAIN_MENU, get_main_menu_keyboard

from . import settings
from . import messages
from . import keyboards
from . import news_logic

logger = logging.getLogger(__name__)


# ===== AUTHORIZATION CHECK =====


def _check_admin(user_id: int) -> bool:
    """Check if user is admin."""
    return check_if_user_admin(user_id)


# ===== ENTRY POINT =====


async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Entry point for admin panel.
    """
    user_id = update.effective_user.id
    
    if not _check_admin(user_id):
        await update.message.reply_text(
            messages.MESSAGE_ADMIN_NOT_AUTHORIZED,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ConversationHandler.END
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_MENU,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_admin_menu_keyboard()
    )
    
    return settings.STATE_ADMIN_MENU


# ===== DRAFTS LIST =====


async def show_drafts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Show list of draft articles.
    """
    page = context.user_data.get(settings.ADMIN_LIST_PAGE_KEY, 0)
    
    articles, total = news_logic.get_articles_by_status(settings.STATUS_DRAFT, page=page)
    
    if not articles:
        await update.message.reply_text(
            messages.MESSAGE_ADMIN_DRAFTS_EMPTY,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_admin_menu_keyboard()
        )
        return settings.STATE_ADMIN_MENU
    
    total_pages = (total + settings.ITEMS_PER_PAGE - 1) // settings.ITEMS_PER_PAGE
    
    text = messages.MESSAGE_ADMIN_DRAFTS_LIST.format(count=total)
    
    keyboard = keyboards.get_news_list_keyboard(
        articles, page, total_pages,
        prefix=settings.CALLBACK_ADMIN_ARTICLE_PREFIX,
        page_prefix=settings.CALLBACK_ADMIN_PAGE_PREFIX
    )
    
    await update.message.reply_text(
        text,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboard
    )
    
    context.user_data['admin_view_status'] = settings.STATUS_DRAFT
    return settings.STATE_ADMIN_DRAFTS_LIST


# ===== PUBLISHED LIST =====


async def show_published(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Show list of published articles.
    """
    page = context.user_data.get(settings.ADMIN_LIST_PAGE_KEY, 0)
    
    articles, total = news_logic.get_articles_by_status(settings.STATUS_PUBLISHED, page=page)
    
    if not articles:
        await update.message.reply_text(
            messages.MESSAGE_ADMIN_PUBLISHED_EMPTY,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_admin_menu_keyboard()
        )
        return settings.STATE_ADMIN_MENU
    
    total_pages = (total + settings.ITEMS_PER_PAGE - 1) // settings.ITEMS_PER_PAGE
    
    text = messages.MESSAGE_ADMIN_PUBLISHED_LIST.format(count=total)
    
    keyboard = keyboards.get_news_list_keyboard(
        articles, page, total_pages,
        prefix=settings.CALLBACK_ADMIN_ARTICLE_PREFIX,
        page_prefix=settings.CALLBACK_ADMIN_PAGE_PREFIX
    )
    
    await update.message.reply_text(
        text,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboard
    )
    
    context.user_data['admin_view_status'] = settings.STATUS_PUBLISHED
    return settings.STATE_ADMIN_PUBLISHED_LIST


# ===== ARTICLE DETAIL =====


async def handle_admin_article_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle selection of an article from admin list.
    """
    query = update.callback_query
    await query.answer()
    
    article_id = int(query.data.replace(settings.CALLBACK_ADMIN_ARTICLE_PREFIX, ''))
    article = news_logic.get_article_by_id(article_id)
    
    if not article:
        await query.edit_message_text(
            messages.MESSAGE_ARTICLE_NOT_FOUND,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return settings.STATE_ADMIN_MENU
    
    context.user_data[settings.ADMIN_CURRENT_ARTICLE_KEY] = article_id
    
    # Format article detail
    text = _format_admin_article_detail(article)
    keyboard = keyboards.get_admin_article_actions_keyboard(article_id, article['status'])
    
    await query.edit_message_text(
        text,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboard
    )
    
    return settings.STATE_ADMIN_VIEW_ARTICLE


async def handle_admin_article_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle admin action on article (preview, publish, delete, etc.).
    """
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    # Parse action from callback data
    action_data = query.data.replace(settings.CALLBACK_ADMIN_ACTION_PREFIX, '')
    
    if action_data == 'back':
        # Go back to list
        return await _return_to_admin_list(update, context)
    
    parts = action_data.split('_')
    if len(parts) < 2:
        return settings.STATE_ADMIN_VIEW_ARTICLE
    
    action = parts[0]
    article_id = int(parts[1])
    
    article = news_logic.get_article_by_id(article_id)
    if not article:
        await query.edit_message_text(
            messages.MESSAGE_ARTICLE_NOT_FOUND,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return settings.STATE_ADMIN_MENU
    
    if action == 'preview':
        # Send preview to admin
        await _send_preview(query, context, article)
        return settings.STATE_ADMIN_VIEW_ARTICLE
    
    elif action == 'publish':
        # Show publish confirmation
        return await _show_publish_confirmation(query, context, article)
    
    elif action == 'delete':
        # Delete article
        news_logic.delete_article(article_id)
        await query.edit_message_text(
            messages.MESSAGE_ADMIN_ARTICLE_DELETED,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return await _return_to_admin_menu_callback(query, context)
    
    elif action == 'archive':
        # Archive article
        news_logic.update_article(article_id, status=settings.STATUS_ARCHIVED)
        await query.edit_message_text(
            messages.MESSAGE_ADMIN_ARTICLE_ARCHIVED,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return await _return_to_admin_menu_callback(query, context)
    
    elif action == 'rebroadcast':
        # Re-broadcast published article
        return await _start_broadcast(query, context, article)
    
    return settings.STATE_ADMIN_VIEW_ARTICLE


async def _send_preview(query, context: ContextTypes.DEFAULT_TYPE, article: dict) -> None:
    """
    Send preview of article to admin.
    """
    user_id = query.from_user.id
    bot = context.bot
    
    # Format article as users would see it
    title = messages.escape_markdown_v2(article['title'])
    content = article['content']
    category_emoji = article.get('category_emoji', '📰')
    category_name = messages.escape_markdown_v2(article.get('category_name', ''))
    
    # Use current time for preview
    published_date = messages.escape_markdown_v2(datetime.now().strftime('%d.%m.%Y'))
    
    reactions = {'like': 0, 'love': 0, 'dislike': 0}
    
    text = messages.format_news_article(
        title=title,
        content=content,
        category_emoji=category_emoji,
        category_name=category_name,
        published_date=published_date,
        reactions=reactions
    )
    
    keyboard = keyboards.get_reaction_keyboard(article['id'], reactions)
    
    # Send preview
    if article.get('image_file_id'):
        await bot.send_photo(
            chat_id=user_id,
            photo=article['image_file_id'],
            caption=text,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboard
        )
    else:
        await bot.send_message(
            chat_id=user_id,
            text=text,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboard
        )
    
    # Send attachment if present
    if article.get('attachment_file_id'):
        await bot.send_document(
            chat_id=user_id,
            document=article['attachment_file_id'],
            filename=article.get('attachment_filename'),
            caption="📎 Прикреплённый файл"
        )
    
    # Inform admin
    await query.message.reply_text(
        messages.MESSAGE_ADMIN_PREVIEW_SENT,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )


async def _show_publish_confirmation(query, context: ContextTypes.DEFAULT_TYPE, article: dict) -> int:
    """
    Show publish confirmation dialog.
    """
    context.user_data[settings.ADMIN_CURRENT_ARTICLE_KEY] = article['id']
    
    # Build warning message based on article settings
    if article.get('is_silent'):
        broadcast_warning = messages.MESSAGE_ADMIN_BROADCAST_WARNING_SILENT
    else:
        user_count = len(news_logic.get_all_user_ids())
        broadcast_warning = messages.MESSAGE_ADMIN_BROADCAST_WARNING_NOTIFY.format(user_count=user_count)
    
    if article.get('is_mandatory'):
        broadcast_warning += "\n\n" + messages.MESSAGE_ADMIN_BROADCAST_WARNING_MANDATORY
    
    text = messages.MESSAGE_ADMIN_CONFIRM_PUBLISH.format(
        title=messages.escape_markdown_v2(article['title']),
        broadcast_warning=broadcast_warning
    )
    
    await query.edit_message_text(
        text,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_confirm_keyboard("publish")
    )
    
    return settings.STATE_ADMIN_CONFIRM_PUBLISH


async def handle_publish_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle publish confirmation callback.
    """
    query = update.callback_query
    await query.answer()
    
    action_data = query.data.replace(settings.CALLBACK_ADMIN_CONFIRM_PREFIX, '')
    
    if action_data.startswith('no_'):
        # Cancelled
        await query.edit_message_text(
            messages.MESSAGE_CANCEL,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return await _return_to_admin_menu_callback(query, context)
    
    if action_data.startswith('yes_publish'):
        article_id = context.user_data.get(settings.ADMIN_CURRENT_ARTICLE_KEY)
        if not article_id:
            return await _return_to_admin_menu_callback(query, context)
        
        article = news_logic.get_article_by_id(article_id)
        if not article:
            await query.edit_message_text(
                messages.MESSAGE_ARTICLE_NOT_FOUND,
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
            return settings.STATE_ADMIN_MENU
        
        # Publish the article
        news_logic.publish_article(article_id)
        
        # Reload article to get updated status
        article = news_logic.get_article_by_id(article_id)
        
        if article.get('is_silent'):
            # Silent publish - no broadcast
            await query.edit_message_text(
                messages.MESSAGE_ADMIN_PUBLISHED,
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
            return await _return_to_admin_menu_callback(query, context)
        else:
            # Start broadcast
            return await _start_broadcast(query, context, article)
    
    return settings.STATE_ADMIN_CONFIRM_PUBLISH


async def _start_broadcast(query, context: ContextTypes.DEFAULT_TYPE, article: dict) -> int:
    """
    Start broadcasting news to all users.
    """
    user_ids = news_logic.get_all_user_ids()
    total = len(user_ids)
    
    if total == 0:
        await query.edit_message_text(
            "⚠️ Нет пользователей для рассылки\\.",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return await _return_to_admin_menu_callback(query, context)
    
    # Show initial progress
    await query.edit_message_text(
        messages.MESSAGE_ADMIN_BROADCAST_STARTED.format(total=total),
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    # Define progress callback
    async def progress_callback(sent: int, failed: int, total: int):
        try:
            await query.edit_message_text(
                messages.MESSAGE_ADMIN_BROADCAST_PROGRESS.format(
                    sent=sent, failed=failed, total=total
                ),
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
        except Exception:
            pass  # Ignore edit errors
    
    # Run broadcast
    bot = context.bot
    results = await news_logic.broadcast_news(bot, article, user_ids, progress_callback)
    
    # Show final results
    await query.message.reply_text(
        messages.MESSAGE_ADMIN_BROADCAST_COMPLETE.format(
            sent=results['sent'],
            failed=results['failed'],
            total=total
        ),
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_admin_menu_keyboard()
    )
    
    return settings.STATE_ADMIN_MENU


# ===== CREATE NEWS =====


async def start_create_news(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Start news creation wizard.
    """
    if not _check_admin(update.effective_user.id):
        await update.message.reply_text(
            messages.MESSAGE_ADMIN_NOT_AUTHORIZED,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ConversationHandler.END
    
    # Initialize draft data
    context.user_data[settings.ADMIN_DRAFT_DATA_KEY] = {}
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_CREATE_TITLE,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_cancel_keyboard()
    )
    
    return settings.STATE_ADMIN_CREATE_TITLE


async def receive_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Receive article title.
    """
    title = update.message.text.strip()
    
    if len(title) > 255:
        await update.message.reply_text(
            messages.MESSAGE_TITLE_TOO_LONG,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return settings.STATE_ADMIN_CREATE_TITLE
    
    context.user_data[settings.ADMIN_DRAFT_DATA_KEY]['title'] = title
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_CREATE_CONTENT,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_cancel_keyboard()
    )
    
    return settings.STATE_ADMIN_CREATE_CONTENT


async def receive_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Receive article content.
    """
    content = update.message.text.strip()
    
    context.user_data[settings.ADMIN_DRAFT_DATA_KEY]['content'] = content
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_CREATE_IMAGE,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_skip_cancel_keyboard()
    )
    
    return settings.STATE_ADMIN_CREATE_IMAGE


async def receive_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Receive article image.
    """
    if update.message.photo:
        # Get the largest photo
        photo = update.message.photo[-1]
        context.user_data[settings.ADMIN_DRAFT_DATA_KEY]['image_file_id'] = photo.file_id
    elif update.message.document and update.message.document.mime_type and update.message.document.mime_type.startswith('image/'):
        context.user_data[settings.ADMIN_DRAFT_DATA_KEY]['image_file_id'] = update.message.document.file_id
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_CREATE_FILE,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_skip_cancel_keyboard()
    )
    
    return settings.STATE_ADMIN_CREATE_FILE


async def skip_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Skip image step.
    """
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_CREATE_FILE,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_skip_cancel_keyboard()
    )
    
    return settings.STATE_ADMIN_CREATE_FILE


async def receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Receive article attachment file.
    """
    if update.message.document:
        context.user_data[settings.ADMIN_DRAFT_DATA_KEY]['attachment_file_id'] = update.message.document.file_id
        context.user_data[settings.ADMIN_DRAFT_DATA_KEY]['attachment_filename'] = update.message.document.file_name
    
    return await _show_category_selection(update, context)


async def skip_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Skip file step.
    """
    return await _show_category_selection(update, context)


async def _show_category_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Show category selection.
    """
    categories = news_logic.get_active_categories()
    
    if not categories:
        await update.message.reply_text(
            "⚠️ Нет активных категорий\\. Сначала создайте категорию\\.",
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_admin_menu_keyboard()
        )
        return settings.STATE_ADMIN_MENU
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_CREATE_CATEGORY,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_category_keyboard(categories)
    )
    
    return settings.STATE_ADMIN_CREATE_CATEGORY


async def receive_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Receive category selection.
    """
    query = update.callback_query
    await query.answer()
    
    if query.data == settings.CALLBACK_CANCEL:
        await query.edit_message_text(
            messages.MESSAGE_CANCEL,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return await _return_to_admin_menu_callback(query, context)
    
    category_id = int(query.data.replace(settings.CALLBACK_ADMIN_CATEGORY_PREFIX, ''))
    context.user_data[settings.ADMIN_DRAFT_DATA_KEY]['category_id'] = category_id
    
    await query.edit_message_text(
        messages.MESSAGE_ADMIN_CREATE_MODE,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_publish_mode_keyboard()
    )
    
    return settings.STATE_ADMIN_CREATE_MODE


async def receive_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Receive publish mode selection.
    """
    query = update.callback_query
    await query.answer()
    
    if query.data == settings.CALLBACK_CANCEL:
        await query.edit_message_text(
            messages.MESSAGE_CANCEL,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return await _return_to_admin_menu_callback(query, context)
    
    action = query.data.replace(settings.CALLBACK_ADMIN_ACTION_PREFIX, '')
    
    is_silent = (action == 'silent')
    context.user_data[settings.ADMIN_DRAFT_DATA_KEY]['is_silent'] = is_silent
    
    await query.edit_message_text(
        messages.MESSAGE_ADMIN_CREATE_MANDATORY,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_mandatory_mode_keyboard()
    )
    
    return settings.STATE_ADMIN_CREATE_MANDATORY


async def receive_mandatory(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Receive mandatory mode selection and create the draft.
    """
    query = update.callback_query
    await query.answer()
    
    if query.data == settings.CALLBACK_CANCEL:
        await query.edit_message_text(
            messages.MESSAGE_CANCEL,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return await _return_to_admin_menu_callback(query, context)
    
    action = query.data.replace(settings.CALLBACK_ADMIN_ACTION_PREFIX, '')
    
    is_mandatory = (action == 'mandatory')
    
    draft_data = context.user_data.get(settings.ADMIN_DRAFT_DATA_KEY, {})
    draft_data['is_mandatory'] = is_mandatory
    
    # Create the article
    user_id = query.from_user.id
    
    article_id = news_logic.create_article(
        title=draft_data.get('title', ''),
        content=draft_data.get('content', ''),
        category_id=draft_data.get('category_id', 1),
        created_by=user_id,
        is_silent=draft_data.get('is_silent', False),
        is_mandatory=is_mandatory,
        image_file_id=draft_data.get('image_file_id'),
        attachment_file_id=draft_data.get('attachment_file_id'),
        attachment_filename=draft_data.get('attachment_filename')
    )
    
    if article_id:
        await query.edit_message_text(
            messages.MESSAGE_ADMIN_DRAFT_SAVED,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        
        # Show the created article
        article = news_logic.get_article_by_id(article_id)
        if article:
            context.user_data[settings.ADMIN_CURRENT_ARTICLE_KEY] = article_id
            text = _format_admin_article_detail(article)
            inline_keyboard = keyboards.get_admin_article_actions_keyboard(article_id, article['status'])
            
            # Update reply keyboard to show Back button
            await query.message.reply_text(
                "👇 Используйте кнопки ниже для действий с черновиком",
                reply_markup=keyboards.get_back_keyboard()
            )
            
            # Send article detail with inline actions keyboard
            await query.message.reply_text(
                text,
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=inline_keyboard
            )
            return settings.STATE_ADMIN_VIEW_ARTICLE
    else:
        await query.edit_message_text(
            messages.MESSAGE_ERROR,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
    
    return await _return_to_admin_menu_callback(query, context)


# ===== EDIT ARTICLE =====


async def handle_edit_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle edit field selection.
    """
    query = update.callback_query
    await query.answer()
    
    # Parse callback data: news_adm_edit_{field}_{article_id}
    data = query.data.replace(settings.CALLBACK_ADMIN_EDIT_PREFIX, '')
    parts = data.split('_')
    
    if len(parts) < 2:
        return settings.STATE_ADMIN_VIEW_ARTICLE
    
    field = parts[0]
    article_id = int(parts[1])
    
    context.user_data[settings.ADMIN_CURRENT_ARTICLE_KEY] = article_id
    context.user_data[settings.ADMIN_EDIT_FIELD_KEY] = field
    
    article = news_logic.get_article_by_id(article_id)
    if not article:
        await query.edit_message_text(
            messages.MESSAGE_ARTICLE_NOT_FOUND,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return settings.STATE_ADMIN_MENU
    
    if field == 'title':
        await query.edit_message_text(
            messages.MESSAGE_ADMIN_EDIT_TITLE.format(
                current=messages.escape_markdown_v2(article['title'])
            ),
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return settings.STATE_ADMIN_EDIT_FIELD
    
    elif field == 'content':
        await query.edit_message_text(
            messages.MESSAGE_ADMIN_EDIT_CONTENT,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return settings.STATE_ADMIN_EDIT_FIELD
    
    elif field == 'image':
        await query.edit_message_text(
            messages.MESSAGE_ADMIN_CREATE_IMAGE,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return settings.STATE_ADMIN_EDIT_FIELD
    
    elif field == 'file':
        await query.edit_message_text(
            messages.MESSAGE_ADMIN_CREATE_FILE,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return settings.STATE_ADMIN_EDIT_FIELD
    
    elif field == 'category':
        categories = news_logic.get_active_categories()
        await query.edit_message_text(
            messages.MESSAGE_ADMIN_CREATE_CATEGORY,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_category_keyboard(categories)
        )
        return settings.STATE_ADMIN_CREATE_CATEGORY
    
    elif field == 'mode':
        await query.edit_message_text(
            messages.MESSAGE_ADMIN_CREATE_MODE,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_publish_mode_keyboard()
        )
        return settings.STATE_ADMIN_CREATE_MODE
    
    return settings.STATE_ADMIN_VIEW_ARTICLE


async def receive_edit_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Receive edited field value.
    """
    article_id = context.user_data.get(settings.ADMIN_CURRENT_ARTICLE_KEY)
    field = context.user_data.get(settings.ADMIN_EDIT_FIELD_KEY)
    
    if not article_id or not field:
        return settings.STATE_ADMIN_MENU
    
    if field == 'title':
        title = update.message.text.strip()
        if len(title) > 255:
            await update.message.reply_text(
                messages.MESSAGE_TITLE_TOO_LONG,
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
            return settings.STATE_ADMIN_EDIT_FIELD
        news_logic.update_article(article_id, title=title)
    
    elif field == 'content':
        content = update.message.text.strip()
        news_logic.update_article(article_id, content=content)
    
    elif field == 'image':
        if update.message.photo:
            photo = update.message.photo[-1]
            news_logic.update_article(article_id, image_file_id=photo.file_id)
        elif update.message.document:
            news_logic.update_article(article_id, image_file_id=update.message.document.file_id)
    
    elif field == 'file':
        if update.message.document:
            news_logic.update_article(
                article_id,
                attachment_file_id=update.message.document.file_id,
                attachment_filename=update.message.document.file_name
            )
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_EDIT_SAVED,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    # Show updated article
    article = news_logic.get_article_by_id(article_id)
    if article:
        text = _format_admin_article_detail(article)
        keyboard = keyboards.get_admin_article_actions_keyboard(article_id, article['status'])
        
        await update.message.reply_text(
            text,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboard
        )
        return settings.STATE_ADMIN_VIEW_ARTICLE
    
    return settings.STATE_ADMIN_MENU


# ===== CATEGORY MANAGEMENT =====


async def show_categories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Show category list for management.
    """
    categories = news_logic.get_all_categories()
    
    text = messages.MESSAGE_ADMIN_CATEGORIES_LIST
    keyboard = keyboards.get_admin_category_list_keyboard(categories)
    
    await update.message.reply_text(
        text,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboard
    )
    await update.message.reply_text(
        "Выберите категорию или добавьте новую:",
        reply_markup=keyboards.get_admin_category_keyboard()
    )
    
    return settings.STATE_ADMIN_CATEGORIES_LIST


async def start_create_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Start category creation.
    """
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_CATEGORY_CREATE_NAME,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_cancel_keyboard()
    )
    return settings.STATE_ADMIN_CATEGORY_CREATE_NAME


async def receive_category_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Receive new category name.
    """
    name = update.message.text.strip()
    context.user_data['new_category_name'] = name
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_CATEGORY_CREATE_EMOJI,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_cancel_keyboard()
    )
    return settings.STATE_ADMIN_CATEGORY_CREATE_EMOJI


async def receive_category_emoji(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Receive category emoji and create the category.
    """
    emoji = update.message.text.strip()
    name = context.user_data.get('new_category_name', 'Новая категория')
    
    category_id = news_logic.create_category(name, emoji)
    
    if category_id:
        await update.message.reply_text(
            messages.MESSAGE_ADMIN_CATEGORY_CREATED,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
    else:
        await update.message.reply_text(
            messages.MESSAGE_ERROR,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
    
    return await show_categories(update, context)


async def handle_category_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle category management action.
    """
    query = update.callback_query
    await query.answer()
    
    data = query.data.replace(settings.CALLBACK_ADMIN_CATEGORY_PREFIX, '')
    
    if data == 'back':
        await query.delete_message()
        return settings.STATE_ADMIN_MENU
    
    if data.startswith('page_'):
        # Pagination - not implemented for categories yet
        return settings.STATE_ADMIN_CATEGORIES_LIST
    
    parts = data.split('_')
    if len(parts) < 2:
        return settings.STATE_ADMIN_CATEGORIES_LIST
    
    action = parts[0]
    category_id = int(parts[1])
    
    if action == 'edit':
        category = news_logic.get_category_by_id(category_id)
        if category:
            context.user_data[settings.ADMIN_CURRENT_CATEGORY_KEY] = category_id
            keyboard = keyboards.get_admin_category_edit_keyboard(category_id, category.get('active', True))
            
            text = f"📂 *Категория:* {category.get('emoji', '📰')} {messages.escape_markdown_v2(category.get('name', ''))}\n\n"
            text += "Выберите действие:"
            
            await query.edit_message_text(
                text,
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=keyboard
            )
        return settings.STATE_ADMIN_CATEGORY_EDIT
    
    elif action == 'activate':
        news_logic.update_category(category_id, active=True)
        await query.answer("✅ Категория активирована")
    
    elif action == 'deactivate':
        news_logic.update_category(category_id, active=False)
        await query.answer("🔴 Категория деактивирована")
    
    elif action == 'delete':
        success, error = news_logic.delete_category(category_id)
        if success:
            await query.answer("🗑️ Категория удалена")
        elif error == 'has_articles':
            await query.answer("⚠️ Нельзя удалить - есть новости")
        else:
            await query.answer("❌ Ошибка удаления")
    
    elif action == 'name':
        context.user_data[settings.ADMIN_CURRENT_CATEGORY_KEY] = category_id
        context.user_data['edit_category_field'] = 'name'
        await query.edit_message_text(
            "Введите новое название категории:",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return settings.STATE_ADMIN_CATEGORY_EDIT
    
    elif action == 'emoji':
        context.user_data[settings.ADMIN_CURRENT_CATEGORY_KEY] = category_id
        context.user_data['edit_category_field'] = 'emoji'
        await query.edit_message_text(
            "Введите новый эмодзи для категории:",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return settings.STATE_ADMIN_CATEGORY_EDIT
    
    # Refresh category list
    categories = news_logic.get_all_categories()
    keyboard = keyboards.get_admin_category_list_keyboard(categories)
    
    await query.edit_message_text(
        messages.MESSAGE_ADMIN_CATEGORIES_LIST,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboard
    )
    
    return settings.STATE_ADMIN_CATEGORIES_LIST


async def receive_category_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Receive category edit value.
    """
    category_id = context.user_data.get(settings.ADMIN_CURRENT_CATEGORY_KEY)
    field = context.user_data.get('edit_category_field')
    
    if not category_id or not field:
        return settings.STATE_ADMIN_MENU
    
    value = update.message.text.strip()
    
    if field == 'name':
        news_logic.update_category(category_id, name=value)
    elif field == 'emoji':
        news_logic.update_category(category_id, emoji=value)
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_CATEGORY_UPDATED,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    return await show_categories(update, context)


# ===== NAVIGATION =====


async def back_to_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Return to admin menu.
    """
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_MENU,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_admin_menu_keyboard()
    )
    return settings.STATE_ADMIN_MENU


async def _return_to_admin_menu_callback(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Return to admin menu from callback.
    """
    await query.message.reply_text(
        messages.MESSAGE_ADMIN_MENU,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_admin_menu_keyboard()
    )
    return settings.STATE_ADMIN_MENU


async def _return_to_admin_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Return to admin article list.
    """
    query = update.callback_query
    status = context.user_data.get('admin_view_status', settings.STATUS_DRAFT)
    
    articles, total = news_logic.get_articles_by_status(status)
    
    if status == settings.STATUS_DRAFT:
        text = messages.MESSAGE_ADMIN_DRAFTS_LIST.format(count=total)
    else:
        text = messages.MESSAGE_ADMIN_PUBLISHED_LIST.format(count=total)
    
    total_pages = (total + settings.ITEMS_PER_PAGE - 1) // settings.ITEMS_PER_PAGE
    
    keyboard = keyboards.get_news_list_keyboard(
        articles, 0, total_pages,
        prefix=settings.CALLBACK_ADMIN_ARTICLE_PREFIX,
        page_prefix=settings.CALLBACK_ADMIN_PAGE_PREFIX
    )
    
    await query.edit_message_text(
        text,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboard
    )
    
    return settings.STATE_ADMIN_DRAFTS_LIST if status == settings.STATUS_DRAFT else settings.STATE_ADMIN_PUBLISHED_LIST


async def cancel_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Cancel current operation and return to admin menu.
    """
    # Clear temp data
    context.user_data.pop(settings.ADMIN_DRAFT_DATA_KEY, None)
    context.user_data.pop(settings.ADMIN_EDIT_FIELD_KEY, None)
    
    return await back_to_admin_menu(update, context)


async def back_to_news_submenu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Return to news submenu from admin.
    """
    from . import news_bot_part
    return await news_bot_part.back_to_submenu(update, context)


# ===== HELPER FUNCTIONS =====


def _format_admin_article_detail(article: dict) -> str:
    """
    Format article for admin detail view.
    """
    title = messages.escape_markdown_v2(article.get('title', 'Без названия'))
    content = article.get('content', '')
    
    # Truncate content if too long
    if len(content) > 500:
        content = content[:497] + "\\.\\.\\."
    
    status_map = {
        'draft': '📝 Черновик',
        'published': '📢 Опубликована',
        'archived': '📂 Архив'
    }
    status = status_map.get(article.get('status', 'draft'), '📝 Черновик')
    
    category = f"{article.get('category_emoji', '📰')} {messages.escape_markdown_v2(article.get('category_name', ''))}"
    
    created_ts = article.get('created_timestamp', 0)
    created_date = messages.escape_markdown_v2(
        datetime.fromtimestamp(created_ts).strftime('%d.%m.%Y %H:%M') if created_ts else ''
    )
    
    published_ts = article.get('published_timestamp')
    if published_ts:
        published_line = f"*Опубликована:* {messages.escape_markdown_v2(datetime.fromtimestamp(published_ts).strftime('%d.%m.%Y %H:%M'))}"
    else:
        published_line = ""
    
    is_silent = "✅ Да" if article.get('is_silent') else "❌ Нет"
    is_mandatory = "🚨 Да" if article.get('is_mandatory') else "❌ Нет"
    
    image_line = "🖼️ *Изображение:* ✅" if article.get('image_file_id') else ""
    attachment_line = f"📎 *Файл:* {messages.escape_markdown_v2(article.get('attachment_filename', ''))}" if article.get('attachment_file_id') else ""
    
    # Reactions section
    if article.get('status') == settings.STATUS_PUBLISHED:
        reactions = news_logic.get_article_reactions(article['id'])
        delivery_stats = news_logic.get_delivery_stats(article['id'])
        total_users = len(news_logic.get_all_user_ids())
        
        reactions_section = messages.MESSAGE_ADMIN_REACTIONS_SECTION.format(
            like=reactions.get('like', 0),
            love=reactions.get('love', 0),
            dislike=reactions.get('dislike', 0),
            delivered=delivery_stats.get('sent', 0),
            total_users=total_users
        )
    else:
        reactions_section = ""
    
    return messages.MESSAGE_ADMIN_ARTICLE_DETAIL.format(
        title=title,
        status=status,
        category=category,
        created_date=created_date,
        published_line=published_line,
        is_silent=is_silent,
        is_mandatory=is_mandatory,
        image_line=image_line,
        attachment_line=attachment_line,
        content=content,
        reactions_section=reactions_section
    )


# ===== CONVERSATION HANDLER =====


def get_news_admin_handler() -> ConversationHandler:
    """
    Create and return the news admin ConversationHandler.
    """
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(f"^{settings.BUTTON_ADMIN_PANEL}$"), admin_menu),
        ],
        states={
            settings.STATE_ADMIN_MENU: [
                MessageHandler(filters.Regex(f"^{settings.BUTTON_CREATE_NEWS}$"), start_create_news),
                MessageHandler(filters.Regex(f"^{settings.BUTTON_DRAFTS}$"), show_drafts),
                MessageHandler(filters.Regex(f"^{settings.BUTTON_PUBLISHED}$"), show_published),
                MessageHandler(filters.Regex(f"^{settings.BUTTON_CATEGORIES}$"), show_categories),
                MessageHandler(filters.Regex(f"^{settings.BUTTON_BACK}$"), back_to_news_submenu),
            ],
            settings.STATE_ADMIN_DRAFTS_LIST: [
                CallbackQueryHandler(handle_admin_article_select, pattern=f"^{settings.CALLBACK_ADMIN_ARTICLE_PREFIX}"),
                CallbackQueryHandler(handle_admin_article_action, pattern=f"^{settings.CALLBACK_ADMIN_ACTION_PREFIX}"),
                MessageHandler(filters.Regex(f"^{settings.BUTTON_BACK}$"), back_to_admin_menu),
            ],
            settings.STATE_ADMIN_PUBLISHED_LIST: [
                CallbackQueryHandler(handle_admin_article_select, pattern=f"^{settings.CALLBACK_ADMIN_ARTICLE_PREFIX}"),
                CallbackQueryHandler(handle_admin_article_action, pattern=f"^{settings.CALLBACK_ADMIN_ACTION_PREFIX}"),
                MessageHandler(filters.Regex(f"^{settings.BUTTON_BACK}$"), back_to_admin_menu),
            ],
            settings.STATE_ADMIN_VIEW_ARTICLE: [
                CallbackQueryHandler(handle_admin_article_action, pattern=f"^{settings.CALLBACK_ADMIN_ACTION_PREFIX}"),
                CallbackQueryHandler(handle_edit_field, pattern=f"^{settings.CALLBACK_ADMIN_EDIT_PREFIX}"),
                MessageHandler(filters.Regex(f"^{settings.BUTTON_BACK}$"), back_to_admin_menu),
            ],
            settings.STATE_ADMIN_CREATE_TITLE: [
                MessageHandler(filters.Regex(f"^{settings.BUTTON_CANCEL}$"), cancel_admin),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_title),
            ],
            settings.STATE_ADMIN_CREATE_CONTENT: [
                MessageHandler(filters.Regex(f"^{settings.BUTTON_CANCEL}$"), cancel_admin),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_content),
            ],
            settings.STATE_ADMIN_CREATE_IMAGE: [
                MessageHandler(filters.Regex("^⏭️ Пропустить$"), skip_image),
                MessageHandler(filters.Regex(f"^{settings.BUTTON_CANCEL}$"), cancel_admin),
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, receive_image),
            ],
            settings.STATE_ADMIN_CREATE_FILE: [
                MessageHandler(filters.Regex("^⏭️ Пропустить$"), skip_file),
                MessageHandler(filters.Regex(f"^{settings.BUTTON_CANCEL}$"), cancel_admin),
                MessageHandler(filters.Document.ALL, receive_file),
            ],
            settings.STATE_ADMIN_CREATE_CATEGORY: [
                CallbackQueryHandler(receive_category, pattern=f"^{settings.CALLBACK_ADMIN_CATEGORY_PREFIX}"),
                CallbackQueryHandler(receive_category, pattern=f"^{settings.CALLBACK_CANCEL}$"),
            ],
            settings.STATE_ADMIN_CREATE_MODE: [
                CallbackQueryHandler(receive_mode, pattern=f"^{settings.CALLBACK_ADMIN_ACTION_PREFIX}"),
                CallbackQueryHandler(receive_mode, pattern=f"^{settings.CALLBACK_CANCEL}$"),
            ],
            settings.STATE_ADMIN_CREATE_MANDATORY: [
                CallbackQueryHandler(receive_mandatory, pattern=f"^{settings.CALLBACK_ADMIN_ACTION_PREFIX}"),
                CallbackQueryHandler(receive_mandatory, pattern=f"^{settings.CALLBACK_CANCEL}$"),
            ],
            settings.STATE_ADMIN_CONFIRM_PUBLISH: [
                CallbackQueryHandler(handle_publish_confirmation, pattern=f"^{settings.CALLBACK_ADMIN_CONFIRM_PREFIX}"),
            ],
            settings.STATE_ADMIN_EDIT_FIELD: [
                MessageHandler(filters.Regex(f"^{settings.BUTTON_CANCEL}$"), cancel_admin),
                MessageHandler(filters.PHOTO | filters.Document.ALL, receive_edit_value),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_edit_value),
            ],
            settings.STATE_ADMIN_CATEGORIES_LIST: [
                CallbackQueryHandler(handle_category_action, pattern=f"^{settings.CALLBACK_ADMIN_CATEGORY_PREFIX}"),
                MessageHandler(filters.Regex(f"^{settings.BUTTON_ADD_CATEGORY}$"), start_create_category),
                MessageHandler(filters.Regex(f"^{settings.BUTTON_BACK}$"), back_to_admin_menu),
            ],
            settings.STATE_ADMIN_CATEGORY_CREATE_NAME: [
                MessageHandler(filters.Regex(f"^{settings.BUTTON_CANCEL}$"), show_categories),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_category_name),
            ],
            settings.STATE_ADMIN_CATEGORY_CREATE_EMOJI: [
                MessageHandler(filters.Regex(f"^{settings.BUTTON_CANCEL}$"), show_categories),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_category_emoji),
            ],
            settings.STATE_ADMIN_CATEGORY_EDIT: [
                CallbackQueryHandler(handle_category_action, pattern=f"^{settings.CALLBACK_ADMIN_CATEGORY_PREFIX}"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_category_edit),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_admin),
            MessageHandler(filters.Regex(f"^{BUTTON_MAIN_MENU}$"), back_to_news_submenu),
        ],
        name="news_admin_handler",
        persistent=False
    )
