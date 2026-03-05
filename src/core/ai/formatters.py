"""
formatters.py — функции форматирования и MarkdownV2-эскейпинга для AI-ответов.

Содержит переиспользуемые утилиты, не привязанные к Telegram-боту:
- escape_markdown_v2()
- format_rag_answer_markdown_v2()
- Константы этапов прогресса (AI_PROGRESS_STAGE_*) и ключей сообщений (AI_MESSAGE_KEY_*)
- Маппинги стадий на ключи сообщений

Telegram-специфичные строки сообщений (MESSAGE_AI_*, pre-escaped MarkdownV2)
остаются в src/sbs_helper_telegram_bot/ai_router/messages.py.
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
# Ключи сообщений и этапы прогресса
# =============================================

AI_MESSAGE_KEY_PROCESSING = "placeholder.processing"
AI_MESSAGE_KEY_WAITING_FOR_AI = "placeholder.waiting_for_ai"
AI_MESSAGE_KEY_PREFILTERING_DOCUMENTS = "placeholder.prefiltering_documents"
AI_MESSAGE_KEY_REQUESTING_AUGMENTED_PAYLOAD = "placeholder.requesting_augmented_payload"
AI_MESSAGE_KEY_UPOS_NOT_FOUND_FALLBACK = "placeholder.upos_not_found_fallback"
AI_MESSAGE_KEY_STATUS_LOW_CONFIDENCE = "status.low_confidence"
AI_MESSAGE_KEY_STATUS_ERROR = "status.error"
AI_MESSAGE_KEY_STATUS_CIRCUIT_OPEN = "status.circuit_open"

AI_PROGRESS_STAGE_RAG_PREFILTER_STARTED = "rag_prefilter_started"
AI_PROGRESS_STAGE_RAG_AUGMENTED_REQUEST_STARTED = "rag_augmented_request_started"
AI_PROGRESS_STAGE_RAG_CACHE_HIT = "rag_cache_hit"
AI_PROGRESS_STAGE_RAG_FALLBACK_STARTED = "rag_fallback_started"
AI_PROGRESS_STAGE_UPOS_NOT_FOUND_FALLBACK_STARTED = "upos_not_found_fallback_started"

AI_STATUS_TO_MESSAGE_KEY: Dict[str, str] = {
    "low_confidence": AI_MESSAGE_KEY_STATUS_LOW_CONFIDENCE,
    "error": AI_MESSAGE_KEY_STATUS_ERROR,
    "circuit_open": AI_MESSAGE_KEY_STATUS_CIRCUIT_OPEN,
}

AI_PROGRESS_STAGE_TO_MESSAGE_KEY: Dict[str, str] = {
    AI_PROGRESS_STAGE_RAG_CACHE_HIT: AI_MESSAGE_KEY_WAITING_FOR_AI,
    AI_PROGRESS_STAGE_RAG_PREFILTER_STARTED: AI_MESSAGE_KEY_PREFILTERING_DOCUMENTS,
    AI_PROGRESS_STAGE_RAG_AUGMENTED_REQUEST_STARTED: AI_MESSAGE_KEY_REQUESTING_AUGMENTED_PAYLOAD,
    AI_PROGRESS_STAGE_RAG_FALLBACK_STARTED: AI_MESSAGE_KEY_REQUESTING_AUGMENTED_PAYLOAD,
    AI_PROGRESS_STAGE_UPOS_NOT_FOUND_FALLBACK_STARTED: AI_MESSAGE_KEY_UPOS_NOT_FOUND_FALLBACK,
}

# =============================================
# Вспомогательные функции форматирования
# =============================================


def format_rate_limit_message(seconds_remaining: int, template: str) -> str:
    """
    Отформатировать сообщение об ограничении частоты.

    Args:
        seconds_remaining: Оставшееся время ожидания в секундах.
        template: Шаблон сообщения с placeholder {seconds}.

    Returns:
        Готовое MarkdownV2 сообщение.
    """
    return template.format(seconds=str(seconds_remaining))


def format_ai_chat_response(text: str, prefix: str = "🤖 ") -> str:
    """
    Отформатировать свободный ответ AI для отправки в Telegram.

    Args:
        text: Текст ответа от LLM.
        prefix: Префикс сообщения (по умолчанию эмодзи робота).

    Returns:
        Экранированный для MarkdownV2 текст с префиксом.
    """
    escaped = escape_markdown_v2(text)
    return f"{prefix}{escaped}"


def format_module_disabled_message(module_name: str, template: str) -> str:
    """
    Отформатировать сообщение об отключённом модуле.

    Args:
        module_name: Название модуля.
        template: Шаблон сообщения с placeholder {module_name}.

    Returns:
        MarkdownV2-сообщение.
    """
    escaped_name = escape_markdown_v2(module_name)
    return template.format(module_name=escaped_name)
