"""
messages.py — сообщения модуля AI-маршрутизации.

Содержит все текстовые сообщения, используемые модулем AI-маршрутизации.
Все сообщения экранированы для MarkdownV2.
"""

import re


_RAG_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_RAG_BOLD_RE = re.compile(r"\*\*([^\n*][^\n]*?)\*\*")


def _escape_inline_code_content(text: str) -> str:
    """
    Экранировать содержимое inline-code для MarkdownV2.

    Внутри обратных кавычек в Telegram MarkdownV2 важно экранировать
    только обратный слэш и сам символ обратной кавычки.
    """
    return text.replace("\\", "\\\\").replace("`", "\\`")


def escape_markdown_v2(text: str) -> str:
    """
    Экранировать текст для Telegram MarkdownV2.

    Сначала экранируются обратные слэши, затем спецсимволы.
    Это гарантирует корректную обработку текста, содержащего
    обратные слэши (например, от LLM с предварительным экранированием).

    Args:
        text: Исходный текст для экранирования.

    Returns:
        Экранированный текст.
    """
    # Сначала экранируем обратные слэши, чтобы \! не превратился
    # в \\! (экранированный бэкслеш + неэкранированный спецсимвол)
    text = text.replace("\\", "\\\\")
    special_chars = r"_*[]()~`>#+-=|{}.!"
    return re.sub(f"([{re.escape(special_chars)}])", r"\\\1", text)


def format_rag_answer_markdown_v2(text: str) -> str:
    """
    Безопасно подготовить RAG-ответ к Telegram MarkdownV2.

    Поддерживает ограниченный набор разметки из ответов модели:
    - жирный: **текст**
    - inline-code: `код`

    Весь остальной контент экранируется как обычный MarkdownV2-текст.
    """
    if not text:
        return ""

    placeholders: dict[str, str] = {}

    def _store(token_type: str, content: str) -> str:
        token = f"RAGTOKEN{token_type}{len(placeholders)}END"
        placeholders[token] = content
        return token

    prepared = _RAG_INLINE_CODE_RE.sub(
        lambda match: _store("CODE", match.group(1)),
        text,
    )
    prepared = _RAG_BOLD_RE.sub(
        lambda match: _store("BOLD", match.group(1)),
        prepared,
    )

    escaped = escape_markdown_v2(prepared)

    for token, content in placeholders.items():
        if "CODE" in token:
            replacement = f"`{_escape_inline_code_content(content)}`"
        else:
            replacement = f"*{escape_markdown_v2(content)}*"
        escaped = escaped.replace(token, replacement)

    return escaped


# =============================================
# Сообщения для пользователей
# =============================================

MESSAGE_AI_PROCESSING = "⏳ _Обрабатываю ваш запрос\\.\\.\\._"
MESSAGE_AI_WAITING_FOR_AI = "⏳ _Ожидаю ответа ИИ_"

MESSAGE_AI_RATE_LIMITED = (
    "⚠️ *Слишком много запросов*\n\n"
    "Пожалуйста, подождите {seconds} сек\\. перед следующим запросом\\.\n"
    "Используйте кнопки меню для быстрого доступа к функциям\\."
)

MESSAGE_AI_UNAVAILABLE = (
    "⚠️ *AI\\-помощник временно недоступен*\n\n"
    "Используйте кнопки меню для навигации по функциям бота\\."
)

MESSAGE_AI_ERROR = (
    "❌ *Ошибка обработки запроса*\n\n"
    "Попробуйте позже или используйте кнопки меню\\."
)

MESSAGE_AI_MODULE_DISABLED = (
    "⚠️ *Модуль «{module_name}» временно отключён*\n\n"
    "Обратитесь к администратору или попробуйте другой запрос\\."
)

MESSAGE_AI_LOW_CONFIDENCE = (
    "🤔 Я не совсем уверен, что вы имеете в виду\\.\n"
    "Попробуйте перефразировать или используйте кнопки меню\\."
)

MESSAGE_MODULE_DISABLED_BUTTON = (
    "⚠️ *Модуль временно отключён*\n\n"
    "Этот модуль деактивирован администратором\\. "
    "Используйте другие доступные функции из главного меню\\."
)

# =============================================
# Сообщения для chat-ответов
# =============================================

MESSAGE_AI_CHAT_PREFIX = "🤖 "

# =============================================
# Форматирование
# =============================================


def format_rate_limit_message(seconds_remaining: int) -> str:
    """
    Отформатировать сообщение об ограничении частоты.

    Args:
        seconds_remaining: Оставшееся время ожидания в секундах.

    Returns:
        Готовое MarkdownV2 сообщение.
    """
    return MESSAGE_AI_RATE_LIMITED.format(seconds=str(seconds_remaining))


def format_ai_chat_response(text: str) -> str:
    """
    Отформатировать свободный ответ AI для отправки в Telegram.

    Args:
        text: Текст ответа от LLM.

    Returns:
        Экранированный для MarkdownV2 текст с префиксом.
    """
    escaped = escape_markdown_v2(text)
    return f"{MESSAGE_AI_CHAT_PREFIX}{escaped}"


def format_module_disabled_message(module_name: str) -> str:
    """
    Отформатировать сообщение об отключённом модуле.

    Args:
        module_name: Название модуля.

    Returns:
        MarkdownV2-сообщение.
    """
    escaped_name = escape_markdown_v2(module_name)
    return MESSAGE_AI_MODULE_DISABLED.format(module_name=escaped_name)
