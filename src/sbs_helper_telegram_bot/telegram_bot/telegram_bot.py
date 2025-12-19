"""
imagebot.py

Telegram bot for an invite-only image processing service.

Features:
- Invite-based access control
- Accepts images sent as document files (not photos)
- Enforces one active job per user
- Queue position feedback
- Issues new invites to verified users
- Stores user data and tracks invite usage

Commands:
    /start   - Welcome message (requires valid invite)
    /invite  - List user's unused invite codes

Non-legitimate users are prompted to enter an invite code via text message.
"""
# pylint: disable=line-too-long

import logging

from telegram import Update, constants
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

import src.common.database as database
import src.common.invites as invites
 

from src.common.constants.os import ASSETS_DIR
from src.common.constants.errorcodes import InviteStatus
from src.common.constants.telegram import TELEGRAM_TOKEN
from src.common.messages import MESSAGE_PLEASE_ENTER_INVITE,MESSAGE_WELCOME
from src.common.telegram_user import check_if_user_legit,update_user_info_from_telegram
from src.sbs_helper_telegram_bot.vyezd_byl.vyezd_byl_bot_part import handle_incoming_document

from config.settings import DEBUG


logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    handlers=[logging.StreamHandler()]   # console
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

#FIXME: bad code The following function contains a racing condition which should be fixed by FOR UDPATE logic
def check_if_invite_entered(telegram_id,invite) -> bool:
    """
        Validates and consumes an invite code for a user.

        Checks if the given invite code exists and has not been used yet
        (consumed_userid is NULL). If valid, marks it as consumed by the user
        with the current timestamp.

        Args:
            telegram_id: Telegram user ID attempting to use the invite.
            invite: Invite code string to validate.

        Returns:
            True if the invite was valid and successfully consumed,
            False if already used or doesn't exist.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            #check if invite is already consumed
            sql_query = "SELECT count(invite) as invites_count from invites where consumed_userid is not null and invite=%s"
            val=(invite,)
            cursor.execute(sql_query,val)
            result = cursor.fetchone()
            if result["invites_count"]>0:
                return InviteStatus.ALREADY_CONSUMED
            #check if invite exists and is unused
            sql_query = "SELECT count(invite) as invites_count from invites where consumed_userid is NULL and invite=%s"
            val=(invite,)
            cursor.execute(sql_query,val)
            result = cursor.fetchone()
            if result["invites_count"]>0:
                sql_query = "update invites set consumed_userid=%s, consumed_timestamp=UNIX_TIMESTAMP() where invite=%s"
                val=(telegram_id,invite)
                cursor.execute(sql_query,val)
                return InviteStatus.SUCCESS          
            return InviteStatus.NOT_EXISTS







async def start(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """
        Handles the /start command.

        - Verifies the user has a valid invite (via check_if_user_legit() )
        - If not, replies with the invite-required message and exits
        - Otherwise, updates the user's info from Telegram data and sends the welcome message
    """
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(MESSAGE_PLEASE_ENTER_INVITE)
        return

    user = update.effective_user
    update_user_info_from_telegram(user)
    await update.message.reply_text(MESSAGE_WELCOME,parse_mode=constants.ParseMode.MARKDOWN_V2)

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


async def text_entered(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """
        Handles incoming text messages.

        - If the user is not yet authorized, checks whether the message contains a valid invite code.
        On success: registers the user, issues a number of invite codes
        and sends a welcome message.
        - If the user is already authorized, sends the standard welcome message with a promotional image.
    """
    if not check_if_user_legit(update.effective_user.id):
        if check_if_invite_entered(update.effective_user.id,update.message.text) == InviteStatus.SUCCESS:
            update_user_info_from_telegram(update.effective_user)
            await update.message.reply_text("Добро пожаловать!")
            for _ in range(2):                            
                invite=invites.generate_invite_for_user(update.effective_user.id)
                await update.message.reply_text("Вам выдан инвайт. Вы можете им поделиться: "+invite)
        elif check_if_invite_entered(update.effective_user.id,update.message.text) == InviteStatus.NOT_EXISTS:
            await update.message.reply_text(MESSAGE_PLEASE_ENTER_INVITE)
            return
        else:
            await update.message.reply_text("Данный инвайт уже был использован. Пожалуйста, введите другой инвайт.")
            return

    await update.message.reply_text(MESSAGE_WELCOME,parse_mode=constants.ParseMode.MARKDOWN_V2)
    await update.message.reply_photo(ASSETS_DIR / "promo3.jpg")



def main() -> None:

    """
        Entry point for the Telegram bot.

        Builds and configures the Application instance using python-telegram-bot,
        registers all command and message handlers, then starts the bot in polling mode.

        Registered handlers:
            /start          → start
            /invite         → invite_command
            Image documents → handle_incoming_document
            Plain text      → text_entered

        Runs indefinitely, processing all update types.
    """

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("invite", invite_command))
    application.add_handler(MessageHandler(filters.Document.IMAGE,handle_incoming_document))
    application.add_handler(MessageHandler(filters.PHOTO | filters.TEXT & ~filters.COMMAND, text_entered))
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
