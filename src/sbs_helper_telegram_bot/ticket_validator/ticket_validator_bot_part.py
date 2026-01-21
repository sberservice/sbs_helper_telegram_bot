"""
Ticket Validator Bot Handlers

Telegram bot handlers for ticket validation functionality.
"""

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from telegram import constants
import logging

from src.common.telegram_user import check_if_user_legit, update_user_info_from_telegram
import src.common.messages as messages
from src.common.messages import get_validator_submenu_keyboard
from .validation_rules import (
    load_rules_from_db,
    store_validation_result,
    get_validation_history,
    load_template_by_name,
    list_all_templates,
    load_all_ticket_types,
    load_ticket_type_by_id
)
from .validators import validate_ticket, detect_ticket_type

# Set up logging
logger = logging.getLogger(__name__)

# Conversation states
WAITING_FOR_TICKET = 1


async def validate_ticket_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Start ticket validation conversation.
    Handler for /validate command.
    
    Args:
        update: Telegram update object
        context: Telegram context
        
    Returns:
        Next conversation state
    """
    # Check if user is authorized
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(
            messages.MESSAGE_PLEASE_ENTER_INVITE,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ConversationHandler.END
    
    # Update user info
    update_user_info_from_telegram(update.effective_user)
    
    # Ask for ticket text
    await update.message.reply_text(
        messages.MESSAGE_SEND_TICKET,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    return WAITING_FOR_TICKET


async def process_ticket_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Process and validate submitted ticket text.
    
    Args:
        update: Telegram update object
        context: Telegram context
        
    Returns:
        ConversationHandler.END to finish conversation
    """
    ticket_text = update.message.text
    user_id = update.effective_user.id
    
    # Load ticket types and detect which type this ticket is
    try:
        ticket_types = load_all_ticket_types()
        detected_type = detect_ticket_type(ticket_text, ticket_types) if ticket_types else None
        
        # Load validation rules - either for detected type or all rules
        if detected_type:
            rules = load_rules_from_db(ticket_type_id=detected_type.id)
            type_info = f" (тип: _{detected_type.type_name}_)"
        else:
            rules = load_rules_from_db()
            type_info = ""
        
        if not rules:
            await update.message.reply_text(
                "⚠️ Правила валидации не настроены\\. Обратитесь к администратору\\.",
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
            return ConversationHandler.END
        
        # Validate the ticket
        result = validate_ticket(ticket_text, rules, detected_ticket_type=detected_type)
        
        # Store validation result in history
        store_validation_result(
            userid=user_id,
            ticket_text=ticket_text,
            is_valid=result.is_valid,
            failed_rules=result.failed_rules,
            ticket_type_id=detected_type.id if detected_type else None
        )
        
        # Send response to user
        if result.is_valid:
            response = messages.MESSAGE_VALIDATION_SUCCESS
            if type_info:
                response = response.replace("\\.", type_info + "\\.")
            await update.message.reply_text(
                response,
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=get_validator_submenu_keyboard()
            )
        else:
            # Format error messages
            errors_formatted = "\\n".join([
                f"• {msg.replace('.', '\\.').replace('-', '\\-').replace('!', '\\!')}"
                for msg in result.error_messages
            ])
            
            response = messages.MESSAGE_VALIDATION_FAILED.format(errors=errors_formatted)
            if type_info:
                # Add detected type info to error message
                response = response.replace("*Заявка не прошла валидацию*", 
                                          f"*Заявка не прошла валидацию*{type_info}")
            await update.message.reply_text(
                response,
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=get_validator_submenu_keyboard()
            )
        
    except Exception as e:
        logger.error(f"Error validating ticket: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Произошла ошибка при валидации\\. Попробуйте позже\\.",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
    
    return ConversationHandler.END


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Show user's validation history.
    Handler for /history command.
    
    Args:
        update: Telegram update object
        context: Telegram context
    """
    # Check if user is authorized
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(
            messages.MESSAGE_PLEASE_ENTER_INVITE,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return
    
    # Update user info
    update_user_info_from_telegram(update.effective_user)
    
    user_id = update.effective_user.id
    
    try:
        history = get_validation_history(user_id, limit=5)
        
        if not history:
            await update.message.reply_text(
                "У вас пока нет истории проверок\\.",
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
            return
        
        # Format history
        history_text = "*История последних проверок:*\\n\\n"
        
        for i, record in enumerate(history, 1):
            status_emoji = "✅" if record['validation_result'] == 'valid' else "❌"
            # Truncate ticket text for display
            ticket_preview = record['ticket_text'][:50].replace('\n', ' ')
            ticket_preview = ticket_preview.replace('.', '\\.').replace('-', '\\-').replace('!', '\\!')
            
            history_text += f"{i}\\. {status_emoji} _{ticket_preview}_\\.\\.\\.\\n"
        
        await update.message.reply_text(
            history_text,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        
    except Exception as e:
        logger.error(f"Error fetching history: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Ошибка при загрузке истории\\.",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )


async def template_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Show ticket template or list available templates.
    Handler for /template command.
    
    Args:
        update: Telegram update object
        context: Telegram context
    """
    # Check if user is authorized
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(
            messages.MESSAGE_PLEASE_ENTER_INVITE,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return
    
    # Update user info
    update_user_info_from_telegram(update.effective_user)
    
    try:
        # Check if template name was provided
        if context.args and len(context.args) > 0:
            template_name = ' '.join(context.args)
            template = load_template_by_name(template_name)
            
            if template:
                # Escape special characters for Markdown V2
                template_text = template['template_text'].replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(']', '\\]').replace('(', '\\(').replace(')', '\\)').replace('~', '\\~').replace('`', '\\`').replace('>', '\\>').replace('#', '\\#').replace('+', '\\+').replace('-', '\\-').replace('=', '\\=').replace('|', '\\|').replace('{', '\\{').replace('}', '\\}').replace('.', '\\.').replace('!', '\\!')
                
                response = f"*Шаблон: {template['template_name']}*\\n\\n{template_text}"
                await update.message.reply_text(
                    response,
                    parse_mode=constants.ParseMode.MARKDOWN_V2
                )
            else:
                await update.message.reply_text(
                    f"Шаблон '{template_name}' не найден\\. Используйте /template для списка доступных шаблонов\\.",
                    parse_mode=constants.ParseMode.MARKDOWN_V2
                )
        else:
            # List all templates
            templates = list_all_templates()
            
            if not templates:
                await update.message.reply_text(
                    "Шаблоны пока не настроены\\.",
                    parse_mode=constants.ParseMode.MARKDOWN_V2
                )
                return
            
            response = "*Доступные шаблоны:*\\n\\n"
            for template in templates:
                desc = template.get('description', '').replace('.', '\\.').replace('-', '\\-').replace('!', '\\!')
                response += f"• _{template['template_name']}_"
                if desc:
                    response += f" \\- {desc}"
                response += "\\n"
            
            response += "\\nИспользуйте `/template <название>` для просмотра шаблона\\."
            
            await update.message.reply_text(
                response,
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
    
    except Exception as e:
        logger.error(f"Error loading template: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Ошибка при загрузке шаблона\\.",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Show validation help information.
    Handler for /help_validate command.
    
    Args:
        update: Telegram update object
        context: Telegram context
    """
    # Check if user is authorized
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(
            messages.MESSAGE_PLEASE_ENTER_INVITE,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return
    
    # Update user info
    update_user_info_from_telegram(update.effective_user)
    
    await update.message.reply_text(
        messages.MESSAGE_VALIDATION_HELP,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )


async def cancel_validation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Cancel validation conversation.
    Handler for /cancel command during validation.
    
    Args:
        update: Telegram update object
        context: Telegram context
        
    Returns:
        ConversationHandler.END
    """
    await update.message.reply_text(
        "Проверка заявки отменена\\.",
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    return ConversationHandler.END
