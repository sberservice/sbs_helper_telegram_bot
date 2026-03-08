"""Сервис LLM-классификации сообщений Group Knowledge как вопросов."""

import json
import logging
import time
from dataclasses import dataclass
from typing import Optional

from config import ai_settings
from src.core.ai.llm_provider import get_provider
from src.group_knowledge.settings import MIN_QUESTION_LENGTH

logger = logging.getLogger(__name__)

QUESTION_CLASSIFICATION_PROMPT = """Ты определяешь, является ли сообщение однозначно вопросом для технической поддержки.

Правила:
1. Считай вопросом только явные вопросы, пусть даже без вопросительного знака.
2. Если ты не уверен, что это вопрос, классифицируй как НЕ ВОПРОС. Не угадывай и не классифицируй как вопрос сомнительные случаи.
3. Благодарности, отчёты о том, что всё работает, шутки и обычные утверждения без запроса помощи — не вопрос.
4. Если в сообщении написано, что надо предпринять какое-то действие, это НЕ вопрос. Явный запрос на выполнение действие - НЕ ВОПРОС.
5. Если сообщение является подписью к изображению (`has_image=true`), это сильный сигнал, что пользователь показывает проблему и ожидает помощь даже без `?`.
6. Но подпись к изображению НЕ является вопросом автоматически: фотоотчёт, результат работы, благодарность и простое описание без запроса помощи — это НЕ ВОПРОС.
7. Если пользователь уточняет что-то у другого пользователя, например "зачем тебе", то это НЕ вопрос.
8. Отчёт о проблеме, отчёт о несоответствии - это вопрос. 

Верни JSON:
{{
    "is_question": true/false,
    "confidence": 0.0-1.0,
    "reason": "краткая причина"
}}

МЕТАДАННЫЕ СООБЩЕНИЯ:
{message_metadata}

СООБЩЕНИЕ ПОЛЬЗОВАТЕЛЯ:
{message}

"""


@dataclass
class QuestionClassificationResult:
    """Результат классификации сообщения как вопроса."""

    is_question: bool
    confidence: float
    reason: str = ""
    model_used: str = ""
    detected_at: int = 0


class QuestionClassifierService:
    """LLM-классификатор сообщений для определения вопроса."""

    def __init__(self, model_name: Optional[str] = None):
        """Инициализация классификатора."""
        self._model_name = model_name or ai_settings.GK_RESPONDER_MODEL

    async def classify(
        self,
        text: str,
        *,
        is_caption: bool = False,
        has_image: bool = False,
        image_description: Optional[str] = None,
    ) -> QuestionClassificationResult:
        """Классифицировать сообщение как вопрос или не вопрос."""
        normalized = (text or "").strip()
        detected_at = int(time.time())
        if len(normalized) < MIN_QUESTION_LENGTH:
            return QuestionClassificationResult(
                is_question=False,
                confidence=0.0,
                reason="Сообщение слишком короткое для осмысленного вопроса",
                model_used=self._model_name,
                detected_at=detected_at,
            )

        provider = get_provider("deepseek")
        prompt = QUESTION_CLASSIFICATION_PROMPT.format(
            message_metadata=self._format_message_metadata(
                is_caption=is_caption,
                has_image=has_image,
                image_description="",
            ),
            message=normalized[:4000],
        )
        raw = await provider.chat(
            messages=[{"role": "user", "content": prompt}],
            system_prompt="Ты — классификатор сообщений технической поддержки.",
            purpose="gk_question_detection",
            model_override=self._model_name,
            response_format={"type": "json_object"},
        )
        parsed = self._parse_json_response(raw)
        if not parsed:
            raise ValueError("Классификатор вопроса вернул непарсируемый JSON")

        return QuestionClassificationResult(
            is_question=bool(parsed.get("is_question", False)),
            confidence=max(0.0, min(1.0, float(parsed.get("confidence", 0.0) or 0.0))),
            reason=str(parsed.get("reason", "") or "")[:512],
            model_used=self._model_name,
            detected_at=detected_at,
        )

    @staticmethod
    def _format_message_metadata(
        *,
        is_caption: bool,
        has_image: bool,
        image_description: Optional[str],
    ) -> str:
        """Сформировать текстовый блок метаданных сообщения для prompt-классификатора."""
        parts = [
            f"- is_caption: {'true' if is_caption else 'false'}",
            f"- has_image: {'true' if has_image else 'false'}",
        ]

        normalized_image_description = (image_description or "").strip()
        if normalized_image_description:
            parts.append(f"- image_description: {normalized_image_description[:1000]}")

        return "\n".join(parts)

    @staticmethod
    def _parse_json_response(raw: str):
        """Извлечь JSON из ответа модели."""
        if not raw or not raw.strip():
            return None

        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            if len(lines) >= 3:
                text = "\n".join(lines[1:-1])
            else:
                text = text.strip("`").strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(raw[start:end + 1])
                except json.JSONDecodeError:
                    logger.warning("Не удалось распарсить JSON классификатора вопроса")
                    return None
        return None
