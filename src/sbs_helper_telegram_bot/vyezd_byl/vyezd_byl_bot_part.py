from telegram import Update, constants
from telegram.ext import ContextTypes, ConversationHandler
from src.common.telegram_user import check_if_user_legit, update_user_info_from_telegram

import src.common.database as database
from src.common.messages import MESSAGE_PLEASE_ENTER_INVITE, get_main_menu_keyboard
from src.common.constants.os import IMAGES_DIR
import logging
from pathlib import Path  

# Import module-specific messages, settings, and keyboards
from . import messages
from . import settings
from .keyboards import get_submenu_keyboard
from config.settings import DEBUG

# Conversation states
WAITING_FOR_SCREENSHOT = 1

logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    handlers=[logging.StreamHandler()]   # console
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

def get_number_of_jobs_in_the_queue() -> int:
    """
        Returns the number of jobs currently pending or in progress.

        Counts all entries in the `imagequeue` table with status < 2
        (i.e., not yet marked as finished).

        Returns:
            Total count of unfinished jobs.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql_query = "SELECT count(*) as jobs_in_the_queue from imagequeue where status <2"
            cursor.execute(sql_query)
            result = cursor.fetchone()
            return result["jobs_in_the_queue"]
        
def check_if_user_has_unprocessed_job(user_id) -> bool:
    """
        Checks whether the user has any jobs that are not yet completed (status ≠ 2).

        Args:
            user_id: Telegram user ID to check.

        Returns:
            True if the user has at least one pending or in-progress job, False otherwise.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql_query = "SELECT count(*) as number_of_jobs from imagequeue WHERE userid=%s and status<>2"
            val = (user_id,)
            cursor.execute(sql_query, val)
            result=cursor.fetchone()
            if result["number_of_jobs"]:
                if result["number_of_jobs"]>0:
                    return True
                else:
                    return False
            else:
                return False
            
def add_to_image_queue(user_id,file_name) -> None:
    """
        Adds a new image processing job to the queue.

        Inserts a record into the `imagequeue` table with current UNIX timestamp,
        given user_id, file_name, and status 0 (pending).

        Args:
            user_id: Telegram user ID who uploaded the image.
            file_name: Name of the saved image file (e.g., '123456789.jpg').

        The job will be picked up by the background worker (processimagequeue.py).
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql_query = "INSERT INTO imagequeue (timestamp, userid,file_name,status) VALUES (UNIX_TIMESTAMP()," \
        " %s, %s, 0)"
            val = (user_id,file_name)
            cursor.execute(sql_query, val)
async def handle_incoming_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
        Handles incoming document messages from Telegram users.

        - Rejects non-legitimate users (invite check)
        - Saves received image files (sent as documents) to disk as <user_id>.jpg
        - Rejects files > certain size
        - Prevents queue spamming (one active job per user)
        - Adds valid images to the processing queue
        - Informs the user about their queue position

        Expected files: screenshots sent as "document" (not photo) to preserve original quality.
        
        Returns:
            WAITING_FOR_SCREENSHOT to continue waiting for more screenshots,
            or ConversationHandler.END if user is not authorized
    """
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(MESSAGE_PLEASE_ENTER_INVITE)
        return ConversationHandler.END

    update_user_info_from_telegram(update.effective_user)
    user_id = update.effective_user.id
    if update.message.document:
        file_id = update.message.document.file_id
        file_name = update.message.document.file_name
        file_size = update.message.document.file_size
        file_name = update.message.document.file_name

        if file_size > settings.MAX_SCREENSHOT_SIZE_BYTES:
            await update.message.reply_text(messages.MESSAGE_FILE_TOO_LARGE)
            return WAITING_FOR_SCREENSHOT

        if check_if_user_has_unprocessed_job(user_id):
            await update.message.reply_text(
                messages.MESSAGE_ACTIVE_JOB_EXISTS,
                reply_markup=get_submenu_keyboard()
            )
            return WAITING_FOR_SCREENSHOT
        else:
            position=get_number_of_jobs_in_the_queue()+1
            await update.message.reply_text(
                messages.MESSAGE_FILE_RECEIVED.format(position=position),
                reply_markup=get_submenu_keyboard()
            )
            file_name_to_save=IMAGES_DIR / f"{user_id}.jpg"
            new_file = await context.bot.get_file(file_id)
            await new_file.download_to_drive(custom_path=file_name_to_save)
            if not Path(file_name_to_save).exists():
                logger.critical("Couldn't save the file from telegram to path: %s",file_name_to_save)
            add_to_image_queue(user_id,file_name)
    else:
        await update.message.reply_text(messages.MESSAGE_DOCUMENTS_ONLY)
    
    return WAITING_FOR_SCREENSHOT


async def handle_wrong_input_in_screenshot_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle when user sends a photo or text instead of a document in screenshot mode.
    Reminds them to send the image as a file.
    
    Args:
        update: Telegram update object
        context: Telegram context
        
    Returns:
        WAITING_FOR_SCREENSHOT to continue waiting for proper document
    """
    await update.message.reply_text(
        messages.MESSAGE_INSTRUCTIONS,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=get_submenu_keyboard()
    )
    return WAITING_FOR_SCREENSHOT


async def enter_screenshot_module(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Entry point for the screenshot processing module.
    Shows instructions and waits for screenshot.
    
    Args:
        update: Telegram update object
        context: Telegram context
        
    Returns:
        WAITING_FOR_SCREENSHOT state to wait for document
    """
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(MESSAGE_PLEASE_ENTER_INVITE)
        return ConversationHandler.END
    
    update_user_info_from_telegram(update.effective_user)
    
    await update.message.reply_text(
        messages.MESSAGE_INSTRUCTIONS,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=get_submenu_keyboard()
    )
    
    return WAITING_FOR_SCREENSHOT


async def show_screenshot_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Show help for screenshot module with a promo image.
    
    Args:
        update: Telegram update object
        context: Telegram context
        
    Returns:
        WAITING_FOR_SCREENSHOT state to continue waiting for document
    """
    from src.common.constants.os import ASSETS_DIR
    
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(MESSAGE_PLEASE_ENTER_INVITE)
        return ConversationHandler.END
    
    await update.message.reply_photo(
        ASSETS_DIR / "promo3.jpg",
        caption=messages.MESSAGE_INSTRUCTIONS,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=get_submenu_keyboard()
    )
    
    return WAITING_FOR_SCREENSHOT


async def cancel_screenshot_module(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Cancel/exit from the screenshot module when user navigates away.
    
    Args:
        update: Telegram update object
        context: Telegram context
        
    Returns:
        ConversationHandler.END to exit the module
    """
    await update.message.reply_text(
        "📷 Режим отправки скриншота завершён\\.",
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=get_main_menu_keyboard()
    )
    return ConversationHandler.END


def get_menu_button_exit_pattern() -> str:
    """
    Get regex pattern for buttons that should exit the screenshot module.
    
    Returns:
        Regex pattern string matching menu buttons that exit the module
    """
    import re
    # Buttons that should exit the screenshot module
    exit_buttons = [
        "🏠 Главное меню",
        "📦 Модули",
        "⚙️ Настройки",
        "✅ Валидация заявок",
        "🎫 Мои инвайты",
        "❓ Помощь",
        "🔐 Админ панель",
        "📋 Проверить заявку",
        "🔢 UPOS Ошибки",
    ]
    escaped_buttons = [re.escape(btn) for btn in exit_buttons]
    return "^(" + "|".join(escaped_buttons) + ")$"
