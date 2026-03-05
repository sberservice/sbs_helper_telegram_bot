"""Генерация summary документов через LLM для тестирования промптов.

Использует LLMProvider из ai_router для вызовов к DeepSeek API.
Поддерживает кастомные system_prompt + user_message + model + temperature.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, List, Optional

from src.sbs_helper_telegram_bot.ai_router import settings as ai_settings

logger = logging.getLogger(__name__)

# Максимальная длина excerpt для summary (совпадает с RagKnowledgeService)
_DEFAULT_MAX_INPUT_CHARS = 12000
_DEFAULT_MAX_SUMMARY_CHARS = 1200


def build_summary_excerpt(chunks: List[str], max_chars: Optional[int] = None) -> str:
    """Собрать ограниченный по длине фрагмент документа для суммаризации.

    Логика идентична RagKnowledgeService._build_summary_excerpt().

    Args:
        chunks: Список текстовых чанков документа.
        max_chars: Ограничение по символам (по умолчанию из settings).

    Returns:
        Склеенный фрагмент документа.
    """
    if not chunks:
        return ""

    limit = max(500, int(max_chars or ai_settings.AI_RAG_SUMMARY_INPUT_MAX_CHARS))
    collected: List[str] = []
    current_len = 0

    for chunk in chunks:
        normalized_chunk = (chunk or "").strip()
        if not normalized_chunk:
            continue

        remaining = limit - current_len
        if remaining <= 0:
            break

        piece = normalized_chunk[:remaining]
        if piece:
            collected.append(piece)
            current_len += len(piece)

    return "\n\n".join(collected).strip()


def normalize_summary_text(summary_text: str, max_chars: Optional[int] = None) -> str:
    """Нормализовать текст summary.

    Логика идентична RagKnowledgeService._normalize_summary_text().
    """
    normalized = re.sub(r"\\s+", " ", (summary_text or "").strip())
    if not normalized:
        return ""
    limit = max(200, int(max_chars or ai_settings.AI_RAG_SUMMARY_MAX_CHARS))
    return normalized[:limit].strip()


def render_system_prompt(
    template: str,
    document_name: str,
    document_excerpt: str,
    max_summary_chars: Optional[int] = None,
) -> str:
    """Подставить переменные в шаблон system prompt.

    Доступные плейсхолдеры:
    - {document_name} — имя документа
    - {document_excerpt} — фрагмент содержимого
    - {max_summary_chars} — ограничение длины summary

    Args:
        template: Шаблон system prompt.
        document_name: Имя документа.
        document_excerpt: Фрагмент содержимого.
        max_summary_chars: Ограничение длины summary.

    Returns:
        Готовый system prompt.
    """
    max_chars = int(max_summary_chars or ai_settings.AI_RAG_SUMMARY_MAX_CHARS)
    try:
        return template.format(
            document_name=document_name,
            document_excerpt=document_excerpt,
            max_summary_chars=max_chars,
        )
    except KeyError as exc:
        logger.warning("Неизвестный плейсхолдер в шаблоне: %s", exc)
        # Fallback: подставляем что можем
        result = template
        result = result.replace("{document_name}", document_name)
        result = result.replace("{document_excerpt}", document_excerpt)
        result = result.replace("{max_summary_chars}", str(max_chars))
        return result


async def generate_summary(
    *,
    system_prompt_template: str,
    user_message: str,
    document_name: str,
    chunks: List[str],
    model_name: Optional[str] = None,
    temperature: Optional[float] = None,
    max_summary_chars: Optional[int] = None,
) -> Dict[str, Any]:
    """Сгенерировать summary документа с заданной конфигурацией промпта.

    Args:
        system_prompt_template: Шаблон system prompt с плейсхолдерами.
        user_message: User message для LLM.
        document_name: Имя документа.
        chunks: Чанки документа.
        model_name: Override модели (None = модель по умолчанию).
        temperature: Override температуры (None = дефолт).
        max_summary_chars: Ограничение длины summary.

    Returns:
        Словарь с ключами:
        - summary_text: str | None
        - system_prompt_used: str
        - user_message_used: str
        - model_name: str | None
        - temperature_used: float | None
        - generation_time_ms: int
        - error_message: str | None
    """
    excerpt = build_summary_excerpt(chunks)
    rendered_prompt = render_system_prompt(
        template=system_prompt_template,
        document_name=document_name,
        document_excerpt=excerpt,
        max_summary_chars=max_summary_chars,
    )

    result: Dict[str, Any] = {
        "summary_text": None,
        "system_prompt_used": rendered_prompt,
        "user_message_used": user_message,
        "model_name": model_name,
        "temperature_used": temperature,
        "generation_time_ms": 0,
        "error_message": None,
    }

    start_ts = time.monotonic()
    try:
        from src.sbs_helper_telegram_bot.ai_router.llm_provider import get_provider

        provider = get_provider()
        actual_model = model_name

        # Строим full_messages вручную и вызываем _call_api для поддержки temperature
        full_messages = [
            {"role": "system", "content": rendered_prompt},
            {"role": "user", "content": user_message},
        ]

        # Определяем температуру
        effective_temp = temperature if temperature is not None else ai_settings.LLM_CHAT_TEMPERATURE

        raw_summary = await provider._call_api(
            messages=full_messages,
            temperature=effective_temp,
            max_tokens=ai_settings.LLM_CHAT_MAX_TOKENS,
            purpose="rag_summary",
            force_model=actual_model,
        )

        elapsed_ms = int((time.monotonic() - start_ts) * 1000)
        normalized = normalize_summary_text(raw_summary, max_summary_chars)

        result["summary_text"] = normalized if normalized else raw_summary
        result["generation_time_ms"] = elapsed_ms

        # Получаем фактическое имя модели
        if actual_model:
            result["model_name"] = actual_model
        else:
            result["model_name"] = provider.get_model_name(purpose="rag_summary")

    except Exception as exc:
        elapsed_ms = int((time.monotonic() - start_ts) * 1000)
        result["generation_time_ms"] = elapsed_ms
        result["error_message"] = str(exc)
        logger.warning(
            "Ошибка генерации summary: document=%s model=%s error=%s",
            document_name, model_name, exc,
        )

    return result
