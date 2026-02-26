"""
telegram_bot.py

Telegram-бот для сервиса обработки изображений с доступом по инвайтам.

Возможности:
- Контроль доступа через инвайты
- Приём изображений как документов (не фото)
- Ограничение: одна активная задача на пользователя
- Обратная связь по позиции в очереди
- Выдача новых инвайтов проверенным пользователям
- Хранение данных пользователей и учёт инвайтов
- Модульная архитектура для расширяемости

Команды:
    /start   - приветствие (нужен валидный инвайт)
    /invite  - список неиспользованных инвайтов пользователя

Нелегитимным пользователям предлагается ввести инвайт-код текстом.
"""
# pylint: disable=line-too-long

import logging
import re
import time
import asyncio

from telegram import Update, constants, BotCommand, ReplyKeyboardMarkup
from telegram.error import TimedOut, NetworkError, BadRequest
import httpx
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, CallbackQueryHandler, filters, ConversationHandler

import src.common.database as database
import src.common.invites as invites
import src.common.bot_settings as bot_settings
 

from src.common.constants.os import ASSETS_DIR
from src.common.constants.errorcodes import InviteStatus
from src.common.constants.telegram import TELEGRAM_TOKEN

# Общие сообщения (только глобальные/общие)
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
    BUTTON_SOOS,
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

# Импорт сообщений, настроек и клавиатур модулей
from src.sbs_helper_telegram_bot.ticket_validator import messages as validator_messages
from src.sbs_helper_telegram_bot.ticket_validator import keyboards as validator_keyboards
from src.sbs_helper_telegram_bot.ticket_validator import settings as validator_settings
from src.sbs_helper_telegram_bot.vyezd_byl import messages as image_messages
from src.sbs_helper_telegram_bot.vyezd_byl import keyboards as image_keyboards
from src.sbs_helper_telegram_bot.vyezd_byl import settings as vyezd_settings
from src.sbs_helper_telegram_bot.soos import settings as soos_settings
from src.sbs_helper_telegram_bot.upos_error import messages as upos_messages
from src.sbs_helper_telegram_bot.upos_error import keyboards as upos_keyboards
from src.sbs_helper_telegram_bot.upos_error import settings as upos_settings
from src.sbs_helper_telegram_bot.ai_router.rag_service import preload_rag_runtime_dependencies

from src.common.telegram_user import (
    check_if_user_legit,
    check_if_invite_user_blocked,
    check_if_user_admin,
    get_user_auth_status,
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
from src.sbs_helper_telegram_bot.soos.soos_bot_part import (
    enter_soos_module,
    show_soos_help,
    process_soos_ticket_text,
    cancel_soos_module,
    get_menu_button_exit_pattern as get_soos_menu_button_exit_pattern,
    WAITING_FOR_SOOS_TICKET,
)

# Импорт обработчиков валидатора заявок
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

# Импорт обработчика загрузки файлов для пакетной валидации
from src.sbs_helper_telegram_bot.ticket_validator.file_upload_bot_part import (
    get_file_validation_handler
)

# Импорт обработчиков админ-панели
from src.sbs_helper_telegram_bot.ticket_validator.admin_panel_bot_part import (
    get_admin_conversation_handler
)

# Импорт обработчиков ошибок UPOS
from src.sbs_helper_telegram_bot.upos_error.upos_error_bot_part import (
    show_popular_errors,
    get_user_conversation_handler as get_upos_user_handler,
    get_admin_conversation_handler as get_upos_admin_handler
)

# Импорт обработчиков модуля КТР
from src.sbs_helper_telegram_bot.ktr import keyboards as ktr_keyboards
from src.sbs_helper_telegram_bot.ktr import messages as ktr_messages
from src.sbs_helper_telegram_bot.ktr import settings as ktr_settings
from src.sbs_helper_telegram_bot.ktr.ktr_bot_part import (
    show_popular_codes as show_popular_ktr_codes,
    get_user_conversation_handler as get_ktr_user_handler,
    get_admin_conversation_handler as get_ktr_admin_handler
)

# Импорт обработчиков модуля аттестации
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

# Импорт обработчиков админ-модуля бота
from src.sbs_helper_telegram_bot.bot_admin.admin_bot_part import (
    get_admin_conversation_handler as get_bot_admin_handler
)

# Импорт обработчиков модуля обратной связи
from src.sbs_helper_telegram_bot.feedback import messages as feedback_messages
from src.sbs_helper_telegram_bot.feedback import keyboards as feedback_keyboards
from src.sbs_helper_telegram_bot.feedback.feedback_bot_part import (
    get_feedback_user_handler,
)
from src.sbs_helper_telegram_bot.feedback.admin_panel_bot_part import (
    get_feedback_admin_handler,
)

# Импорт обработчиков модуля геймификации
from src.sbs_helper_telegram_bot.gamification import settings as gamification_settings
from src.sbs_helper_telegram_bot.gamification import messages as gamification_messages
from src.sbs_helper_telegram_bot.gamification import keyboards as gamification_keyboards
from src.sbs_helper_telegram_bot.gamification.gamification_bot_part import (
    get_gamification_user_handler,
)
from src.sbs_helper_telegram_bot.gamification.admin_panel_bot_part import (
    get_gamification_admin_handler,
)

# Импорт обработчиков модуля новостей
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
# Импорт AI-маршрутизатора
from src.sbs_helper_telegram_bot.ai_router.intent_router import get_router as get_ai_router
from src.sbs_helper_telegram_bot.ai_router.messages import (
    MESSAGE_MODULE_DISABLED_BUTTON,
    AI_MESSAGE_KEY_PROCESSING,
    AI_MESSAGE_KEY_WAITING_FOR_AI,
    AI_PROGRESS_STAGE_RAG_PREFILTER_STARTED,
    AI_PROGRESS_STAGE_RAG_AUGMENTED_REQUEST_STARTED,
    get_ai_message_by_key,
    get_ai_progress_message,
    get_ai_status_message,
    escape_markdown_v2,
)
from src.sbs_helper_telegram_bot.ai_router.rag_admin_bot_part import (
    handle_rag_document_upload,
    handle_rag_admin_command,
)

from src.sbs_helper_telegram_bot.news.admin_panel_bot_part import (
    get_news_admin_handler,
)

from config.settings import (
    DEBUG,
    INVITES_PER_NEW_USER,
    TELEGRAM_SEND_MSG_CONNECT_TIMEOUT_SECONDS,
    TELEGRAM_SEND_MSG_READ_TIMEOUT_SECONDS,
)


logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    handlers=[logging.StreamHandler()]   # консоль
)
# Повышаем уровень логирования для httpx, чтобы не логировать все GET/POST
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

CTX_LAST_REPLY_KEYBOARD = "last_reply_keyboard"

AI_STATUS_FALLBACK_KEYS = {
    "low_confidence",
    "error",
    "circuit_open",
}


def _format_profile_steps(steps: list[tuple[str, int]]) -> str:
    """Сформировать компактную строку шагов профилирования в миллисекундах."""
    if not steps:
        return "no_steps"
    return ", ".join(f"{name}={duration_ms}ms" for name, duration_ms in steps)


def _remember_reply_keyboard(context: ContextTypes.DEFAULT_TYPE, reply_markup) -> None:
    """Сохранить последнюю показанную reply-клавиатуру пользователя."""
    if not isinstance(reply_markup, ReplyKeyboardMarkup):
        return
    if not hasattr(context, "user_data") or not isinstance(context.user_data, dict):
        return
    context.user_data[CTX_LAST_REPLY_KEYBOARD] = reply_markup


def _get_last_reply_keyboard_or_main(context: ContextTypes.DEFAULT_TYPE, is_admin: bool):
    """Вернуть последнюю сохранённую reply-клавиатуру или главное меню как fallback."""
    if hasattr(context, "user_data") and isinstance(context.user_data, dict):
        saved_keyboard = context.user_data.get(CTX_LAST_REPLY_KEYBOARD)
        if isinstance(saved_keyboard, ReplyKeyboardMarkup):
            return saved_keyboard
    return get_main_menu_keyboard(is_admin=is_admin)


async def _reply_markdown_safe(message, text: str, reply_markup) -> None:
    """
    Отправить MarkdownV2-сообщение с безопасным fallback.

    Если исходный текст содержит неэкранированные спецсимволы и Telegram
    возвращает ошибку парсинга сущностей, повторяем отправку как plain text,
    убирая MarkdownV2-экранирование.
    """
    try:
        await message.reply_text(
            text,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=reply_markup,
        )
    except BadRequest as exc:
        if "Can't parse entities" not in str(exc):
            raise

        logger.warning(
            "MarkdownV2 parse failed on reply, fallback to plain text: %s",
            exc,
        )
        # Убираем MarkdownV2-экранирование для plain-text отправки,
        # чтобы не показывать пользователю обратные слэши.
        plain_text = _strip_markdown_v2_escaping(text)
        await message.reply_text(
            plain_text,
            reply_markup=reply_markup,
        )


def _strip_markdown_v2_escaping(text: str) -> str:
    """
    Убрать MarkdownV2-экранирование из текста для plain-text отправки.

    Удаляет обратные слэши перед спецсимволами MarkdownV2, а также
    снимает форматирование (звёздочки, подчёркивания).

    Args:
        text: Текст с MarkdownV2-экранированием.

    Returns:
        Чистый текст без экранирования.
    """
    # Убираем любые последовательности обратных слэшей перед спецсимволами.
    # Это важно для кейсов, когда исходный текст уже частично экранирован,
    # а затем повторно экранирован для MarkdownV2 (например: \\\.).
    result = re.sub(r'\\+([_*\[\]()~`>#+\-=|{}.!])', r'\1', text)
    return result


def _split_markdown_v2_message(text: str, max_chunk_len: int = 3900) -> list[str]:
    """
    Разбить длинный MarkdownV2-текст на безопасные части для Telegram.

    Сплит выполняется с приоритетом переноса строки, затем пробела.
    Дополнительно не допускается завершение чанка одинарным `\\`,
    чтобы не ломать MarkdownV2-парсер Telegram.

    Args:
        text: Текст для отправки.
        max_chunk_len: Максимальная длина одной части.

    Returns:
        Список частей текста (минимум одна часть).
    """
    if len(text) <= max_chunk_len:
        return [text]

    chunks: list[str] = []
    remaining = text

    while remaining:
        if len(remaining) <= max_chunk_len:
            chunk = remaining
            remaining = ""
        else:
            chunk = remaining[:max_chunk_len]
            split_idx = chunk.rfind("\n")
            if split_idx < int(max_chunk_len * 0.5):
                split_idx = chunk.rfind(" ")
            if split_idx > 0:
                chunk = remaining[:split_idx]
                remaining = remaining[split_idx:].lstrip("\n ")
            else:
                remaining = remaining[max_chunk_len:]

        if chunk.endswith("\\") and remaining:
            chunk = chunk[:-1]
            remaining = "\\" + remaining

        if chunk:
            chunks.append(chunk)

    return chunks or [text]


async def _edit_markdown_safe(sent_message, text: str) -> None:
    """
    Отредактировать ранее отправленное сообщение с MarkdownV2 и безопасным fallback.

    Если текст содержит неэкранированные спецсимволы и Telegram
    возвращает ошибку парсинга, повторяем редактирование без форматирования
    (plain text), чтобы избежать двойного экранирования.

    Args:
        sent_message: Объект Message, который нужно отредактировать.
        text: Новый текст сообщения в формате MarkdownV2.
    """
    msg_id = getattr(sent_message, 'message_id', '?')
    chat_id = getattr(sent_message, 'chat_id',
                      getattr(getattr(sent_message, 'chat', None), 'id', '?'))
    try:
        await sent_message.edit_text(
            text,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
        )
    except BadRequest as exc:
        exc_msg = str(exc)
        if "Can't parse entities" in exc_msg:
            logger.warning(
                "MarkdownV2 parse failed on edit, fallback to plain text: %s "
                "(msg_id=%s, chat_id=%s, text_len=%d, text_preview=%.80s)",
                exc, msg_id, chat_id, len(text), repr(text[:80]),
            )
            # Убираем MarkdownV2-экранирование для plain-text отправки,
            # чтобы не показывать пользователю обратные слэши.
            plain_text = _strip_markdown_v2_escaping(text)
            await sent_message.edit_text(plain_text)
        else:
            logger.warning(
                "edit_text BadRequest (non-parse): %s (msg_id=%s, chat_id=%s, "
                "msg_date=%s, text_len=%d)",
                exc, msg_id, chat_id,
                getattr(sent_message, 'date', '?'), len(text),
            )
            raise


def clear_all_states(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Сбросить все состояния диалога всех модулей.
    
    Функция очищает ключи context.user_data, которые используют модули
    для управления состоянием диалогов. Она НЕ затрагивает данные в БД —
    только состояния в памяти.
    
    Используйте при /reset или /menu, чтобы вернуться в главное меню из
    любого зависшего состояния.
    """
    # Импорт функций очистки контекста модулей
    from src.sbs_helper_telegram_bot.certification.certification_bot_part import (
        clear_test_context,
        clear_learning_context,
    )
    from src.sbs_helper_telegram_bot.certification import settings as cert_settings
    from src.sbs_helper_telegram_bot.feedback import settings as feedback_settings
    from src.sbs_helper_telegram_bot.news import settings as news_settings
    from src.sbs_helper_telegram_bot.bot_admin import settings as admin_settings
    
    # Очищаем состояния модуля аттестации
    clear_test_context(context)
    clear_learning_context(context)
    # Очищаем состояния админ-панели аттестации
    context.user_data.pop(cert_settings.ADMIN_NEW_QUESTION_DATA_KEY, None)
    context.user_data.pop(cert_settings.ADMIN_NEW_CATEGORY_DATA_KEY, None)
    context.user_data.pop(cert_settings.ADMIN_EDITING_QUESTION_KEY, None)
    context.user_data.pop(cert_settings.ADMIN_EDITING_CATEGORY_KEY, None)
    context.user_data.pop('cert_search_mode', None)
    context.user_data.pop('cert_search_query', None)
    context.user_data.pop('editing_question_categories', None)
    context.user_data.pop('edit_field', None)
    
    # Очищаем состояния модуля обратной связи
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
    
    # Очищаем состояния валидатора заявок
    context.user_data.pop('new_rule', None)
    context.user_data.pop('test_pattern', None)
    context.user_data.pop('pending_rule_id', None)
    context.user_data.pop('new_template', None)
    context.user_data.pop('manage_type_id', None)
    context.user_data.pop('manage_template_id', None)
    
    # Очищаем состояния модуля ошибок UPOS
    context.user_data.pop('upos_temp', None)
    
    # Очищаем состояния модуля КТР
    context.user_data.pop('ktr_temp', None)
    
    # Очищаем состояния модуля новостей
    news_keys = [
        news_settings.CURRENT_PAGE_KEY,
        news_settings.SEARCH_QUERY_KEY,
        news_settings.VIEW_MODE_KEY,
        news_settings.ADMIN_DRAFT_DATA_KEY,
        news_settings.ADMIN_EDIT_FIELD_KEY,
    ]
    for key in news_keys:
        context.user_data.pop(key, None)
    
    # Очищаем состояния админ-модуля бота
    context.user_data.pop('new_preinvite', None)
    context.user_data.pop('new_manual_user', None)
    context.user_data.pop('issue_invites_user', None)
    
    # Очищаем состояния геймификации (если есть специфичные)
    # Геймификация в основном использует БД, но чистим временный контекст
    
    # Очищаем состояния модуля скриншотов/vyezd_byl (если есть)
    # Этот модуль в основном использует состояния ConversationHandler

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
            # Блокируем строку, чтобы избежать гонок
            sql_query = "SELECT consumed_userid FROM invites WHERE invite=%s FOR UPDATE"
            val=(invite,)
            cursor.execute(sql_query,val)
            result = cursor.fetchone()
            
            # Инвайт не существует
            if result is None:
                return InviteStatus.NOT_EXISTS
            
            # Инвайт уже использован
            if result["consumed_userid"] is not None:
                return InviteStatus.ALREADY_CONSUMED
            
            # Инвайт валиден и не использован — помечаем как использованный
            sql_query = "UPDATE invites SET consumed_userid=%s, consumed_timestamp=UNIX_TIMESTAMP() WHERE invite=%s"
            val=(telegram_id,invite)
            cursor.execute(sql_query,val)
            return InviteStatus.SUCCESS


async def _show_mandatory_news(update: Update, mandatory_news: dict) -> None:
    """
    Показать обязательную новость, которую нужно подтвердить перед продолжением.
    
    Args:
        update: объект Telegram Update.
        mandatory_news: словарь с данными новости из get_unacked_mandatory_news().
    """
    from datetime import datetime
    
    keyboard = news_keyboards.get_mandatory_ack_keyboard(mandatory_news['id'])
    
    # Формируем дату из published_timestamp
    published_ts = mandatory_news.get('published_timestamp')
    if published_ts:
        published_date = datetime.fromtimestamp(published_ts).strftime('%d.%m.%Y')
    else:
        published_date = ''
    
    formatted_content = news_messages.format_news_article(
        title=news_messages.escape_markdown_v2(mandatory_news['title']),
        content=mandatory_news['content'],  # Считаем, что контент уже в MarkdownV2
        category_emoji=mandatory_news.get('category_emoji', '📌'),
        category_name=news_messages.escape_markdown_v2(mandatory_news.get('category_name', '')),
        published_date=news_messages.escape_markdown_v2(published_date)
    )
    
    text = f"🚨 *ВАЖНОЕ ОБЪЯВЛЕНИЕ*\n\nПрежде чем продолжить, ознакомьтесь с обязательной новостью\\.\n\n{formatted_content}\n\nПосле прочтения нажмите кнопку «✅ Принято» внизу\\."
    
    # Отправляем с изображением, если есть
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
    
    # Отправляем вложение, если есть
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
    
    # Проверяем, является ли пользователь предварительно приглашённым и не активирован
    if invites.check_if_user_pre_invited(user_id) and not invites.is_pre_invited_user_activated(user_id):
        # Активируем предварительно приглашённого пользователя
        invites.mark_pre_invited_user_activated(user_id)
        update_user_info_from_telegram(update.effective_user)
        
        # Выдаём инвайты недавно активированному пользователю
        await update.message.reply_text(MESSAGE_WELCOME_PRE_INVITED)
        for _ in range(INVITES_PER_NEW_USER):
            invite = invites.generate_invite_for_user(user_id)
            await update.message.reply_text(MESSAGE_INVITE_ISSUED.format(invite=invite))
        
        # Показываем главное меню
        is_admin = check_if_user_admin(user_id)
        main_keyboard = get_main_menu_keyboard(is_admin=is_admin)
        _remember_reply_keyboard(_context, main_keyboard)
        await update.message.reply_text(
            get_main_menu_message(user_id, update.effective_user.first_name),
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=main_keyboard
        )
        return
    
    # Проверяем, заблокирован ли пользователь из-за выключенной системы инвайтов
    if check_if_invite_user_blocked(user_id):
        await update.message.reply_text(MESSAGE_INVITE_SYSTEM_DISABLED)
        return
    
    if not check_if_user_legit(user_id):
        await update.message.reply_text(get_unauthorized_message(user_id))
        return

    user = update.effective_user
    update_user_info_from_telegram(user)
    is_admin = check_if_user_admin(user_id)
    
    # Проверяем наличие непрочитанных обязательных новостей
    mandatory_news = get_unacked_mandatory_news(user_id)
    if mandatory_news:
        await _show_mandatory_news(update, mandatory_news)
        return

    main_keyboard = get_main_menu_keyboard(is_admin=is_admin)
    _remember_reply_keyboard(_context, main_keyboard)
    
    await update.message.reply_text(
        MESSAGE_WELCOME,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        disable_web_page_preview=True,
        reply_markup=main_keyboard
    )
    await update.message.reply_text(
        get_main_menu_message(user_id, update.effective_user.first_name),
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=main_keyboard
    )

async def invite_command(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """
        Handles the /invite command.

        Shows the user all their unused invite codes.
        If the user is not registered (has not entered an invite), replies with a prompt to do so.
    """
    user_id = update.effective_user.id
    
    # Проверяем, заблокирован ли пользователь из-за выключенной системы инвайтов
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
    
    # Проверяем, заблокирован ли пользователь из-за выключенной системы инвайтов
    if check_if_invite_user_blocked(user_id):
        await update.message.reply_text(MESSAGE_INVITE_SYSTEM_DISABLED)
        return
    
    if not check_if_user_legit(user_id):
        await update.message.reply_text(get_unauthorized_message(user_id))
        return
    
    # Очищаем состояния всех модулей
    clear_all_states(_context)
    logger.info(f"User {user_id} used /menu - cleared all conversation states")
    
    update_user_info_from_telegram(update.effective_user)
    is_admin = check_if_user_admin(user_id)
    
    # Проверяем наличие непрочитанных обязательных новостей
    mandatory_news = get_unacked_mandatory_news(user_id)
    if mandatory_news:
        await _show_mandatory_news(update, mandatory_news)
        return

    main_keyboard = get_main_menu_keyboard(is_admin=is_admin)
    _remember_reply_keyboard(_context, main_keyboard)
    
    await update.message.reply_text(
        get_main_menu_message(user_id, update.effective_user.first_name),
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=main_keyboard
    )


async def reset_command(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> int:
    """
        Handles the /reset command.

        Clears all conversation states from all modules and returns to main menu.
        This is useful when navigation buttons stop working or users get stuck.
        Returns ConversationHandler.END to terminate any active conversations.
    """
    user_id = update.effective_user.id
    
    # Проверяем, заблокирован ли пользователь из-за выключенной системы инвайтов
    if check_if_invite_user_blocked(user_id):
        await update.message.reply_text(MESSAGE_INVITE_SYSTEM_DISABLED)
        return ConversationHandler.END
    
    if not check_if_user_legit(user_id):
        await update.message.reply_text(get_unauthorized_message(user_id))
        return ConversationHandler.END
    
    # Очищаем состояния всех модулей
    clear_all_states(_context)
    logger.info(f"User {user_id} used /reset - cleared all conversation states")
    
    update_user_info_from_telegram(update.effective_user)
    is_admin = check_if_user_admin(user_id)
    
    # Проверяем наличие непрочитанных обязательных новостей
    mandatory_news = get_unacked_mandatory_news(user_id)
    if mandatory_news:
        await _show_mandatory_news(update, mandatory_news)
        return ConversationHandler.END

    main_keyboard = get_main_menu_keyboard(is_admin=is_admin)
    _remember_reply_keyboard(_context, main_keyboard)
    
    # Тихо показываем главное меню (без подтверждения)
    await update.message.reply_text(
        get_main_menu_message(user_id, update.effective_user.first_name),
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=main_keyboard
    )
    
    return ConversationHandler.END


async def help_main_command(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """
        Handles the /help command.

        Shows the main help message to authorized users.
    """
    user_id = update.effective_user.id
    
    # Проверяем, заблокирован ли пользователь из-за выключенной системы инвайтов
    if check_if_invite_user_blocked(user_id):
        await update.message.reply_text(MESSAGE_INVITE_SYSTEM_DISABLED)
        return
    
    if not check_if_user_legit(user_id):
        await update.message.reply_text(get_unauthorized_message(user_id))
        return
    
    settings_keyboard = get_settings_menu_keyboard()
    _remember_reply_keyboard(_context, settings_keyboard)
    await update.message.reply_text(
        MESSAGE_MAIN_HELP,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=settings_keyboard
    )


async def text_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
        Handles incoming text messages.

        - If the user is pre-invited but not yet activated, activates them and welcomes them.
        - If the user is not yet authorized, checks whether the message contains a valid invite code.
        On success: registers the user, issues a number of invite codes
        and sends a welcome message.
        - If the user is blocked due to invite system being disabled, shows appropriate message.
        - If the user is already authorized, handles menu button presses or sends the standard welcome message.
    """
    profile_started_at = time.perf_counter()
    last_step_at = profile_started_at
    profile_steps: list[tuple[str, int]] = []
    profile_result = "unknown"
    profile_user_id = getattr(getattr(update, "effective_user", None), "id", "unknown")

    def mark_step(
        step_name: str,
        duration_ms: int | None = None,
        reset_marker: bool = True,
    ) -> None:
        """Зафиксировать длительность шага с прошлого маркера."""
        nonlocal last_step_at
        now = time.perf_counter()
        if duration_ms is None:
            step_duration_ms = int((now - last_step_at) * 1000)
        else:
            step_duration_ms = int(duration_ms)
        profile_steps.append((step_name, max(step_duration_ms, 0)))
        if reset_marker:
            last_step_at = now

    try:
        # Проверяем, что сообщение существует и содержит текст
        if not update.message or not update.message.text:
            logger.warning("Received update without message or text")
            profile_result = "ignored_empty_update"
            return

        text = update.message.text
        user_id = update.effective_user.id
        profile_user_id = user_id
        mark_step("parse_message")

        # Единая проверка авторизации (одно подключение к БД вместо 6-9)
        auth = get_user_auth_status(user_id)
        mark_step("check_pre_invited")
        if auth.is_pre_invited and not auth.is_pre_invited_activated:
            # Активируем предварительно приглашённого пользователя
            invites.mark_pre_invited_user_activated(user_id)
            update_user_info_from_telegram(update.effective_user)
            mark_step("activate_pre_invited")

            # Выдаём инвайты недавно активированному пользователю
            await update.message.reply_text(MESSAGE_WELCOME_PRE_INVITED)
            for _ in range(INVITES_PER_NEW_USER):
                invite = invites.generate_invite_for_user(user_id)
                await update.message.reply_text(MESSAGE_INVITE_ISSUED.format(invite=invite))
            mark_step("send_pre_invited_welcome")

            # Показываем главное меню
            is_admin = auth.is_admin
            await update.message.reply_text(
                get_main_menu_message(user_id, update.effective_user.first_name),
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=get_main_menu_keyboard(is_admin=is_admin)
            )
            mark_step("send_main_menu")
            profile_result = "pre_invited_activated"
            return

        # Проверяем, заблокирован ли пользователь из-за выключенной системы инвайтов
        if auth.is_invite_blocked:
            mark_step("check_invite_blocked")
            await update.message.reply_text(MESSAGE_INVITE_SYSTEM_DISABLED)
            mark_step("send_invite_disabled")
            profile_result = "invite_system_disabled"
            return
        mark_step("check_invite_blocked")

        is_legit_user = auth.is_legit
        mark_step("check_legit_user")
        if not is_legit_user:
            invite_status = check_if_invite_entered(user_id, text)
            mark_step("check_invite_code")
            if invite_status == InviteStatus.SUCCESS:
                update_user_info_from_telegram(update.effective_user)
                await update.message.reply_text(MESSAGE_WELCOME_SHORT)
                for _ in range(INVITES_PER_NEW_USER):
                    invite = invites.generate_invite_for_user(user_id)
                    await update.message.reply_text(MESSAGE_INVITE_ISSUED.format(invite=invite))
                mark_step("send_registration_welcome")
                # Показываем главное меню после успешной регистрации
                is_admin = auth.is_admin
                await update.message.reply_text(
                    get_main_menu_message(user_id, update.effective_user.first_name),
                    parse_mode=constants.ParseMode.MARKDOWN_V2,
                    reply_markup=get_main_menu_keyboard(is_admin=is_admin)
                )
                mark_step("send_main_menu")
                profile_result = "authorized_by_invite"
            elif invite_status == InviteStatus.NOT_EXISTS:
                await update.message.reply_text(get_unauthorized_message(user_id))
                mark_step("send_unauthorized")
                profile_result = "invite_not_found"
                return
            else:
                await update.message.reply_text(MESSAGE_INVITE_ALREADY_USED)
                mark_step("send_invite_already_used")
                profile_result = "invite_already_used"
                return
            return

        # Обрабатываем нажатия кнопок меню для авторизованных пользователей
        is_admin = auth.is_admin
        mark_step("check_admin")

        # Очищаем AI-контекст при навигации по меню (не для произвольного текста)
        if text in (BUTTON_MAIN_MENU, BUTTON_MODULES, BUTTON_SETTINGS, BUTTON_VALIDATE_TICKET,
                    BUTTON_UPOS_ERRORS, BUTTON_CERTIFICATION, BUTTON_KTR, BUTTON_FEEDBACK,
                BUTTON_PROFILE, BUTTON_NEWS, BUTTON_SCREENSHOT, BUTTON_SOOS, BUTTON_BOT_ADMIN,
                    BUTTON_MY_INVITES, BUTTON_HELP):
            ai_router = get_ai_router()
            ai_router.clear_context(user_id)
            mark_step("clear_ai_context")

        if text == BUTTON_MAIN_MENU:
            main_menu_started_at = time.perf_counter()
            main_menu_message = get_main_menu_message(user_id, update.effective_user.first_name)
            main_menu_keyboard = get_main_menu_keyboard(is_admin=is_admin)
            _remember_reply_keyboard(context, main_menu_keyboard)
            mark_step("main_menu_build")

            await update.message.reply_text(
                main_menu_message,
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=main_menu_keyboard
            )
            mark_step("telegram_send_main_menu")
            mark_step(
                "reply_main_menu",
                duration_ms=int((time.perf_counter() - main_menu_started_at) * 1000),
                reset_marker=False,
            )
            profile_result = "main_menu"
        elif text == BUTTON_MODULES:
            # Показываем меню модулей
            modules_keyboard = get_modules_menu_keyboard()
            _remember_reply_keyboard(context, modules_keyboard)
            await update.message.reply_text(
                MESSAGE_MODULES_MENU,
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=modules_keyboard
            )
            mark_step("reply_modules_menu")
            profile_result = "modules_menu"
        elif text == BUTTON_SETTINGS:
            # Показываем меню настроек
            settings_keyboard = get_settings_menu_keyboard()
            _remember_reply_keyboard(context, settings_keyboard)
            await update.message.reply_text(
                MESSAGE_SETTINGS_MENU,
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=settings_keyboard
            )
            mark_step("reply_settings_menu")
            profile_result = "settings_menu"
        elif text == BUTTON_VALIDATE_TICKET:
            # Показываем подменю валидации (с админ-панелью для админа)
            if not bot_settings.is_module_enabled('ticket_validator'):
                main_keyboard = get_main_menu_keyboard(is_admin=is_admin)
                _remember_reply_keyboard(context, main_keyboard)
                await update.message.reply_text(MESSAGE_MODULE_DISABLED_BUTTON, parse_mode=constants.ParseMode.MARKDOWN_V2, reply_markup=main_keyboard)
                mark_step("reply_module_disabled_ticket_validator")
                profile_result = "ticket_validator_disabled"
                return
            if is_admin:
                keyboard = validator_keyboards.get_admin_submenu_keyboard()
            else:
                keyboard = validator_keyboards.get_submenu_keyboard()
            _remember_reply_keyboard(context, keyboard)
            await update.message.reply_text(
                validator_messages.get_submenu_message(),
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=keyboard
            )
            mark_step("reply_ticket_validator_submenu")
            profile_result = "ticket_validator_submenu"
        elif text == validator_settings.BUTTON_VALIDATE_TICKET:
            await validate_ticket_command(update, context)
            mark_step("run_validate_ticket_command")
            profile_result = "validate_ticket_command"
        elif text == validator_settings.BUTTON_TEST_TEMPLATES:
            # Кнопка быстрого доступа к тестовым шаблонам (только админ)
            await run_test_templates_command(update, context)
            mark_step("run_test_templates_command")
            profile_result = "test_templates_command"
        elif text == validator_settings.BUTTON_HELP_VALIDATION:
            await help_command(update, context)
            mark_step("run_help_validation")
            profile_result = "help_validation"
        elif text == BUTTON_MY_INVITES:
            await invite_command(update, context)
            mark_step("run_invite_command")
            profile_result = "my_invites"
        elif text == BUTTON_HELP:
            settings_keyboard = get_settings_menu_keyboard()
            _remember_reply_keyboard(context, settings_keyboard)
            await update.message.reply_text(
                MESSAGE_MAIN_HELP,
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=settings_keyboard
            )
            mark_step("reply_main_help")
            profile_result = "help"
        elif text == BUTTON_SCREENSHOT or text == vyezd_settings.BUTTON_SEND_SCREENSHOT:
            # Эти кнопки обрабатываются ConversationHandler модуля скриншотов
            # Фолбэк на всякий случай: обычно ConversationHandler их перехватывает
            if not bot_settings.is_module_enabled('screenshot'):
                main_keyboard = get_main_menu_keyboard(is_admin=is_admin)
                _remember_reply_keyboard(context, main_keyboard)
                await update.message.reply_text(MESSAGE_MODULE_DISABLED_BUTTON, parse_mode=constants.ParseMode.MARKDOWN_V2, reply_markup=main_keyboard)
                mark_step("reply_module_disabled_screenshot")
                profile_result = "screenshot_disabled"
                return
            result = await enter_screenshot_module(update, context)
            mark_step("enter_screenshot_module")
            profile_result = "screenshot_module"
            return result
        elif text == vyezd_settings.BUTTON_SCREENSHOT_HELP:
            screenshot_keyboard = image_keyboards.get_submenu_keyboard()
            _remember_reply_keyboard(context, screenshot_keyboard)
            await update.message.reply_photo(
                ASSETS_DIR / "promo3.jpg",
                caption=image_messages.MESSAGE_INSTRUCTIONS,
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=screenshot_keyboard
            )
            mark_step("reply_screenshot_help")
            profile_result = "screenshot_help"
        elif text == BUTTON_SOOS or text == soos_settings.BUTTON_GENERATE_SOOS:
            if not bot_settings.is_module_enabled('soos'):
                main_keyboard = get_main_menu_keyboard(is_admin=is_admin)
                _remember_reply_keyboard(context, main_keyboard)
                await update.message.reply_text(MESSAGE_MODULE_DISABLED_BUTTON, parse_mode=constants.ParseMode.MARKDOWN_V2, reply_markup=main_keyboard)
                mark_step("reply_module_disabled_soos")
                profile_result = "soos_disabled"
                return
            result = await enter_soos_module(update, context)
            mark_step("enter_soos_module")
            profile_result = "soos_module"
            return result
        elif text == soos_settings.BUTTON_SOOS_HELP:
            result = await show_soos_help(update, context)
            mark_step("reply_soos_help")
            profile_result = "soos_help"
            return result
        elif text == validator_settings.BUTTON_ADMIN_PANEL:
            # Показываем админ-панель, если пользователь — админ
            if is_admin:
                admin_keyboard = validator_keyboards.get_admin_menu_keyboard()
                _remember_reply_keyboard(context, admin_keyboard)
                await update.message.reply_text(
                    validator_messages.MESSAGE_ADMIN_MENU,
                    parse_mode=constants.ParseMode.MARKDOWN_V2,
                    reply_markup=admin_keyboard
                )
                mark_step("reply_validator_admin_menu")
                profile_result = "validator_admin_menu"
            else:
                main_keyboard = get_main_menu_keyboard(is_admin=is_admin)
                _remember_reply_keyboard(context, main_keyboard)
                await update.message.reply_text(
                    MESSAGE_NO_ADMIN_RIGHTS,
                    parse_mode=constants.ParseMode.MARKDOWN_V2,
                    reply_markup=main_keyboard
                )
                mark_step("reply_no_admin_rights")
                profile_result = "no_admin_rights"
        elif text == BUTTON_BOT_ADMIN:
            # Показываем админ-панель бота для админа — входная точка в ConversationHandler
            # Фолбэк на случай, если обработчик не поймал
            if not is_admin:
                main_keyboard = get_main_menu_keyboard(is_admin=is_admin)
                _remember_reply_keyboard(context, main_keyboard)
                await update.message.reply_text(
                    MESSAGE_NO_ADMIN_RIGHTS,
                    parse_mode=constants.ParseMode.MARKDOWN_V2,
                    reply_markup=main_keyboard
                )
                mark_step("reply_no_admin_rights")
                profile_result = "no_admin_rights"
            else:
                profile_result = "bot_admin_handler"
        elif text == BUTTON_UPOS_ERRORS:
            # Показываем подменю модуля ошибок UPOS
            if not bot_settings.is_module_enabled('upos_errors'):
                main_keyboard = get_main_menu_keyboard(is_admin=is_admin)
                _remember_reply_keyboard(context, main_keyboard)
                await update.message.reply_text(MESSAGE_MODULE_DISABLED_BUTTON, parse_mode=constants.ParseMode.MARKDOWN_V2, reply_markup=main_keyboard)
                mark_step("reply_module_disabled_upos")
                profile_result = "upos_disabled"
                return
            if is_admin:
                keyboard = upos_keyboards.get_admin_submenu_keyboard()
            else:
                keyboard = upos_keyboards.get_submenu_keyboard()
            _remember_reply_keyboard(context, keyboard)
            await update.message.reply_text(
                upos_messages.get_submenu_message(),
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=keyboard
            )
            mark_step("reply_upos_submenu")
            profile_result = "upos_submenu"
        elif text == upos_settings.BUTTON_POPULAR_ERRORS:
            await show_popular_errors(update, context)
            mark_step("run_upos_popular_errors")
            profile_result = "upos_popular_errors"
        elif text == BUTTON_CERTIFICATION:
            # Показываем подменю аттестации (делегируем обработчику модуля)
            if not bot_settings.is_module_enabled('certification'):
                main_keyboard = get_main_menu_keyboard(is_admin=is_admin)
                _remember_reply_keyboard(context, main_keyboard)
                await update.message.reply_text(MESSAGE_MODULE_DISABLED_BUTTON, parse_mode=constants.ParseMode.MARKDOWN_V2, reply_markup=main_keyboard)
                mark_step("reply_module_disabled_certification")
                profile_result = "certification_disabled"
                return
            await enter_certification_module(update, context)
            mark_step("enter_certification_module")
            profile_result = "certification_submenu"
        elif text == certification_settings.BUTTON_MY_RANKING:
            await show_my_ranking(update, context)
            mark_step("run_certification_my_ranking")
            profile_result = "certification_my_ranking"
        elif text == certification_settings.BUTTON_TEST_HISTORY:
            await show_test_history(update, context)
            mark_step("run_certification_test_history")
            profile_result = "certification_test_history"
        elif text == certification_settings.BUTTON_MONTHLY_TOP:
            await show_monthly_top(update, context)
            mark_step("run_certification_monthly_top")
            profile_result = "certification_monthly_top"
        elif text == BUTTON_KTR:
            # Показываем подменю модуля КТР
            if not bot_settings.is_module_enabled('ktr'):
                main_keyboard = get_main_menu_keyboard(is_admin=is_admin)
                _remember_reply_keyboard(context, main_keyboard)
                await update.message.reply_text(MESSAGE_MODULE_DISABLED_BUTTON, parse_mode=constants.ParseMode.MARKDOWN_V2, reply_markup=main_keyboard)
                mark_step("reply_module_disabled_ktr")
                profile_result = "ktr_disabled"
                return
            if is_admin:
                keyboard = ktr_keyboards.get_admin_submenu_keyboard()
            else:
                keyboard = ktr_keyboards.get_submenu_keyboard()
            _remember_reply_keyboard(context, keyboard)
            await update.message.reply_text(
                ktr_messages.get_submenu_message(),
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=keyboard
            )
            mark_step("reply_ktr_submenu")
            profile_result = "ktr_submenu"
        elif text == ktr_settings.BUTTON_POPULAR_CODES:
            await show_popular_ktr_codes(update, context)
            mark_step("run_ktr_popular_codes")
            profile_result = "ktr_popular_codes"
        elif text == ktr_settings.BUTTON_ACHIEVEMENTS:
            # Показываем достижения КТР (обрабатывает модуль КТР)
            from src.sbs_helper_telegram_bot.ktr.ktr_bot_part import show_ktr_achievements
            await show_ktr_achievements(update, context)
            mark_step("run_ktr_achievements")
            profile_result = "ktr_achievements"
        elif text == BUTTON_FEEDBACK:
            # Показываем подменю обратной связи
            if not bot_settings.is_module_enabled('feedback'):
                main_keyboard = get_main_menu_keyboard(is_admin=is_admin)
                _remember_reply_keyboard(context, main_keyboard)
                await update.message.reply_text(MESSAGE_MODULE_DISABLED_BUTTON, parse_mode=constants.ParseMode.MARKDOWN_V2, reply_markup=main_keyboard)
                mark_step("reply_module_disabled_feedback")
                profile_result = "feedback_disabled"
                return
            if is_admin:
                keyboard = feedback_keyboards.get_submenu_keyboard(is_admin=True)
            else:
                keyboard = feedback_keyboards.get_submenu_keyboard(is_admin=False)
            _remember_reply_keyboard(context, keyboard)
            await update.message.reply_text(
                feedback_messages.MESSAGE_SUBMENU,
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=keyboard
            )
            mark_step("reply_feedback_submenu")
            profile_result = "feedback_submenu"
        elif text == BUTTON_PROFILE:
            # Показываем подменю профиля геймификации
            if is_admin:
                keyboard = gamification_keyboards.get_admin_submenu_keyboard()
            else:
                keyboard = gamification_keyboards.get_submenu_keyboard()
            _remember_reply_keyboard(context, keyboard)
            # Убеждаемся, что у пользователя есть запись итогов
            from src.sbs_helper_telegram_bot.gamification.gamification_logic import ensure_user_totals_exist
            ensure_user_totals_exist(user_id)
            await update.message.reply_text(
                gamification_messages.MESSAGE_SUBMENU,
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=keyboard
            )
            mark_step("reply_profile_submenu")
            profile_result = "profile_submenu"
        elif text == BUTTON_NEWS or text.startswith("📰 Новости"):
            # Показываем подменю новостей (с индикатором непрочитанных)
            if not bot_settings.is_module_enabled('news'):
                main_keyboard = get_main_menu_keyboard(is_admin=is_admin)
                _remember_reply_keyboard(context, main_keyboard)
                await update.message.reply_text(MESSAGE_MODULE_DISABLED_BUTTON, parse_mode=constants.ParseMode.MARKDOWN_V2, reply_markup=main_keyboard)
                mark_step("reply_module_disabled_news")
                profile_result = "news_disabled"
                return
            # Помечаем все новости прочитанными при входе
            from src.sbs_helper_telegram_bot.news import news_logic
            news_logic.mark_all_as_read(user_id)

            if is_admin:
                keyboard = news_keyboards.get_submenu_keyboard(is_admin=True)
            else:
                keyboard = news_keyboards.get_submenu_keyboard(is_admin=False)
            _remember_reply_keyboard(context, keyboard)
            await update.message.reply_text(
                news_messages.MESSAGE_SUBMENU,
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=keyboard
            )
            mark_step("reply_news_submenu")
            profile_result = "news_submenu"
        else:
            # AI-маршрутизация: пробуем классифицировать произвольный текст
            ai_router = get_ai_router()
            placeholder_started_at = time.perf_counter()

            # Показываем индикатор набора текста и плейсхолдер пока AI обрабатывает
            # это действие практически сразу же обнуляется последующим сообщением
            # с плейсхолдером, но оставляем на всякий для лучшей UX в случае задержек
            chat_action_started_at = time.perf_counter()
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id,
                action=constants.ChatAction.TYPING,
            )
            chat_action_ms = int((time.perf_counter() - chat_action_started_at) * 1000)
            mark_step("ai_chat_action", duration_ms=chat_action_ms, reset_marker=False)

            main_menu_keyboard = get_main_menu_keyboard(is_admin=is_admin)
            logger.info(
                "AI placeholder strategy: send without reply_markup for editability "
                "(keyboard_type=%s, is_admin=%s)",
                type(main_menu_keyboard).__name__ if main_menu_keyboard is not None else "None",
                is_admin,
            )
            if isinstance(main_menu_keyboard, ReplyKeyboardMarkup):
                logger.info(
                    "AI placeholder uses deferred keyboard: ReplyKeyboardMarkup can lead to "
                    "'Message can't be edited' on edit_text in Telegram API"
                )

            placeholder_reply_started_at = time.perf_counter()
            placeholder = await update.message.reply_text(
                get_ai_message_by_key(AI_MESSAGE_KEY_PROCESSING),
                parse_mode=constants.ParseMode.MARKDOWN_V2,
            )
            placeholder_reply_ms = int((time.perf_counter() - placeholder_reply_started_at) * 1000)
            mark_step("ai_placeholder_reply", duration_ms=placeholder_reply_ms, reset_marker=False)
            placeholder_total_ms = int((time.perf_counter() - placeholder_started_at) * 1000)
            logger.info(
                "AI placeholder profiling: user_id=%s total_ms=%s chat_action_ms=%s "
                "placeholder_reply_ms=%s",
                user_id,
                placeholder_total_ms,
                chat_action_ms,
                placeholder_reply_ms,
            )
            mark_step("ai_placeholder_sent")

            classified_intent = None

            async def _on_ai_classified(classification) -> None:
                """Обновить плейсхолдер, когда запрос распознан как RAG."""
                nonlocal classified_intent
                classified_intent = getattr(classification, "intent", "")
                if getattr(classification, "intent", "") != "rag_qa":
                    return
                try:
                    await _edit_markdown_safe(
                        placeholder,
                        get_ai_message_by_key(AI_MESSAGE_KEY_WAITING_FOR_AI),
                    )
                except Exception as rag_placeholder_exc:
                    logger.warning(
                        "Failed to switch AI placeholder to RAG waiting state: %s",
                        rag_placeholder_exc,
                    )

            async def _on_ai_progress(stage: str, payload=None) -> None:
                """Обновить плейсхолдер по этапам прогресса RAG."""
                if stage not in {
                    AI_PROGRESS_STAGE_RAG_PREFILTER_STARTED,
                    AI_PROGRESS_STAGE_RAG_AUGMENTED_REQUEST_STARTED,
                }:
                    return

                stage_message = get_ai_progress_message(stage)
                if not stage_message:
                    return

                try:
                    await _edit_markdown_safe(placeholder, stage_message)
                except Exception as progress_placeholder_exc:
                    logger.warning(
                        "Failed to update AI placeholder by progress stage: stage=%s payload=%s error=%s",
                        stage,
                        payload,
                        progress_placeholder_exc,
                    )

            try:
                response, status = await ai_router.route(
                    text,
                    user_id,
                    on_classified=_on_ai_classified,
                    on_progress=_on_ai_progress,
                )
            except Exception as ai_exc:
                logger.error("AI router exception: user=%s, error=%s", user_id, ai_exc)
                response, status = None, "error"
            mark_step("ai_route")

            if response and status in ("routed", "chat", "rate_limited", "module_disabled"):
                restore_keyboard = _get_last_reply_keyboard_or_main(context, is_admin)
                is_rag_response = classified_intent == "rag_qa"
                response_chunks = (
                    _split_markdown_v2_message(response)
                    if is_rag_response
                    else [response]
                )
                try:
                    await _edit_markdown_safe(placeholder, response_chunks[0])
                    for chunk in response_chunks[1:]:
                        await _reply_markdown_safe(update.message, chunk, None)
                    try:
                        await update.message.reply_text(
                            "Выберите действие из меню или введите произвольный запрос:",
                            reply_markup=restore_keyboard,
                        )
                    except Exception as keyboard_exc:
                        logger.warning("Failed to restore previous keyboard after AI reply: %s", keyboard_exc)
                except Exception as edit_exc:
                    logger.warning(
                        "Failed to edit AI placeholder, sending new message: %s "
                        "(type=%s, placeholder_msg_id=%s, chat_id=%s, "
                        "placeholder_date=%s, response_len=%d, response_preview=%.80s)",
                        edit_exc,
                        type(edit_exc).__name__,
                        getattr(placeholder, 'message_id', '?'),
                        getattr(placeholder, 'chat_id',
                                getattr(getattr(placeholder, 'chat', None), 'id', '?')),
                        getattr(placeholder, 'date', '?'),
                        len(response) if response else 0,
                        repr(response[:80]) if response else 'None',
                    )
                    try:
                        await placeholder.delete()
                    except Exception:
                        pass
                    await _reply_markdown_safe(
                        update.message,
                        response_chunks[0],
                        restore_keyboard,
                    )
                    for chunk in response_chunks[1:]:
                        await _reply_markdown_safe(update.message, chunk, None)
                mark_step("reply_ai_response")
                profile_result = f"ai_{status}"
            else:
                # Ответ по статусу AI (или дефолт для нераспознанного текста)
                restore_keyboard = _get_last_reply_keyboard_or_main(context, is_admin)
                fallback_message = get_ai_status_message(status)
                if fallback_message is None:
                    fallback_message = MESSAGE_UNRECOGNIZED_INPUT
                try:
                    await _edit_markdown_safe(placeholder, fallback_message)
                    try:
                        await update.message.reply_text(
                            "Выберите действие из меню или введите произвольный запрос:",
                            reply_markup=restore_keyboard,
                        )
                    except Exception as keyboard_exc:
                        logger.warning("Failed to restore previous keyboard after unrecognized input: %s", keyboard_exc)
                except Exception as edit_exc:
                    logger.warning(
                        "Failed to edit AI placeholder for unrecognized input: %s "
                        "(type=%s, placeholder_msg_id=%s, chat_id=%s)",
                        edit_exc,
                        type(edit_exc).__name__,
                        getattr(placeholder, 'message_id', '?'),
                        getattr(placeholder, 'chat_id',
                                getattr(getattr(placeholder, 'chat', None), 'id', '?')),
                    )
                    try:
                        await placeholder.delete()
                    except Exception:
                        pass
                    await update.message.reply_text(
                        fallback_message,
                        parse_mode=constants.ParseMode.MARKDOWN_V2,
                        reply_markup=restore_keyboard,
                    )
                mark_step("reply_unrecognized_input")
                profile_result = f"ai_{status}" if status in AI_STATUS_FALLBACK_KEYS else "unrecognized_input"
    finally:
        total_ms = int((time.perf_counter() - profile_started_at) * 1000)
        logger.info(
            "Update profiling: user_id=%s result=%s total_ms=%s steps=[%s]",
            profile_user_id,
            profile_result,
            total_ms,
            _format_profile_steps(profile_steps),
        )



async def post_init(application: Application) -> None:
    """
        Post-initialization setup after bot starts.
        
        Sets up bot command menu that appears in Telegram UI.
        Only core bot commands are shown here - module-specific commands
        are still functional but not listed in the menu to keep it clean.
    """
    # Устанавливаем команды бота для меню в Telegram
    # Показываем только базовые команды — модульные работают, но не отображаются
    await application.bot.set_my_commands([
        BotCommand("start", COMMAND_DESC_START),
        BotCommand("menu", COMMAND_DESC_MENU),
        BotCommand("reset", "Сбросить состояние и вернуться в главное меню"),
        BotCommand("help", COMMAND_DESC_HELP),
    ])

    await asyncio.to_thread(preload_rag_runtime_dependencies)


def main() -> None:

    """
        Точка входа Telegram-бота.

        Создаёт и настраивает Application через python-telegram-bot,
        регистрирует обработчики команд и сообщений, настраивает меню бота
        и запускает polling.

        Зарегистрированные обработчики:
            /start          → start
            /menu           → menu_command
            /invite         → invite_command
            /debug          → toggle_debug_mode (только админы)
            /admin          → админ-панель (только админы)
            Документы-изображения → handle_incoming_document
            Обычный текст   → text_entered (также обрабатывает кнопки меню)

        Работает непрерывно, обрабатывая все типы обновлений.
    """

    application = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .post_init(post_init)
        .read_timeout(TELEGRAM_SEND_MSG_READ_TIMEOUT_SECONDS)
        .write_timeout(TELEGRAM_SEND_MSG_READ_TIMEOUT_SECONDS)
        .connect_timeout(TELEGRAM_SEND_MSG_CONNECT_TIMEOUT_SECONDS)
        .build()
    )

    # Создаём ConversationHandler для проверки заявок
    # Входная точка: кнопка меню
    # Фолбэки: /cancel, любая команда и кнопки меню модуля валидатора
    menu_button_pattern = get_menu_button_regex_pattern()
    # Исключаем кнопки меню из WAITING_FOR_TICKET, чтобы они попадали в фолбэки
    menu_button_filter = filters.Regex(menu_button_pattern)
    ticket_validator_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(f"^{re.escape(validator_settings.BUTTON_VALIDATE_TICKET)}$"), validate_ticket_command)
        ],
        states={
            WAITING_FOR_TICKET: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_button_filter, process_ticket_text)]
        },
        fallbacks=[
            CommandHandler("cancel", cancel_validation),
            CommandHandler("reset", reset_command),
            CommandHandler("menu", menu_command),
            # Любая другая команда отменяет режим валидации
            MessageHandler(filters.COMMAND, cancel_validation_on_menu),
            # Кнопки меню ticket_validator отменяют режим валидации
            MessageHandler(menu_button_filter, cancel_validation_on_menu)
        ]
    )

    # Создаём ConversationHandler для админ-панели
    admin_handler = get_admin_conversation_handler()

    # Создаём ConversationHandlers для модуля ошибок UPOS
    upos_user_handler = get_upos_user_handler()
    upos_admin_handler = get_upos_admin_handler()

    # Создаём ConversationHandler для модуля обработки скриншотов
    screenshot_exit_pattern = get_menu_button_exit_pattern()
    screenshot_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(f"^{re.escape(vyezd_settings.MENU_BUTTON_TEXT)}$"), enter_screenshot_module),
            MessageHandler(filters.Regex(f"^{re.escape(vyezd_settings.BUTTON_SEND_SCREENSHOT)}$"), enter_screenshot_module)
        ],
        states={
            WAITING_FOR_SCREENSHOT: [
                MessageHandler(filters.Document.IMAGE, handle_incoming_document),
                # Кнопка помощи показывает справку с фото
                MessageHandler(filters.Regex(f"^{re.escape(vyezd_settings.BUTTON_SCREENSHOT_HELP)}$"), show_screenshot_help),
                # Кнопки меню, которые должны выходить из модуля (до общего текстового обработчика)
                MessageHandler(filters.Regex(screenshot_exit_pattern), cancel_screenshot_module),
                # Обработка неверного ввода: фото вместо документа или текст
                MessageHandler(filters.PHOTO, handle_wrong_input_in_screenshot_mode),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_wrong_input_in_screenshot_mode),
            ]
        },
        fallbacks=[
            CommandHandler("reset", reset_command),
            CommandHandler("menu", menu_command),
            # Любая команда выходит из модуля
            MessageHandler(filters.COMMAND, cancel_screenshot_module),
        ]
    )

    soos_exit_pattern = get_soos_menu_button_exit_pattern()
    soos_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(f"^{re.escape(soos_settings.MENU_BUTTON_TEXT)}$"), enter_soos_module),
            MessageHandler(filters.Regex(f"^{re.escape(soos_settings.BUTTON_GENERATE_SOOS)}$"), enter_soos_module),
        ],
        states={
            WAITING_FOR_SOOS_TICKET: [
                MessageHandler(filters.Regex(f"^{re.escape(soos_settings.BUTTON_SOOS_HELP)}$"), show_soos_help),
                MessageHandler(filters.Regex(soos_exit_pattern), cancel_soos_module),
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_soos_ticket_text),
            ]
        },
        fallbacks=[
            CommandHandler("reset", reset_command),
            CommandHandler("menu", menu_command),
            MessageHandler(filters.COMMAND, cancel_soos_module),
        ],
    )

    # Создаём ConversationHandlers для модуля аттестации
    certification_user_handler = get_certification_user_handler()
    certification_admin_handler = get_certification_admin_handler()

    # Создаём ConversationHandlers для модуля КТР
    ktr_user_handler = get_ktr_user_handler()
    ktr_admin_handler = get_ktr_admin_handler()

    # Создаём ConversationHandler для основной админ-панели бота
    bot_admin_handler = get_bot_admin_handler()

    # Создаём ConversationHandlers для модуля обратной связи
    feedback_user_handler = get_feedback_user_handler()
    feedback_admin_handler = get_feedback_admin_handler()

    # Создаём ConversationHandlers для модуля геймификации
    gamification_user_handler = get_gamification_user_handler()
    gamification_admin_handler = get_gamification_admin_handler()

    # Создаём ConversationHandlers для модуля новостей
    news_user_handler = get_news_user_handler()
    news_admin_handler = get_news_admin_handler()
    news_mandatory_ack_handler = get_mandatory_ack_handler()

    # Регистрируем все обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("reset", reset_command))
    application.add_handler(CommandHandler("help", help_main_command))
    application.add_handler(CommandHandler("invite", invite_command))
    application.add_handler(CommandHandler("debug", toggle_debug_mode))
    application.add_handler(bot_admin_handler)  # Основная админ-панель (до админов модулей)
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
    application.add_handler(news_mandatory_ack_handler)  # Глобальный обработчик обязательных новостей
    application.add_handler(screenshot_handler)
    application.add_handler(soos_handler)
    
    # Админ-загрузка документов в RAG по подписи #rag
    application.add_handler(
        MessageHandler(
            filters.Document.ALL & filters.CaptionRegex(r"(?i)^#rag\b"),
            handle_rag_document_upload,
        )
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.Regex(r"(?i)^#rag(\s|$)"),
            handle_rag_admin_command,
        )
    )

    # Создаём ConversationHandler для проверки загружаемых файлов
    file_validation_handler = get_file_validation_handler()
    application.add_handler(file_validation_handler)
    
    application.add_handler(ticket_validator_handler)
    application.add_handler(MessageHandler(filters.PHOTO | filters.TEXT & ~filters.COMMAND, text_entered))
    
    # Добавляем обработчик ошибок
    application.add_error_handler(error_handler)
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)


async def _answer_callback_silent(update: object, text: str) -> None:
    """
    Пробует ответить на callback-запрос всплывающим уведомлением.
    Ошибки при ответе не пробрасываются, чтобы не зациклить обработку.
    """
    try:
        if isinstance(update, Update) and update.callback_query:
            await update.callback_query.answer(text=text, show_alert=True)
    except Exception:  # pylint: disable=broad-except
        pass


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик ошибок во время работы бота.

    При сетевых ошибках (ConnectError, RemoteProtocolError, NetworkError, TimedOut),
    возникших при нажатии кнопки меню, уведомляет пользователя всплывающим
    сообщением, чтобы он знал, что запрос не прошёл и нужно повторить.
    Остальные ошибки логируются.
    """
    error = context.error

    # httpx-ошибки низкого уровня (ConnectError, RemoteProtocolError и др.)
    # оборачиваются python-telegram-bot в NetworkError, но иногда могут
    # всплыть напрямую — обрабатываем оба варианта.
    is_network_issue = isinstance(error, (NetworkError, TimedOut)) or isinstance(
        error, (httpx.ConnectError, httpx.RemoteProtocolError, httpx.ReadError, httpx.WriteError)
    )

    if is_network_issue:
        logger.warning(f"Network error occurred: {error}")
        await _answer_callback_silent(
            update,
            "Нет связи с сервером. Проверьте интернет и нажмите кнопку ещё раз.",
        )
        return

    # Обрабатываем BadRequest с "Message is not modified" — часто и безвредно
    if isinstance(error, BadRequest):
        if "Message is not modified" in str(error):
            # Тихо игнорируем эту ошибку — она безвредна
            return
        logger.warning(f"BadRequest error: {error}")
        return

    # Логируем остальные ошибки
    logger.error(f"Exception while handling an update: {error}", exc_info=context.error)


if __name__ == "__main__":
    main()
