"""
File Upload Bot Handlers

Telegram bot handlers for batch file validation functionality.
Allows users to upload Excel files with tickets for batch validation.
"""

import os
import tempfile
import asyncio
import logging
import re
from typing import Optional

from telegram import Update, Message
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    filters
)
from telegram import constants
from telegram.error import TimedOut

from src.common.telegram_user import check_if_user_legit, check_if_user_admin, update_user_info_from_telegram
from src.common.messages import MESSAGE_PLEASE_ENTER_INVITE, BUTTON_MAIN_MENU

from . import messages
from .keyboards import get_file_upload_keyboard, get_submenu_keyboard, get_admin_submenu_keyboard
from .file_processor import ExcelFileProcessor, get_column_names, FileValidationResult

logger = logging.getLogger(__name__)

# Conversation states
WAITING_FOR_FILE = 1
WAITING_FOR_COLUMN = 2

# Context keys
CTX_TEMP_FILE = 'file_upload_temp_file'
CTX_ORIGINAL_FILENAME = 'file_upload_original_filename'
CTX_COLUMNS = 'file_upload_columns'
CTX_PROGRESS_MESSAGE = 'file_upload_progress_message'

# File size limits (in bytes)
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB

# Supported file extensions
SUPPORTED_EXTENSIONS = ('.xls', '.xlsx')


def _escape_md(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text


def _cleanup_temp_file(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clean up temporary file from context."""
    temp_file = context.user_data.get(CTX_TEMP_FILE)
    if temp_file and os.path.exists(temp_file):
        try:
            os.remove(temp_file)
            logger.debug(f"Cleaned up temp file: {temp_file}")
        except Exception as e:
            logger.warning(f"Failed to clean up temp file {temp_file}: {e}")
    
    # Clear context data
    context.user_data.pop(CTX_TEMP_FILE, None)
    context.user_data.pop(CTX_ORIGINAL_FILENAME, None)
    context.user_data.pop(CTX_COLUMNS, None)
    context.user_data.pop(CTX_PROGRESS_MESSAGE, None)


async def validate_file_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Start file validation conversation.
    Handler for /validate_file command and menu button.
    
    Args:
        update: Telegram update object
        context: Telegram context
        
    Returns:
        Next conversation state
    """
    # Check if user is authorized
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(
            MESSAGE_PLEASE_ENTER_INVITE,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ConversationHandler.END
    
    # Update user info
    update_user_info_from_telegram(update.effective_user)
    
    # Clean up any previous temp files
    _cleanup_temp_file(context)
    
    # Ask for file
    await update.message.reply_text(
        messages.MESSAGE_SEND_FILE,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=get_file_upload_keyboard()
    )
    
    return WAITING_FOR_FILE


async def process_uploaded_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Process uploaded Excel file.
    
    Args:
        update: Telegram update object
        context: Telegram context
        
    Returns:
        Next conversation state
    """
    document = update.message.document
    
    # Check file size
    if document.file_size > MAX_FILE_SIZE:
        max_size_mb = MAX_FILE_SIZE / (1024 * 1024)
        file_size_mb = document.file_size / (1024 * 1024)
        await update.message.reply_text(
            messages.MESSAGE_FILE_TOO_LARGE.format(
                max_size=f"{max_size_mb:.0f}",
                file_size=f"{file_size_mb:.1f}"
            ),
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return WAITING_FOR_FILE
    
    # Check file extension
    filename = document.file_name or "unknown"
    if not filename.lower().endswith(SUPPORTED_EXTENSIONS):
        await update.message.reply_text(
            messages.MESSAGE_UNSUPPORTED_FORMAT,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return WAITING_FOR_FILE
    
    # Show downloading message
    status_message = await update.message.reply_text(
        "⏳ Загружаю файл\\.\\.\\.",
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    try:
        # Download file
        file = await document.get_file()
        
        # Create temp file
        temp_dir = tempfile.gettempdir()
        safe_filename = f"ticket_upload_{update.effective_user.id}_{os.path.basename(filename)}"
        temp_path = os.path.join(temp_dir, safe_filename)
        
        await file.download_to_drive(temp_path)
        logger.info(f"Downloaded file to {temp_path}")
        
        # Store in context
        context.user_data[CTX_TEMP_FILE] = temp_path
        context.user_data[CTX_ORIGINAL_FILENAME] = filename
        
        # Get column names
        columns = get_column_names(temp_path)
        
        if not columns:
            await status_message.edit_text(
                messages.MESSAGE_FILE_NO_COLUMNS,
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
            _cleanup_temp_file(context)
            return WAITING_FOR_FILE
        
        context.user_data[CTX_COLUMNS] = columns
        
        # Build column selection message
        column_list = "\n".join([
            f"{i+1}\\. {_escape_md(col)}" 
            for i, col in enumerate(columns) 
            if col.strip()
        ])
        
        file_size_kb = document.file_size / 1024
        
        message = messages.MESSAGE_SELECT_COLUMN.format(
            filename=_escape_md(filename),
            file_size=_escape_md(f"{file_size_kb:.1f}"),
            columns=column_list
        )
        
        await status_message.edit_text(
            message,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        
        return WAITING_FOR_COLUMN
        
    except Exception as e:
        logger.error(f"Error processing uploaded file: {e}", exc_info=True)
        await status_message.edit_text(
            messages.MESSAGE_FILE_READ_ERROR.format(error=_escape_md(str(e))),
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        _cleanup_temp_file(context)
        return WAITING_FOR_FILE


async def process_column_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Process column selection and start validation.
    
    Args:
        update: Telegram update object
        context: Telegram context
        
    Returns:
        Next conversation state or END
    """
    user_input = update.message.text.strip()
    columns = context.user_data.get(CTX_COLUMNS, [])
    temp_file = context.user_data.get(CTX_TEMP_FILE)
    original_filename = context.user_data.get(CTX_ORIGINAL_FILENAME, "file")
    
    if not temp_file or not os.path.exists(temp_file):
        await update.message.reply_text(
            messages.MESSAGE_FILE_EXPIRED,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        _cleanup_temp_file(context)
        return ConversationHandler.END
    
    # Resolve column
    ticket_column = None
    col_idx = None
    
    # Try to parse as number
    if user_input.isdigit():
        idx = int(user_input) - 1  # Convert to 0-based
        if 0 <= idx < len(columns):
            col_idx = idx
            ticket_column = columns[idx]
    else:
        # Try exact match
        if user_input in columns:
            col_idx = columns.index(user_input)
            ticket_column = user_input
        else:
            # Try case-insensitive match
            lower_columns = [c.lower() for c in columns]
            if user_input.lower() in lower_columns:
                col_idx = lower_columns.index(user_input.lower())
                ticket_column = columns[col_idx]
    
    if ticket_column is None:
        column_list = ", ".join([f"'{c}'" for c in columns if c.strip()])
        await update.message.reply_text(
            messages.MESSAGE_INVALID_COLUMN.format(columns=_escape_md(column_list)),
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return WAITING_FOR_COLUMN
    
    # Start processing
    user_id = update.effective_user.id
    is_admin = check_if_user_admin(user_id)
    
    # Send processing message
    progress_message = await update.message.reply_text(
        messages.MESSAGE_PROCESSING_START.format(column=_escape_md(ticket_column)),
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    context.user_data[CTX_PROGRESS_MESSAGE] = progress_message
    
    try:
        # Create processor
        processor = ExcelFileProcessor()
        
        # Track progress with a shared dict (thread-safe for simple updates)
        progress_data = {'current': 0, 'total': 0, 'running': True}
        
        def sync_progress_callback(current: int, total: int):
            """Sync callback that updates progress data"""
            progress_data['current'] = current
            progress_data['total'] = total
        
        # Start background task to update progress message
        async def progress_updater():
            """Periodically update the progress message"""
            import time
            last_current = 0
            
            while progress_data['running']:
                await asyncio.sleep(3)  # Update every 3 seconds
                
                current = progress_data['current']
                total = progress_data['total']
                
                # Only update if values changed
                if total > 0 and current != last_current:
                    percent = (current / total * 100)
                    bar_length = 10
                    filled = int(bar_length * current / total)
                    bar = '▓' * filled + '░' * (bar_length - filled)
                    
                    try:
                        await progress_message.edit_text(
                            messages.MESSAGE_PROCESSING_PROGRESS.format(
                                current=current,
                                total=total,
                                bar=bar,
                                percent=_escape_md(f"{percent:.0f}")
                            ),
                            parse_mode=constants.ParseMode.MARKDOWN_V2
                        )
                        last_current = current
                    except Exception:
                        # Ignore edit errors (rate limiting, message not modified, etc.)
                        pass
        
        # Start the progress updater task
        loop = asyncio.get_event_loop()
        progress_task = loop.create_task(progress_updater())
        
        # Run validation in executor with sync callback
        result: FileValidationResult = await loop.run_in_executor(
            None,
            lambda: processor.validate_file(
                file_path=temp_file,
                ticket_column=col_idx,
                output_path=None,  # Auto-generate
                ticket_type_id=None,  # Auto-detect
                progress_callback=sync_progress_callback
            )
        )
        
        # Stop progress updater and wait for it to finish
        progress_data['running'] = False
        try:
            await asyncio.wait_for(progress_task, timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning("Progress updater task didn't finish in time")
            progress_task.cancel()
        except Exception as e:
            logger.error(f"Error stopping progress updater: {e}")
        
        # Check for errors
        if result.error_message:
            await progress_message.edit_text(
                messages.MESSAGE_PROCESSING_ERROR.format(error=_escape_md(result.error_message)),
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
            _cleanup_temp_file(context)
            return ConversationHandler.END
        
        # Calculate stats
        processed = result.total_tickets - result.skipped_tickets
        percent_valid = (result.valid_tickets / processed * 100) if processed > 0 else 0
        percent_invalid = (result.invalid_tickets / processed * 100) if processed > 0 else 0
        
        stats_message = messages.MESSAGE_PROCESSING_COMPLETE.format(
            total=result.total_tickets,
            valid=result.valid_tickets,
            percent_valid=_escape_md(f"{percent_valid:.1f}"),
            invalid=result.invalid_tickets,
            percent_invalid=_escape_md(f"{percent_invalid:.1f}"),
            skipped=result.skipped_tickets
        )
        
        # Send results summary (isolated from file send)
        try:
            await progress_message.edit_text(
                stats_message,
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
        except TimedOut:
            logger.warning("Timed out editing stats message, sending as new message")
            try:
                await update.message.reply_text(
                    stats_message,
                    parse_mode=constants.ParseMode.MARKDOWN_V2
                )
            except Exception as e2:
                logger.error(f"Failed to send stats as new message: {e2}")
        except Exception as e:
            logger.error(f"Error sending stats: {e}")
        
        # Send result file (isolated, with extended timeout)
        if result.output_file_path and os.path.exists(result.output_file_path):
            # Generate output filename
            base_name = os.path.splitext(original_filename)[0]
            output_filename = f"{base_name}_validated.xlsx"
            
            try:
                with open(result.output_file_path, 'rb') as f:
                    await update.message.reply_document(
                        document=f,
                        filename=output_filename,
                        caption="📊 Результаты валидации",
                        write_timeout=60,
                        read_timeout=60
                    )
            except TimedOut:
                logger.warning("Timed out sending file, retrying with longer timeout")
                try:
                    with open(result.output_file_path, 'rb') as f:
                        await update.message.reply_document(
                            document=f,
                            filename=output_filename,
                            caption="📊 Результаты валидации",
                            write_timeout=120,
                            read_timeout=120
                        )
                except Exception as e2:
                    logger.error(f"Retry also failed: {e2}")
                    await update.message.reply_text(
                        "⚠️ Не удалось отправить файл из\\-за таймаута\\. Попробуйте загрузить файл ещё раз\\.",
                        parse_mode=constants.ParseMode.MARKDOWN_V2
                    )
            except Exception as e:
                logger.error(f"Error sending validated file: {e}")
            finally:
                # Clean up output file
                try:
                    os.remove(result.output_file_path)
                except Exception:
                    pass
        
        # Show keyboard (isolated)
        reply_keyboard = get_admin_submenu_keyboard() if is_admin else get_submenu_keyboard()
        try:
            await update.message.reply_text(
                "Выберите действие из меню:",
                reply_markup=reply_keyboard
            )
        except Exception as e:
            logger.error(f"Error sending keyboard: {e}")
        
    except Exception as e:
        logger.error(f"Error during file validation: {e}", exc_info=True)
        try:
            await progress_message.edit_text(
                messages.MESSAGE_PROCESSING_ERROR.format(error=_escape_md(str(e))),
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
        except Exception:
            # If even the error message fails, try a simple reply
            try:
                await update.message.reply_text(
                    "❌ Ошибка обработки файла\\. Попробуйте ещё раз\\.",
                    parse_mode=constants.ParseMode.MARKDOWN_V2
                )
            except Exception:
                pass
    
    finally:
        # Clean up temp files
        _cleanup_temp_file(context)
        
        # Clean up output file if it still exists
        output_path = context.user_data.get('output_file_path')
        if output_path and os.path.exists(output_path):
            try:
                os.remove(output_path)
            except Exception:
                pass
    
    return ConversationHandler.END


async def cancel_file_validation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Cancel file validation conversation.
    
    Args:
        update: Telegram update object
        context: Telegram context
        
    Returns:
        ConversationHandler.END
    """
    _cleanup_temp_file(context)
    
    user_id = update.effective_user.id
    is_admin = check_if_user_admin(user_id)
    reply_keyboard = get_admin_submenu_keyboard() if is_admin else get_submenu_keyboard()
    
    await update.message.reply_text(
        messages.MESSAGE_FILE_VALIDATION_CANCELLED,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=reply_keyboard
    )
    
    return ConversationHandler.END


async def cancel_on_menu_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Cancel file validation when menu button pressed.
    
    Args:
        update: Telegram update object
        context: Telegram context
        
    Returns:
        ConversationHandler.END
    """
    _cleanup_temp_file(context)
    return ConversationHandler.END


def get_file_validation_handler() -> ConversationHandler:
    """
    Create and return the file validation conversation handler.
    
    Returns:
        ConversationHandler for file validation
    """
    from . import settings
    
    # Build pattern for menu buttons that should exit the conversation
    exit_buttons = [
        BUTTON_MAIN_MENU,
        settings.BUTTON_VALIDATE_TICKET,
        settings.BUTTON_HELP_VALIDATION,
        settings.BUTTON_ADMIN_PANEL,
        settings.BUTTON_TEST_TEMPLATES,
    ]
    exit_pattern = "^(" + "|".join([re.escape(b) for b in exit_buttons]) + ")$"
    
    # Build filter for exit buttons to exclude from WAITING_FOR_COLUMN state
    exit_filter = filters.Regex(exit_pattern)
    
    return ConversationHandler(
        entry_points=[
            CommandHandler("validate_file", validate_file_command),
            MessageHandler(filters.Regex(f"^{re.escape(settings.BUTTON_FILE_VALIDATION)}$"), validate_file_command),
        ],
        states={
            WAITING_FOR_FILE: [
                MessageHandler(filters.Document.ALL, process_uploaded_file),
                # Cancel button
                MessageHandler(filters.Regex("^❌ Отмена$"), cancel_file_validation),
            ],
            WAITING_FOR_COLUMN: [
                # Exclude menu buttons so they fall through to fallbacks
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~exit_filter, process_column_selection),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_file_validation),
            # Any other command cancels
            MessageHandler(filters.COMMAND, cancel_on_menu_button),
            # Menu buttons cancel
            MessageHandler(exit_filter, cancel_on_menu_button),
        ],
        name="file_validation",
        persistent=False,
        allow_reentry=True
    )


# Export conversation states for external use
FILE_WAITING_FOR_FILE = WAITING_FOR_FILE
FILE_WAITING_FOR_COLUMN = WAITING_FOR_COLUMN
