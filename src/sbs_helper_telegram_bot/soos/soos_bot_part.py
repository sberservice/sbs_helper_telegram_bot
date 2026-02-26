"""
Часть бота для модуля СООС.
"""

from __future__ import annotations

import logging
import re
import time

from telegram import Update, constants
from telegram.ext import ContextTypes, ConversationHandler

import src.common.database as database
from src.common.messages import (
    BUTTON_BOT_ADMIN,
    BUTTON_CERTIFICATION,
    BUTTON_FEEDBACK,
    BUTTON_HELP,
    BUTTON_KTR,
    BUTTON_MAIN_MENU,
    BUTTON_MODULES,
    BUTTON_MY_INVITES,
    BUTTON_NEWS,
    BUTTON_PROFILE,
    BUTTON_SETTINGS,
    BUTTON_UPOS_ERRORS,
    BUTTON_VALIDATE_TICKET,
    get_main_menu_keyboard,
)
from src.common.telegram_user import (
    check_if_user_legit,
    get_unauthorized_message,
    update_user_info_from_telegram,
)
from src.sbs_helper_telegram_bot.ticket_validator import settings as validator_settings
from src.sbs_helper_telegram_bot.vyezd_byl import settings as screenshot_settings

from . import messages, settings, soos_parser
from .keyboards import get_submenu_keyboard

logger = logging.getLogger(__name__)

WAITING_FOR_SOOS_TICKET = 1


def get_number_of_jobs_in_the_queue() -> int:
    """
    Получить количество незавершённых задач в очереди СООС.

    Returns:
        Количество задач со статусом меньше 2.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(
                f"SELECT COUNT(*) AS jobs_in_the_queue FROM {settings.SOOS_QUEUE_TABLE} WHERE status < 2"
            )
            result = cursor.fetchone()
            return int(result["jobs_in_the_queue"]) if result else 0


def check_if_user_has_unprocessed_job(user_id: int) -> bool:
    """
    Проверить наличие активной задачи СООС у пользователя.

    Args:
        user_id: Telegram ID пользователя.

    Returns:
        True, если есть задача со статусом не равным 2.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(
                f"SELECT COUNT(*) AS number_of_jobs FROM {settings.SOOS_QUEUE_TABLE} WHERE userid = %s AND status <> 2",
                (user_id,),
            )
            result = cursor.fetchone()
            return bool(result and result["number_of_jobs"] > 0)


def add_to_soos_queue(user_id: int, ticket_text: str, file_name: str) -> None:
    """
    Добавить задачу в очередь СООС.

    Args:
        user_id: Telegram ID пользователя.
        ticket_text: Полный текст тикета.
        file_name: Имя выходного файла.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(
                f"""
                INSERT INTO {settings.SOOS_QUEUE_TABLE} (timestamp, userid, file_name, ticket_text, status)
                VALUES (UNIX_TIMESTAMP(), %s, %s, %s, 0)
                """,
                (user_id, file_name, ticket_text),
            )


async def enter_soos_module(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Войти в модуль СООС и показать инструкцию.

    Args:
        update: Объект обновления Telegram.
        _context: Контекст Telegram.

    Returns:
        Состояние ожидания текста тикета.
    """
    user_id = update.effective_user.id
    if not check_if_user_legit(user_id):
        await update.message.reply_text(get_unauthorized_message(user_id))
        return ConversationHandler.END

    update_user_info_from_telegram(update.effective_user)
    await update.message.reply_text(
        messages.MESSAGE_SUBMENU,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=get_submenu_keyboard(),
    )
    return WAITING_FOR_SOOS_TICKET


async def show_soos_help(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Показать справку по модулю СООС.

    Args:
        update: Объект обновления Telegram.
        _context: Контекст Telegram.

    Returns:
        Состояние ожидания текста тикета.
    """
    user_id = update.effective_user.id
    if not check_if_user_legit(user_id):
        await update.message.reply_text(get_unauthorized_message(user_id))
        return ConversationHandler.END

    await update.message.reply_text(
        messages.MESSAGE_HELP,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=get_submenu_keyboard(),
    )
    return WAITING_FOR_SOOS_TICKET


async def process_soos_ticket_text(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработать текст тикета, провалидировать поля и поставить задачу в очередь.

    Args:
        update: Объект обновления Telegram.
        _context: Контекст Telegram.

    Returns:
        Состояние ожидания следующего тикета.
    """
    user_id = update.effective_user.id
    if not check_if_user_legit(user_id):
        await update.message.reply_text(get_unauthorized_message(user_id))
        return ConversationHandler.END

    ticket_text = (update.message.text or "").strip()
    if not ticket_text:
        await update.message.reply_text(
            messages.MESSAGE_SUBMENU,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=get_submenu_keyboard(),
        )
        return ConversationHandler.END

    if check_if_user_has_unprocessed_job(user_id):
        await update.message.reply_text(
            messages.MESSAGE_ACTIVE_JOB_EXISTS,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=get_submenu_keyboard(),
        )
        await update.message.reply_text(
            messages.MESSAGE_SUBMENU,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=get_submenu_keyboard(),
        )
        return ConversationHandler.END

    extracted_fields = soos_parser.extract_ticket_fields(ticket_text)
    missing_fields = soos_parser.get_missing_required_fields(extracted_fields)
    if missing_fields:
        missing_fields_text = "\n".join(f"• {field}" for field in missing_fields)
        await update.message.reply_text(
            messages.MESSAGE_MISSING_FIELDS.format(fields_list=missing_fields_text),
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=get_submenu_keyboard(),
        )
        await update.message.reply_text(
            messages.MESSAGE_SUBMENU,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=get_submenu_keyboard(),
        )
        return ConversationHandler.END

    file_name = f"soos_{user_id}_{int(time.time())}.png"
    position = get_number_of_jobs_in_the_queue() + 1
    add_to_soos_queue(user_id, ticket_text, file_name)

    await update.message.reply_text(
        messages.MESSAGE_TICKET_ACCEPTED.format(position=position),
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=get_submenu_keyboard(),
    )
    await update.message.reply_text(
        messages.MESSAGE_SUBMENU,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=get_submenu_keyboard(),
    )
    return ConversationHandler.END


async def cancel_soos_module(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Завершить режим модуля СООС и вернуть пользователя в меню.

    Args:
        update: Объект обновления Telegram.
        _context: Контекст Telegram.

    Returns:
        ConversationHandler.END.
    """
    await update.message.reply_text(
        "🧾 Режим СООС завершён\.",
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=get_main_menu_keyboard(),
    )
    return ConversationHandler.END


def get_menu_button_exit_pattern() -> str:
    """
    Получить regex для кнопок, при нажатии на которые нужно выйти из СООС.

    Returns:
        Regex-паттерн.
    """
    exit_buttons = [
        BUTTON_MAIN_MENU,
        BUTTON_MODULES,
        BUTTON_SETTINGS,
        BUTTON_VALIDATE_TICKET,
        BUTTON_UPOS_ERRORS,
        BUTTON_CERTIFICATION,
        BUTTON_KTR,
        BUTTON_FEEDBACK,
        BUTTON_PROFILE,
        BUTTON_NEWS,
        BUTTON_MY_INVITES,
        BUTTON_HELP,
        BUTTON_BOT_ADMIN,
        validator_settings.BUTTON_VALIDATE_TICKET,
        validator_settings.BUTTON_ADMIN_PANEL,
        screenshot_settings.MENU_BUTTON_TEXT,
        settings.MENU_BUTTON_TEXT,
        settings.BUTTON_GENERATE_SOOS,
    ]
    escaped_buttons = [re.escape(button) for button in exit_buttons]
    return "^(" + "|".join(escaped_buttons) + ")$"
