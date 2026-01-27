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

from telegram import Update, constants, BotCommand
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, ConversationHandler

import src.common.database as database
import src.common.invites as invites
 

from src.common.constants.os import ASSETS_DIR
from src.common.constants.errorcodes import InviteStatus
from src.common.constants.telegram import TELEGRAM_TOKEN

# Common messages (only global/shared messages)
from src.common.messages import (
    MESSAGE_PLEASE_ENTER_INVITE,
    MESSAGE_WELCOME,
    MESSAGE_MAIN_MENU,
    MESSAGE_MAIN_HELP,
    MESSAGE_UNRECOGNIZED_INPUT,
    MESSAGE_SETTINGS_MENU,
    MESSAGE_MODULES_MENU,
    BUTTON_MODULES,
    BUTTON_SETTINGS,
    BUTTON_MAIN_MENU,
    BUTTON_MY_INVITES,
    BUTTON_HELP,
    BUTTON_VALIDATE_TICKET,
    BUTTON_SCREENSHOT,
    BUTTON_UPOS_ERRORS,
    get_main_menu_keyboard,
    get_settings_menu_keyboard,
    get_modules_menu_keyboard,
)

# Import module-specific messages, settings, and keyboards
from src.sbs_helper_telegram_bot.ticket_validator import messages as validator_messages
from src.sbs_helper_telegram_bot.ticket_validator import keyboards as validator_keyboards
from src.sbs_helper_telegram_bot.vyezd_byl import messages as image_messages
from src.sbs_helper_telegram_bot.vyezd_byl import keyboards as image_keyboards
from src.sbs_helper_telegram_bot.upos_error import messages as upos_messages
from src.sbs_helper_telegram_bot.upos_error import keyboards as upos_keyboards

from src.common.telegram_user import check_if_user_legit,update_user_info_from_telegram
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







async def start(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """
        Handles the /start command.

        - Verifies the user has a valid invite (via check_if_user_legit() )
        - If not, replies with the invite-required message and exits
        - Otherwise, updates the user's info from Telegram data and sends the welcome message with main menu
    """
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(MESSAGE_PLEASE_ENTER_INVITE)
        return

    user = update.effective_user
    update_user_info_from_telegram(user)
    await update.message.reply_text(
        MESSAGE_WELCOME,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=get_main_menu_keyboard()
    )

async def invite_command(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """
        Handles the /invite command.

        Shows the user all their unused invite codes.
        If the user is not registered (has not entered an invite), replies with a prompt to do so.
    """
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(MESSAGE_PLEASE_ENTER_INVITE)
        return
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql_query = "SELECT invite from invites where userid=%s and consumed_userid is NULL "
            val=(update.effective_user.id,)
            cursor.execute(sql_query,val)

            result = cursor.fetchall()
            if len(result)>0:
                await update.message.reply_text("Доступные инвайты:")
                for row in result:
                    await update.message.reply_text(f'{row["invite"]}')
            else:
                await update.message.reply_text("У вас нет доступных инвайтов.")


async def menu_command(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """
        Handles the /menu command.

        Shows the main menu keyboard to authorized users.
    """
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(MESSAGE_PLEASE_ENTER_INVITE)
        return
    
    update_user_info_from_telegram(update.effective_user)
    await update.message.reply_text(
        MESSAGE_MAIN_MENU,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=get_main_menu_keyboard()
    )


async def help_main_command(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """
        Handles the /help command.

        Shows the main help message to authorized users.
    """
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(MESSAGE_PLEASE_ENTER_INVITE)
        return
    
    await update.message.reply_text(
        MESSAGE_MAIN_HELP,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=get_settings_menu_keyboard()
    )


async def text_entered(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """
        Handles incoming text messages.

        - If the user is not yet authorized, checks whether the message contains a valid invite code.
        On success: registers the user, issues a number of invite codes
        and sends a welcome message.
        - If the user is already authorized, handles menu button presses or sends the standard welcome message.
    """
    # Check if message exists and has text
    if not update.message or not update.message.text:
        logger.warning("Received update without message or text")
        return
    
    text = update.message.text
    
    if not check_if_user_legit(update.effective_user.id):
        if check_if_invite_entered(update.effective_user.id,text) == InviteStatus.SUCCESS:
            update_user_info_from_telegram(update.effective_user)
            await update.message.reply_text("Добро пожаловать!")
            for _ in range(INVITES_PER_NEW_USER):                            
                invite=invites.generate_invite_for_user(update.effective_user.id)
                await update.message.reply_text("Вам выдан инвайт. Вы можете им поделиться: "+invite)
            # Show main menu after successful registration
            await update.message.reply_text(
                MESSAGE_MAIN_MENU,
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=get_main_menu_keyboard()
            )
        elif check_if_invite_entered(update.effective_user.id,text) == InviteStatus.NOT_EXISTS:
            await update.message.reply_text(MESSAGE_PLEASE_ENTER_INVITE)
            return
        else:
            await update.message.reply_text("Данный инвайт уже был использован. Пожалуйста, введите другой инвайт.")
            return
        return
    
    # Handle menu button presses for authorized users
    if text == BUTTON_MAIN_MENU:
        await update.message.reply_text(
            MESSAGE_MAIN_MENU,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=get_main_menu_keyboard()
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
        if check_if_user_admin(update.effective_user.id):
            keyboard = validator_keyboards.get_admin_submenu_keyboard()
        else:
            keyboard = validator_keyboards.get_submenu_keyboard()
        await update.message.reply_text(
            validator_messages.MESSAGE_SUBMENU,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboard
        )
    elif text == "📋 Проверить заявку":
        await validate_ticket_command(update, _context)
    elif text == "🧪 Тест шаблонов":
        # Admin-only button for quick test template access
        await run_test_templates_command(update, _context)
    elif text == "ℹ️ Помощь по валидации":
        await help_command(update, _context)
    elif text == BUTTON_MY_INVITES:
        await invite_command(update, _context)
    elif text == BUTTON_HELP:
        await update.message.reply_text(
            MESSAGE_MAIN_HELP,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=get_settings_menu_keyboard()
        )
    elif text == BUTTON_SCREENSHOT or text == "📸 Отправить скриншот":
        # These buttons are now handled by the screenshot ConversationHandler
        # This fallback is for safety, but normally the ConversationHandler will catch them
        return await enter_screenshot_module(update, _context)
    elif text == "❓ Помощь по скриншотам":
        await update.message.reply_photo(
            ASSETS_DIR / "promo3.jpg",
            caption=image_messages.MESSAGE_INSTRUCTIONS,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=image_keyboards.get_submenu_keyboard()
        )
    elif text == "🔐 Админ панель":
        # Show admin panel if user is admin
        if check_if_user_admin(update.effective_user.id):
            await update.message.reply_text(
                validator_messages.MESSAGE_ADMIN_MENU,
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=validator_keyboards.get_admin_menu_keyboard()
            )
        else:
            await update.message.reply_text(
                "⛔ У вас нет прав администратора\\.",
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=get_main_menu_keyboard()
            )
    elif text == BUTTON_UPOS_ERRORS:
        # Show UPOS error module submenu
        if check_if_user_admin(update.effective_user.id):
            keyboard = upos_keyboards.get_admin_submenu_keyboard()
        else:
            keyboard = upos_keyboards.get_submenu_keyboard()
        await update.message.reply_text(
            upos_messages.MESSAGE_SUBMENU,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboard
        )
    elif text == "📊 Популярные ошибки":
        await show_popular_errors(update, _context)
    else:
        # Default response for unrecognized text
        await update.message.reply_text(
            MESSAGE_UNRECOGNIZED_INPUT,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=get_main_menu_keyboard()
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
        BotCommand("start", "Начать работу с ботом"),
        BotCommand("menu", "Показать главное меню"),
        BotCommand("help", "Показать справку"),
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

    application = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()

    # Create ConversationHandler for ticket validation
    # Entry points include both /validate command and the menu button
    # Fallbacks include /cancel, any command, and menu buttons from the validator module
    menu_button_pattern = get_menu_button_regex_pattern()
    ticket_validator_handler = ConversationHandler(
        entry_points=[
            CommandHandler("validate", validate_ticket_command),
            MessageHandler(filters.Regex("^📋 Проверить заявку$"), validate_ticket_command)
        ],
        states={
            WAITING_FOR_TICKET: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_ticket_text)]
        },
        fallbacks=[
            CommandHandler("cancel", cancel_validation),
            # Any other command cancels validation mode
            MessageHandler(filters.COMMAND, cancel_validation_on_menu),
            # Menu buttons from ticket_validator module cancel validation mode
            MessageHandler(filters.Regex(menu_button_pattern), cancel_validation_on_menu)
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
            MessageHandler(filters.Regex("^📸 Обработать скриншот$"), enter_screenshot_module),
            MessageHandler(filters.Regex("^📸 Отправить скриншот$"), enter_screenshot_module)
        ],
        states={
            WAITING_FOR_SCREENSHOT: [
                MessageHandler(filters.Document.IMAGE, handle_incoming_document),
                # Help button shows help with photo
                MessageHandler(filters.Regex("^❓ Помощь по скриншотам$"), show_screenshot_help),
                # Menu buttons that should exit the module (must be before generic text handler)
                MessageHandler(filters.Regex(screenshot_exit_pattern), cancel_screenshot_module),
                # Handle wrong input: photo instead of document, or text
                MessageHandler(filters.PHOTO, handle_wrong_input_in_screenshot_mode),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_wrong_input_in_screenshot_mode),
            ]
        },
        fallbacks=[
            # Any command exits the module
            MessageHandler(filters.COMMAND, cancel_screenshot_module),
        ]
    )

    # Register all handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("help", help_main_command))
    application.add_handler(CommandHandler("invite", invite_command))
    application.add_handler(CommandHandler("help_validate", help_command))
    application.add_handler(CommandHandler("debug", toggle_debug_mode))
    application.add_handler(admin_handler)
    application.add_handler(upos_admin_handler)
    application.add_handler(upos_user_handler)
    application.add_handler(screenshot_handler)
    application.add_handler(ticket_validator_handler)
    application.add_handler(MessageHandler(filters.PHOTO | filters.TEXT & ~filters.COMMAND, text_entered))
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
