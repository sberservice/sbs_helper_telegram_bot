"""LLM-as-Judge — автоматическая оценка качества summary.

Использует LLM для попарного сравнения summary и выбора лучшего.
Порядок A/B рандомизируется для защиты от position bias.
"""

from __future__ import annotations

import json
import logging
import random
from typing import Any, Dict, Optional

from src.sbs_helper_telegram_bot.ai_router import settings as ai_settings

logger = logging.getLogger(__name__)

_JUDGE_SYSTEM_PROMPT = """Ты — экспертный оценщик качества summary документов.

Тебе дан фрагмент оригинального документа и два варианта summary (A и B).

Задача: определить, какой summary лучше отражает содержание документа.

Критерии оценки:
1. Точность — summary корректно передаёт основную тему документа.
2. Полнота — ключевые аспекты документа упомянуты.
3. Краткость — summary не содержит лишней или выдуманной информации.
4. Поисковая полезность — summary помогает найти этот документ при поиске.

Ответ СТРОГО в JSON формате:
{"winner": "A", "reasoning": "Краткое объяснение выбора на русском языке"}

Допустимые значения winner: "A", "B", "tie" (если оба одинаково хороши/плохи).
НЕ добавляй ничего помимо JSON-объекта."""

_JUDGE_USER_MESSAGE_TEMPLATE = """Имя документа: {document_name}

Фрагмент документа:
{document_excerpt}

---

Summary A:
{summary_a}

---

Summary B:
{summary_b}"""


async def judge_pair(
    *,
    document_name: str,
    document_excerpt: str,
    summary_a: str,
    summary_b: str,
    prompt_a_label: str,
    prompt_b_label: str,
) -> Dict[str, Any]:
    """Оценить пару summary через LLM-судью.

    Порядок A/B рандомизируется для защиты от position bias.

    Args:
        document_name: Имя документа.
        document_excerpt: Фрагмент документа.
        summary_a: Summary первого промпта.
        summary_b: Summary второго промпта.
        prompt_a_label: Название первого промпта (для логирования).
        prompt_b_label: Название второго промпта (для логирования).

    Returns:
        Словарь с ключами:
        - winner: "a" | "b" | "tie"
        - reasoning: str
        - was_swapped: bool — был ли порядок A/B перевёрнут
        - error: str | None
    """
    # Рандомизация порядка для защиты от position bias
    swapped = random.random() < 0.5
    if swapped:
        shown_a, shown_b = summary_b, summary_a
    else:
        shown_a, shown_b = summary_a, summary_b

    user_message = _JUDGE_USER_MESSAGE_TEMPLATE.format(
        document_name=document_name,
        document_excerpt=document_excerpt,
        summary_a=shown_a,
        summary_b=shown_b,
    )

    result: Dict[str, Any] = {
        "winner": "tie",
        "reasoning": "",
        "was_swapped": swapped,
        "error": None,
    }

    try:
        from src.sbs_helper_telegram_bot.ai_router.llm_provider import get_provider

        provider = get_provider()

        raw_response = await provider.chat(
            messages=[{"role": "user", "content": user_message}],
            system_prompt=_JUDGE_SYSTEM_PROMPT,
            purpose="prompt_tester_judge",
            response_format={"type": "json_object"},
        )

        parsed = _parse_judge_response(raw_response)
        llm_winner = parsed.get("winner", "tie").upper()
        reasoning = parsed.get("reasoning", "")

        # Преобразуем обратно с учётом рандомизации порядка
        if llm_winner == "A":
            result["winner"] = "b" if swapped else "a"
        elif llm_winner == "B":
            result["winner"] = "a" if swapped else "b"
        else:
            result["winner"] = "tie"

        result["reasoning"] = reasoning

        logger.info(
            "LLM Judge: document=%s prompt_a=%s prompt_b=%s llm_raw=%s actual_winner=%s swapped=%s",
            document_name,
            prompt_a_label,
            prompt_b_label,
            llm_winner,
            result["winner"],
            swapped,
        )

    except Exception as exc:
        result["error"] = str(exc)
        logger.warning(
            "LLM Judge ошибка: document=%s error=%s",
            document_name, exc,
        )

    return result


def _parse_judge_response(raw: str) -> Dict[str, Any]:
    """Извлечь JSON из ответа LLM-судьи с fallback."""
    raw_stripped = (raw or "").strip()
    if not raw_stripped:
        return {"winner": "tie", "reasoning": "Пустой ответ LLM"}

    try:
        return json.loads(raw_stripped)
    except json.JSONDecodeError:
        pass

    # Попытка извлечь JSON из markdown code block
    import re
    json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_stripped, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # Попытка найти JSON-объект в тексте
    json_match = re.search(r"\{[^{}]*\"winner\"[^{}]*\}", raw_stripped, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass

    logger.warning("Не удалось распарсить ответ LLM-судьи: %s", raw_stripped[:200])
    return {"winner": "tie", "reasoning": f"Не удалось распарсить: {raw_stripped[:200]}"}
