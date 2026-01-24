"""
Ticket Validator Bot Handlers

Telegram bot handlers for ticket validation functionality.
"""

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from telegram import constants
import logging

from src.common.telegram_user import check_if_user_legit, check_if_user_admin, update_user_info_from_telegram
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

# Debug mode key for user_data
DEBUG_MODE_KEY = 'validator_debug_mode'


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
    
    # Check if debug mode is enabled for this admin user
    is_admin = check_if_user_admin(user_id)
    debug_enabled = is_admin and context.user_data.get(DEBUG_MODE_KEY, False)
    
    # Load ticket types and detect which type this ticket is
    try:
        ticket_types = load_all_ticket_types()
        detected_type, debug_info = detect_ticket_type(
            ticket_text, 
            ticket_types, 
            debug=debug_enabled
        ) if ticket_types else (None, None)
        
        # Send debug info first if enabled
        if debug_enabled and debug_info:
            debug_message = format_debug_info_for_telegram(debug_info)
            await update.message.reply_text(
                debug_message,
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
        
        # Check if ticket type was detected
        if not detected_type:
            await update.message.reply_text(
                "⚠️ *Не удалось определить тип заявки*\n\n"
                "Пожалуйста, убедитесь что заявка соответствует одному из известных форматов\\.\n"
                "Используйте /template для просмотра доступных шаблонов\\.",
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
            return ConversationHandler.END
        
        # Load validation rules for detected type
        rules = load_rules_from_db(ticket_type_id=detected_type.id)
        
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
            response = f"✅ *Заявка прошла валидацию\\!*\n\n🎫 Тип заявки: _{_escape_md(detected_type.type_name)}_\n\nВсе обязательные поля заполнены корректно\\."
            await update.message.reply_text(
                response,
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=get_validator_submenu_keyboard()
            )
        else:
            # Format error messages
            errors_formatted = "\\n".join([
                f"• {msg.replace('.', '\\.').replace('-', '\\-').replace('!', '\\!').replace('(', '\\(').replace(')', '\\)')}"
                for msg in result.error_messages
            ])
            
            response = messages.MESSAGE_VALIDATION_FAILED.format(errors=errors_formatted)
            # Add detected ticket type to error message
            response = response.replace("*Заявка не прошла валидацию*", 
                                      f"*Заявка не прошла валидацию*\n\n🎫 Тип заявки: _{_escape_md(detected_type.type_name)}_")
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


async def toggle_debug_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Toggle debug mode for ticket type detection.
    Only available for admin users.
    
    Args:
        update: Telegram update object
        context: Telegram context
    """
    user_id = update.effective_user.id
    
    # Check if user is authorized
    if not check_if_user_legit(user_id):
        await update.message.reply_text(
            messages.MESSAGE_PLEASE_ENTER_INVITE,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return
    
    # Check if user is admin
    if not check_if_user_admin(user_id):
        await update.message.reply_text(
            messages.MESSAGE_DEBUG_MODE_NOT_ADMIN,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return
    
    # Toggle debug mode
    current_state = context.user_data.get(DEBUG_MODE_KEY, False)
    new_state = not current_state
    context.user_data[DEBUG_MODE_KEY] = new_state
    
    if new_state:
        await update.message.reply_text(
            messages.MESSAGE_DEBUG_MODE_ENABLED,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
    else:
        await update.message.reply_text(
            messages.MESSAGE_DEBUG_MODE_DISABLED,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )


def format_debug_info_for_telegram(debug_info) -> str:
    """
    Format DetectionDebugInfo for Telegram message.
    
    Args:
        debug_info: DetectionDebugInfo object
        
    Returns:
        Formatted string safe for MarkdownV2
    """
    lines = []
    lines.append("🔍 *DEBUG: Определение типа заявки*")
    lines.append("")
    
    if debug_info.detected_type:
        lines.append(f"✅ *Определён тип:* {_escape_md(debug_info.detected_type.type_name)}")
    else:
        lines.append("❌ *Тип не определён*")
    
    lines.append(f"📊 Оценено типов: {debug_info.total_types_evaluated}")
    lines.append("")
    lines.append("*Результаты по типам:*")
    
    # Sort by score descending
    sorted_scores = sorted(debug_info.all_scores, key=lambda x: x.total_score, reverse=True)
    
    for score_info in sorted_scores:
        type_name = _escape_md(score_info.ticket_type.type_name)
        # Escape decimal points and minus signs in numeric values
        total_score_str = str(score_info.total_score).replace('.', '\\.').replace('-', '\\-')
        match_pct_str = f"{score_info.match_percentage:.1f}".replace('.', '\\.')
        
        lines.append("")
        lines.append(f"📋 *{type_name}*")
        lines.append(f"   Счёт: {total_score_str}")
        lines.append(f"   Совпало: {score_info.matched_keywords_count}/{score_info.total_keywords_count} \\({match_pct_str}%\\)")
        
        if score_info.keyword_matches:
            lines.append("   Ключевые слова:")
            for match in score_info.keyword_matches[:5]:  # Limit to 5 keywords to avoid too long messages
                keyword = _escape_md(match.keyword)
                weight_str = str(match.weight).replace('.', '\\.')
                score_str = str(match.weighted_score).replace('.', '\\.').replace('-', '\\-')
                # Use different indicator for negative keywords
                indicator = "⊖" if match.is_negative else "⊕"
                lines.append(f"     {indicator} '{keyword}': {match.count}x \\(вес: {weight_str}, счёт: {score_str}\\)")
            if len(score_info.keyword_matches) > 5:
                lines.append(f"     _\\.\\.\\.и ещё {len(score_info.keyword_matches) - 5}_")
    
    return "\n".join(lines)


def _escape_md(text: str) -> str:
    """Escape special characters for MarkdownV2."""
    if text is None:
        return ""
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = str(text).replace(char, f'\\{char}')
    return text
