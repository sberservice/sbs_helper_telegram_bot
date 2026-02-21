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

from telegram import Update, constants, BotCommand
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
    escape_markdown_v2,
)

from src.sbs_helper_telegram_bot.news.admin_panel_bot_part import (
    get_news_admin_handler,
)

from src.common.telegram_user import check_if_user_admin

from config.settings import DEBUG, INVITES_PER_NEW_USER


logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    handlers=[logging.StreamHandler()]   # консоль
)
# Повышаем уровень логирования для httpx, чтобы не логировать все GET/POST
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


def _format_profile_steps(steps: list[tuple[str, int]]) -> str:
    """Сформировать компактную строку шагов профилирования в миллисекундах."""
    if not steps:
        return "no_steps"
    return ", ".join(f"{name}={duration_ms}ms" for name, duration_ms in steps)


async def _reply_markdown_safe(message, text: str, reply_markup) -> None:
    """
    Отправить MarkdownV2-сообщение с безопасным fallback.

    Если исходный текст содержит неэкранированные спецсимволы и Telegram
    возвращает ошибку парсинга сущностей, повторяем отправку полностью
    экранированным текстом.
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
            "MarkdownV2 parse failed, fallback to escaped text: %s",
            exc,
        )
        await message.reply_text(
            escape_markdown_v2(text),
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=reply_markup,
        )


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
        await update.message.reply_text(
            get_main_menu_message(user_id, update.effective_user.first_name),
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=get_main_menu_keyboard(is_admin=is_admin)
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
    
    await update.message.reply_text(
        MESSAGE_WELCOME,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        disable_web_page_preview=True,
        reply_markup=get_main_menu_keyboard(is_admin=is_admin)
    )
    await update.message.reply_text(
        get_main_menu_message(user_id, update.effective_user.first_name),
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
    
    # Тихо показываем главное меню (без подтверждения)
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
    
    # Проверяем, заблокирован ли пользователь из-за выключенной системы инвайтов
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
    profile_started_at = time.perf_counter()
    last_step_at = profile_started_at
    profile_steps: list[tuple[str, int]] = []
    profile_result = "unknown"
    profile_user_id = getattr(getattr(update, "effective_user", None), "id", "unknown")

    def mark_step(step_name: str) -> None:
        """Зафиксировать длительность шага с прошлого маркера."""
        nonlocal last_step_at
        now = time.perf_counter()
        duration_ms = int((now - last_step_at) * 1000)
        profile_steps.append((step_name, max(duration_ms, 0)))
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

        # Сначала проверяем, не является ли пользователь предварительно приглашённым
        # Это приоритетнее проверки инвайт-кода, чтобы не "тратить" инвайты
        is_pre_invited = invites.check_if_user_pre_invited(user_id)
        is_pre_invited_activated = invites.is_pre_invited_user_activated(user_id) if is_pre_invited else True
        mark_step("check_pre_invited")
        if is_pre_invited and not is_pre_invited_activated:
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
            is_admin = check_if_user_admin(user_id)
            await update.message.reply_text(
                get_main_menu_message(user_id, update.effective_user.first_name),
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=get_main_menu_keyboard(is_admin=is_admin)
            )
            mark_step("send_main_menu")
            profile_result = "pre_invited_activated"
            return

        # Проверяем, заблокирован ли пользователь из-за выключенной системы инвайтов
        if check_if_invite_user_blocked(user_id):
            mark_step("check_invite_blocked")
            await update.message.reply_text(MESSAGE_INVITE_SYSTEM_DISABLED)
            mark_step("send_invite_disabled")
            profile_result = "invite_system_disabled"
            return
        mark_step("check_invite_blocked")

        is_legit_user = check_if_user_legit(user_id)
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
                is_admin = check_if_user_admin(user_id)
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
        is_admin = check_if_user_admin(user_id)
        mark_step("check_admin")

        # Очищаем AI-контекст при навигации по меню (не для произвольного текста)
        if text in (BUTTON_MAIN_MENU, BUTTON_MODULES, BUTTON_SETTINGS, BUTTON_VALIDATE_TICKET,
                    BUTTON_UPOS_ERRORS, BUTTON_CERTIFICATION, BUTTON_KTR, BUTTON_FEEDBACK,
                    BUTTON_PROFILE, BUTTON_NEWS, BUTTON_SCREENSHOT, BUTTON_BOT_ADMIN,
                    BUTTON_MY_INVITES, BUTTON_HELP):
            ai_router = get_ai_router()
            ai_router.clear_context(user_id)
            mark_step("clear_ai_context")

        if text == BUTTON_MAIN_MENU:
            await update.message.reply_text(
                get_main_menu_message(user_id, update.effective_user.first_name),
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=get_main_menu_keyboard(is_admin=is_admin)
            )
            mark_step("reply_main_menu")
            profile_result = "main_menu"
        elif text == BUTTON_MODULES:
            # Показываем меню модулей
            await update.message.reply_text(
                MESSAGE_MODULES_MENU,
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=get_modules_menu_keyboard()
            )
            mark_step("reply_modules_menu")
            profile_result = "modules_menu"
        elif text == BUTTON_SETTINGS:
            # Показываем меню настроек
            await update.message.reply_text(
                MESSAGE_SETTINGS_MENU,
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=get_settings_menu_keyboard()
            )
            mark_step("reply_settings_menu")
            profile_result = "settings_menu"
        elif text == BUTTON_VALIDATE_TICKET:
            # Показываем подменю валидации (с админ-панелью для админа)
            if not bot_settings.is_module_enabled('ticket_validator'):
                await update.message.reply_text(MESSAGE_MODULE_DISABLED_BUTTON, parse_mode=constants.ParseMode.MARKDOWN_V2, reply_markup=get_main_menu_keyboard(is_admin=is_admin))
                mark_step("reply_module_disabled_ticket_validator")
                profile_result = "ticket_validator_disabled"
                return
            if is_admin:
                keyboard = validator_keyboards.get_admin_submenu_keyboard()
            else:
                keyboard = validator_keyboards.get_submenu_keyboard()
            await update.message.reply_text(
                validator_messages.get_submenu_message(),
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=keyboard
            )
            mark_step("reply_ticket_validator_submenu")
            profile_result = "ticket_validator_submenu"
        elif text == validator_settings.BUTTON_VALIDATE_TICKET:
            await validate_ticket_command(update, _context)
            mark_step("run_validate_ticket_command")
            profile_result = "validate_ticket_command"
        elif text == validator_settings.BUTTON_TEST_TEMPLATES:
            # Кнопка быстрого доступа к тестовым шаблонам (только админ)
            await run_test_templates_command(update, _context)
            mark_step("run_test_templates_command")
            profile_result = "test_templates_command"
        elif text == validator_settings.BUTTON_HELP_VALIDATION:
            await help_command(update, _context)
            mark_step("run_help_validation")
            profile_result = "help_validation"
        elif text == BUTTON_MY_INVITES:
            await invite_command(update, _context)
            mark_step("run_invite_command")
            profile_result = "my_invites"
        elif text == BUTTON_HELP:
            await update.message.reply_text(
                MESSAGE_MAIN_HELP,
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=get_settings_menu_keyboard()
            )
            mark_step("reply_main_help")
            profile_result = "help"
        elif text == BUTTON_SCREENSHOT or text == vyezd_settings.BUTTON_SEND_SCREENSHOT:
            # Эти кнопки обрабатываются ConversationHandler модуля скриншотов
            # Фолбэк на всякий случай: обычно ConversationHandler их перехватывает
            if not bot_settings.is_module_enabled('screenshot'):
                await update.message.reply_text(MESSAGE_MODULE_DISABLED_BUTTON, parse_mode=constants.ParseMode.MARKDOWN_V2, reply_markup=get_main_menu_keyboard(is_admin=is_admin))
                mark_step("reply_module_disabled_screenshot")
                profile_result = "screenshot_disabled"
                return
            result = await enter_screenshot_module(update, _context)
            mark_step("enter_screenshot_module")
            profile_result = "screenshot_module"
            return result
        elif text == vyezd_settings.BUTTON_SCREENSHOT_HELP:
            await update.message.reply_photo(
                ASSETS_DIR / "promo3.jpg",
                caption=image_messages.MESSAGE_INSTRUCTIONS,
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=image_keyboards.get_submenu_keyboard()
            )
            mark_step("reply_screenshot_help")
            profile_result = "screenshot_help"
        elif text == validator_settings.BUTTON_ADMIN_PANEL:
            # Показываем админ-панель, если пользователь — админ
            if is_admin:
                await update.message.reply_text(
                    validator_messages.MESSAGE_ADMIN_MENU,
                    parse_mode=constants.ParseMode.MARKDOWN_V2,
                    reply_markup=validator_keyboards.get_admin_menu_keyboard()
                )
                mark_step("reply_validator_admin_menu")
                profile_result = "validator_admin_menu"
            else:
                await update.message.reply_text(
                    MESSAGE_NO_ADMIN_RIGHTS,
                    parse_mode=constants.ParseMode.MARKDOWN_V2,
                    reply_markup=get_main_menu_keyboard(is_admin=is_admin)
                )
                mark_step("reply_no_admin_rights")
                profile_result = "no_admin_rights"
        elif text == BUTTON_BOT_ADMIN:
            # Показываем админ-панель бота для админа — входная точка в ConversationHandler
            # Фолбэк на случай, если обработчик не поймал
            if not is_admin:
                await update.message.reply_text(
                    MESSAGE_NO_ADMIN_RIGHTS,
                    parse_mode=constants.ParseMode.MARKDOWN_V2,
                    reply_markup=get_main_menu_keyboard(is_admin=is_admin)
                )
                mark_step("reply_no_admin_rights")
                profile_result = "no_admin_rights"
            else:
                profile_result = "bot_admin_handler"
        elif text == BUTTON_UPOS_ERRORS:
            # Показываем подменю модуля ошибок UPOS
            if not bot_settings.is_module_enabled('upos_errors'):
                await update.message.reply_text(MESSAGE_MODULE_DISABLED_BUTTON, parse_mode=constants.ParseMode.MARKDOWN_V2, reply_markup=get_main_menu_keyboard(is_admin=is_admin))
                mark_step("reply_module_disabled_upos")
                profile_result = "upos_disabled"
                return
            if is_admin:
                keyboard = upos_keyboards.get_admin_submenu_keyboard()
            else:
                keyboard = upos_keyboards.get_submenu_keyboard()
            await update.message.reply_text(
                upos_messages.get_submenu_message(),
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=keyboard
            )
            mark_step("reply_upos_submenu")
            profile_result = "upos_submenu"
        elif text == upos_settings.BUTTON_POPULAR_ERRORS:
            await show_popular_errors(update, _context)
            mark_step("run_upos_popular_errors")
            profile_result = "upos_popular_errors"
        elif text == BUTTON_CERTIFICATION:
            # Показываем подменю аттестации (делегируем обработчику модуля)
            if not bot_settings.is_module_enabled('certification'):
                await update.message.reply_text(MESSAGE_MODULE_DISABLED_BUTTON, parse_mode=constants.ParseMode.MARKDOWN_V2, reply_markup=get_main_menu_keyboard(is_admin=is_admin))
                mark_step("reply_module_disabled_certification")
                profile_result = "certification_disabled"
                return
            await enter_certification_module(update, _context)
            mark_step("enter_certification_module")
            profile_result = "certification_submenu"
        elif text == certification_settings.BUTTON_MY_RANKING:
            await show_my_ranking(update, _context)
            mark_step("run_certification_my_ranking")
            profile_result = "certification_my_ranking"
        elif text == certification_settings.BUTTON_TEST_HISTORY:
            await show_test_history(update, _context)
            mark_step("run_certification_test_history")
            profile_result = "certification_test_history"
        elif text == certification_settings.BUTTON_MONTHLY_TOP:
            await show_monthly_top(update, _context)
            mark_step("run_certification_monthly_top")
            profile_result = "certification_monthly_top"
        elif text == BUTTON_KTR:
            # Показываем подменю модуля КТР
            if not bot_settings.is_module_enabled('ktr'):
                await update.message.reply_text(MESSAGE_MODULE_DISABLED_BUTTON, parse_mode=constants.ParseMode.MARKDOWN_V2, reply_markup=get_main_menu_keyboard(is_admin=is_admin))
                mark_step("reply_module_disabled_ktr")
                profile_result = "ktr_disabled"
                return
            if is_admin:
                keyboard = ktr_keyboards.get_admin_submenu_keyboard()
            else:
                keyboard = ktr_keyboards.get_submenu_keyboard()
            await update.message.reply_text(
                ktr_messages.get_submenu_message(),
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=keyboard
            )
            mark_step("reply_ktr_submenu")
            profile_result = "ktr_submenu"
        elif text == ktr_settings.BUTTON_POPULAR_CODES:
            await show_popular_ktr_codes(update, _context)
            mark_step("run_ktr_popular_codes")
            profile_result = "ktr_popular_codes"
        elif text == ktr_settings.BUTTON_ACHIEVEMENTS:
            # Показываем достижения КТР (обрабатывает модуль КТР)
            from src.sbs_helper_telegram_bot.ktr.ktr_bot_part import show_ktr_achievements
            await show_ktr_achievements(update, _context)
            mark_step("run_ktr_achievements")
            profile_result = "ktr_achievements"
        elif text == BUTTON_FEEDBACK:
            # Показываем подменю обратной связи
            if not bot_settings.is_module_enabled('feedback'):
                await update.message.reply_text(MESSAGE_MODULE_DISABLED_BUTTON, parse_mode=constants.ParseMode.MARKDOWN_V2, reply_markup=get_main_menu_keyboard(is_admin=is_admin))
                mark_step("reply_module_disabled_feedback")
                profile_result = "feedback_disabled"
                return
            if is_admin:
                keyboard = feedback_keyboards.get_submenu_keyboard(is_admin=True)
            else:
                keyboard = feedback_keyboards.get_submenu_keyboard(is_admin=False)
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
                await update.message.reply_text(MESSAGE_MODULE_DISABLED_BUTTON, parse_mode=constants.ParseMode.MARKDOWN_V2, reply_markup=get_main_menu_keyboard(is_admin=is_admin))
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
            try:
                response, status = await ai_router.route(text, user_id)
            except Exception as ai_exc:
                logger.error("AI router exception: user=%s, error=%s", user_id, ai_exc)
                response, status = None, "error"
            mark_step("ai_route")

            if response and status in ("routed", "chat", "rate_limited", "module_disabled"):
                await _reply_markdown_safe(
                    update.message,
                    response,
                    get_main_menu_keyboard(is_admin=is_admin),
                )
                mark_step("reply_ai_response")
                profile_result = f"ai_{status}"
            else:
                # Ответ по умолчанию для нераспознанного текста
                await update.message.reply_text(
                    MESSAGE_UNRECOGNIZED_INPUT,
                    parse_mode=constants.ParseMode.MARKDOWN_V2,
                    reply_markup=get_main_menu_keyboard(is_admin=is_admin)
                )
                mark_step("reply_unrecognized_input")
                profile_result = "unrecognized_input"
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
        .read_timeout(30)
        .write_timeout(30)
        .connect_timeout(15)
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
