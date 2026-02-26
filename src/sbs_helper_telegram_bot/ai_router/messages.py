"""
messages.py — сообщения модуля AI-маршрутизации.

Содержит все текстовые сообщения, используемые модулем AI-маршрутизации.
Все сообщения экранированы для MarkdownV2.
"""

import re
from typing import Callable, Dict, Optional


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

    placeholders: dict[str, tuple[str, str]] = {}

    def _store(token_type: str, content: str) -> str:
        token = f"RAGTOKEN{token_type}{len(placeholders)}END"
        placeholders[token] = (token_type, content)
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

    for token, (token_type, content) in reversed(list(placeholders.items())):
        if token_type == "CODE":
            replacement = f"`{_escape_inline_code_content(content)}`"
        else:
            replacement = f"*{escape_markdown_v2(content)}*"
        escaped = escaped.replace(token, replacement)

    return escaped


# =============================================
# Сообщения для пользователей
# =============================================

MESSAGE_AI_PROCESSING = "⏳ _Пытаюсь понять запрос\\.\\.\\._"
MESSAGE_AI_WAITING_FOR_AI = "⏳ _Ожидаю ответа ИИ_"
MESSAGE_AI_PREFILTERING_DOCUMENTS = "⏳ _Подбираю подходящие материалы из базы знаний\._"
MESSAGE_AI_REQUESTING_AUGMENTED_PAYLOAD = "⏳ _Собираю контекст и отправляю запрос ИИ\._"

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
# Ключи сообщений и этапы прогресса
# =============================================

AI_MESSAGE_KEY_PROCESSING = "placeholder.processing"
AI_MESSAGE_KEY_WAITING_FOR_AI = "placeholder.waiting_for_ai"
AI_MESSAGE_KEY_PREFILTERING_DOCUMENTS = "placeholder.prefiltering_documents"
AI_MESSAGE_KEY_REQUESTING_AUGMENTED_PAYLOAD = "placeholder.requesting_augmented_payload"
AI_MESSAGE_KEY_STATUS_LOW_CONFIDENCE = "status.low_confidence"
AI_MESSAGE_KEY_STATUS_ERROR = "status.error"
AI_MESSAGE_KEY_STATUS_CIRCUIT_OPEN = "status.circuit_open"

AI_PROGRESS_STAGE_RAG_PREFILTER_STARTED = "rag_prefilter_started"
AI_PROGRESS_STAGE_RAG_AUGMENTED_REQUEST_STARTED = "rag_augmented_request_started"

_AI_MESSAGE_DEFAULTS: Dict[str, str] = {
    AI_MESSAGE_KEY_PROCESSING: MESSAGE_AI_PROCESSING,
    AI_MESSAGE_KEY_WAITING_FOR_AI: MESSAGE_AI_WAITING_FOR_AI,
    AI_MESSAGE_KEY_PREFILTERING_DOCUMENTS: MESSAGE_AI_PREFILTERING_DOCUMENTS,
    AI_MESSAGE_KEY_REQUESTING_AUGMENTED_PAYLOAD: MESSAGE_AI_REQUESTING_AUGMENTED_PAYLOAD,
    AI_MESSAGE_KEY_STATUS_LOW_CONFIDENCE: MESSAGE_AI_LOW_CONFIDENCE,
    AI_MESSAGE_KEY_STATUS_ERROR: MESSAGE_AI_UNAVAILABLE,
    AI_MESSAGE_KEY_STATUS_CIRCUIT_OPEN: MESSAGE_AI_UNAVAILABLE,
}

AI_STATUS_TO_MESSAGE_KEY: Dict[str, str] = {
    "low_confidence": AI_MESSAGE_KEY_STATUS_LOW_CONFIDENCE,
    "error": AI_MESSAGE_KEY_STATUS_ERROR,
    "circuit_open": AI_MESSAGE_KEY_STATUS_CIRCUIT_OPEN,
}

AI_PROGRESS_STAGE_TO_MESSAGE_KEY: Dict[str, str] = {
    AI_PROGRESS_STAGE_RAG_PREFILTER_STARTED: AI_MESSAGE_KEY_PREFILTERING_DOCUMENTS,
    AI_PROGRESS_STAGE_RAG_AUGMENTED_REQUEST_STARTED: AI_MESSAGE_KEY_REQUESTING_AUGMENTED_PAYLOAD,
}

_ai_message_resolver: Optional[Callable[[str], Optional[str]]] = None


def set_ai_message_resolver(resolver: Optional[Callable[[str], Optional[str]]]) -> None:
    """
    Установить внешний резолвер текстов AI-сообщений.

    Используется для будущего подключения источника из БД без изменения
    бизнес-логики в роутере/telegram-слое.
    """
    global _ai_message_resolver
    _ai_message_resolver = resolver


def get_ai_message_by_key(message_key: str) -> str:
    """
    Получить текст AI-сообщения по ключу с безопасным fallback.

    При наличии внешнего резолвера сначала пробуем получить текст из него,
    затем используем встроенный словарь default-значений.
    """
    if _ai_message_resolver is not None:
        try:
            resolved = _ai_message_resolver(message_key)
            if isinstance(resolved, str) and resolved.strip():
                return resolved
        except Exception:
            pass

    return _AI_MESSAGE_DEFAULTS.get(message_key, MESSAGE_AI_PROCESSING)


def get_ai_status_message(status: str) -> Optional[str]:
    """Вернуть текст fallback-сообщения для AI-статуса."""
    message_key = AI_STATUS_TO_MESSAGE_KEY.get(status)
    if not message_key:
        return None
    return get_ai_message_by_key(message_key)


def get_ai_progress_message(stage: str) -> Optional[str]:
    """Вернуть текст для отображения этапа прогресса AI/RAG."""
    message_key = AI_PROGRESS_STAGE_TO_MESSAGE_KEY.get(stage)
    if not message_key:
        return None
    return get_ai_message_by_key(message_key)

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
