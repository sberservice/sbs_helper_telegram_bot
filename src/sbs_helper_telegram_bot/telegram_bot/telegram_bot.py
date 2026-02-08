"""
telegram_bot.py

Telegram bot for an invite-only image processing service.

Features:
- Invite-based access control
- Accepts images sent as document files (not photos)
- Enforces one active job per user
- Queue position feedback
- Issues new invites to verified users
- Stores user data and tracks invite usage
- Modular design for extensibility

Commands:
    /start   - Welcome message (requires valid invite)
    /invite  - List user's unused invite codes

Non-legitimate users are prompted to enter an invite code via text message.
"""
# pylint: disable=line-too-long

import logging
import re

from telegram import Update, constants, BotCommand
from telegram.error import TimedOut, NetworkError, BadRequest
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, CallbackQueryHandler, filters, ConversationHandler

import src.common.database as database
import src.common.invites as invites
 

from src.common.constants.os import ASSETS_DIR
from src.common.constants.errorcodes import InviteStatus
from src.common.constants.telegram import TELEGRAM_TOKEN

# Common messages (only global/shared messages)
from src.common.messages import (
    MESSAGE_INVITE_SYSTEM_DISABLED,
    MESSAGE_WELCOME,
    MESSAGE_MAIN_HELP,
    MESSAGE_UNRECOGNIZED_INPUT,
    MESSAGE_SETTINGS_MENU,
    MESSAGE_MODULES_MENU,
    MESSAGE_AVAILABLE_INVITES,
    MESSAGE_NO_INVITES,
    MESSAGE_WELCOME_SHORT,
    MESSAGE_WELCOME_PRE_INVITED,
    MESSAGE_INVITE_ISSUED,
    MESSAGE_INVITE_ALREADY_USED,
    MESSAGE_NO_ADMIN_RIGHTS,
    COMMAND_DESC_START,
    COMMAND_DESC_MENU,
    COMMAND_DESC_HELP,
    BUTTON_MODULES,
    BUTTON_SETTINGS,
    BUTTON_MAIN_MENU,
    BUTTON_MY_INVITES,
    BUTTON_HELP,
    BUTTON_VALIDATE_TICKET,
    BUTTON_SCREENSHOT,
    BUTTON_UPOS_ERRORS,
    BUTTON_CERTIFICATION,
    BUTTON_KTR,
    BUTTON_BOT_ADMIN,
    BUTTON_FEEDBACK,
    BUTTON_PROFILE,
    BUTTON_NEWS,
    get_main_menu_message,
    get_main_menu_keyboard,
    get_settings_menu_keyboard,
    get_modules_menu_keyboard,
)

# Import module-specific messages, settings, and keyboards
from src.sbs_helper_telegram_bot.ticket_validator import messages as validator_messages
from src.sbs_helper_telegram_bot.ticket_validator import keyboards as validator_keyboards
from src.sbs_helper_telegram_bot.ticket_validator import settings as validator_settings
from src.sbs_helper_telegram_bot.vyezd_byl import messages as image_messages
from src.sbs_helper_telegram_bot.vyezd_byl import keyboards as image_keyboards
from src.sbs_helper_telegram_bot.vyezd_byl import settings as vyezd_settings
from src.sbs_helper_telegram_bot.upos_error import messages as upos_messages
from src.sbs_helper_telegram_bot.upos_error import keyboards as upos_keyboards
from src.sbs_helper_telegram_bot.upos_error import settings as upos_settings

from src.common.telegram_user import (
    check_if_user_legit,
    check_if_invite_user_blocked,
    update_user_info_from_telegram,
    get_unauthorized_message,
)
from src.sbs_helper_telegram_bot.vyezd_byl.vyezd_byl_bot_part import (
    handle_incoming_document,
    handle_wrong_input_in_screenshot_mode,
    enter_screenshot_module,
    show_screenshot_help,
    cancel_screenshot_module,
    get_menu_button_exit_pattern,
    WAITING_FOR_SCREENSHOT
)

# Import ticket validator handlers
from src.sbs_helper_telegram_bot.ticket_validator.ticket_validator_bot_part import (
    validate_ticket_command,
    process_ticket_text,
    cancel_validation,
    cancel_validation_on_menu,
    help_command,
    toggle_debug_mode,
    run_test_templates_command,
    get_menu_button_regex_pattern,
    WAITING_FOR_TICKET
)

# Import file upload handler for batch validation
from src.sbs_helper_telegram_bot.ticket_validator.file_upload_bot_part import (
    get_file_validation_handler
)

# Import admin panel handlers
from src.sbs_helper_telegram_bot.ticket_validator.admin_panel_bot_part import (
    get_admin_conversation_handler
)

# Import UPOS error handlers
from src.sbs_helper_telegram_bot.upos_error.upos_error_bot_part import (
    show_popular_errors,
    get_user_conversation_handler as get_upos_user_handler,
    get_admin_conversation_handler as get_upos_admin_handler
)

# Import KTR module handlers
from src.sbs_helper_telegram_bot.ktr import keyboards as ktr_keyboards
from src.sbs_helper_telegram_bot.ktr import messages as ktr_messages
from src.sbs_helper_telegram_bot.ktr import settings as ktr_settings
from src.sbs_helper_telegram_bot.ktr.ktr_bot_part import (
    show_popular_codes as show_popular_ktr_codes,
    get_user_conversation_handler as get_ktr_user_handler,
    get_admin_conversation_handler as get_ktr_admin_handler
)

# Import certification module handlers
from src.sbs_helper_telegram_bot.certification import keyboards as certification_keyboards
from src.sbs_helper_telegram_bot.certification import messages as certification_messages
from src.sbs_helper_telegram_bot.certification import settings as certification_settings
from src.sbs_helper_telegram_bot.certification.certification_bot_part import (
    get_user_conversation_handler as get_certification_user_handler,
    certification_submenu as enter_certification_module,
    show_my_ranking,
    show_test_history,
    show_monthly_top,
    handle_top_category_selection,
)
from src.sbs_helper_telegram_bot.certification.admin_panel_bot_part import (
    get_admin_conversation_handler as get_certification_admin_handler
)

# Import bot admin module handlers
from src.sbs_helper_telegram_bot.bot_admin.admin_bot_part import (
    get_admin_conversation_handler as get_bot_admin_handler
)

# Import feedback module handlers
from src.sbs_helper_telegram_bot.feedback import messages as feedback_messages
from src.sbs_helper_telegram_bot.feedback import keyboards as feedback_keyboards
from src.sbs_helper_telegram_bot.feedback.feedback_bot_part import (
    get_feedback_user_handler,
)
from src.sbs_helper_telegram_bot.feedback.admin_panel_bot_part import (
    get_feedback_admin_handler,
)

# Import gamification module handlers
from src.sbs_helper_telegram_bot.gamification import settings as gamification_settings
from src.sbs_helper_telegram_bot.gamification import messages as gamification_messages
from src.sbs_helper_telegram_bot.gamification import keyboards as gamification_keyboards
from src.sbs_helper_telegram_bot.gamification.gamification_bot_part import (
    get_gamification_user_handler,
)
from src.sbs_helper_telegram_bot.gamification.admin_panel_bot_part import (
    get_gamification_admin_handler,
)

# Import news module handlers
from src.sbs_helper_telegram_bot.news import settings as news_settings
from src.sbs_helper_telegram_bot.news import messages as news_messages
from src.sbs_helper_telegram_bot.news import keyboards as news_keyboards
from src.sbs_helper_telegram_bot.news import (
    get_unread_count as get_news_unread_count,
    get_unacked_mandatory_news,
    has_unacked_mandatory_news,
    get_menu_button_with_badge as get_news_button_with_badge,
)
from src.sbs_helper_telegram_bot.news.news_bot_part import (
    get_news_user_handler,
    get_mandatory_ack_handler,
)
from src.sbs_helper_telegram_bot.news.admin_panel_bot_part import (
    get_news_admin_handler,
)

from src.common.telegram_user import check_if_user_admin

from config.settings import DEBUG, INVITES_PER_NEW_USER


logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    handlers=[logging.StreamHandler()]   # console
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


def clear_all_states(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Clear all conversation states from all modules.
    
    This function clears context.user_data keys used by all modules
    for conversation state management. It does NOT affect user data
    stored in the database - only in-memory conversation states.
    
    Use this when implementing /reset or /menu to return to main menu
    from any stuck conversation state.
    """
    # Import module-specific context clearing functions
    from src.sbs_helper_telegram_bot.certification.certification_bot_part import (
        clear_test_context,
        clear_learning_context,
    )
    from src.sbs_helper_telegram_bot.certification import settings as cert_settings
    from src.sbs_helper_telegram_bot.feedback import settings as feedback_settings
    from src.sbs_helper_telegram_bot.news import settings as news_settings
    from src.sbs_helper_telegram_bot.bot_admin import settings as admin_settings
    
    # Clear certification module states
    clear_test_context(context)
    clear_learning_context(context)
    # Clear certification admin states
    context.user_data.pop(cert_settings.ADMIN_NEW_QUESTION_DATA_KEY, None)
    context.user_data.pop(cert_settings.ADMIN_NEW_CATEGORY_DATA_KEY, None)
    context.user_data.pop(cert_settings.ADMIN_EDITING_QUESTION_KEY, None)
    context.user_data.pop(cert_settings.ADMIN_EDITING_CATEGORY_KEY, None)
    context.user_data.pop('cert_search_mode', None)
    context.user_data.pop('cert_search_query', None)
    context.user_data.pop('editing_question_categories', None)
    context.user_data.pop('edit_field', None)
    
    # Clear feedback module states
    feedback_keys = [
        feedback_settings.CURRENT_CATEGORY_KEY,
        feedback_settings.CURRENT_MESSAGE_KEY,
        feedback_settings.CURRENT_ENTRY_ID_KEY,
        feedback_settings.MY_FEEDBACK_PAGE_KEY,
        feedback_settings.ADMIN_CURRENT_ENTRY_KEY,
        feedback_settings.ADMIN_REPLY_TEXT_KEY,
        feedback_settings.ADMIN_LIST_PAGE_KEY,
        feedback_settings.ADMIN_FILTER_STATUS_KEY,
        feedback_settings.ADMIN_FILTER_CATEGORY_KEY,
    ]
    for key in feedback_keys:
        context.user_data.pop(key, None)
    
    # Clear ticket validator states
    context.user_data.pop('new_rule', None)
    context.user_data.pop('test_pattern', None)
    context.user_data.pop('pending_rule_id', None)
    context.user_data.pop('new_template', None)
    context.user_data.pop('manage_type_id', None)
    context.user_data.pop('manage_template_id', None)
    
    # Clear UPOS error module states
    context.user_data.pop('upos_temp', None)
    
    # Clear KTR module states
    context.user_data.pop('ktr_temp', None)
    
    # Clear news module states
    news_keys = [
        news_settings.CURRENT_PAGE_KEY,
        news_settings.SEARCH_QUERY_KEY,
        news_settings.VIEW_MODE_KEY,
        news_settings.ADMIN_DRAFT_DATA_KEY,
        news_settings.ADMIN_EDIT_FIELD_KEY,
    ]
    for key in news_keys:
        context.user_data.pop(key, None)
    
    # Clear bot admin module states
    context.user_data.pop('new_preinvite', None)
    context.user_data.pop('new_manual_user', None)
    context.user_data.pop('issue_invites_user', None)
    
    # Clear gamification states (if any specific ones exist)
    # Gamification mainly uses database, but clear any temp context
    
    # Clear screenshot/vyezd_byl module states (if any)
    # This module primarily uses ConversationHandler states

def check_if_invite_entered(telegram_id,invite) -> InviteStatus:
    """
        Validates and consumes an invite code for a user.

        Checks if the given invite code exists and has not been used yet
        (consumed_userid is NULL). If valid, marks it as consumed by the user
        with the current timestamp.

        Uses SELECT ... FOR UPDATE to prevent race conditions by locking the row
        during the entire transaction.

        Args:
            telegram_id: Telegram user ID attempting to use the invite.
            invite: Invite code string to validate.

        Returns:
            InviteStatus.SUCCESS if the invite was valid and successfully consumed,
            InviteStatus.ALREADY_CONSUMED if already used,
            InviteStatus.NOT_EXISTS if doesn't exist.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            # Lock the row to prevent race conditions
            sql_query = "SELECT consumed_userid FROM invites WHERE invite=%s FOR UPDATE"
            val=(invite,)
            cursor.execute(sql_query,val)
            result = cursor.fetchone()
            
            # Invite doesn't exist
            if result is None:
                return InviteStatus.NOT_EXISTS
            
            # Invite is already consumed
            if result["consumed_userid"] is not None:
                return InviteStatus.ALREADY_CONSUMED
            
            # Invite is valid and unused - consume it
            sql_query = "UPDATE invites SET consumed_userid=%s, consumed_timestamp=UNIX_TIMESTAMP() WHERE invite=%s"
            val=(telegram_id,invite)
            cursor.execute(sql_query,val)
            return InviteStatus.SUCCESS


async def _show_mandatory_news(update: Update, mandatory_news: dict) -> None:
    """
    Show mandatory news article that must be acknowledged before continuing.
    
    Args:
        update: Telegram update object
        mandatory_news: Dictionary with news article data from get_unacked_mandatory_news()
    """
    from datetime import datetime
    
    keyboard = news_keyboards.get_mandatory_ack_keyboard(mandatory_news['id'])
    
    # Format the date from published_timestamp
    published_ts = mandatory_news.get('published_timestamp')
    if published_ts:
        published_date = datetime.fromtimestamp(published_ts).strftime('%d.%m.%Y')
    else:
        published_date = ''
    
    formatted_content = news_messages.format_news_article(
        title=news_messages.escape_markdown_v2(mandatory_news['title']),
        content=mandatory_news['content'],  # Assume content is already MarkdownV2
        category_emoji=mandatory_news.get('category_emoji', '📌'),
        category_name=news_messages.escape_markdown_v2(mandatory_news.get('category_name', '')),
        published_date=news_messages.escape_markdown_v2(published_date)
    )
    
    text = f"🚨 *ВАЖНОЕ ОБЪЯВЛЕНИЕ*\n\nПрежде чем продолжить, ознакомьтесь с обязательной новостью\\.\n\n{formatted_content}\n\nПосле прочтения нажмите кнопку «✅ Принято» внизу\\."
    
    # Send with image if present
    if mandatory_news.get('image_file_id'):
        await update.message.reply_photo(
            photo=mandatory_news['image_file_id'],
            caption=text,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboard
        )
    else:
        await update.message.reply_text(
            text,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboard
        )
    
    # Send attachment if present
    if mandatory_news.get('attachment_file_id'):
        await update.message.reply_document(
            document=mandatory_news['attachment_file_id'],
            caption=news_messages.escape_markdown_v2("📎 Прикреплённый файл"),
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )


async def start(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """
        Handles the /start command.

        - Checks if user is pre-invited (in chat_members) and activates them if needed
        - Verifies the user has a valid invite (via check_if_user_legit())
        - If not authorized, replies with the invite-required message and exits
        - If user is blocked due to invite system being disabled, shows appropriate message
        - Otherwise, updates the user's info from Telegram data and sends the welcome message with main menu
    """
    user_id = update.effective_user.id
    
    # Check if this is a pre-invited user who hasn't activated yet
    if invites.check_if_user_pre_invited(user_id) and not invites.is_pre_invited_user_activated(user_id):
        # Activate the pre-invited user
        invites.mark_pre_invited_user_activated(user_id)
        update_user_info_from_telegram(update.effective_user)
        
        # Issue invites to the newly activated pre-invited user
        await update.message.reply_text(MESSAGE_WELCOME_PRE_INVITED)
        for _ in range(INVITES_PER_NEW_USER):
            invite = invites.generate_invite_for_user(user_id)
            await update.message.reply_text(MESSAGE_INVITE_ISSUED.format(invite=invite))
        
        # Show main menu
        is_admin = check_if_user_admin(user_id)
        await update.message.reply_text(
            get_main_menu_message(user_id, update.effective_user.first_name),
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=get_main_menu_keyboard(is_admin=is_admin)
        )
        return
    
    # Check if user is blocked due to invite system being disabled
    if check_if_invite_user_blocked(user_id):
        await update.message.reply_text(MESSAGE_INVITE_SYSTEM_DISABLED)
        return
    
    if not check_if_user_legit(user_id):
        await update.message.reply_text(get_unauthorized_message(user_id))
        return

    user = update.effective_user
    update_user_info_from_telegram(user)
    is_admin = check_if_user_admin(user_id)
    
    # Check for unacknowledged mandatory news
    mandatory_news = get_unacked_mandatory_news(user_id)
    if mandatory_news:
        await _show_mandatory_news(update, mandatory_news)
        return
    
    await update.message.reply_text(
        MESSAGE_WELCOME,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=get_main_menu_keyboard(is_admin=is_admin)
    )

async def invite_command(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """
        Handles the /invite command.

        Shows the user all their unused invite codes.
        If the user is not registered (has not entered an invite), replies with a prompt to do so.
    """
    user_id = update.effective_user.id
    
    # Check if user is blocked due to invite system being disabled
    if check_if_invite_user_blocked(user_id):
        await update.message.reply_text(MESSAGE_INVITE_SYSTEM_DISABLED)
        return
    
    if not check_if_user_legit(user_id):
        await update.message.reply_text(get_unauthorized_message(user_id))
        return
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql_query = "SELECT invite from invites where userid=%s and consumed_userid is NULL "
            val=(user_id,)
            cursor.execute(sql_query,val)

            result = cursor.fetchall()
            if len(result)>0:
                await update.message.reply_text(MESSAGE_AVAILABLE_INVITES)
                for row in result:
                    await update.message.reply_text(f'{row["invite"]}')
            else:
                await update.message.reply_text(MESSAGE_NO_INVITES)


async def menu_command(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """
        Handles the /menu command.

        Clears all conversation states from all modules and shows the main menu.
        This helps users recover from stuck conversation states.
    """
    user_id = update.effective_user.id
    
    # Check if user is blocked due to invite system being disabled
    if check_if_invite_user_blocked(user_id):
        await update.message.reply_text(MESSAGE_INVITE_SYSTEM_DISABLED)
        return
    
    if not check_if_user_legit(user_id):
        await update.message.reply_text(get_unauthorized_message(user_id))
        return
    
    # Clear all module conversation states
    clear_all_states(_context)
    logger.info(f"User {user_id} used /menu - cleared all conversation states")
    
    update_user_info_from_telegram(update.effective_user)
    is_admin = check_if_user_admin(user_id)
    
    # Check for unacknowledged mandatory news
    mandatory_news = get_unacked_mandatory_news(user_id)
    if mandatory_news:
        await _show_mandatory_news(update, mandatory_news)
        return
    
    await update.message.reply_text(
        get_main_menu_message(user_id, update.effective_user.first_name),
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=get_main_menu_keyboard(is_admin=is_admin)
    )


async def reset_command(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> int:
    """
        Handles the /reset command.

        Clears all conversation states from all modules and returns to main menu.
        This is useful when navigation buttons stop working or users get stuck.
        Returns ConversationHandler.END to terminate any active conversations.
    """
    user_id = update.effective_user.id
    
    # Check if user is blocked due to invite system being disabled
    if check_if_invite_user_blocked(user_id):
        await update.message.reply_text(MESSAGE_INVITE_SYSTEM_DISABLED)
        return ConversationHandler.END
    
    if not check_if_user_legit(user_id):
        await update.message.reply_text(get_unauthorized_message(user_id))
        return ConversationHandler.END
    
    # Clear all module conversation states
    clear_all_states(_context)
    logger.info(f"User {user_id} used /reset - cleared all conversation states")
    
    update_user_info_from_telegram(update.effective_user)
    is_admin = check_if_user_admin(user_id)
    
    # Check for unacknowledged mandatory news
    mandatory_news = get_unacked_mandatory_news(user_id)
    if mandatory_news:
        await _show_mandatory_news(update, mandatory_news)
        return ConversationHandler.END
    
    # Silently show main menu (no confirmation message)
    await update.message.reply_text(
        get_main_menu_message(user_id, update.effective_user.first_name),
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=get_main_menu_keyboard(is_admin=is_admin)
    )
    
    return ConversationHandler.END


async def help_main_command(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """
        Handles the /help command.

        Shows the main help message to authorized users.
    """
    user_id = update.effective_user.id
    
    # Check if user is blocked due to invite system being disabled
    if check_if_invite_user_blocked(user_id):
        await update.message.reply_text(MESSAGE_INVITE_SYSTEM_DISABLED)
        return
    
    if not check_if_user_legit(user_id):
        await update.message.reply_text(get_unauthorized_message(user_id))
        return
    
    await update.message.reply_text(
        MESSAGE_MAIN_HELP,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=get_settings_menu_keyboard()
    )


async def text_entered(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """
        Handles incoming text messages.

        - If the user is pre-invited but not yet activated, activates them and welcomes them.
        - If the user is not yet authorized, checks whether the message contains a valid invite code.
        On success: registers the user, issues a number of invite codes
        and sends a welcome message.
        - If the user is blocked due to invite system being disabled, shows appropriate message.
        - If the user is already authorized, handles menu button presses or sends the standard welcome message.
    """
    # Check if message exists and has text
    if not update.message or not update.message.text:
        logger.warning("Received update without message or text")
        return
    
    text = update.message.text
    user_id = update.effective_user.id
    
    # First, check if this is a pre-invited user who hasn't activated yet
    # This takes priority over invite code validation to avoid "wasting" invites
    if invites.check_if_user_pre_invited(user_id) and not invites.is_pre_invited_user_activated(user_id):
        # Activate the pre-invited user
        invites.mark_pre_invited_user_activated(user_id)
        update_user_info_from_telegram(update.effective_user)
        
        # Issue invites to the newly activated pre-invited user
        await update.message.reply_text(MESSAGE_WELCOME_PRE_INVITED)
        for _ in range(INVITES_PER_NEW_USER):
            invite = invites.generate_invite_for_user(user_id)
            await update.message.reply_text(MESSAGE_INVITE_ISSUED.format(invite=invite))
        
        # Show main menu
        is_admin = check_if_user_admin(user_id)
        await update.message.reply_text(
            get_main_menu_message(user_id, update.effective_user.first_name),
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=get_main_menu_keyboard(is_admin=is_admin)
        )
        return
    
    # Check if user is blocked due to invite system being disabled
    if check_if_invite_user_blocked(user_id):
        await update.message.reply_text(MESSAGE_INVITE_SYSTEM_DISABLED)
        return
    
    if not check_if_user_legit(user_id):
        if check_if_invite_entered(user_id, text) == InviteStatus.SUCCESS:
            update_user_info_from_telegram(update.effective_user)
            await update.message.reply_text(MESSAGE_WELCOME_SHORT)
            for _ in range(INVITES_PER_NEW_USER):                            
                invite = invites.generate_invite_for_user(user_id)
                await update.message.reply_text(MESSAGE_INVITE_ISSUED.format(invite=invite))
            # Show main menu after successful registration
            is_admin = check_if_user_admin(user_id)
            await update.message.reply_text(
                get_main_menu_message(user_id, update.effective_user.first_name),
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=get_main_menu_keyboard(is_admin=is_admin)
            )
        elif check_if_invite_entered(user_id, text) == InviteStatus.NOT_EXISTS:
            await update.message.reply_text(get_unauthorized_message(user_id))
            return
        else:
            await update.message.reply_text(MESSAGE_INVITE_ALREADY_USED)
            return
        return
    
    # Handle menu button presses for authorized users
    is_admin = check_if_user_admin(user_id)
    if text == BUTTON_MAIN_MENU:
        await update.message.reply_text(
            get_main_menu_message(user_id, update.effective_user.first_name),
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=get_main_menu_keyboard(is_admin=is_admin)
        )
    elif text == BUTTON_MODULES:
        # Show modules menu
        await update.message.reply_text(
            MESSAGE_MODULES_MENU,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=get_modules_menu_keyboard()
        )
    elif text == BUTTON_SETTINGS:
        # Show settings menu
        await update.message.reply_text(
            MESSAGE_SETTINGS_MENU,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=get_settings_menu_keyboard()
        )
    elif text == BUTTON_VALIDATE_TICKET:
        # Show validation submenu (with admin panel if user is admin)
        if is_admin:
            keyboard = validator_keyboards.get_admin_submenu_keyboard()
        else:
            keyboard = validator_keyboards.get_submenu_keyboard()
        await update.message.reply_text(
            validator_messages.get_submenu_message(),
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboard
        )
    elif text == validator_settings.BUTTON_VALIDATE_TICKET:
        await validate_ticket_command(update, _context)
    elif text == validator_settings.BUTTON_TEST_TEMPLATES:
        # Admin-only button for quick test template access
        await run_test_templates_command(update, _context)
    elif text == validator_settings.BUTTON_HELP_VALIDATION:
        await help_command(update, _context)
    elif text == BUTTON_MY_INVITES:
        await invite_command(update, _context)
    elif text == BUTTON_HELP:
        await update.message.reply_text(
            MESSAGE_MAIN_HELP,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=get_settings_menu_keyboard()
        )
    elif text == BUTTON_SCREENSHOT or text == vyezd_settings.BUTTON_SEND_SCREENSHOT:
        # These buttons are now handled by the screenshot ConversationHandler
        # This fallback is for safety, but normally the ConversationHandler will catch them
        return await enter_screenshot_module(update, _context)
    elif text == vyezd_settings.BUTTON_SCREENSHOT_HELP:
        await update.message.reply_photo(
            ASSETS_DIR / "promo3.jpg",
            caption=image_messages.MESSAGE_INSTRUCTIONS,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=image_keyboards.get_submenu_keyboard()
        )
    elif text == validator_settings.BUTTON_ADMIN_PANEL:
        # Show admin panel if user is admin
        if is_admin:
            await update.message.reply_text(
                validator_messages.MESSAGE_ADMIN_MENU,
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=validator_keyboards.get_admin_menu_keyboard()
            )
        else:
            await update.message.reply_text(
                MESSAGE_NO_ADMIN_RIGHTS,
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=get_main_menu_keyboard(is_admin=is_admin)
            )
    elif text == BUTTON_BOT_ADMIN:
        # Show bot admin panel if user is admin - this is entry point handled by ConversationHandler
        # This fallback is for safety if handler doesn't catch it
        if not is_admin:
            await update.message.reply_text(
                MESSAGE_NO_ADMIN_RIGHTS,
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=get_main_menu_keyboard(is_admin=is_admin)
            )
    elif text == BUTTON_UPOS_ERRORS:
        # Show UPOS error module submenu
        if is_admin:
            keyboard = upos_keyboards.get_admin_submenu_keyboard()
        else:
            keyboard = upos_keyboards.get_submenu_keyboard()
        await update.message.reply_text(
            upos_messages.get_submenu_message(),
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboard
        )
    elif text == upos_settings.BUTTON_POPULAR_ERRORS:
        await show_popular_errors(update, _context)
    elif text == BUTTON_CERTIFICATION:
        # Show certification module submenu (delegates to the module handler)
        await enter_certification_module(update, _context)
    elif text == certification_settings.BUTTON_MY_RANKING:
        await show_my_ranking(update, _context)
    elif text == certification_settings.BUTTON_TEST_HISTORY:
        await show_test_history(update, _context)
    elif text == certification_settings.BUTTON_MONTHLY_TOP:
        await show_monthly_top(update, _context)
    elif text == BUTTON_KTR:
        # Show KTR module submenu
        if is_admin:
            keyboard = ktr_keyboards.get_admin_submenu_keyboard()
        else:
            keyboard = ktr_keyboards.get_submenu_keyboard()
        await update.message.reply_text(
            ktr_messages.get_submenu_message(),
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboard
        )
    elif text == ktr_settings.BUTTON_POPULAR_CODES:
        await show_popular_ktr_codes(update, _context)
    elif text == ktr_settings.BUTTON_ACHIEVEMENTS:
        # Show KTR achievements (handled by KTR module)
        from src.sbs_helper_telegram_bot.ktr.ktr_bot_part import show_ktr_achievements
        await show_ktr_achievements(update, _context)
    elif text == BUTTON_FEEDBACK:
        # Show feedback module submenu
        if is_admin:
            keyboard = feedback_keyboards.get_submenu_keyboard(is_admin=True)
        else:
            keyboard = feedback_keyboards.get_submenu_keyboard(is_admin=False)
        await update.message.reply_text(
            feedback_messages.MESSAGE_SUBMENU,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboard
        )
    elif text == BUTTON_PROFILE:
        # Show gamification profile submenu
        if is_admin:
            keyboard = gamification_keyboards.get_admin_submenu_keyboard()
        else:
            keyboard = gamification_keyboards.get_submenu_keyboard()
        # Ensure user has totals record
        from src.sbs_helper_telegram_bot.gamification.gamification_logic import ensure_user_totals_exist
        ensure_user_totals_exist(user_id)
        await update.message.reply_text(
            gamification_messages.MESSAGE_SUBMENU,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboard
        )
    elif text == BUTTON_NEWS or text.startswith("📰 Новости"):
        # Show news module submenu (with possible unread badge)
        # Mark all news as read when entering
        from src.sbs_helper_telegram_bot.news import news_logic
        news_logic.mark_all_as_read(user_id)
        
        if is_admin:
            keyboard = news_keyboards.get_submenu_keyboard(is_admin=True)
        else:
            keyboard = news_keyboards.get_submenu_keyboard(is_admin=False)
        await update.message.reply_text(
            news_messages.MESSAGE_SUBMENU,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboard
        )
    else:
        # Default response for unrecognized text
        await update.message.reply_text(
            MESSAGE_UNRECOGNIZED_INPUT,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=get_main_menu_keyboard(is_admin=is_admin)
        )



async def post_init(application: Application) -> None:
    """
        Post-initialization setup after bot starts.
        
        Sets up bot command menu that appears in Telegram UI.
        Only core bot commands are shown here - module-specific commands
        are still functional but not listed in the menu to keep it clean.
    """
    # Set bot commands for the menu button in Telegram
    # Only core commands are listed - module commands still work but aren't shown
    await application.bot.set_my_commands([
        BotCommand("start", COMMAND_DESC_START),
        BotCommand("menu", COMMAND_DESC_MENU),
        BotCommand("reset", "Сбросить состояние и вернуться в главное меню"),
        BotCommand("help", COMMAND_DESC_HELP),
    ])


def main() -> None:

    """
        Entry point for the Telegram bot.

        Builds and configures the Application instance using python-telegram-bot,
        registers all command and message handlers, sets up bot menu commands,
        then starts the bot in polling mode.

        Registered handlers:
            /start          → start
            /menu           → menu_command
            /invite         → invite_command
            /validate       → validate_ticket_command (ConversationHandler)
            /help_validate  → help_command
            /debug          → toggle_debug_mode (admins only)
            /admin          → admin panel (admins only)
            Image documents → handle_incoming_document
            Plain text      → text_entered (also handles menu button presses)

        Runs indefinitely, processing all update types.
    """

    application = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .post_init(post_init)
        .read_timeout(30)
        .write_timeout(30)
        .connect_timeout(15)
        .build()
    )

    # Create ConversationHandler for ticket validation
    # Entry points include both /validate command and the menu button
    # Fallbacks include /cancel, any command, and menu buttons from the validator module
    menu_button_pattern = get_menu_button_regex_pattern()
    # Exclude menu buttons from WAITING_FOR_TICKET state so they fall through to fallbacks
    menu_button_filter = filters.Regex(menu_button_pattern)
    ticket_validator_handler = ConversationHandler(
        entry_points=[
            CommandHandler("validate", validate_ticket_command),
            MessageHandler(filters.Regex(f"^{re.escape(validator_settings.BUTTON_VALIDATE_TICKET)}$"), validate_ticket_command)
        ],
        states={
            WAITING_FOR_TICKET: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_button_filter, process_ticket_text)]
        },
        fallbacks=[
            CommandHandler("cancel", cancel_validation),
            CommandHandler("reset", reset_command),
            CommandHandler("menu", menu_command),
            # Any other command cancels validation mode
            MessageHandler(filters.COMMAND, cancel_validation_on_menu),
            # Menu buttons from ticket_validator module cancel validation mode
            MessageHandler(menu_button_filter, cancel_validation_on_menu)
        ]
    )

    # Create ConversationHandler for admin panel
    admin_handler = get_admin_conversation_handler()

    # Create ConversationHandlers for UPOS error module
    upos_user_handler = get_upos_user_handler()
    upos_admin_handler = get_upos_admin_handler()

    # Create ConversationHandler for screenshot processing module
    screenshot_exit_pattern = get_menu_button_exit_pattern()
    screenshot_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(f"^{re.escape(vyezd_settings.MENU_BUTTON_TEXT)}$"), enter_screenshot_module),
            MessageHandler(filters.Regex(f"^{re.escape(vyezd_settings.BUTTON_SEND_SCREENSHOT)}$"), enter_screenshot_module)
        ],
        states={
            WAITING_FOR_SCREENSHOT: [
                MessageHandler(filters.Document.IMAGE, handle_incoming_document),
                # Help button shows help with photo
                MessageHandler(filters.Regex(f"^{re.escape(vyezd_settings.BUTTON_SCREENSHOT_HELP)}$"), show_screenshot_help),
                # Menu buttons that should exit the module (must be before generic text handler)
                MessageHandler(filters.Regex(screenshot_exit_pattern), cancel_screenshot_module),
                # Handle wrong input: photo instead of document, or text
                MessageHandler(filters.PHOTO, handle_wrong_input_in_screenshot_mode),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_wrong_input_in_screenshot_mode),
            ]
        },
        fallbacks=[
            CommandHandler("reset", reset_command),
            CommandHandler("menu", menu_command),
            # Any command exits the module
            MessageHandler(filters.COMMAND, cancel_screenshot_module),
        ]
    )

    # Create ConversationHandlers for certification module
    certification_user_handler = get_certification_user_handler()
    certification_admin_handler = get_certification_admin_handler()

    # Create ConversationHandlers for KTR module
    ktr_user_handler = get_ktr_user_handler()
    ktr_admin_handler = get_ktr_admin_handler()

    # Create ConversationHandler for main bot admin panel
    bot_admin_handler = get_bot_admin_handler()

    # Create ConversationHandlers for feedback module
    feedback_user_handler = get_feedback_user_handler()
    feedback_admin_handler = get_feedback_admin_handler()

    # Create ConversationHandlers for gamification module
    gamification_user_handler = get_gamification_user_handler()
    gamification_admin_handler = get_gamification_admin_handler()

    # Create ConversationHandlers for news module
    news_user_handler = get_news_user_handler()
    news_admin_handler = get_news_admin_handler()
    news_mandatory_ack_handler = get_mandatory_ack_handler()

    # Register all handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("reset", reset_command))
    application.add_handler(CommandHandler("help", help_main_command))
    application.add_handler(CommandHandler("invite", invite_command))
    application.add_handler(CommandHandler("help_validate", help_command))
    application.add_handler(CommandHandler("debug", toggle_debug_mode))
    application.add_handler(bot_admin_handler)  # Main bot admin panel (must be before module admins)
    application.add_handler(admin_handler)
    application.add_handler(upos_admin_handler)
    application.add_handler(upos_user_handler)
    application.add_handler(ktr_admin_handler)
    application.add_handler(ktr_user_handler)
    application.add_handler(certification_admin_handler)
    application.add_handler(certification_user_handler)
    application.add_handler(CallbackQueryHandler(handle_top_category_selection, pattern="^cert_top_"))
    application.add_handler(feedback_admin_handler)
    application.add_handler(feedback_user_handler)
    application.add_handler(gamification_admin_handler)
    application.add_handler(gamification_user_handler)
    application.add_handler(news_admin_handler)
    application.add_handler(news_user_handler)
    application.add_handler(news_mandatory_ack_handler)  # Global handler for mandatory news acknowledgment
    application.add_handler(screenshot_handler)
    
    # Create ConversationHandler for file upload validation
    file_validation_handler = get_file_validation_handler()
    application.add_handler(file_validation_handler)
    
    application.add_handler(ticket_validator_handler)
    application.add_handler(MessageHandler(filters.PHOTO | filters.TEXT & ~filters.COMMAND, text_entered))
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle errors that occur during bot operation.
    
    Logs the error and silently ignores recoverable errors like
    TimedOut and NetworkError to prevent spam in logs.
    """
    error = context.error
    
    # Silently ignore TimedOut errors - these are usually transient
    if isinstance(error, TimedOut):
        logger.warning(f"Telegram API timed out: {error}")
        return
    
    # Silently ignore NetworkError - these are usually transient
    if isinstance(error, NetworkError):
        logger.warning(f"Network error occurred: {error}")
        return
    
    # Handle BadRequest with "Message is not modified" - common and harmless
    if isinstance(error, BadRequest):
        if "Message is not modified" in str(error):
            # Silently ignore this error - it's harmless
            return
        logger.warning(f"BadRequest error: {error}")
        return
    
    # Log other errors
    logger.error(f"Exception while handling an update: {error}", exc_info=context.error)


if __name__ == "__main__":
    main()
