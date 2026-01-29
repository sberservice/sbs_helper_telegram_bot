"""
Feedback Module Messages

All user-facing messages for the feedback module.
Messages use Telegram MarkdownV2 format where needed.
"""
# pylint: disable=line-too-long
# Note: Double backslashes are intentional for Telegram MarkdownV2 escaping


def _escape_markdown_v2(text: str) -> str:
    """
    Escape special characters for Telegram MarkdownV2.
    
    Args:
        text: Text to escape
        
    Returns:
        Escaped text
    """
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text


# ===== USER MESSAGES =====

MESSAGE_SUBMENU = "📬 *Обратная связь*\n\nЗдесь вы можете отправить отзыв, предложение или сообщить об ошибке\\.\n\nВыберите действие:"

MESSAGE_SELECT_CATEGORY = "📂 *Выберите категорию обращения:*\n\nВыберите тип вашего сообщения\\."

MESSAGE_ENTER_MESSAGE = """📝 *Напишите ваше сообщение*

Опишите подробно вашу проблему, предложение или вопрос\\.

⚠️ *Обратите внимание:*
• Ссылки в сообщениях запрещены
• Пишите максимально понятно и подробно

Для отмены нажмите кнопку «❌ Отмена» или используйте /cancel"""

MESSAGE_LINKS_NOT_ALLOWED = "⛔ *Ссылки запрещены\\!*\n\nВаше сообщение содержит ссылки, которые не разрешены\\.\n\nПожалуйста, уберите ссылки и отправьте сообщение снова\\."

MESSAGE_CONFIRM_SUBMIT = """📋 *Проверьте ваше обращение*

*Категория:* {category}

*Сообщение:*
{message}

Отправить обращение?"""

MESSAGE_FEEDBACK_SUBMITTED = """✅ *Обращение отправлено\\!*

Ваше обращение *\\#{entry_id}* успешно зарегистрировано\\.

Мы рассмотрим его в ближайшее время и ответим вам в этом чате\\.

Вы можете отслеживать статус в разделе «📋 Мои обращения»\\."""

MESSAGE_FEEDBACK_CANCELLED = "❌ Отправка обращения отменена\\."

MESSAGE_RATE_LIMITED = """⏳ *Подождите немного*

Вы недавно отправляли обращение\\. 
Следующее обращение можно отправить через *{minutes}* мин\\.

Если у вас срочный вопрос, дождитесь ответа на предыдущее обращение\\."""

MESSAGE_MY_FEEDBACK_EMPTY = "📭 *У вас пока нет обращений*\n\nОтправьте своё первое обращение с помощью кнопки «📝 Отправить отзыв»\\."

MESSAGE_MY_FEEDBACK_LIST = "📋 *Ваши обращения*\n\nВсего: {count}\n\nНажмите на обращение для просмотра:"

MESSAGE_FEEDBACK_DETAIL = """📋 *Обращение \\#{entry_id}*

*Категория:* {category}
*Статус:* {status}
*Дата:* {date}

*Ваше сообщение:*
{message}

{responses_section}"""

MESSAGE_NO_RESPONSES = "_Ответов пока нет\\. Ожидайте\\._"

MESSAGE_RESPONSES_HEADER = "*Ответы от команды поддержки:*\n"

MESSAGE_RESPONSE_TEMPLATE = """
📨 *Ответ от {date}:*
{response}
"""

MESSAGE_NEW_RESPONSE_NOTIFICATION = """📬 *Новый ответ на ваше обращение\\!*

На ваше обращение *\\#{entry_id}* получен ответ от команды поддержки\\.

*Ответ:*
{response}

Для просмотра всех ответов перейдите в «📋 Мои обращения»\\."""

MESSAGE_STATUS_CHANGED_NOTIFICATION = """📬 *Статус обращения изменён*

Статус вашего обращения *\\#{entry_id}* изменён на: *{status}*"""

MESSAGE_CANCEL = "❌ Операция отменена\\."

MESSAGE_ERROR = "❌ Произошла ошибка\\. Попробуйте позже\\."

MESSAGE_ENTRY_NOT_FOUND = "❌ Обращение не найдено\\."


# ===== ADMIN MESSAGES =====

MESSAGE_ADMIN_NOT_AUTHORIZED = "⛔ У вас нет прав администратора\\."

MESSAGE_ADMIN_MENU = """🔐 *Управление обратной связью*

Просматривайте обращения пользователей и отвечайте на них\\.

⚠️ *Важно:* Ваши ответы отправляются анонимно от имени «Команда поддержки»\\.

Выберите действие:"""

MESSAGE_ADMIN_LIST_EMPTY = "📭 *Обращений не найдено*\n\nНет обращений, соответствующих выбранным критериям\\."

MESSAGE_ADMIN_LIST_NEW = "📥 *Новые обращения*\n\nВсего: {count}\n\nНажмите для просмотра:"

MESSAGE_ADMIN_LIST_ALL = "📊 *Все обращения*\n\nВсего: {count}\n\nНажмите для просмотра:"

MESSAGE_ADMIN_LIST_BY_CATEGORY = "📂 *Обращения по категориям*\n\nВыберите категорию:"

MESSAGE_ADMIN_ENTRY_DETAIL = """📋 *Обращение \\#{entry_id}*

*От:* `{user_id}`
*Категория:* {category}
*Статус:* {status}
*Дата:* {date}

*Сообщение пользователя:*
{message}

{responses_section}

Выберите действие:"""

MESSAGE_ADMIN_NO_RESPONSES = "_Ответов ещё не было_"

MESSAGE_ADMIN_RESPONSES_HEADER = "*История ответов:*\n"

MESSAGE_ADMIN_RESPONSE_TEMPLATE = """
📨 *{date}:*
{response}
"""

MESSAGE_ADMIN_COMPOSE_REPLY = """✏️ *Напишите ответ пользователю*

Обращение *\\#{entry_id}*

Ваш ответ будет отправлен *анонимно* от имени команды поддержки\\.

Для отмены нажмите «❌ Отмена» или используйте /cancel"""

MESSAGE_ADMIN_CONFIRM_REPLY = """📝 *Проверьте ответ*

*Обращение:* \\#{entry_id}

*Ваш ответ:*
{reply}

⚠️ Ответ будет отправлен анонимно\\. Отправить?"""

MESSAGE_ADMIN_REPLY_SENT = """✅ *Ответ отправлен\\!*

Пользователь получит уведомление о новом ответе\\.
Статус обращения изменён на «⏳ В работе»\\."""

MESSAGE_ADMIN_REPLY_CANCELLED = "❌ Отправка ответа отменена\\."

MESSAGE_ADMIN_SELECT_STATUS = """📊 *Изменить статус*

Текущий статус: *{current_status}*

Выберите новый статус:"""

MESSAGE_ADMIN_STATUS_CHANGED = "✅ Статус обращения изменён на *{status}*\\."

MESSAGE_ADMIN_CATEGORY_ENTRIES = "📂 *{category}*\n\nОбращений: {count}\n\nНажмите для просмотра:"

MESSAGE_ADMIN_ERROR = "❌ Произошла ошибка\\. Попробуйте позже\\."


# ===== HELPER FUNCTIONS =====

def format_feedback_detail(
    entry_id: int,
    category: str,
    status: str,
    date: str,
    message: str,
    responses: list
) -> str:
    """
    Format feedback detail message for user view.
    
    Args:
        entry_id: Feedback entry ID
        category: Category name
        status: Status display name
        date: Formatted date string
        message: User's message
        responses: List of response dicts with 'date' and 'text' keys
        
    Returns:
        Formatted message string
    """
    if responses:
        responses_section = MESSAGE_RESPONSES_HEADER
        for resp in responses:
            responses_section += MESSAGE_RESPONSE_TEMPLATE.format(
                date=_escape_markdown_v2(resp['date']),
                response=_escape_markdown_v2(resp['text'])
            )
    else:
        responses_section = MESSAGE_NO_RESPONSES
    
    return MESSAGE_FEEDBACK_DETAIL.format(
        entry_id=entry_id,
        category=_escape_markdown_v2(category),
        status=_escape_markdown_v2(status),
        date=_escape_markdown_v2(date),
        message=_escape_markdown_v2(message),
        responses_section=responses_section
    )


def format_admin_entry_detail(
    entry_id: int,
    user_id: int,
    category: str,
    status: str,
    date: str,
    message: str,
    responses: list
) -> str:
    """
    Format feedback detail message for admin view.
    NOTE: user_id is shown to admin for context, but NEVER in responses to user.
    
    Args:
        entry_id: Feedback entry ID
        user_id: User's Telegram ID (admin-only info)
        category: Category name
        status: Status display name
        date: Formatted date string
        message: User's message
        responses: List of response dicts with 'date' and 'text' keys
        
    Returns:
        Formatted message string
    """
    if responses:
        responses_section = MESSAGE_ADMIN_RESPONSES_HEADER
        for resp in responses:
            responses_section += MESSAGE_ADMIN_RESPONSE_TEMPLATE.format(
                date=_escape_markdown_v2(resp['date']),
                response=_escape_markdown_v2(resp['text'])
            )
    else:
        responses_section = MESSAGE_ADMIN_NO_RESPONSES
    
    return MESSAGE_ADMIN_ENTRY_DETAIL.format(
        entry_id=entry_id,
        user_id=user_id,
        category=_escape_markdown_v2(category),
        status=_escape_markdown_v2(status),
        date=_escape_markdown_v2(date),
        message=_escape_markdown_v2(message),
        responses_section=responses_section
    )


def format_rate_limit_message(seconds_remaining: int) -> str:
    """
    Format rate limit message with remaining time.
    
    Args:
        seconds_remaining: Seconds until next submission allowed
        
    Returns:
        Formatted message string
    """
    minutes = max(1, seconds_remaining // 60)
    return MESSAGE_RATE_LIMITED.format(minutes=minutes)


def format_confirm_submit(category: str, message: str) -> str:
    """
    Format confirmation message before submitting feedback.
    
    Args:
        category: Selected category name
        message: User's message text
        
    Returns:
        Formatted message string
    """
    return MESSAGE_CONFIRM_SUBMIT.format(
        category=_escape_markdown_v2(category),
        message=_escape_markdown_v2(message)
    )


def format_feedback_submitted(entry_id: int) -> str:
    """
    Format success message after feedback submission.
    
    Args:
        entry_id: Created entry ID
        
    Returns:
        Formatted message string
    """
    return MESSAGE_FEEDBACK_SUBMITTED.format(entry_id=entry_id)


def format_new_response_notification(entry_id: int, response: str) -> str:
    """
    Format notification message for user when admin replies.
    NOTE: No admin identification is included - anonymous reply.
    
    Args:
        entry_id: Feedback entry ID
        response: Admin's response text
        
    Returns:
        Formatted message string
    """
    return MESSAGE_NEW_RESPONSE_NOTIFICATION.format(
        entry_id=entry_id,
        response=_escape_markdown_v2(response)
    )


def format_status_changed_notification(entry_id: int, status: str) -> str:
    """
    Format notification message for user when status changes.
    
    Args:
        entry_id: Feedback entry ID
        status: New status display name
        
    Returns:
        Formatted message string
    """
    return MESSAGE_STATUS_CHANGED_NOTIFICATION.format(
        entry_id=entry_id,
        status=_escape_markdown_v2(status)
    )


def format_admin_confirm_reply(entry_id: int, reply: str) -> str:
    """
    Format confirmation message before sending admin reply.
    
    Args:
        entry_id: Feedback entry ID
        reply: Admin's reply text
        
    Returns:
        Formatted message string
    """
    return MESSAGE_ADMIN_CONFIRM_REPLY.format(
        entry_id=entry_id,
        reply=_escape_markdown_v2(reply)
    )
