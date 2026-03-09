"""Утилиты подготовки текста вопросов для RAG в Group Knowledge."""

from typing import Optional

from src.group_knowledge.models import GroupMessage


def enrich_question_for_rag(
    question_text: str,
    source_message: Optional[GroupMessage],
    enabled: bool,
) -> str:
    """Добавить gist изображения к вопросу только для задач RAG при включённом флаге."""
    base_question = (question_text or "").strip()
    if not base_question and source_message is not None:
        base_question = (source_message.full_text or "").strip()
    if not base_question:
        return ""

    if not enabled or source_message is None:
        return base_question

    image_gist = (source_message.image_description or "").strip()
    if not image_gist:
        return base_question

    normalized_question = " ".join(base_question.lower().split())
    normalized_gist = " ".join(image_gist.lower().split())
    if normalized_gist and normalized_gist in normalized_question:
        return base_question

    return f"{base_question}\n[Суть по изображению: {image_gist[:1200]}]"