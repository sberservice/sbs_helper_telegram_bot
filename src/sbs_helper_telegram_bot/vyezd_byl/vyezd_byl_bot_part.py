from telegram import Update
from telegram.ext import ContextTypes
from src.common.telegram_user import check_if_user_legit, update_user_info_from_telegram

import src.common.database as database
from src.common.messages import MESSAGE_PLEASE_ENTER_INVITE
from src.common.constants.os import IMAGES_DIR
import logging
from pathlib import Path  

# Import module-specific messages, settings, and keyboards
from . import messages
from . import settings
from .keyboards import get_submenu_keyboard
from config.settings import DEBUG

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
async def handle_incoming_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
        Handles incoming document messages from Telegram users.

        - Rejects non-legitimate users (invite check)
        - Saves received image files (sent as documents) to disk as <user_id>.jpg
        - Rejects files > certain size
        - Prevents queue spamming (one active job per user)
        - Adds valid images to the processing queue
        - Informs the user about their queue position

        Expected files: screenshots sent as "document" (not photo) to preserve original quality.
    """
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(MESSAGE_PLEASE_ENTER_INVITE)
        return

    update_user_info_from_telegram(update.effective_user)
    user_id = update.effective_user.id
    if update.message.document:
        file_id = update.message.document.file_id
        file_name = update.message.document.file_name
        file_size = update.message.document.file_size
        file_name = update.message.document.file_name

        if file_size > settings.MAX_SCREENSHOT_SIZE_BYTES:
            await update.message.reply_text(messages.MESSAGE_FILE_TOO_LARGE)
            return

        if check_if_user_has_unprocessed_job(user_id):
            await update.message.reply_text(
                messages.MESSAGE_ACTIVE_JOB_EXISTS,
                reply_markup=get_submenu_keyboard()
            )
            return
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
