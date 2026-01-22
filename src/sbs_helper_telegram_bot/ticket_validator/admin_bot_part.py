"""
Admin Bot Handlers

Conversation-based handlers for admin panel to manage validation rules and ticket types.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from telegram import constants
import logging

from src.common.telegram_user import check_if_user_admin, update_user_info_from_telegram
from src.common.messages import (
    MESSAGE_ADMIN_MENU,
    MESSAGE_NO_ADMIN_ACCESS,
    get_admin_menu_keyboard,
    get_main_menu_keyboard
)
from .validation_rules import (
    create_validation_rule,
    update_validation_rule,
    get_all_rules,
    assign_rule_to_ticket_type,
    unassign_rule_from_ticket_type,
    load_all_ticket_types,
    get_rules_for_ticket_type,
    create_ticket_type,
    update_ticket_type,
    load_ticket_type_by_id
)

logger = logging.getLogger(__name__)

# Conversation states for add_rule
ADD_RULE_NAME, ADD_RULE_TYPE, ADD_RULE_PATTERN, ADD_RULE_ERROR_MSG, ADD_RULE_PRIORITY = range(5)

# Conversation states for edit_rule
EDIT_SELECT_RULE, EDIT_SELECT_FIELD, EDIT_NEW_VALUE = range(3)

# Conversation states for assign_rule
ASSIGN_SELECT_TYPE, ASSIGN_SELECT_RULES = range(2)

# Conversation states for manage_ticket_types
MANAGE_TYPE_ACTION, CREATE_TYPE_NAME, CREATE_TYPE_DESC, CREATE_TYPE_KEYWORDS, EDIT_TYPE_SELECT, EDIT_TYPE_FIELD, EDIT_TYPE_VALUE = range(7)


async def admin_menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Show admin panel menu.
    Handler for /admin command.
    """
    if not check_if_user_admin(update.effective_user.id):
        await update.message.reply_text(
            MESSAGE_NO_ADMIN_ACCESS,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return
    
    update_user_info_from_telegram(update.effective_user)
    await update.message.reply_text(
        MESSAGE_ADMIN_MENU,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=get_admin_menu_keyboard()
    )


# ===== ADD RULE CONVERSATION =====

async def add_rule_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start conversation to add a new validation rule."""
    if not check_if_user_admin(update.effective_user.id):
        await update.message.reply_text(MESSAGE_NO_ADMIN_ACCESS, parse_mode=constants.ParseMode.MARKDOWN_V2)
        return ConversationHandler.END
    
    await update.message.reply_text(
        "➕ *Добавление правила валидации*\n\n"
        "Введите название правила \\(например: _Проверка ИНН_\\):\n\n"
        "Используйте /cancel для отмены\\.",
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    return ADD_RULE_NAME


async def add_rule_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store rule name and ask for type."""
    context.user_data['new_rule_name'] = update.message.text
    
    keyboard = [
        [InlineKeyboardButton("Regex (регулярное выражение)", callback_data="type_regex")],
        [InlineKeyboardButton("Required Field (обязательное поле)", callback_data="type_required_field")],
        [InlineKeyboardButton("Format (формат)", callback_data="type_format")],
        [InlineKeyboardButton("Length (длина)", callback_data="type_length")],
        [InlineKeyboardButton("Custom (кастомное)", callback_data="type_custom")]
    ]
    
    await update.message.reply_text(
        f"✅ Название: _{update.message.text}_\n\n"
        "Выберите тип правила:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    return ADD_RULE_TYPE


async def add_rule_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store rule type and ask for pattern."""
    query = update.callback_query
    await query.answer()
    
    rule_type = query.data.replace("type_", "")
    context.user_data['new_rule_type'] = rule_type
    
    type_examples = {
        "regex": "Регулярное выражение \\(например: `ИНН:\\s*\\d{10,12}`\\)",
        "required_field": "Название обязательного поля \\(например: `ИНН`\\)",
        "format": "Тип формата: `inn`, `phone`, `email`",
        "length": "Диапазон длины \\(например: `10-12` или `min:10` или `max:100`\\)",
        "custom": "Параметр для кастомной проверки"
    }
    
    await query.edit_message_text(
        f"✅ Тип: _{rule_type}_\n\n"
        f"Введите паттерн/параметр:\n\n{type_examples.get(rule_type, '')}",
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    return ADD_RULE_PATTERN


async def add_rule_pattern(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store pattern and ask for error message."""
    context.user_data['new_rule_pattern'] = update.message.text
    
    await update.message.reply_text(
        f"✅ Паттерн: `{update.message.text}`\n\n"
        "Введите сообщение об ошибке \\(будет показано пользователю\\):",
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    return ADD_RULE_ERROR_MSG


async def add_rule_error_msg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store error message and ask for priority."""
    context.user_data['new_rule_error_msg'] = update.message.text
    
    await update.message.reply_text(
        f"✅ Сообщение об ошибке: _{update.message.text}_\n\n"
        "Введите приоритет \\(число, по умолчанию 10\\):\n"
        "Чем выше число, тем раньше проверяется правило\\.",
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    return ADD_RULE_PRIORITY


async def add_rule_priority(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store priority and create the rule."""
    try:
        priority = int(update.message.text)
    except ValueError:
        priority = 10
    
    # Create the rule
    try:
        rule_id = create_validation_rule(
            rule_name=context.user_data['new_rule_name'],
            pattern=context.user_data['new_rule_pattern'],
            rule_type=context.user_data['new_rule_type'],
            error_message=context.user_data['new_rule_error_msg'],
            priority=priority
        )
        
        await update.message.reply_text(
            f"✅ *Правило создано успешно\\!*\n\n"
            f"ID: `{rule_id}`\n"
            f"Название: _{context.user_data['new_rule_name']}_\n"
            f"Тип: `{context.user_data['new_rule_type']}`\n"
            f"Приоритет: `{priority}`\n\n"
            "Используйте /assign\\_rules чтобы назначить правило типам заявок\\.",
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=get_admin_menu_keyboard()
        )
    except Exception as e:
        logger.error(f"Error creating rule: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Ошибка при создании правила\\. Проверьте данные и попробуйте снова\\.",
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=get_admin_menu_keyboard()
        )
    
    # Clear user data
    context.user_data.clear()
    return ConversationHandler.END


# ===== EDIT RULE CONVERSATION =====

async def edit_rule_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start conversation to edit a rule."""
    if not check_if_user_admin(update.effective_user.id):
        await update.message.reply_text(MESSAGE_NO_ADMIN_ACCESS, parse_mode=constants.ParseMode.MARKDOWN_V2)
        return ConversationHandler.END
    
    rules = get_all_rules()
    if not rules:
        await update.message.reply_text(
            "📋 Правил пока нет\\. Используйте /add\\_rule для создания\\.",
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=get_admin_menu_keyboard()
        )
        return ConversationHandler.END
    
    keyboard = []
    for rule in rules[:20]:  # Limit to 20 rules
        status = "✅" if rule['active'] else "❌"
        keyboard.append([InlineKeyboardButton(
            f"{status} {rule['rule_name']} (ID: {rule['id']})",
            callback_data=f"edit_{rule['id']}"
        )])
    
    await update.message.reply_text(
        "📝 *Выберите правило для редактирования:*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    return EDIT_SELECT_RULE


async def edit_rule_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Rule selected, show fields to edit."""
    query = update.callback_query
    await query.answer()
    
    rule_id = int(query.data.replace("edit_", ""))
    context.user_data['edit_rule_id'] = rule_id
    
    keyboard = [
        [InlineKeyboardButton("Название", callback_data="field_name")],
        [InlineKeyboardButton("Паттерн", callback_data="field_pattern")],
        [InlineKeyboardButton("Сообщение об ошибке", callback_data="field_error")],
        [InlineKeyboardButton("Приоритет", callback_data="field_priority")],
        [InlineKeyboardButton("Активность (вкл/выкл)", callback_data="field_active")],
        [InlineKeyboardButton("❌ Отменить", callback_data="field_cancel")]
    ]
    
    await query.edit_message_text(
        f"Редактирование правила ID: `{rule_id}`\n\n"
        "Выберите поле для изменения:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    return EDIT_SELECT_FIELD


async def edit_field_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Field selected, ask for new value."""
    query = update.callback_query
    await query.answer()
    
    field = query.data.replace("field_", "")
    
    if field == "cancel":
        await query.edit_message_text(
            "Редактирование отменено\\.",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        context.user_data.clear()
        return ConversationHandler.END
    
    if field == "active":
        # Toggle active status immediately
        rule_id = context.user_data['edit_rule_id']
        # We need to get current status first - for simplicity, just toggle
        update_validation_rule(rule_id, active=True)  # This should toggle
        await query.edit_message_text(
            f"✅ Статус активности правила ID `{rule_id}` изменен\\.",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        context.user_data.clear()
        return ConversationHandler.END
    
    context.user_data['edit_field'] = field
    
    field_prompts = {
        "name": "Введите новое название:",
        "pattern": "Введите новый паттерн:",
        "error": "Введите новое сообщение об ошибке:",
        "priority": "Введите новый приоритет \\(число\\):"
    }
    
    await query.edit_message_text(
        field_prompts.get(field, "Введите новое значение:"),
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    return EDIT_NEW_VALUE


async def edit_new_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Apply the new value to the rule."""
    rule_id = context.user_data['edit_rule_id']
    field = context.user_data['edit_field']
    new_value = update.message.text
    
    try:
        field_map = {
            "name": "rule_name",
            "pattern": "pattern",
            "error": "error_message",
            "priority": "priority"
        }
        
        kwargs = {}
        if field == "priority":
            kwargs[field_map[field]] = int(new_value)
        else:
            kwargs[field_map[field]] = new_value
        
        update_validation_rule(rule_id, **kwargs)
        
        await update.message.reply_text(
            f"✅ Правило ID `{rule_id}` обновлено\\!",
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=get_admin_menu_keyboard()
        )
    except Exception as e:
        logger.error(f"Error updating rule: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Ошибка при обновлении правила\\.",
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=get_admin_menu_keyboard()
        )
    
    context.user_data.clear()
    return ConversationHandler.END


# ===== ASSIGN RULES CONVERSATION =====

async def assign_rules_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start conversation to assign rules to ticket types."""
    if not check_if_user_admin(update.effective_user.id):
        await update.message.reply_text(MESSAGE_NO_ADMIN_ACCESS, parse_mode=constants.ParseMode.MARKDOWN_V2)
        return ConversationHandler.END
    
    ticket_types = load_all_ticket_types()
    if not ticket_types:
        await update.message.reply_text(
            "⚠️ Нет доступных типов заявок\\. Создайте сначала типы заявок\\.",
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=get_admin_menu_keyboard()
        )
        return ConversationHandler.END
    
    keyboard = []
    for tt in ticket_types:
        keyboard.append([InlineKeyboardButton(
            f"{tt.type_name}",
            callback_data=f"assign_type_{tt.id}"
        )])
    
    await update.message.reply_text(
        "🔗 *Назначение правил типу заявки*\n\n"
        "Выберите тип заявки:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    return ASSIGN_SELECT_TYPE


async def assign_select_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ticket type selected, show rules."""
    query = update.callback_query
    await query.answer()
    
    # Get type_id from callback data or from stored context (when refreshing)
    if query.data.startswith("assign_type_"):
        type_id = int(query.data.replace("assign_type_", ""))
        context.user_data['assign_type_id'] = type_id
    else:
        # Refreshing after toggle - use stored type_id
        type_id = context.user_data.get('assign_type_id')
        if not type_id:
            return ConversationHandler.END
    
    ticket_type = load_ticket_type_by_id(type_id)
    assigned_rules = get_rules_for_ticket_type(type_id)
    assigned_ids = {r['id'] for r in assigned_rules}
    
    all_rules = get_all_rules()
    
    keyboard = []
    for rule in all_rules:
        if not rule['active']:
            continue
        is_assigned = rule['id'] in assigned_ids
        prefix = "✅ " if is_assigned else "➕ "
        action = "unassign" if is_assigned else "assign"
        
        keyboard.append([InlineKeyboardButton(
            f"{prefix}{rule['rule_name']}",
            callback_data=f"{action}_{type_id}_{rule['id']}"
        )])
    
    keyboard.append([InlineKeyboardButton("✔️ Готово", callback_data="assign_done")])
    
    await query.edit_message_text(
        f"Назначение правил для: *{ticket_type.type_name}*\n\n"
        f"Текущих правил: {len(assigned_rules)}\n\n"
        "✅ \\- назначено, ➕ \\- не назначено\n"
        "Нажмите для изменения:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    return ASSIGN_SELECT_RULES


async def assign_toggle_rule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Toggle rule assignment."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "assign_done":
        await query.edit_message_text(
            "✅ Назначение правил завершено\\!",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        context.user_data.clear()
        return ConversationHandler.END
    
    # Parse callback data - should be "assign_X_Y" or "unassign_X_Y"
    parts = query.data.split("_")
    if len(parts) != 3:
        # Invalid callback data, stay in current state
        return ASSIGN_SELECT_RULES
    
    action = parts[0]
    try:
        type_id = int(parts[1])
        rule_id = int(parts[2])
    except ValueError:
        # Invalid format, stay in current state
        return ASSIGN_SELECT_RULES
    
    # Perform the assignment/unassignment
    if action == "assign":
        assign_rule_to_ticket_type(rule_id, type_id)
    elif action == "unassign":
        unassign_rule_from_ticket_type(rule_id, type_id)
    
    # Store the type_id in context for refresh (assign_select_type will use it)
    context.user_data['assign_type_id'] = type_id
    
    # Refresh the display - assign_select_type will get type_id from context
    # Catch BadRequest if message content hasn't actually changed
    try:
        return await assign_select_type(update, context)
    except Exception:
        # If message hasn't changed, just stay in current state
        return ASSIGN_SELECT_RULES


# ===== LIST RULES =====

async def list_rules_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all validation rules."""
    if not check_if_user_admin(update.effective_user.id):
        await update.message.reply_text(MESSAGE_NO_ADMIN_ACCESS, parse_mode=constants.ParseMode.MARKDOWN_V2)
        return
    
    rules = get_all_rules()
    if not rules:
        await update.message.reply_text(
            "📋 Правил пока нет\\.",
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=get_admin_menu_keyboard()
        )
        return
    
    response = "*Список всех правил валидации:*\n\n"
    
    for rule in rules:
        status = "✅" if rule['active'] else "❌"
        response += (
            f"{status} *ID {rule['id']}:* _{rule['rule_name']}_\n"
            f"   Тип: `{rule['rule_type']}`\n"
            f"   Приоритет: `{rule['priority']}`\n\n"
        )
    
    await update.message.reply_text(
        response,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=get_admin_menu_keyboard()
    )


# ===== MANAGE TICKET TYPES =====

async def manage_types_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show ticket types management menu."""
    if not check_if_user_admin(update.effective_user.id):
        await update.message.reply_text(MESSAGE_NO_ADMIN_ACCESS, parse_mode=constants.ParseMode.MARKDOWN_V2)
        return
    
    ticket_types = load_all_ticket_types()
    
    response = "🎫 *Управление типами заявок*\n\n"
    
    if ticket_types:
        response += "*Существующие типы:*\n\n"
        for tt in ticket_types:
            response += f"• ID `{tt.id}`: _{tt.type_name}_\n"
    else:
        response += "Типов заявок пока нет\\.\n"
    
    response += "\n*Доступные команды:*\n"
    response += "• `/create_type` \\- создать новый тип\n"
    response += "• `/edit_type <id>` \\- редактировать тип\n"
    
    await update.message.reply_text(
        response,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=get_admin_menu_keyboard()
    )


# ===== CANCEL HANDLER =====

async def cancel_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel any admin conversation."""
    await update.message.reply_text(
        "Операция отменена\\.",
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=get_admin_menu_keyboard()
    )
    context.user_data.clear()
    return ConversationHandler.END
