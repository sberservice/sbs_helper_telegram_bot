"""
Bot Admin Module Keyboards

Telegram keyboard builders for the bot administration module.
"""

from telegram import ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from . import settings


def get_admin_menu_keyboard() -> ReplyKeyboardMarkup:
    """
    Build bot admin main menu keyboard.
    
    Returns:
        ReplyKeyboardMarkup for admin menu
    """
    return ReplyKeyboardMarkup(
        settings.ADMIN_MENU_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_user_management_keyboard() -> ReplyKeyboardMarkup:
    """
    Build user management submenu keyboard.
    
    Returns:
        ReplyKeyboardMarkup for user management
    """
    return ReplyKeyboardMarkup(
        settings.USER_MANAGEMENT_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_preinvite_keyboard() -> ReplyKeyboardMarkup:
    """
    Build pre-invite management keyboard.
    
    Returns:
        ReplyKeyboardMarkup for pre-invite management
    """
    return ReplyKeyboardMarkup(
        settings.PREINVITE_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_statistics_keyboard() -> ReplyKeyboardMarkup:
    """
    Build statistics submenu keyboard.
    
    Returns:
        ReplyKeyboardMarkup for statistics menu
    """
    return ReplyKeyboardMarkup(
        settings.STATISTICS_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_invite_management_keyboard() -> ReplyKeyboardMarkup:
    """
    Build invite management submenu keyboard.
    
    Returns:
        ReplyKeyboardMarkup for invite management
    """
    return ReplyKeyboardMarkup(
        settings.INVITE_MANAGEMENT_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_bot_settings_keyboard() -> ReplyKeyboardMarkup:
    """
    Build bot settings submenu keyboard.
    
    Returns:
        ReplyKeyboardMarkup for bot settings menu
    """
    return ReplyKeyboardMarkup(
        settings.BOT_SETTINGS_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_manual_users_keyboard() -> ReplyKeyboardMarkup:
    """
    Build manual users management submenu keyboard.
    
    Returns:
        ReplyKeyboardMarkup for manual users management menu
    """
    return ReplyKeyboardMarkup(
        settings.MANUAL_USERS_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_invite_system_toggle_keyboard(is_enabled: bool) -> InlineKeyboardMarkup:
    """
    Build inline keyboard for invite system toggle.
    
    Args:
        is_enabled: Whether invite system is currently enabled
        
    Returns:
        InlineKeyboardMarkup for invite system toggle
    """
    if is_enabled:
        button_text = "❌ Выключить инвайт-систему"
        callback = "bot_admin_invite_system_disable"
    else:
        button_text = "✅ Включить инвайт-систему"
        callback = "bot_admin_invite_system_enable"
    
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(button_text, callback_data=callback)],
        [InlineKeyboardButton("🔙 Назад", callback_data="bot_admin_settings_menu")]
    ])


def get_ai_model_toggle_keyboard(
    classification_model: str,
    response_model: str,
    html_splitter_enabled: bool,
) -> InlineKeyboardMarkup:
    """
    Build inline keyboard for switching DeepSeek model mode.

    Args:
        classification_model: Модель для классификации intent.
        response_model: Модель для ответов (chat/RAG).
        html_splitter_enabled: Флаг включения HTML header-splitter для RAG.

    Returns:
        InlineKeyboardMarkup with model switch actions.
    """
    class_is_chat = classification_model == "deepseek-chat"
    class_is_reasoner = classification_model == "deepseek-reasoner"
    response_is_chat = response_model == "deepseek-chat"
    response_is_reasoner = response_model == "deepseek-reasoner"

    class_chat_label = f"{'✅' if class_is_chat else '⚪️'} Классификация: deepseek-chat"
    class_reasoner_label = f"{'✅' if class_is_reasoner else '⚪️'} Классификация: deepseek-reasoner"
    response_chat_label = f"{'✅' if response_is_chat else '⚪️'} Ответы/RAG: deepseek-chat"
    response_reasoner_label = f"{'✅' if response_is_reasoner else '⚪️'} Ответы/RAG: deepseek-reasoner"
    html_splitter_label = (
        "✅ HTML splitter: включён"
        if html_splitter_enabled
        else "❌ HTML splitter: выключен"
    )
    html_splitter_callback = (
        "bot_admin_ai_html_splitter_disable"
        if html_splitter_enabled
        else "bot_admin_ai_html_splitter_enable"
    )

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(class_chat_label, callback_data="bot_admin_ai_model_class_chat")],
        [InlineKeyboardButton(class_reasoner_label, callback_data="bot_admin_ai_model_class_reasoner")],
        [InlineKeyboardButton(response_chat_label, callback_data="bot_admin_ai_model_response_chat")],
        [InlineKeyboardButton(response_reasoner_label, callback_data="bot_admin_ai_model_response_reasoner")],
        [InlineKeyboardButton(html_splitter_label, callback_data=html_splitter_callback)],
        [InlineKeyboardButton("🔙 Назад", callback_data="bot_admin_settings_menu")],
    ])


def get_modules_management_keyboard() -> ReplyKeyboardMarkup:
    """
    Build modules management submenu keyboard.
    
    Returns:
        ReplyKeyboardMarkup for modules management menu
    """
    return ReplyKeyboardMarkup(
        settings.MODULES_MANAGEMENT_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_planned_outages_keyboard() -> ReplyKeyboardMarkup:
    """
    Build planned outages submenu keyboard.

    Returns:
        ReplyKeyboardMarkup for planned outages menu
    """
    return ReplyKeyboardMarkup(
        settings.PLANNED_OUTAGES_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_planned_outage_type_keyboard() -> ReplyKeyboardMarkup:
    """
    Build outage type selection keyboard.

    Returns:
        ReplyKeyboardMarkup for outage type selection
    """
    return ReplyKeyboardMarkup(
        settings.PLANNED_OUTAGE_TYPE_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_confirm_delete_outage_keyboard(outage_id: int) -> InlineKeyboardMarkup:
    """
    Build confirmation keyboard for deleting a planned outage.

    Args:
        outage_id: Outage ID to delete

    Returns:
        InlineKeyboardMarkup for confirmation
    """
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Да, удалить", callback_data=f"bot_admin_outage_confirm_delete_{outage_id}"),
            InlineKeyboardButton("❌ Отмена", callback_data="bot_admin_outage_cancel_delete"),
        ]
    ])


def get_modules_toggle_keyboard(module_states: dict) -> InlineKeyboardMarkup:
    """
    Build inline keyboard for toggling modules on/off.
    
    Args:
        module_states: Dictionary mapping module_key to enabled state
        
    Returns:
        InlineKeyboardMarkup for module toggles
    """
    from src.common.bot_settings import MODULE_NAMES
    
    buttons = []
    for module_key, is_enabled in module_states.items():
        module_name = MODULE_NAMES.get(module_key, module_key)
        status = "✅" if is_enabled else "❌"
        action = "disable" if is_enabled else "enable"
        buttons.append([
            InlineKeyboardButton(
                f"{status} {module_name}",
                callback_data=f"bot_admin_module_{action}_{module_key}"
            )
        ])
    
    buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="bot_admin_settings_menu")])
    
    return InlineKeyboardMarkup(buttons)


def get_user_details_keyboard(user_id: int, is_admin: bool, is_self: bool = False) -> InlineKeyboardMarkup:
    """
    Build inline keyboard for user details view.
    
    Args:
        user_id: The user's Telegram ID
        is_admin: Whether the user is currently an admin
        is_self: Whether viewing own profile
        
    Returns:
        InlineKeyboardMarkup for user management actions
    """
    buttons = []
    
    if not is_self:
        if is_admin:
            buttons.append([
                InlineKeyboardButton("❌ Отозвать админа", callback_data=f"bot_admin_revoke_{user_id}")
            ])
        else:
            buttons.append([
                InlineKeyboardButton("👑 Назначить админом", callback_data=f"bot_admin_grant_{user_id}")
            ])
    
    buttons.append([
        InlineKeyboardButton("🎁 Выдать инвайты", callback_data=f"bot_admin_issue_invites_{user_id}")
    ])
    
    buttons.append([
        InlineKeyboardButton("🔙 К списку", callback_data="bot_admin_user_list")
    ])
    
    return InlineKeyboardMarkup(buttons)


def get_preinvite_details_keyboard(telegram_id: int) -> InlineKeyboardMarkup:
    """
    Build inline keyboard for pre-invite details view.
    
    Args:
        telegram_id: The pre-invited user's Telegram ID
        
    Returns:
        InlineKeyboardMarkup for pre-invite management actions
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑️ Удалить", callback_data=f"bot_admin_preinvite_delete_{telegram_id}")],
        [InlineKeyboardButton("🔙 К списку", callback_data="bot_admin_preinvite_list")]
    ])


def get_confirm_delete_preinvite_keyboard(telegram_id: int) -> InlineKeyboardMarkup:
    """
    Build confirmation keyboard for deleting a pre-invite.
    
    Args:
        telegram_id: The pre-invited user's Telegram ID
        
    Returns:
        InlineKeyboardMarkup for confirmation
    """
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Да, удалить", callback_data=f"bot_admin_preinvite_confirm_delete_{telegram_id}"),
            InlineKeyboardButton("❌ Отмена", callback_data="bot_admin_preinvite_cancel_delete")
        ]
    ])


def get_manual_user_details_keyboard(telegram_id: int) -> InlineKeyboardMarkup:
    """
    Build inline keyboard for manual user details view.
    
    Args:
        telegram_id: The manual user's Telegram ID
        
    Returns:
        InlineKeyboardMarkup for manual user management actions
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑️ Удалить", callback_data=f"bot_admin_manual_delete_{telegram_id}")],
        [InlineKeyboardButton("🔙 К списку", callback_data="bot_admin_manual_list")]
    ])


def get_confirm_delete_manual_user_keyboard(telegram_id: int) -> InlineKeyboardMarkup:
    """
    Build confirmation keyboard for deleting a manual user.
    
    Args:
        telegram_id: The manual user's Telegram ID
        
    Returns:
        InlineKeyboardMarkup for confirmation
    """
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Да, удалить", callback_data=f"bot_admin_manual_confirm_delete_{telegram_id}"),
            InlineKeyboardButton("❌ Отмена", callback_data="bot_admin_manual_cancel_delete")
        ]
    ])


def get_confirm_admin_action_keyboard(user_id: int, action: str) -> InlineKeyboardMarkup:
    """
    Build confirmation keyboard for admin grant/revoke.
    
    Args:
        user_id: The user's Telegram ID
        action: Either 'grant' or 'revoke'
        
    Returns:
        InlineKeyboardMarkup for confirmation
    """
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Да", callback_data=f"bot_admin_confirm_{action}_{user_id}"),
            InlineKeyboardButton("❌ Отмена", callback_data=f"bot_admin_user_view_{user_id}")
        ]
    ])


def get_pagination_keyboard(current_page: int, total_pages: int, callback_prefix: str) -> list:
    """
    Build pagination buttons for lists.
    
    Args:
        current_page: Current page number (1-based)
        total_pages: Total number of pages
        callback_prefix: Prefix for callback data
        
    Returns:
        List of InlineKeyboardButton for pagination
    """
    buttons = []
    
    if current_page > 1:
        buttons.append(InlineKeyboardButton("◀️", callback_data=f"{callback_prefix}_page_{current_page - 1}"))
    
    buttons.append(InlineKeyboardButton(f"{current_page}/{total_pages}", callback_data="bot_admin_noop"))
    
    if current_page < total_pages:
        buttons.append(InlineKeyboardButton("▶️", callback_data=f"{callback_prefix}_page_{current_page + 1}"))
    
    return buttons
