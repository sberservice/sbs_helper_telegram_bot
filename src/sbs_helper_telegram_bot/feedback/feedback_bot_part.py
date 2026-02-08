"""
Feedback Module - User Bot Part

User-facing conversation handlers for submitting and viewing feedback.
"""

import logging
from telegram import Update, constants
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    CommandHandler,
    filters,
)

from src.common.telegram_user import check_if_user_legit, check_if_user_admin

from . import settings
from . import messages
from . import keyboards
from . import feedback_logic

logger = logging.getLogger(__name__)


# ===== HELPER FUNCTIONS =====


def _clear_user_context(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear all feedback-related user context data."""
    keys_to_clear = [
        settings.CURRENT_CATEGORY_KEY,
        settings.CURRENT_MESSAGE_KEY,
        settings.CURRENT_ENTRY_ID_KEY,
        settings.MY_FEEDBACK_PAGE_KEY,
    ]
    for key in keys_to_clear:
        context.user_data.pop(key, None)


async def _send_message_safe(
    update: Update,
    text: str,
    reply_markup=None,
    parse_mode: str = "MarkdownV2"
) -> None:
    """
    Send message handling both message and callback query updates.
    """
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup if isinstance(reply_markup, type(None)) or hasattr(reply_markup, 'inline_keyboard') else None
        )
    else:
        await update.message.reply_text(
            text=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup
        )


# ===== ENTRY POINTS =====


async def feedback_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Entry point for feedback module (menu button click).
    Shows the feedback submenu.
    """
    if not check_if_user_legit(update.effective_user.id):
        return ConversationHandler.END
    
    _clear_user_context(context)
    
    is_admin = check_if_user_admin(update.effective_user.id)
    keyboard = keyboards.get_submenu_keyboard(is_admin)
    
    await update.message.reply_text(
        messages.MESSAGE_SUBMENU,
        parse_mode="MarkdownV2",
        reply_markup=keyboard
    )
    
    return settings.STATE_SUBMENU


# ===== SUBMIT FEEDBACK FLOW =====


async def submit_feedback_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:  # pylint: disable=unused-argument
    """
    Start the feedback submission flow.
    Checks rate limit, then shows category selection.
    """
    user_id = update.effective_user.id
    
    # Check rate limit
    is_allowed, seconds_remaining = feedback_logic.check_rate_limit(user_id)
    
    if not is_allowed:
        is_admin = check_if_user_admin(user_id)
        keyboard = keyboards.get_submenu_keyboard(is_admin)
        
        await update.message.reply_text(
            messages.format_rate_limit_message(seconds_remaining),
            parse_mode="MarkdownV2",
            reply_markup=keyboard
        )
        return settings.STATE_SUBMENU
    
    # Get categories
    categories = feedback_logic.get_active_categories()
    
    if not categories:
        is_admin = check_if_user_admin(user_id)
        keyboard = keyboards.get_submenu_keyboard(is_admin)
        
        await update.message.reply_text(
            messages.MESSAGE_ERROR,
            parse_mode="MarkdownV2",
            reply_markup=keyboard
        )
        return settings.STATE_SUBMENU
    
    inline_keyboard = keyboards.get_category_keyboard(categories)
    
    await update.message.reply_text(
        messages.MESSAGE_SELECT_CATEGORY,
        parse_mode="MarkdownV2",
        reply_markup=inline_keyboard
    )
    
    return settings.STATE_SELECT_CATEGORY


async def category_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle category selection callback.
    """
    query = update.callback_query
    await query.answer()
    
    # Parse category ID from callback data
    callback_data = query.data
    
    if callback_data == settings.CALLBACK_CANCEL:
        return await cancel_submission(update, context)
    
    if not callback_data.startswith(settings.CALLBACK_CATEGORY_PREFIX):
        return settings.STATE_SELECT_CATEGORY
    
    try:
        category_id = int(callback_data.replace(settings.CALLBACK_CATEGORY_PREFIX, ""))
    except ValueError:
        return settings.STATE_SELECT_CATEGORY
    
    # Verify category exists
    category = feedback_logic.get_category_by_id(category_id)
    if not category:
        return settings.STATE_SELECT_CATEGORY
    
    # Store selected category
    context.user_data[settings.CURRENT_CATEGORY_KEY] = {
        'id': category_id,
        'name': category['name'],
        'emoji': category.get('emoji', '📝')
    }
    
    # Show message input prompt
    cancel_keyboard = keyboards.get_cancel_keyboard()
    
    await query.edit_message_text(
        messages.MESSAGE_ENTER_MESSAGE,
        parse_mode="MarkdownV2"
    )
    
    await query.message.reply_text(
        "👇",
        reply_markup=cancel_keyboard
    )
    
    return settings.STATE_ENTER_MESSAGE


async def message_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle user's feedback message input.
    Validates for links and shows confirmation.
    """
    user_message = update.message.text
    
    # Check for links
    if feedback_logic.contains_links(user_message):
        await update.message.reply_text(
            messages.MESSAGE_LINKS_NOT_ALLOWED,
            parse_mode="MarkdownV2",
            reply_markup=keyboards.get_cancel_keyboard()
        )
        return settings.STATE_ENTER_MESSAGE
    
    # Store message
    context.user_data[settings.CURRENT_MESSAGE_KEY] = user_message
    
    # Get category info
    category_info = context.user_data.get(settings.CURRENT_CATEGORY_KEY, {})
    category_name = f"{category_info.get('emoji', '📝')} {category_info.get('name', 'Без категории')}"
    
    # Show confirmation
    confirm_keyboard = keyboards.get_confirm_keyboard()
    
    await update.message.reply_text(
        messages.format_confirm_submit(category_name, user_message),
        parse_mode="MarkdownV2",
        reply_markup=confirm_keyboard
    )
    
    return settings.STATE_CONFIRM_SUBMIT


async def confirm_submission(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle submission confirmation callback.
    """
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    is_admin = check_if_user_admin(user_id)
    keyboard = keyboards.get_submenu_keyboard(is_admin)
    
    if query.data == settings.CALLBACK_CONFIRM_NO:
        await query.edit_message_text(
            messages.MESSAGE_FEEDBACK_CANCELLED,
            parse_mode="MarkdownV2"
        )
        _clear_user_context(context)
        
        await query.message.reply_text(
            messages.MESSAGE_SUBMENU,
            parse_mode="MarkdownV2",
            reply_markup=keyboard
        )
        return settings.STATE_SUBMENU
    
    if query.data == settings.CALLBACK_CONFIRM_YES:
        # Get stored data
        category_info = context.user_data.get(settings.CURRENT_CATEGORY_KEY, {})
        message_text = context.user_data.get(settings.CURRENT_MESSAGE_KEY, "")
        
        if not category_info or not message_text:
            await query.edit_message_text(
                messages.MESSAGE_ERROR,
                parse_mode="MarkdownV2"
            )
            _clear_user_context(context)
            return settings.STATE_SUBMENU
        
        # Create feedback entry
        entry_id = feedback_logic.create_feedback_entry(
            user_id=user_id,
            category_id=category_info['id'],
            message=message_text
        )
        
        if entry_id:
            await query.edit_message_text(
                messages.format_feedback_submitted(entry_id),
                parse_mode="MarkdownV2"
            )
        else:
            await query.edit_message_text(
                messages.MESSAGE_ERROR,
                parse_mode="MarkdownV2"
            )
        
        _clear_user_context(context)
        
        await query.message.reply_text(
            messages.MESSAGE_SUBMENU,
            parse_mode="MarkdownV2",
            reply_markup=keyboard
        )
        return settings.STATE_SUBMENU
    
    return settings.STATE_CONFIRM_SUBMIT


async def cancel_submission(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Cancel feedback submission.
    """
    user_id = update.effective_user.id
    is_admin = check_if_user_admin(user_id)
    keyboard = keyboards.get_submenu_keyboard(is_admin)
    
    _clear_user_context(context)
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            messages.MESSAGE_FEEDBACK_CANCELLED,
            parse_mode="MarkdownV2"
        )
        await update.callback_query.message.reply_text(
            messages.MESSAGE_SUBMENU,
            parse_mode="MarkdownV2",
            reply_markup=keyboard
        )
    else:
        await update.message.reply_text(
            messages.MESSAGE_FEEDBACK_CANCELLED,
            parse_mode="MarkdownV2",
            reply_markup=keyboard
        )
    
    return settings.STATE_SUBMENU


# ===== VIEW MY FEEDBACK FLOW =====


async def view_my_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Show user's feedback list.
    """
    user_id = update.effective_user.id
    page = context.user_data.get(settings.MY_FEEDBACK_PAGE_KEY, 0)
    
    entries, total = feedback_logic.get_user_feedback_entries(user_id, page)
    
    if not entries and total == 0:
        is_admin = check_if_user_admin(user_id)
        keyboard = keyboards.get_submenu_keyboard(is_admin)
        
        await update.message.reply_text(
            messages.MESSAGE_MY_FEEDBACK_EMPTY,
            parse_mode="MarkdownV2",
            reply_markup=keyboard
        )
        return settings.STATE_SUBMENU
    
    total_pages = (total + settings.ITEMS_PER_PAGE - 1) // settings.ITEMS_PER_PAGE
    inline_keyboard = keyboards.get_my_feedback_keyboard(entries, page, total_pages)
    
    await update.message.reply_text(
        messages.MESSAGE_MY_FEEDBACK_LIST.format(count=total),
        parse_mode="MarkdownV2",
        reply_markup=inline_keyboard
    )
    
    return settings.STATE_VIEW_MY_FEEDBACK


async def my_feedback_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle callbacks in my feedback list view.
    """
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    user_id = update.effective_user.id
    
    # Handle pagination
    if callback_data.startswith(settings.CALLBACK_PAGE_PREFIX):
        try:
            page = int(callback_data.replace(settings.CALLBACK_PAGE_PREFIX, ""))
            context.user_data[settings.MY_FEEDBACK_PAGE_KEY] = page
        except ValueError:
            page = 0
        
        entries, total = feedback_logic.get_user_feedback_entries(user_id, page)
        
        if not entries:
            # Return to first page if current is empty
            page = 0
            context.user_data[settings.MY_FEEDBACK_PAGE_KEY] = 0
            entries, total = feedback_logic.get_user_feedback_entries(user_id, page)
        
        total_pages = (total + settings.ITEMS_PER_PAGE - 1) // settings.ITEMS_PER_PAGE
        inline_keyboard = keyboards.get_my_feedback_keyboard(entries, page, total_pages)
        
        await query.edit_message_text(
            messages.MESSAGE_MY_FEEDBACK_LIST.format(count=total),
            parse_mode="MarkdownV2",
            reply_markup=inline_keyboard
        )
        return settings.STATE_VIEW_MY_FEEDBACK
    
    # Handle entry selection
    if callback_data.startswith(settings.CALLBACK_ENTRY_PREFIX):
        try:
            entry_id = int(callback_data.replace(settings.CALLBACK_ENTRY_PREFIX, ""))
        except ValueError:
            return settings.STATE_VIEW_MY_FEEDBACK
        
        # Get entry details (verify ownership)
        entry = feedback_logic.get_feedback_entry(entry_id, user_id)
        
        if not entry:
            await query.edit_message_text(
                messages.MESSAGE_ENTRY_NOT_FOUND,
                parse_mode="MarkdownV2"
            )
            return settings.STATE_VIEW_MY_FEEDBACK
        
        context.user_data[settings.CURRENT_ENTRY_ID_KEY] = entry_id
        
        # Format detail message
        status_name = feedback_logic.get_status_display_name(entry['status'])
        detail_message = messages.format_feedback_detail(
            entry_id=entry['id'],
            category=entry['category'],
            status=status_name,
            date=entry['date'],
            message=entry['message'],
            responses=entry['responses']
        )
        
        detail_keyboard = keyboards.get_feedback_detail_keyboard(entry_id)
        
        await query.edit_message_text(
            detail_message,
            parse_mode="MarkdownV2",
            reply_markup=detail_keyboard
        )
        return settings.STATE_VIEW_FEEDBACK_DETAIL
    
    return settings.STATE_VIEW_MY_FEEDBACK


# ===== NAVIGATION =====


async def back_to_submenu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Return to feedback submenu.
    """
    user_id = update.effective_user.id
    is_admin = check_if_user_admin(user_id)
    keyboard = keyboards.get_submenu_keyboard(is_admin)
    
    _clear_user_context(context)
    
    await update.message.reply_text(
        messages.MESSAGE_SUBMENU,
        parse_mode="MarkdownV2",
        reply_markup=keyboard
    )
    
    return settings.STATE_SUBMENU


async def back_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Return to main menu and end conversation.
    """
    # Import here to avoid circular import
    from src.common.messages import get_main_menu_message, get_main_menu_keyboard
    
    _clear_user_context(context)
    
    user = update.effective_user
    is_admin = check_if_user_admin(user.id)
    await update.message.reply_text(
        get_main_menu_message(user.id, user.first_name),
        reply_markup=get_main_menu_keyboard(is_admin=is_admin),
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    return ConversationHandler.END


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle /cancel command.
    """
    user_id = update.effective_user.id
    is_admin = check_if_user_admin(user_id)
    keyboard = keyboards.get_submenu_keyboard(is_admin)
    
    _clear_user_context(context)
    
    await update.message.reply_text(
        messages.MESSAGE_CANCEL,
        parse_mode="MarkdownV2",
        reply_markup=keyboard
    )
    
    return settings.STATE_SUBMENU


# ===== CONVERSATION HANDLER =====


def get_feedback_user_handler() -> ConversationHandler:
    """
    Build and return the user feedback conversation handler.
    """
    return ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.Regex(f"^{settings.MENU_BUTTON_TEXT}$"),
                feedback_entry
            ),
        ],
        states={
            settings.STATE_SUBMENU: [
                MessageHandler(
                    filters.Regex(f"^{settings.BUTTON_SUBMIT_FEEDBACK}$"),
                    submit_feedback_start
                ),
                MessageHandler(
                    filters.Regex(f"^{settings.BUTTON_MY_FEEDBACK}$"),
                    view_my_feedback
                ),
                MessageHandler(
                    filters.Regex(f"^{settings.BUTTON_MAIN_MENU}$"),
                    back_to_main_menu
                ),
                # Admin panel button is handled by admin handler
            ],
            settings.STATE_SELECT_CATEGORY: [
                CallbackQueryHandler(
                    category_selected,
                    pattern=f"^({settings.CALLBACK_CATEGORY_PREFIX}|{settings.CALLBACK_CANCEL})"
                ),
            ],
            settings.STATE_ENTER_MESSAGE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND & ~filters.Regex(f"^{settings.BUTTON_CANCEL}$"),
                    message_entered
                ),
                MessageHandler(
                    filters.Regex(f"^{settings.BUTTON_CANCEL}$"),
                    cancel_submission
                ),
            ],
            settings.STATE_CONFIRM_SUBMIT: [
                CallbackQueryHandler(
                    confirm_submission,
                    pattern=f"^({settings.CALLBACK_CONFIRM_YES}|{settings.CALLBACK_CONFIRM_NO})$"
                ),
            ],
            settings.STATE_VIEW_MY_FEEDBACK: [
                CallbackQueryHandler(
                    my_feedback_callback,
                    pattern=f"^({settings.CALLBACK_ENTRY_PREFIX}|{settings.CALLBACK_PAGE_PREFIX})"
                ),
            ],
            settings.STATE_VIEW_FEEDBACK_DETAIL: [
                CallbackQueryHandler(
                    my_feedback_callback,
                    pattern=f"^{settings.CALLBACK_PAGE_PREFIX}"
                ),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_command),
            CommandHandler("reset", back_to_main_menu),
            CommandHandler("menu", back_to_main_menu),
            MessageHandler(
                filters.Regex(f"^{settings.BUTTON_MAIN_MENU}$"),
                back_to_main_menu
            ),
            MessageHandler(filters.COMMAND, back_to_main_menu),
        ],
        name="feedback_user_conversation",
        persistent=False,
        allow_reentry=True
    )
