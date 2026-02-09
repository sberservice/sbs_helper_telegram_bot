"""
Модуль обратной связи — часть бота для админ-панели

Админ-обработчики для просмотра обращений и отправки анонимных ответов.
КРИТИЧНО: личность администратора НЕЛЬЗЯ раскрывать пользователям.
"""

import logging
from telegram import Update, Bot, constants
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    CommandHandler,
    filters,
)

from src.common.telegram_user import check_if_user_admin

from . import settings
from . import messages
from . import keyboards
from . import feedback_logic

logger = logging.getLogger(__name__)


# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====


def _clear_admin_context(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Очистить все данные контекста, связанные с админкой обратной связи."""
    keys_to_clear = [
        settings.ADMIN_CURRENT_ENTRY_KEY,
        settings.ADMIN_REPLY_TEXT_KEY,
        settings.ADMIN_LIST_PAGE_KEY,
        settings.ADMIN_FILTER_STATUS_KEY,
        settings.ADMIN_FILTER_CATEGORY_KEY,
    ]
    for key in keys_to_clear:
        context.user_data.pop(key, None)


async def _notify_user(
    bot: Bot,
    user_id: int,
    message: str
) -> bool:
    """
    Отправить уведомление пользователю.
    ПРИМЕЧАНИЕ: в уведомлениях не содержится информация об администраторе.
    
    Args:
        bot: Экземпляр Telegram-бота
        user_id: Telegram ID пользователя
        message: Текст сообщения
        
    Returns:
        True при успехе, False при ошибке
    """
    try:
        await bot.send_message(
            chat_id=user_id,
            text=message,
            parse_mode="MarkdownV2"
        )
        return True
    except Exception as e:
        logger.error("Failed to notify user %s: %s", user_id, e)
        return False


# ===== ТОЧКИ ВХОДА =====


async def admin_panel_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Точка входа в админ-панель.
    """
    user_id = update.effective_user.id
    
    if not check_if_user_admin(user_id):
        await update.message.reply_text(
            messages.MESSAGE_ADMIN_NOT_AUTHORIZED,
            parse_mode="MarkdownV2"
        )
        return ConversationHandler.END
    
    _clear_admin_context(context)
    
    keyboard = keyboards.get_admin_menu_keyboard()
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_MENU,
        parse_mode="MarkdownV2",
        reply_markup=keyboard
    )
    
    return settings.STATE_ADMIN_MENU


# ===== ПРОСМОТР ОБРАЩЕНИЙ =====


async def view_new_entries(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Показать список новых (необработанных) обращений.
    """
    user_id = update.effective_user.id
    
    if not check_if_user_admin(user_id):
        return ConversationHandler.END
    
    context.user_data[settings.ADMIN_FILTER_STATUS_KEY] = settings.STATUS_NEW
    context.user_data[settings.ADMIN_LIST_PAGE_KEY] = 0
    
    page = 0
    entries, total = feedback_logic.get_feedback_entries_by_status(
        status=settings.STATUS_NEW,
        page=page
    )
    
    if not entries:
        await update.message.reply_text(
            messages.MESSAGE_ADMIN_LIST_EMPTY,
            parse_mode="MarkdownV2",
            reply_markup=keyboards.get_admin_menu_keyboard()
        )
        return settings.STATE_ADMIN_MENU
    
    total_pages = (total + settings.ITEMS_PER_PAGE - 1) // settings.ITEMS_PER_PAGE
    inline_keyboard = keyboards.get_admin_entries_keyboard(entries, page, total_pages)
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_LIST_NEW.format(count=total),
        parse_mode="MarkdownV2",
        reply_markup=inline_keyboard
    )
    
    return settings.STATE_ADMIN_VIEW_LIST


async def view_all_entries(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Показать список всех обращений.
    """
    user_id = update.effective_user.id
    
    if not check_if_user_admin(user_id):
        return ConversationHandler.END
    
    context.user_data[settings.ADMIN_FILTER_STATUS_KEY] = None
    context.user_data[settings.ADMIN_LIST_PAGE_KEY] = 0
    
    page = 0
    entries, total = feedback_logic.get_feedback_entries_by_status(page=page)
    
    if not entries:
        await update.message.reply_text(
            messages.MESSAGE_ADMIN_LIST_EMPTY,
            parse_mode="MarkdownV2",
            reply_markup=keyboards.get_admin_menu_keyboard()
        )
        return settings.STATE_ADMIN_MENU
    
    total_pages = (total + settings.ITEMS_PER_PAGE - 1) // settings.ITEMS_PER_PAGE
    inline_keyboard = keyboards.get_admin_entries_keyboard(entries, page, total_pages)
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_LIST_ALL.format(count=total),
        parse_mode="MarkdownV2",
        reply_markup=inline_keyboard
    )
    
    return settings.STATE_ADMIN_VIEW_LIST


async def view_by_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:  # pylint: disable=unused-argument
    """
    Показать категории с количеством обращений для фильтрации.
    """
    user_id = update.effective_user.id
    
    if not check_if_user_admin(user_id):
        return ConversationHandler.END
    
    categories = feedback_logic.get_categories_with_counts()
    
    if not categories:
        await update.message.reply_text(
            messages.MESSAGE_ADMIN_LIST_EMPTY,
            parse_mode="MarkdownV2",
            reply_markup=keyboards.get_admin_menu_keyboard()
        )
        return settings.STATE_ADMIN_MENU
    
    inline_keyboard = keyboards.get_admin_category_keyboard(categories)
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_LIST_BY_CATEGORY,
        parse_mode="MarkdownV2",
        reply_markup=inline_keyboard
    )
    
    return settings.STATE_ADMIN_BY_CATEGORY


async def category_filter_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработать выбор категории для фильтрации.
    """
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    
    if callback_data == settings.CALLBACK_ADMIN_BACK:
        await query.edit_message_text(
            messages.MESSAGE_ADMIN_MENU,
            parse_mode="MarkdownV2"
        )
        return settings.STATE_ADMIN_MENU
    
    if not callback_data.startswith(settings.CALLBACK_CATEGORY_PREFIX):
        return settings.STATE_ADMIN_BY_CATEGORY
    
    try:
        category_id = int(callback_data.replace(settings.CALLBACK_CATEGORY_PREFIX, ""))
    except ValueError:
        return settings.STATE_ADMIN_BY_CATEGORY
    
    context.user_data[settings.ADMIN_FILTER_CATEGORY_KEY] = category_id
    context.user_data[settings.ADMIN_FILTER_STATUS_KEY] = None
    context.user_data[settings.ADMIN_LIST_PAGE_KEY] = 0
    
    page = 0
    entries, total = feedback_logic.get_feedback_entries_by_status(
        category_id=category_id,
        page=page
    )
    
    if not entries:
        await query.edit_message_text(
            messages.MESSAGE_ADMIN_LIST_EMPTY,
            parse_mode="MarkdownV2"
        )
        return settings.STATE_ADMIN_BY_CATEGORY
    
    # Получаем название категории
    category = feedback_logic.get_category_by_id(category_id)
    cat_name = category['name'] if category else "Неизвестная"
    
    total_pages = (total + settings.ITEMS_PER_PAGE - 1) // settings.ITEMS_PER_PAGE
    inline_keyboard = keyboards.get_admin_entries_keyboard(entries, page, total_pages)
    
    await query.edit_message_text(
        messages.MESSAGE_ADMIN_CATEGORY_ENTRIES.format(category=cat_name, count=total),
        parse_mode="MarkdownV2",
        reply_markup=inline_keyboard
    )
    
    return settings.STATE_ADMIN_VIEW_LIST


# ===== КОЛБЭКИ СПИСКА ОБРАЩЕНИЙ =====


async def admin_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработать колбэки в списке обращений администратора.
    """
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    
    # Назад в админ-меню
    if callback_data == settings.CALLBACK_ADMIN_BACK:
        await query.edit_message_text(
            messages.MESSAGE_ADMIN_MENU,
            parse_mode="MarkdownV2"
        )
        return settings.STATE_ADMIN_MENU
    
    # Обработать пагинацию
    if callback_data.startswith(settings.CALLBACK_ADMIN_PAGE_PREFIX):
        try:
            page = int(callback_data.replace(settings.CALLBACK_ADMIN_PAGE_PREFIX, ""))
            context.user_data[settings.ADMIN_LIST_PAGE_KEY] = page
        except ValueError:
            page = 0
        
        status_filter = context.user_data.get(settings.ADMIN_FILTER_STATUS_KEY)
        category_filter = context.user_data.get(settings.ADMIN_FILTER_CATEGORY_KEY)
        
        entries, total = feedback_logic.get_feedback_entries_by_status(
            status=status_filter,
            category_id=category_filter,
            page=page
        )
        
        total_pages = (total + settings.ITEMS_PER_PAGE - 1) // settings.ITEMS_PER_PAGE
        inline_keyboard = keyboards.get_admin_entries_keyboard(entries, page, total_pages)
        
        list_message = messages.MESSAGE_ADMIN_LIST_ALL.format(count=total)
        if status_filter == settings.STATUS_NEW:
            list_message = messages.MESSAGE_ADMIN_LIST_NEW.format(count=total)
        
        await query.edit_message_text(
            list_message,
            parse_mode="MarkdownV2",
            reply_markup=inline_keyboard
        )
        return settings.STATE_ADMIN_VIEW_LIST
    
    # Обработать выбор обращения
    if callback_data.startswith(settings.CALLBACK_ADMIN_ENTRY_PREFIX):
        try:
            entry_id = int(callback_data.replace(settings.CALLBACK_ADMIN_ENTRY_PREFIX, ""))
        except ValueError:
            return settings.STATE_ADMIN_VIEW_LIST
        
        # Получаем детали обращения (админский вид — включает user_id)
        entry = feedback_logic.get_feedback_entry(entry_id)
        
        if not entry:
            await query.answer("Обращение не найдено", show_alert=True)
            return settings.STATE_ADMIN_VIEW_LIST
        
        context.user_data[settings.ADMIN_CURRENT_ENTRY_KEY] = entry_id
        
        # Формируем сообщение с деталями
        status_name = feedback_logic.get_status_display_name(entry['status'])
        detail_message = messages.format_admin_entry_detail(
            entry_id=entry['id'],
            user_id=entry['user_id'],
            category=entry['category'],
            status=status_name,
            date=entry['date'],
            message=entry['message'],
            responses=entry['responses']
        )
        
        detail_keyboard = keyboards.get_admin_entry_detail_keyboard(entry_id, entry['status'])
        
        await query.edit_message_text(
            detail_message,
            parse_mode="MarkdownV2",
            reply_markup=detail_keyboard
        )
        return settings.STATE_ADMIN_VIEW_ENTRY
    
    return settings.STATE_ADMIN_VIEW_LIST


# ===== КОЛБЭКИ ПРОСМОТРА ОБРАЩЕНИЯ =====


async def admin_entry_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработать колбэки на экране деталей обращения.
    """
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    entry_id = context.user_data.get(settings.ADMIN_CURRENT_ENTRY_KEY)
    
    # Назад к списку
    if callback_data == settings.CALLBACK_ADMIN_BACK:
        page = context.user_data.get(settings.ADMIN_LIST_PAGE_KEY, 0)
        status_filter = context.user_data.get(settings.ADMIN_FILTER_STATUS_KEY)
        category_filter = context.user_data.get(settings.ADMIN_FILTER_CATEGORY_KEY)
        
        entries, total = feedback_logic.get_feedback_entries_by_status(
            status=status_filter,
            category_id=category_filter,
            page=page
        )
        
        if not entries:
            await query.edit_message_text(
                messages.MESSAGE_ADMIN_LIST_EMPTY,
                parse_mode="MarkdownV2"
            )
            return settings.STATE_ADMIN_MENU
        
        total_pages = (total + settings.ITEMS_PER_PAGE - 1) // settings.ITEMS_PER_PAGE
        inline_keyboard = keyboards.get_admin_entries_keyboard(entries, page, total_pages)
        
        list_message = messages.MESSAGE_ADMIN_LIST_ALL.format(count=total)
        if status_filter == settings.STATUS_NEW:
            list_message = messages.MESSAGE_ADMIN_LIST_NEW.format(count=total)
        
        await query.edit_message_text(
            list_message,
            parse_mode="MarkdownV2",
            reply_markup=inline_keyboard
        )
        return settings.STATE_ADMIN_VIEW_LIST
    
    # Ответить на обращение
    if callback_data == settings.CALLBACK_ADMIN_REPLY:
        if not entry_id:
            await query.answer("Ошибка: обращение не выбрано", show_alert=True)
            return settings.STATE_ADMIN_VIEW_ENTRY
        
        await query.edit_message_text(
            messages.MESSAGE_ADMIN_COMPOSE_REPLY.format(entry_id=entry_id),
            parse_mode="MarkdownV2"
        )
        
        # Клавиатуру отправляем отдельно
        await query.message.reply_text(
            "👇",
            reply_markup=keyboards.get_cancel_keyboard()
        )
        
        return settings.STATE_ADMIN_COMPOSE_REPLY
    
    # Изменить статус
    if callback_data == settings.CALLBACK_ADMIN_STATUS:
        if not entry_id:
            await query.answer("Ошибка: обращение не выбрано", show_alert=True)
            return settings.STATE_ADMIN_VIEW_ENTRY
        
        entry = feedback_logic.get_feedback_entry(entry_id)
        if not entry:
            await query.answer("Обращение не найдено", show_alert=True)
            return settings.STATE_ADMIN_VIEW_ENTRY
        
        current_status = entry['status']
        status_name = feedback_logic.get_status_display_name(current_status)
        
        status_keyboard = keyboards.get_admin_status_keyboard(current_status)
        
        await query.edit_message_text(
            messages.MESSAGE_ADMIN_SELECT_STATUS.format(current_status=status_name),
            parse_mode="MarkdownV2",
            reply_markup=status_keyboard
        )
        return settings.STATE_ADMIN_SELECT_STATUS
    
    return settings.STATE_ADMIN_VIEW_ENTRY


# ===== СМЕНА СТАТУСА =====


async def status_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработать выбор статуса.
    """
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    entry_id = context.user_data.get(settings.ADMIN_CURRENT_ENTRY_KEY)
    
    if callback_data == settings.CALLBACK_CANCEL:
        # Возвращаемся к деталям обращения
        entry = feedback_logic.get_feedback_entry(entry_id)
        if entry:
            status_name = feedback_logic.get_status_display_name(entry['status'])
            detail_message = messages.format_admin_entry_detail(
                entry_id=entry['id'],
                user_id=entry['user_id'],
                category=entry['category'],
                status=status_name,
                date=entry['date'],
                message=entry['message'],
                responses=entry['responses']
            )
            detail_keyboard = keyboards.get_admin_entry_detail_keyboard(entry_id, entry['status'])
            
            await query.edit_message_text(
                detail_message,
                parse_mode="MarkdownV2",
                reply_markup=detail_keyboard
            )
        return settings.STATE_ADMIN_VIEW_ENTRY
    
    if not callback_data.startswith(settings.CALLBACK_STATUS_PREFIX):
        return settings.STATE_ADMIN_SELECT_STATUS
    
    new_status = callback_data.replace(settings.CALLBACK_STATUS_PREFIX, "")
    
    if new_status not in settings.STATUS_NAMES:
        return settings.STATE_ADMIN_SELECT_STATUS
    
    # Обновляем статус
    success = feedback_logic.update_entry_status(entry_id, new_status)
    
    if not success:
        await query.answer("Ошибка при обновлении статуса", show_alert=True)
        return settings.STATE_ADMIN_SELECT_STATUS
    
    # Уведомляем пользователя об изменении статуса (анонимно)
    user_id_to_notify = feedback_logic.get_entry_user_id(entry_id)
    if user_id_to_notify:
        status_display = feedback_logic.get_status_display_name(new_status)
        notification = messages.format_status_changed_notification(entry_id, status_display)
        await _notify_user(context.bot, user_id_to_notify, notification)
    
    # Показываем обновлённое обращение
    entry = feedback_logic.get_feedback_entry(entry_id)
    if entry:
        status_name = feedback_logic.get_status_display_name(entry['status'])
        detail_message = messages.format_admin_entry_detail(
            entry_id=entry['id'],
            user_id=entry['user_id'],
            category=entry['category'],
            status=status_name,
            date=entry['date'],
            message=entry['message'],
            responses=entry['responses']
        )
        detail_keyboard = keyboards.get_admin_entry_detail_keyboard(entry_id, entry['status'])
        
        await query.edit_message_text(
            detail_message,
            parse_mode="MarkdownV2",
            reply_markup=detail_keyboard
        )
    
    return settings.STATE_ADMIN_VIEW_ENTRY


# ===== СОСТАВЛЕНИЕ ОТВЕТА =====


async def reply_text_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработать ввод текста ответа администратора.
    """
    admin_id = update.effective_user.id
    
    if not check_if_user_admin(admin_id):
        return ConversationHandler.END
    
    reply_text = update.message.text
    entry_id = context.user_data.get(settings.ADMIN_CURRENT_ENTRY_KEY)
    
    if not entry_id:
        await update.message.reply_text(
            messages.MESSAGE_ADMIN_ERROR,
            parse_mode="MarkdownV2",
            reply_markup=keyboards.get_admin_menu_keyboard()
        )
        return settings.STATE_ADMIN_MENU
    
    # Сохраняем текст ответа для подтверждения
    context.user_data[settings.ADMIN_REPLY_TEXT_KEY] = reply_text
    
    # Показываем подтверждение
    confirm_keyboard = keyboards.get_admin_confirm_reply_keyboard()
    
    await update.message.reply_text(
        messages.format_admin_confirm_reply(entry_id, reply_text),
        parse_mode="MarkdownV2",
        reply_markup=confirm_keyboard
    )
    
    return settings.STATE_ADMIN_CONFIRM_REPLY


async def confirm_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработать подтверждение ответа.
    """
    query = update.callback_query
    await query.answer()
    
    admin_id = update.effective_user.id
    entry_id = context.user_data.get(settings.ADMIN_CURRENT_ENTRY_KEY)
    reply_text = context.user_data.get(settings.ADMIN_REPLY_TEXT_KEY)
    
    if query.data == settings.CALLBACK_CONFIRM_NO:
        # Отменяем ответ и возвращаемся к деталям обращения
        await query.edit_message_text(
            messages.MESSAGE_ADMIN_REPLY_CANCELLED,
            parse_mode="MarkdownV2"
        )
        
        context.user_data.pop(settings.ADMIN_REPLY_TEXT_KEY, None)
        
        # Возвращаемся к просмотру обращения
        entry = feedback_logic.get_feedback_entry(entry_id)
        if entry:
            status_name = feedback_logic.get_status_display_name(entry['status'])
            detail_message = messages.format_admin_entry_detail(
                entry_id=entry['id'],
                user_id=entry['user_id'],
                category=entry['category'],
                status=status_name,
                date=entry['date'],
                message=entry['message'],
                responses=entry['responses']
            )
            detail_keyboard = keyboards.get_admin_entry_detail_keyboard(entry_id, entry['status'])
            
            await query.message.reply_text(
                detail_message,
                parse_mode="MarkdownV2",
                reply_markup=detail_keyboard
            )
        
        await query.message.reply_text(
            "👆",
            reply_markup=keyboards.get_admin_menu_keyboard()
        )
        
        return settings.STATE_ADMIN_VIEW_ENTRY
    
    if query.data == settings.CALLBACK_CONFIRM_YES:
        if not entry_id or not reply_text:
            await query.edit_message_text(
                messages.MESSAGE_ADMIN_ERROR,
                parse_mode="MarkdownV2"
            )
            return settings.STATE_ADMIN_MENU
        
        # Создаём ответ (admin_id сохраняется, но НИКОГДА не показывается пользователю)
        success = feedback_logic.create_admin_response(
            entry_id=entry_id,
            admin_id=admin_id,  # Только для внутреннего использования
            response_text=reply_text
        )
        
        if not success:
            await query.edit_message_text(
                messages.MESSAGE_ADMIN_ERROR,
                parse_mode="MarkdownV2"
            )
            return settings.STATE_ADMIN_VIEW_ENTRY
        
        # Уведомляем пользователя (АНОНИМНО — без данных админа!)
        user_id_to_notify = feedback_logic.get_entry_user_id(entry_id)
        if user_id_to_notify:
            notification = messages.format_new_response_notification(entry_id, reply_text)
            await _notify_user(context.bot, user_id_to_notify, notification)
        
        await query.edit_message_text(
            messages.MESSAGE_ADMIN_REPLY_SENT,
            parse_mode="MarkdownV2"
        )
        
        context.user_data.pop(settings.ADMIN_REPLY_TEXT_KEY, None)
        
        # Возвращаемся к обращению с обновлёнными данными
        entry = feedback_logic.get_feedback_entry(entry_id)
        if entry:
            status_name = feedback_logic.get_status_display_name(entry['status'])
            detail_message = messages.format_admin_entry_detail(
                entry_id=entry['id'],
                user_id=entry['user_id'],
                category=entry['category'],
                status=status_name,
                date=entry['date'],
                message=entry['message'],
                responses=entry['responses']
            )
            detail_keyboard = keyboards.get_admin_entry_detail_keyboard(entry_id, entry['status'])
            
            await query.message.reply_text(
                detail_message,
                parse_mode="MarkdownV2",
                reply_markup=detail_keyboard
            )
        
        await query.message.reply_text(
            "👆",
            reply_markup=keyboards.get_admin_menu_keyboard()
        )
        
        return settings.STATE_ADMIN_VIEW_ENTRY
    
    return settings.STATE_ADMIN_CONFIRM_REPLY


async def cancel_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Отменить составление ответа.
    """
    context.user_data.pop(settings.ADMIN_REPLY_TEXT_KEY, None)
    
    entry_id = context.user_data.get(settings.ADMIN_CURRENT_ENTRY_KEY)
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_REPLY_CANCELLED,
        parse_mode="MarkdownV2"
    )
    
    # Возвращаемся к просмотру обращения
    entry = feedback_logic.get_feedback_entry(entry_id)
    if entry:
        status_name = feedback_logic.get_status_display_name(entry['status'])
        detail_message = messages.format_admin_entry_detail(
            entry_id=entry['id'],
            user_id=entry['user_id'],
            category=entry['category'],
            status=status_name,
            date=entry['date'],
            message=entry['message'],
            responses=entry['responses']
        )
        detail_keyboard = keyboards.get_admin_entry_detail_keyboard(entry_id, entry['status'])
        
        await update.message.reply_text(
            detail_message,
            parse_mode="MarkdownV2",
            reply_markup=detail_keyboard
        )
        
        await update.message.reply_text(
            "👆",
            reply_markup=keyboards.get_admin_menu_keyboard()
        )
        
        return settings.STATE_ADMIN_VIEW_ENTRY
    
    return settings.STATE_ADMIN_MENU


# ===== НАВИГАЦИЯ =====


async def back_to_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Вернуться в админ-меню.
    """
    user_id = update.effective_user.id
    
    if not check_if_user_admin(user_id):
        return ConversationHandler.END
    
    _clear_admin_context(context)
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_MENU,
        parse_mode="MarkdownV2",
        reply_markup=keyboards.get_admin_menu_keyboard()
    )
    
    return settings.STATE_ADMIN_MENU


async def back_to_feedback_submenu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Вернуться в подменю обратной связи и завершить админ-диалог.
    """
    user_id = update.effective_user.id
    is_admin = check_if_user_admin(user_id)
    
    _clear_admin_context(context)
    
    keyboard = keyboards.get_submenu_keyboard(is_admin)
    
    await update.message.reply_text(
        messages.MESSAGE_SUBMENU,
        parse_mode="MarkdownV2",
        reply_markup=keyboard
    )
    
    return ConversationHandler.END


async def back_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Вернуться в главное меню и завершить диалог.
    """
    # Импортируем здесь, чтобы избежать циклического импорта
    from src.common.messages import get_main_menu_message, get_main_menu_keyboard
    
    _clear_admin_context(context)
    
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
    Обработать команду /cancel в админ-панели.
    """
    user_id = update.effective_user.id
    
    if not check_if_user_admin(user_id):
        return ConversationHandler.END
    
    _clear_admin_context(context)
    
    await update.message.reply_text(
        messages.MESSAGE_CANCEL,
        parse_mode="MarkdownV2",
        reply_markup=keyboards.get_admin_menu_keyboard()
    )
    
    return settings.STATE_ADMIN_MENU


# ===== ОБРАБОТЧИК ДИАЛОГА =====


def get_feedback_admin_handler() -> ConversationHandler:
    """
    Собрать и вернуть обработчик диалога для админской части обратной связи.
    """
    return ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.Regex(f"^{settings.BUTTON_ADMIN_PANEL}$"),
                admin_panel_entry
            ),
        ],
        states={
            settings.STATE_ADMIN_MENU: [
                MessageHandler(
                    filters.Regex(f"^{settings.BUTTON_NEW_ENTRIES}$"),
                    view_new_entries
                ),
                MessageHandler(
                    filters.Regex(f"^{settings.BUTTON_ALL_ENTRIES}$"),
                    view_all_entries
                ),
                MessageHandler(
                    filters.Regex(f"^{settings.BUTTON_BY_CATEGORY}$"),
                    view_by_category
                ),
                MessageHandler(
                    filters.Regex(f"^{settings.BUTTON_BACK}$"),
                    back_to_feedback_submenu
                ),
            ],
            settings.STATE_ADMIN_VIEW_LIST: [
                CallbackQueryHandler(
                    admin_list_callback,
                    pattern=f"^({settings.CALLBACK_ADMIN_ENTRY_PREFIX}|{settings.CALLBACK_ADMIN_PAGE_PREFIX}|{settings.CALLBACK_ADMIN_BACK})"
                ),
            ],
            settings.STATE_ADMIN_VIEW_ENTRY: [
                CallbackQueryHandler(
                    admin_entry_callback,
                    pattern=f"^({settings.CALLBACK_ADMIN_REPLY}|{settings.CALLBACK_ADMIN_STATUS}|{settings.CALLBACK_ADMIN_BACK})"
                ),
            ],
            settings.STATE_ADMIN_SELECT_STATUS: [
                CallbackQueryHandler(
                    status_selected,
                    pattern=f"^({settings.CALLBACK_STATUS_PREFIX}|{settings.CALLBACK_CANCEL})"
                ),
            ],
            settings.STATE_ADMIN_COMPOSE_REPLY: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND & ~filters.Regex(f"^{settings.BUTTON_CANCEL}$"),
                    reply_text_entered
                ),
                MessageHandler(
                    filters.Regex(f"^{settings.BUTTON_CANCEL}$"),
                    cancel_reply
                ),
            ],
            settings.STATE_ADMIN_CONFIRM_REPLY: [
                CallbackQueryHandler(
                    confirm_reply,
                    pattern=f"^({settings.CALLBACK_CONFIRM_YES}|{settings.CALLBACK_CONFIRM_NO})$"
                ),
            ],
            settings.STATE_ADMIN_BY_CATEGORY: [
                CallbackQueryHandler(
                    category_filter_selected,
                    pattern=f"^({settings.CALLBACK_CATEGORY_PREFIX}|{settings.CALLBACK_ADMIN_BACK})"
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
            MessageHandler(
                filters.Regex(f"^{settings.BUTTON_BACK}$"),
                back_to_admin_menu
            ),
            MessageHandler(filters.COMMAND, back_to_main_menu),
        ],
        name="feedback_admin_conversation",
        persistent=False,
        allow_reentry=True
    )
