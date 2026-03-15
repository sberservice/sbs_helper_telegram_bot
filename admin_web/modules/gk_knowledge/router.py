"""Главный роутер модуля Group Knowledge.

Собирает подроутеры всех вкладок:
- /stats — статистика
- /qa-pairs — список Q&A-пар
- /expert-validation — экспертная валидация
- /prompt-tester — тестер промптов
- /final-prompt-tester — тестер финального LLM-промпта ответа пользователю
- /image-prompt-tester — отдельный blind тестер промптов изображений
- /groups — группы
- /responder — лог автоответчика
- /images — очередь изображений
- /search — песочница поиска
- /qa-analyzer-sandbox — песочница анализатора Q&A
"""

from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
import os
import re
import threading
import tempfile
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import ai_settings
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse

from admin_web.core.models import (
    AddTermRequest,
    ChainMessage,
    ExpertValidationRequest,
    ExpertValidationStats,
    QAPairDetail,
    QAPairListResponse,
    TermDetail,
    TermListResponse,
    TermResetRequest,
    TermRecountRequest,
    TermScanRequest,
    TermValidationRequest,
    TermValidationStats,
    WebUser,
)
from admin_web.core.rbac import require_permission
import src.common.database as common_database
from src.common import app_settings
from src.core.ai.llm_provider import (
    GigaChatProvider,
    get_provider,
    get_provider_class,
    is_provider_registered,
    list_registered_provider_names,
)

logger = logging.getLogger(__name__)


GK_PROMPT_TESTER_SYSTEM_PROMPT = "Ты — помощник для анализа пар вопрос-ответ."
GK_IMAGE_PROMPT_TESTER_DEFAULT_PROMPT = (
    "Опиши изображение для инженера техподдержки: что видно, ключевые объекты, "
    "важные детали интерфейса/оборудования и возможные признаки проблемы."
)


def get_supported_deepseek_models() -> List[str]:
    """Вернуть список поддерживаемых моделей DeepSeek для выбора в UI."""
    models: List[str] = []
    for model_name in ai_settings.ALLOWED_DEEPSEEK_MODELS:
        normalized = str(model_name or "").strip()
        if normalized and normalized not in models:
            models.append(normalized)

    for extra_model in (
        ai_settings.get_active_gk_responder_model(),
        ai_settings.get_active_gk_analysis_model(),
        ai_settings.get_active_gk_question_detection_model(),
        ai_settings.get_active_gk_terms_scan_model(),
    ):
        normalized = str(extra_model or "").strip()
        if normalized and normalized not in models:
            models.append(normalized)

    return models


def get_supported_gigachat_models() -> List[str]:
    """Вернуть список поддерживаемых моделей GigaChat для image prompt tester."""
    candidates = [
        ai_settings.get_active_gk_image_description_model(),
        ai_settings.GIGACHAT_MODEL,
        "GigaChat-Pro",
        "GigaChat-Max",
    ]
    models: List[str] = []
    for model_name in candidates:
        normalized = str(model_name or "").strip()
        if normalized and normalized not in models:
            models.append(normalized)
    return models


def _normalize_provider_name(value: Any) -> str:
    """Нормализовать имя провайдера для хранения в настройках."""
    return str(value or "").strip().lower()


def _normalize_model_name(value: Any) -> str:
    """Нормализовать имя модели для хранения в настройках."""
    return str(value or "").strip()


def _build_text_provider_model_options() -> Dict[str, List[str]]:
    """Собрать список рекомендованных моделей для текстовых провайдеров GK."""
    options: Dict[str, List[str]] = {}
    if is_provider_registered("deepseek"):
        options["deepseek"] = get_supported_deepseek_models()
    if is_provider_registered("gigachat"):
        options["gigachat"] = []
    return options


def _build_image_provider_model_options() -> Dict[str, List[str]]:
    """Собрать список рекомендованных моделей для vision-провайдеров GK."""
    options: Dict[str, List[str]] = {}
    if is_provider_registered("gigachat"):
        options["gigachat"] = get_supported_gigachat_models()
    if is_provider_registered("deepseek"):
        options["deepseek"] = []
    return options


async def _describe_uploaded_image_for_search(upload: UploadFile) -> str:
    """Описать загруженное изображение для песочницы поиска GK."""
    filename = (upload.filename or "image").strip() or "image"
    content_type = str(upload.content_type or "").strip().lower()
    if content_type and not content_type.startswith("image/"):
        raise HTTPException(400, "Поддерживаются только изображения")

    image_bytes = await upload.read()
    if not image_bytes:
        raise HTTPException(400, "Файл изображения пустой")
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(400, "Слишком большой файл изображения (макс. 10 MB)")

    logger.info(
        "GK search sandbox image: received filename=%s content_type=%s size_bytes=%d",
        filename,
        content_type or "unknown",
        len(image_bytes),
    )

    suffix = Path(filename).suffix or ".jpg"
    temp_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(image_bytes)
            temp_path = tmp.name

        provider_name = ai_settings.get_active_gk_image_provider()
        provider_class = get_provider_class(provider_name)
        if provider_class is None:
            logger.warning(
                "GK search sandbox image: провайдер '%s' не найден, fallback на gigachat",
                provider_name,
            )
            provider_name = "gigachat"
            provider_class = get_provider_class(provider_name)
        if provider_class is None:
            raise HTTPException(500, "Vision-провайдер для описания изображения недоступен")

        model_name = ai_settings.get_active_gk_image_description_model()
        try:
            provider = provider_class(model=model_name)
        except TypeError:
            provider = provider_class()

        if not hasattr(provider, "describe_image"):
            raise HTTPException(
                400,
                f"Провайдер '{provider_name}' не поддерживает описание изображений",
            )

        description = await provider.describe_image(
            temp_path,
            ai_settings.GK_IMAGE_DESCRIPTION_PROMPT,
        )
        logger.info(
            "GK search sandbox image: description generated filename=%s description_len=%d",
            filename,
            len(str(description or "")),
        )
        return str(description or "").strip()
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Ошибка описания изображения в поисковой песочнице: %s", exc, exc_info=True)
        raise HTTPException(500, "Не удалось описать изображение для поиска") from exc
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def _render_gk_user_prompt(template: str, source_row: Dict[str, Any], chain_context: str) -> str:
    """Подставить значения в пользовательский промпт для генерации Q&A."""
    values = {
        "pair_id": source_row.get("id", ""),
        "group_id": source_row.get("group_id", ""),
        "question": (source_row.get("question_text") or "").strip(),
        "answer": (source_row.get("answer_text") or "").strip(),
        "chain_context": chain_context,
        "thread_context": chain_context,
        "question_confidence_threshold": (
            f"{ai_settings.get_active_gk_analysis_question_confidence_threshold():.2f}"
        ),
    }

    try:
        return template.format(**values)
    except KeyError:
        rendered = template
        for key, value in values.items():
            rendered = rendered.replace(f"{{{key}}}", str(value))
        return rendered


def _normalize_generation_text(value: Any, limit: int = 6000) -> str:
    """Нормализовать и ограничить текстовые поля генерации."""
    normalized = re.sub(r"\s+", " ", str(value or "")).strip()
    return normalized[:limit]


def _normalize_final_tester_questions(body: Dict[str, Any]) -> List[str]:
    """Нормализовать список вопросов для final prompt tester.

    Поддерживает два формата:
    - `questions`: массив строк
    - `questions_text`: многострочный текст, один вопрос на строку
    """
    questions: List[str] = []

    raw_questions = body.get("questions")
    if isinstance(raw_questions, list):
        for item in raw_questions:
            q = str(item or "").strip()
            if q and q not in questions:
                questions.append(q[:1200])

    questions_text = str(body.get("questions_text") or "").strip()
    if questions_text:
        for line in questions_text.splitlines():
            q = re.sub(r"\s+", " ", line).strip()
            if q and q not in questions:
                questions.append(q[:1200])

    return questions


def _extract_generated_pair(raw_response: str) -> Optional[Dict[str, Any]]:
    """Извлечь question/answer/confidence из JSON-ответа модели."""
    if not raw_response or not raw_response.strip():
        return None

    text = raw_response.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if len(lines) >= 3 else text.strip("`").strip()

    parsed: Optional[Dict[str, Any]] = None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                parsed = json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                return None
    if not isinstance(parsed, dict):
        return None

    question = _normalize_generation_text(parsed.get("question") or parsed.get("clean_question"))
    answer = _normalize_generation_text(parsed.get("answer") or parsed.get("clean_answer"))
    if not question or not answer:
        return None

    confidence_value = parsed.get("confidence", 0.5)
    try:
        confidence = float(confidence_value)
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))

    return {
        "question": question,
        "answer": answer,
        "confidence": confidence,
    }


def _format_chain_context(chain_messages: List[Dict[str, Any]], fallback_row: Dict[str, Any]) -> str:
    """Собрать читаемый контекст цепочки для передачи в пользовательский промпт."""
    lines: List[str] = []
    for message in chain_messages:
        sender = message.get("sender_name") or f"User_{message.get('sender_id')}"
        body = (message.get("message_text") or "").strip()
        caption = (message.get("caption") or "").strip()
        image_desc = (message.get("image_description") or "").strip()
        chunks = [chunk for chunk in [body, caption, image_desc] if chunk]
        if not chunks:
            continue
        text = _normalize_generation_text(" | ".join(chunks), limit=1000)
        lines.append(f"[{message.get('telegram_message_id')}] {sender}: {text}")

    if lines:
        return "\n".join(lines)

    question = (fallback_row.get("question_text") or "").strip()
    answer = (fallback_row.get("answer_text") or "").strip()
    return f"Вопрос: {question}\nОтвет: {answer}"


async def _generate_gk_prompt_tester_session(
    *,
    session_id: int,
    prompts_snapshot: List[Dict[str, Any]],
    source_rows: List[Dict[str, Any]],
) -> None:
    """Сгенерировать Q&A для всех промптов и подготовить A/B-сравнения сессии.

    Важно: тестовые генерации сохраняются только в `gk_prompt_tester_generations`
    и никогда не пишутся в основную таблицу `gk_qa_pairs`.
    """
    from admin_web.modules.gk_knowledge import db_expert_validation as ev_db
    from admin_web.modules.gk_knowledge import db_prompt_tester as pt_db

    provider_name = ai_settings.get_active_gk_text_provider()
    if not is_provider_registered(provider_name):
        logger.warning(
            "GK Prompt Tester: провайдер '%s' не зарегистрирован, используем deepseek",
            provider_name,
        )
        provider_name = "deepseek"
    provider = get_provider(provider_name)
    generated_count = 0
    skipped_rows = 0

    try:
        active_prompts = [
            prompt_cfg
            for prompt_cfg in prompts_snapshot
            if (prompt_cfg.get("user_prompt") or "").strip()
        ]

        if len(active_prompts) < 2:
            logger.warning(
                "GK Prompt Tester: недостаточно валидных промптов для сравнений: session=%d active_prompts=%d",
                session_id,
                len(active_prompts),
            )

        for source_row in source_rows:
            pair_id = int(source_row.get("id") or 0)
            chain_messages: List[Dict[str, Any]] = ev_db.get_chain_messages(pair_id) if pair_id else []
            chain_context = _format_chain_context(chain_messages, source_row)
            row_generations: List[Dict[str, Any]] = []
            row_failed = False

            for prompt_cfg in active_prompts:
                user_template = (prompt_cfg.get("user_prompt") or "").strip()

                prompt_text = _render_gk_user_prompt(user_template, source_row, chain_context)
                raw = await provider.chat(
                    messages=[{"role": "user", "content": prompt_text}],
                    system_prompt=GK_PROMPT_TESTER_SYSTEM_PROMPT,
                    purpose="gk_inference",
                    model_override=prompt_cfg.get("model_name"),
                    temperature_override=prompt_cfg.get("temperature"),
                    response_format={"type": "json_object"},
                )

                parsed = _extract_generated_pair(raw)
                if not parsed:
                    logger.warning(
                        "GK Prompt Tester: невалидная генерация, пропуск всей цепочки: session=%d pair_id=%s prompt_id=%s",
                        session_id,
                        source_row.get("id"),
                        prompt_cfg.get("id"),
                    )
                    row_failed = True
                    break

                row_generations.append(
                    {
                        "prompt_id": int(prompt_cfg["id"]),
                        "question_text": parsed["question"],
                        "answer_text": parsed["answer"],
                        "confidence": parsed["confidence"],
                        "extraction_type": str(prompt_cfg.get("extraction_type") or "llm_inferred"),
                        "raw_llm_response": raw,
                    }
                )
                await asyncio.sleep(0.15)

            if row_failed or len(row_generations) != len(active_prompts):
                skipped_rows += 1
                continue

            for generation in row_generations:
                pt_db.save_generation(
                    session_id=session_id,
                    prompt_id=generation["prompt_id"],
                    question_text=generation["question_text"],
                    answer_text=generation["answer_text"],
                    confidence=generation["confidence"],
                    extraction_type=generation["extraction_type"],
                    raw_llm_response=generation["raw_llm_response"],
                )
                generated_count += 1

        comparisons_count = pt_db.create_comparisons_for_session(session_id)
        final_status = "judging" if comparisons_count > 0 else "completed"
        pt_db.update_session_status(session_id, final_status)
        logger.info(
            "GK Prompt Tester: генерация завершена: session=%d generations=%d skipped_rows=%d comparisons=%d status=%s",
            session_id,
            generated_count,
            skipped_rows,
            comparisons_count,
            final_status,
        )
    except Exception as exc:
        logger.error(
            "GK Prompt Tester: ошибка генерации сессии %d: %s",
            session_id,
            exc,
            exc_info=True,
        )
        pt_db.update_session_status(session_id, "abandoned")


async def _generate_gk_final_prompt_tester_session(
    *,
    session_id: int,
    prompts_snapshot: List[Dict[str, Any]],
    questions: List[str],
    source_group_id: Optional[int],
) -> None:
    """Сгенерировать финальные ответы по вопросам и подготовить blind A/B сравнения."""
    from admin_web.modules.gk_knowledge import db_final_prompt_tester as fpt_db
    from admin_web.modules.gk_knowledge import search_service as gk_search_service

    generated_count = 0

    try:
        service = gk_search_service.get_search_service()

        active_prompts = [
            prompt_cfg
            for prompt_cfg in prompts_snapshot
            if (prompt_cfg.get("prompt_template") or "").strip()
        ]

        active_prompts.sort(
            key=lambda prompt_cfg: 0 if "reasoner" in str(prompt_cfg.get("model_name") or "").strip().lower() else 1,
        )

        if len(active_prompts) < 2:
            logger.warning(
                "GK Final Prompt Tester: недостаточно валидных промптов для сравнений: session=%d active_prompts=%d",
                session_id,
                len(active_prompts),
            )

        top_k = int(ai_settings.get_active_gk_responder_top_k())
        for question_index, question in enumerate(questions):
            user_question = str(question or "").strip()
            if not user_question:
                continue

            try:
                relevant_pairs = await service.search(
                    user_question,
                    top_k=top_k,
                    group_id=source_group_id,
                )
            except Exception as exc:
                logger.error(
                    "GK Final Prompt Tester: ошибка retrieval для session=%d question_index=%d: %s",
                    session_id,
                    question_index,
                    exc,
                    exc_info=True,
                )
                continue

            retrieved_pair_ids = [int(pair.id) for pair in relevant_pairs if getattr(pair, "id", None)]

            for prompt_cfg in active_prompts:
                prompt_id = int(prompt_cfg.get("id") or 0)
                if prompt_id <= 0:
                    continue

                prompt_template = str(prompt_cfg.get("prompt_template") or "").strip()
                model_name = str(prompt_cfg.get("model_name") or "").strip() or None
                temperature = float(prompt_cfg.get("temperature") or 0.3)

                try:
                    answer_result = await service.answer_question_from_pairs(
                        user_question,
                        relevant_pairs,
                        group_id=source_group_id,
                        model_override=model_name,
                        temperature_override=temperature,
                        prompt_template_override=prompt_template,
                        return_non_relevant=True,
                    )
                except Exception as exc:
                    logger.error(
                        "GK Final Prompt Tester: ошибка генерации session=%d question_index=%d prompt_id=%d: %s",
                        session_id,
                        question_index,
                        prompt_id,
                        exc,
                        exc_info=True,
                    )
                    answer_result = None

                fpt_db.save_generation(
                    session_id=session_id,
                    prompt_id=prompt_id,
                    question_index=question_index,
                    user_question=user_question,
                    retrieved_pair_ids=retrieved_pair_ids,
                    answer_text=(str((answer_result or {}).get("answer") or "").strip() or None),
                    is_relevant=bool((answer_result or {}).get("is_relevant", False)),
                    confidence=(
                        float((answer_result or {}).get("confidence"))
                        if (answer_result or {}).get("confidence") is not None
                        else None
                    ),
                    confidence_reason=(str((answer_result or {}).get("confidence_reason") or "").strip() or None),
                    used_pair_ids=[int(pid) for pid in ((answer_result or {}).get("source_pair_ids") or []) if isinstance(pid, int)],
                    model_used=model_name,
                    temperature_used=temperature,
                    llm_request_payload=(answer_result or {}).get("llm_request_payload"),
                    raw_llm_response=None,
                )
                generated_count += 1
                await asyncio.sleep(0.12)

        comparisons_count = fpt_db.create_comparisons_for_session(session_id)
        final_status = "judging" if comparisons_count > 0 else "completed"
        fpt_db.update_session_status(session_id, final_status)
        logger.info(
            "GK Final Prompt Tester: генерация завершена: session=%d generations=%d comparisons=%d status=%s",
            session_id,
            generated_count,
            comparisons_count,
            final_status,
        )
    except Exception as exc:
        logger.error(
            "GK Final Prompt Tester: ошибка генерации сессии %d: %s",
            session_id,
            exc,
            exc_info=True,
        )
        fpt_db.update_session_status(session_id, "abandoned")


def _spawn_gk_final_prompt_tester_generation(
    *,
    session_id: int,
    prompts_snapshot: List[Dict[str, Any]],
    questions: List[str],
    source_group_id: Optional[int],
) -> None:
    """Запустить генерацию final prompt tester в отдельном daemon-thread."""

    def _runner() -> None:
        try:
            asyncio.run(
                _generate_gk_final_prompt_tester_session(
                    session_id=session_id,
                    prompts_snapshot=prompts_snapshot,
                    questions=questions,
                    source_group_id=source_group_id,
                )
            )
        except Exception as exc:
            logger.error(
                "GK Final Prompt Tester: фоновый поток завершился с ошибкой session=%d: %s",
                session_id,
                exc,
                exc_info=True,
            )

    thread = threading.Thread(
        target=_runner,
        name=f"gk-final-prompt-session-{session_id}",
        daemon=True,
    )
    thread.start()


async def _generate_gk_image_prompt_tester_session(
    *,
    session_id: int,
    prompts_snapshot: List[Dict[str, Any]],
    source_rows: List[Dict[str, Any]],
) -> None:
    """Сгенерировать описания изображений и подготовить blind A/B сравнения сессии."""
    from admin_web.modules.gk_knowledge import db_image_prompt_tester as ipt_db

    providers: Dict[str, Any] = {}
    generated_count = 0

    try:
        for source_row in source_rows:
            image_queue_id = int(source_row.get("id") or 0)
            image_path_raw = str(source_row.get("image_path") or "").strip()
            if image_queue_id <= 0 or not image_path_raw:
                continue

            image_path = Path(image_path_raw).expanduser().resolve()
            if not image_path.is_file():
                logger.warning(
                    "GK Image Prompt Tester: файл изображения отсутствует: session=%d image_queue_id=%d path=%s",
                    session_id,
                    image_queue_id,
                    image_path,
                )
                continue

            for prompt_cfg in prompts_snapshot:
                prompt_id = int(prompt_cfg.get("id") or 0)
                prompt_text = str(prompt_cfg.get("prompt_text") or "").strip()
                if prompt_id <= 0 or not prompt_text:
                    continue

                model_name = (
                    str(prompt_cfg.get("model_name") or "").strip()
                    or ai_settings.get_active_gk_image_description_model()
                )
                provider_key = f"{ai_settings.get_active_gk_image_provider()}::{model_name}"
                provider = providers.get(provider_key)
                if provider is None:
                    provider_name = ai_settings.get_active_gk_image_provider()
                    provider_class = get_provider_class(provider_name)
                    if provider_class is None:
                        logger.warning(
                            "GK Image Prompt Tester: провайдер '%s' не найден, используем gigachat",
                            provider_name,
                        )
                        provider_class = GigaChatProvider

                    try:
                        provider = provider_class(model=model_name)
                    except TypeError:
                        provider = provider_class()

                    if not hasattr(provider, "describe_image"):
                        logger.warning(
                            "GK Image Prompt Tester: провайдер '%s' не поддерживает describe_image, используем gigachat",
                            provider_name,
                        )
                        provider = GigaChatProvider(model=model_name)

                    providers[provider_key] = provider

                raw_response: Optional[str] = None
                try:
                    raw_response = await provider.describe_image(
                        image_path=str(image_path),
                        prompt=prompt_text,
                    )
                    generated_text = str(raw_response or "").strip()
                except Exception as exc:
                    logger.error(
                        "GK Image Prompt Tester: ошибка генерации session=%d image_queue_id=%d prompt_id=%d model=%s: %s",
                        session_id,
                        image_queue_id,
                        prompt_id,
                        model_name,
                        exc,
                        exc_info=True,
                    )
                    generated_text = f"[Ошибка генерации] {exc}"

                if not generated_text:
                    generated_text = "[Пустой ответ модели]"

                ipt_db.save_generation(
                    session_id=session_id,
                    prompt_id=prompt_id,
                    image_queue_id=image_queue_id,
                    image_path=str(image_path),
                    generated_text=generated_text,
                    model_used=model_name,
                    raw_llm_response=raw_response,
                )
                generated_count += 1
                await asyncio.sleep(0.15)

        comparisons_count = ipt_db.create_comparisons_for_session(session_id)
        final_status = "judging" if comparisons_count > 0 else "completed"
        ipt_db.update_session_status(session_id, final_status)
        logger.info(
            "GK Image Prompt Tester: генерация завершена: session=%d generations=%d comparisons=%d status=%s",
            session_id,
            generated_count,
            comparisons_count,
            final_status,
        )
    except Exception as exc:
        logger.error(
            "GK Image Prompt Tester: ошибка генерации сессии %d: %s",
            session_id,
            exc,
            exc_info=True,
        )
        ipt_db.update_session_status(session_id, "abandoned")


def _row_to_pair_detail(row: Dict[str, Any]) -> QAPairDetail:
    """Преобразовать строку БД в QAPairDetail."""
    created_at = row.get("created_at")
    if isinstance(created_at, (int, float)):
        created_at = datetime.fromtimestamp(created_at).isoformat()
    elif isinstance(created_at, datetime):
        created_at = created_at.isoformat()

    expert_validated_at = row.get("expert_validated_at")
    if isinstance(expert_validated_at, datetime):
        expert_validated_at = expert_validated_at.isoformat()

    return QAPairDetail(
        id=row["id"],
        question_text=row["question_text"],
        answer_text=row["answer_text"],
        question_message_id=row.get("question_message_id"),
        answer_message_id=row.get("answer_message_id"),
        group_id=row.get("group_id"),
        extraction_type=row.get("extraction_type", ""),
        confidence=float(row.get("confidence", 0.0)),
        llm_model_used=row.get("llm_model_used"),
        llm_request_payload=row.get("llm_request_payload"),
        created_at=created_at,
        approved=row.get("approved", 1),
        expert_status=row.get("expert_status"),
        expert_validated_at=expert_validated_at,
        existing_verdict=row.get("existing_verdict"),
        existing_comment=row.get("existing_comment"),
    )


def _row_to_chain_message(row: Dict[str, Any]) -> ChainMessage:
    """Преобразовать строку gk_messages в ChainMessage."""
    return ChainMessage(
        telegram_message_id=row["telegram_message_id"],
        sender_name=row.get("sender_name"),
        sender_id=row.get("sender_id"),
        message_text=row.get("message_text"),
        caption=row.get("caption"),
        image_description=row.get("image_description"),
        has_image=bool(row.get("has_image", 0)),
        reply_to_message_id=row.get("reply_to_message_id"),
        message_date=row.get("message_date", 0),
        is_question=row.get("is_question"),
        question_confidence=row.get("question_confidence"),
    )


def _timestamp_to_iso(value: Any) -> Optional[str]:
    """Нормализовать timestamp/datetime к ISO-строке."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value).isoformat()
        except Exception:
            return None
    text = str(value).strip()
    return text or None


def _normalize_overview_payload(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Привести overview-статистику к контракту frontend-вкладки «Статистика»."""
    messages = raw.get("messages") if isinstance(raw.get("messages"), dict) else {}
    qa_pairs = raw.get("qa_pairs") if isinstance(raw.get("qa_pairs"), dict) else {}
    responder = raw.get("responder") if isinstance(raw.get("responder"), dict) else {}
    images = raw.get("images") if isinstance(raw.get("images"), dict) else {}

    return {
        "total_messages": int(messages.get("total") or raw.get("total_messages") or 0),
        "total_qa_pairs": int(qa_pairs.get("total") or raw.get("total_qa_pairs") or 0),
        "total_responder_entries": int(responder.get("total") or raw.get("total_responder_entries") or 0),
        "total_images": int(images.get("total") or raw.get("total_images") or 0),
        "messages_with_questions": int(messages.get("questions") or raw.get("messages_with_questions") or 0),
        "qa_pairs_approved": int(qa_pairs.get("expert_approved") or raw.get("qa_pairs_approved") or 0),
        "qa_pairs_rejected": int(qa_pairs.get("expert_rejected") or raw.get("qa_pairs_rejected") or 0),
        "qa_pairs_validated": int(
            (qa_pairs.get("expert_approved") or 0) + (qa_pairs.get("expert_rejected") or 0)
            if isinstance(qa_pairs, dict)
            else (raw.get("qa_pairs_validated") or 0)
        ),
        "qa_pairs_unvalidated": int(qa_pairs.get("expert_unvalidated") or raw.get("qa_pairs_unvalidated") or 0),
        "qa_pairs_vector_indexed": int(qa_pairs.get("vector_indexed") or raw.get("qa_pairs_vector_indexed") or 0),
    }


def _normalize_timeline_payload(raw: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Привести timeline-данные к полю `dates` с `date/messages/qa_pairs`."""
    messages = raw.get("messages") if isinstance(raw.get("messages"), list) else []
    qa_pairs = raw.get("qa_pairs") if isinstance(raw.get("qa_pairs"), list) else []

    merged: Dict[str, Dict[str, Any]] = {}
    for row in messages:
        day = str(row.get("day") or "")
        if not day:
            continue
        bucket = merged.setdefault(day, {"date": day, "messages": 0, "qa_pairs": 0})
        bucket["messages"] = int(row.get("message_count") or row.get("messages") or 0)

    for row in qa_pairs:
        day = str(row.get("day") or "")
        if not day:
            continue
        bucket = merged.setdefault(day, {"date": day, "messages": 0, "qa_pairs": 0})
        bucket["qa_pairs"] = int(row.get("pair_count") or row.get("qa_pairs") or 0)

    dates = [merged[key] for key in sorted(merged.keys())]
    return {"dates": dates}


def _normalize_distribution_payload(raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Привести распределение уверенности к полям `range_label`/`count`."""
    normalized: List[Dict[str, Any]] = []
    for row in raw:
        normalized.append(
            {
                "range_label": row.get("range_label") or row.get("confidence_range") or "—",
                "count": int(row.get("count") or 0),
            }
        )
    return normalized


def _normalize_group_payload(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Привести карточку группы к ожидаемому frontend-формату."""
    return {
        "group_id": raw.get("group_id"),
        "group_title": raw.get("group_title"),
        "message_count": int(raw.get("message_count") or 0),
        "sender_count": int(raw.get("sender_count") or 0),
        "question_pct": float(raw.get("question_pct") or 0.0),
        "pair_count": int(raw.get("pair_count") or 0),
        "validated_count": int(raw.get("validated_count") or 0),
        "first_message_date": _timestamp_to_iso(raw.get("first_message_date") or raw.get("first_message_ts")),
        "last_message_date": _timestamp_to_iso(raw.get("last_message_date") or raw.get("last_message_ts")),
    }


def _normalize_group_detail_payload(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Привести детальную статистику группы к плоскому контракту frontend."""
    qa_pairs = raw.get("qa_pairs") if isinstance(raw.get("qa_pairs"), dict) else {}

    return {
        "group_id": raw.get("group_id"),
        "group_title": raw.get("group_title"),
        "message_count": int(raw.get("message_count") or 0),
        "sender_count": int(raw.get("sender_count") or 0),
        "pair_count": int(raw.get("pair_count") or qa_pairs.get("total") or 0),
        "validated_count": int(raw.get("validated_count") or (qa_pairs.get("expert_approved") or 0) + (qa_pairs.get("expert_rejected") or 0)),
        "qa_thread_reply": int(raw.get("qa_thread_reply") or qa_pairs.get("thread_reply") or 0),
        "qa_llm_inferred": int(raw.get("qa_llm_inferred") or qa_pairs.get("llm_inferred") or 0),
        "responder_count": int(raw.get("responder_count") or 0),
        "image_count": int(raw.get("image_count") or 0),
        "question_pct": float(raw.get("question_pct") or 0.0),
        "first_message_date": _timestamp_to_iso(raw.get("first_message_date") or raw.get("first_message_ts")),
        "last_message_date": _timestamp_to_iso(raw.get("last_message_date") or raw.get("last_message_ts")),
    }


def _normalize_responder_summary_payload(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Привести сводку автоответчика к контракту frontend."""
    total_entries = int(raw.get("total_entries") or raw.get("total") or 0)
    return {
        "total_entries": total_entries,
        "total": total_entries,
        "live_count": int(raw.get("live_count") or 0),
        "dry_run_count": int(raw.get("dry_run_count") or 0),
        "avg_confidence": float(raw.get("avg_confidence") or 0.0),
        "first_response_ts": raw.get("first_response_ts"),
        "last_response_ts": raw.get("last_response_ts"),
    }


def _parse_date_boundaries(
    date_from: Optional[str],
    date_to: Optional[str],
) -> tuple[Optional[int], Optional[int]]:
    """Преобразовать YYYY-MM-DD границы в UNIX timestamp (включительно)."""
    from_ts: Optional[int] = None
    to_ts: Optional[int] = None

    if date_from:
        try:
            from_dt = datetime.strptime(date_from, "%Y-%m-%d")
            from_ts = int(from_dt.timestamp())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Некорректная date_from: {date_from}") from exc

    if date_to:
        try:
            to_dt = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1) - timedelta(seconds=1)
            to_ts = int(to_dt.timestamp())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Некорректная date_to: {date_to}") from exc

    if from_ts is not None and to_ts is not None and from_ts > to_ts:
        raise HTTPException(status_code=400, detail="date_from не может быть больше date_to")

    return from_ts, to_ts


def build_gk_router() -> APIRouter:
    """Собрать главный роутер с подмаршрутами всех вкладок."""
    router = APIRouter(tags=["gk-knowledge"])

    # Подключить подроутеры
    router.include_router(_build_stats_router(), prefix="/stats")
    router.include_router(_build_qa_pairs_router(), prefix="/qa-pairs")
    router.include_router(_build_expert_validation_router(), prefix="/expert-validation")
    router.include_router(_build_prompt_tester_router(), prefix="/prompt-tester")
    router.include_router(_build_final_prompt_tester_router(), prefix="/final-prompt-tester")
    router.include_router(_build_groups_router(), prefix="/groups")
    router.include_router(_build_messages_router(), prefix="/messages")
    router.include_router(_build_responder_router(), prefix="/responder")
    router.include_router(_build_images_router(), prefix="/images")
    router.include_router(_build_image_prompt_tester_router(), prefix="/image-prompt-tester")
    router.include_router(_build_search_router(), prefix="/search")
    router.include_router(_build_qa_analyzer_sandbox_router(), prefix="/qa-analyzer-sandbox")
    router.include_router(_build_terms_router(), prefix="/terms")
    router.include_router(_build_settings_router(), prefix="/settings")
    router.include_router(_build_rag_router(), prefix="/rag")

    return router


# ---------------------------------------------------------------------------
# Подроутер: Настройки моделей/провайдеров GK
# ---------------------------------------------------------------------------


def _build_settings_router() -> APIRouter:
    """Подроутер runtime-настроек LLM-провайдера и моделей Group Knowledge."""
    router = APIRouter(tags=["gk-settings"])

    @router.get("/llm")
    async def get_llm_settings(
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> Dict[str, Any]:
        """Вернуть текущие LLM-настройки GK и рекомендованные списки для UI."""
        text_providers = list_registered_provider_names()
        image_providers = list_registered_provider_names()

        return {
            "text_provider": ai_settings.get_active_gk_text_provider(),
            "text_provider_options": text_providers,
            "text_model_options_by_provider": _build_text_provider_model_options(),
            "text_models": {
                "analysis": ai_settings.get_active_gk_analysis_model(),
                "responder": ai_settings.get_active_gk_responder_model(),
                "question_detection": ai_settings.get_active_gk_question_detection_model(),
                "terms_scan": ai_settings.get_active_gk_terms_scan_model(),
            },
            "image_provider": ai_settings.get_active_gk_image_provider(),
            "image_provider_options": image_providers,
            "image_model_options_by_provider": _build_image_provider_model_options(),
            "image_model": ai_settings.get_active_gk_image_description_model(),
            "main_settings": {
                "responder": {
                    "confidence_threshold": ai_settings.get_active_gk_responder_confidence_threshold(),
                    "top_k": ai_settings.get_active_gk_responder_top_k(),
                    "temperature": ai_settings.get_active_gk_responder_temperature(),
                    "include_llm_inferred_answers": ai_settings.get_active_gk_include_llm_inferred_answers(),
                    "exclude_low_tier_from_llm_context": ai_settings.get_active_gk_exclude_low_tier_from_llm_context(),
                },
                "analysis": {
                    "question_confidence_threshold": ai_settings.get_active_gk_analysis_question_confidence_threshold(),
                    "temperature": ai_settings.get_active_gk_analysis_temperature(),
                    "question_detection_temperature": ai_settings.get_active_gk_question_detection_temperature(),
                    "generate_llm_inferred_qa_pairs": ai_settings.get_active_gk_generate_llm_inferred_qa_pairs(),
                },
                "terms": {
                    "acronyms_max_prompt_terms": ai_settings.get_active_gk_acronyms_max_prompt_terms(),
                    "scan_temperature": ai_settings.get_active_gk_terms_scan_temperature(),
                },
                "search": {
                    "hybrid_enabled": ai_settings.get_active_gk_hybrid_enabled(),
                    "relevance_hints_enabled": ai_settings.get_active_gk_relevance_hints_enabled(),
                    "candidates_per_method": ai_settings.get_active_gk_search_candidates_per_method(),
                },
            },
        }

    @router.put("/llm")
    async def update_llm_settings(
        body: Dict[str, Any],
        user: WebUser = Depends(require_permission("gk_knowledge", "edit")),
    ) -> Dict[str, Any]:
        """Обновить runtime-настройки LLM-провайдера и моделей GK."""
        updated_keys: List[str] = []

        if "text_provider" in body:
            text_provider = _normalize_provider_name(body.get("text_provider"))
            if not text_provider:
                raise HTTPException(400, "text_provider не может быть пустым")
            if not is_provider_registered(text_provider):
                raise HTTPException(
                    400,
                    f"Провайдер '{text_provider}' не зарегистрирован",
                )
            app_settings.set_setting(
                ai_settings.GK_TEXT_PROVIDER_SETTING_KEY,
                text_provider,
                user.telegram_id,
            )
            updated_keys.append(ai_settings.GK_TEXT_PROVIDER_SETTING_KEY)

        if "image_provider" in body:
            image_provider = _normalize_provider_name(body.get("image_provider"))
            if not image_provider:
                raise HTTPException(400, "image_provider не может быть пустым")
            if not is_provider_registered(image_provider):
                raise HTTPException(
                    400,
                    f"Провайдер '{image_provider}' не зарегистрирован",
                )
            app_settings.set_setting(
                ai_settings.GK_IMAGE_PROVIDER_SETTING_KEY,
                image_provider,
                user.telegram_id,
            )
            updated_keys.append(ai_settings.GK_IMAGE_PROVIDER_SETTING_KEY)

        text_model_map = {
            "analysis": ai_settings.GK_ANALYSIS_MODEL_SETTING_KEY,
            "responder": ai_settings.GK_RESPONDER_MODEL_SETTING_KEY,
            "question_detection": ai_settings.GK_QUESTION_DETECTION_MODEL_SETTING_KEY,
            "terms_scan": ai_settings.GK_TERMS_SCAN_MODEL_SETTING_KEY,
        }

        text_models_raw = body.get("text_models")
        if text_models_raw is not None:
            if not isinstance(text_models_raw, dict):
                raise HTTPException(400, "text_models должен быть объектом")

            for model_key, setting_key in text_model_map.items():
                if model_key not in text_models_raw:
                    continue
                model_name = _normalize_model_name(text_models_raw.get(model_key))
                if not model_name:
                    raise HTTPException(400, f"text_models.{model_key} не может быть пустым")
                app_settings.set_setting(setting_key, model_name, user.telegram_id)
                updated_keys.append(setting_key)

        if "image_model" in body:
            image_model = _normalize_model_name(body.get("image_model"))
            if not image_model:
                raise HTTPException(400, "image_model не может быть пустым")
            app_settings.set_setting(
                ai_settings.GK_IMAGE_DESCRIPTION_MODEL_SETTING_KEY,
                image_model,
                user.telegram_id,
            )
            updated_keys.append(ai_settings.GK_IMAGE_DESCRIPTION_MODEL_SETTING_KEY)

        main_settings_raw = body.get("main_settings")
        if main_settings_raw is not None:
            if not isinstance(main_settings_raw, dict):
                raise HTTPException(400, "main_settings должен быть объектом")

            responder_settings_raw = main_settings_raw.get("responder")
            if responder_settings_raw is not None:
                if not isinstance(responder_settings_raw, dict):
                    raise HTTPException(400, "main_settings.responder должен быть объектом")

                if "confidence_threshold" in responder_settings_raw:
                    raw_value = responder_settings_raw.get("confidence_threshold")
                    try:
                        confidence_threshold = float(raw_value)
                    except (TypeError, ValueError) as exc:
                        raise HTTPException(
                            400,
                            "main_settings.responder.confidence_threshold должен быть числом",
                        ) from exc
                    if not 0.0 <= confidence_threshold <= 1.0:
                        raise HTTPException(
                            400,
                            "main_settings.responder.confidence_threshold должен быть в диапазоне 0..1",
                        )
                    app_settings.set_setting(
                        ai_settings.GK_RESPONDER_CONFIDENCE_THRESHOLD_SETTING_KEY,
                        str(confidence_threshold),
                        user.telegram_id,
                    )
                    updated_keys.append(ai_settings.GK_RESPONDER_CONFIDENCE_THRESHOLD_SETTING_KEY)

                if "top_k" in responder_settings_raw:
                    raw_value = responder_settings_raw.get("top_k")
                    try:
                        top_k = int(raw_value)
                    except (TypeError, ValueError) as exc:
                        raise HTTPException(
                            400,
                            "main_settings.responder.top_k должен быть целым числом",
                        ) from exc
                    if not 1 <= top_k <= 100:
                        raise HTTPException(
                            400,
                            "main_settings.responder.top_k должен быть в диапазоне 1..100",
                        )
                    app_settings.set_setting(
                        ai_settings.GK_RESPONDER_TOP_K_SETTING_KEY,
                        str(top_k),
                        user.telegram_id,
                    )
                    updated_keys.append(ai_settings.GK_RESPONDER_TOP_K_SETTING_KEY)

                if "temperature" in responder_settings_raw:
                    raw_value = responder_settings_raw.get("temperature")
                    try:
                        temperature = float(raw_value)
                    except (TypeError, ValueError) as exc:
                        raise HTTPException(
                            400,
                            "main_settings.responder.temperature должен быть числом",
                        ) from exc
                    if not 0.0 <= temperature <= 2.0:
                        raise HTTPException(
                            400,
                            "main_settings.responder.temperature должен быть в диапазоне 0..2",
                        )
                    app_settings.set_setting(
                        ai_settings.GK_RESPONDER_TEMPERATURE_SETTING_KEY,
                        str(temperature),
                        user.telegram_id,
                    )
                    updated_keys.append(ai_settings.GK_RESPONDER_TEMPERATURE_SETTING_KEY)

                if "include_llm_inferred_answers" in responder_settings_raw:
                    include_llm_inferred_answers = bool(
                        responder_settings_raw.get("include_llm_inferred_answers")
                    )
                    app_settings.set_setting(
                        ai_settings.GK_INCLUDE_LLM_INFERRED_ANSWERS_SETTING_KEY,
                        "1" if include_llm_inferred_answers else "0",
                        user.telegram_id,
                    )
                    updated_keys.append(ai_settings.GK_INCLUDE_LLM_INFERRED_ANSWERS_SETTING_KEY)

                if "exclude_low_tier_from_llm_context" in responder_settings_raw:
                    exclude_low_tier_from_llm_context = bool(
                        responder_settings_raw.get("exclude_low_tier_from_llm_context")
                    )
                    app_settings.set_setting(
                        ai_settings.GK_EXCLUDE_LOW_TIER_FROM_LLM_CONTEXT_SETTING_KEY,
                        "1" if exclude_low_tier_from_llm_context else "0",
                        user.telegram_id,
                    )
                    updated_keys.append(ai_settings.GK_EXCLUDE_LOW_TIER_FROM_LLM_CONTEXT_SETTING_KEY)

            analysis_settings_raw = main_settings_raw.get("analysis")
            if analysis_settings_raw is not None:
                if not isinstance(analysis_settings_raw, dict):
                    raise HTTPException(400, "main_settings.analysis должен быть объектом")

                if "question_confidence_threshold" in analysis_settings_raw:
                    raw_value = analysis_settings_raw.get("question_confidence_threshold")
                    try:
                        question_confidence_threshold = float(raw_value)
                    except (TypeError, ValueError) as exc:
                        raise HTTPException(
                            400,
                            "main_settings.analysis.question_confidence_threshold должен быть числом",
                        ) from exc
                    if not 0.0 <= question_confidence_threshold <= 1.0:
                        raise HTTPException(
                            400,
                            "main_settings.analysis.question_confidence_threshold должен быть в диапазоне 0..1",
                        )
                    app_settings.set_setting(
                        ai_settings.GK_ANALYSIS_QUESTION_CONFIDENCE_THRESHOLD_SETTING_KEY,
                        str(question_confidence_threshold),
                        user.telegram_id,
                    )
                    updated_keys.append(ai_settings.GK_ANALYSIS_QUESTION_CONFIDENCE_THRESHOLD_SETTING_KEY)

                if "temperature" in analysis_settings_raw:
                    raw_value = analysis_settings_raw.get("temperature")
                    try:
                        temperature = float(raw_value)
                    except (TypeError, ValueError) as exc:
                        raise HTTPException(
                            400,
                            "main_settings.analysis.temperature должен быть числом",
                        ) from exc
                    if not 0.0 <= temperature <= 2.0:
                        raise HTTPException(
                            400,
                            "main_settings.analysis.temperature должен быть в диапазоне 0..2",
                        )
                    app_settings.set_setting(
                        ai_settings.GK_ANALYSIS_TEMPERATURE_SETTING_KEY,
                        str(temperature),
                        user.telegram_id,
                    )
                    updated_keys.append(ai_settings.GK_ANALYSIS_TEMPERATURE_SETTING_KEY)

                if "question_detection_temperature" in analysis_settings_raw:
                    raw_value = analysis_settings_raw.get("question_detection_temperature")
                    try:
                        question_detection_temperature = float(raw_value)
                    except (TypeError, ValueError) as exc:
                        raise HTTPException(
                            400,
                            "main_settings.analysis.question_detection_temperature должен быть числом",
                        ) from exc
                    if not 0.0 <= question_detection_temperature <= 2.0:
                        raise HTTPException(
                            400,
                            "main_settings.analysis.question_detection_temperature должен быть в диапазоне 0..2",
                        )
                    app_settings.set_setting(
                        ai_settings.GK_QUESTION_DETECTION_TEMPERATURE_SETTING_KEY,
                        str(question_detection_temperature),
                        user.telegram_id,
                    )
                    updated_keys.append(ai_settings.GK_QUESTION_DETECTION_TEMPERATURE_SETTING_KEY)

                if "generate_llm_inferred_qa_pairs" in analysis_settings_raw:
                    generate_llm_inferred_qa_pairs = bool(
                        analysis_settings_raw.get("generate_llm_inferred_qa_pairs")
                    )
                    app_settings.set_setting(
                        ai_settings.GK_GENERATE_LLM_INFERRED_QA_PAIRS_SETTING_KEY,
                        "1" if generate_llm_inferred_qa_pairs else "0",
                        user.telegram_id,
                    )
                    updated_keys.append(ai_settings.GK_GENERATE_LLM_INFERRED_QA_PAIRS_SETTING_KEY)

            terms_settings_raw = main_settings_raw.get("terms")
            if terms_settings_raw is not None:
                if not isinstance(terms_settings_raw, dict):
                    raise HTTPException(400, "main_settings.terms должен быть объектом")

                if "acronyms_max_prompt_terms" in terms_settings_raw:
                    raw_value = terms_settings_raw.get("acronyms_max_prompt_terms")
                    try:
                        acronyms_max_prompt_terms = int(raw_value)
                    except (TypeError, ValueError) as exc:
                        raise HTTPException(
                            400,
                            "main_settings.terms.acronyms_max_prompt_terms должен быть целым числом",
                        ) from exc
                    if not 1 <= acronyms_max_prompt_terms <= 500:
                        raise HTTPException(
                            400,
                            "main_settings.terms.acronyms_max_prompt_terms должен быть в диапазоне 1..500",
                        )
                    app_settings.set_setting(
                        ai_settings.GK_ACRONYMS_MAX_PROMPT_TERMS_SETTING_KEY,
                        str(acronyms_max_prompt_terms),
                        user.telegram_id,
                    )
                    updated_keys.append(ai_settings.GK_ACRONYMS_MAX_PROMPT_TERMS_SETTING_KEY)

                if "scan_temperature" in terms_settings_raw:
                    raw_value = terms_settings_raw.get("scan_temperature")
                    try:
                        scan_temperature = float(raw_value)
                    except (TypeError, ValueError) as exc:
                        raise HTTPException(
                            400,
                            "main_settings.terms.scan_temperature должен быть числом",
                        ) from exc
                    if not 0.0 <= scan_temperature <= 2.0:
                        raise HTTPException(
                            400,
                            "main_settings.terms.scan_temperature должен быть в диапазоне 0..2",
                        )
                    app_settings.set_setting(
                        ai_settings.GK_TERMS_SCAN_TEMPERATURE_SETTING_KEY,
                        str(scan_temperature),
                        user.telegram_id,
                    )
                    updated_keys.append(ai_settings.GK_TERMS_SCAN_TEMPERATURE_SETTING_KEY)

            search_settings_raw = main_settings_raw.get("search")
            if search_settings_raw is not None:
                if not isinstance(search_settings_raw, dict):
                    raise HTTPException(400, "main_settings.search должен быть объектом")

                if "hybrid_enabled" in search_settings_raw:
                    hybrid_enabled = bool(search_settings_raw.get("hybrid_enabled"))
                    app_settings.set_setting(
                        ai_settings.GK_HYBRID_ENABLED_SETTING_KEY,
                        "1" if hybrid_enabled else "0",
                        user.telegram_id,
                    )
                    updated_keys.append(ai_settings.GK_HYBRID_ENABLED_SETTING_KEY)

                if "relevance_hints_enabled" in search_settings_raw:
                    relevance_hints_enabled = bool(search_settings_raw.get("relevance_hints_enabled"))
                    app_settings.set_setting(
                        ai_settings.GK_RELEVANCE_HINTS_ENABLED_SETTING_KEY,
                        "1" if relevance_hints_enabled else "0",
                        user.telegram_id,
                    )
                    updated_keys.append(ai_settings.GK_RELEVANCE_HINTS_ENABLED_SETTING_KEY)

                if "candidates_per_method" in search_settings_raw:
                    raw_value = search_settings_raw.get("candidates_per_method")
                    try:
                        candidates_per_method = int(raw_value)
                    except (TypeError, ValueError) as exc:
                        raise HTTPException(
                            400,
                            "main_settings.search.candidates_per_method должен быть целым числом",
                        ) from exc
                    if not 1 <= candidates_per_method <= 200:
                        raise HTTPException(
                            400,
                            "main_settings.search.candidates_per_method должен быть в диапазоне 1..200",
                        )
                    app_settings.set_setting(
                        ai_settings.GK_SEARCH_CANDIDATES_PER_METHOD_SETTING_KEY,
                        str(candidates_per_method),
                        user.telegram_id,
                    )
                    updated_keys.append(ai_settings.GK_SEARCH_CANDIDATES_PER_METHOD_SETTING_KEY)

        if not updated_keys:
            raise HTTPException(400, "Нет полей для обновления")

        return {
            "message": "Настройки LLM Group Knowledge обновлены",
            "updated_keys": updated_keys,
        }

    return router


# ---------------------------------------------------------------------------
# Подроутер: RAG corpus statistics
# ---------------------------------------------------------------------------


def _build_rag_router() -> APIRouter:
    """Подроутер статистики RAG-корпуса для отдельной страницы RAG в admin web."""
    router = APIRouter(tags=["gk-rag"])

    @router.get("/corpus-stats")
    async def rag_corpus_stats(
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> Dict[str, Any]:
        """Вернуть максимально полный набор статистики RAG-корпуса из MySQL-таблиц."""
        stats: Dict[str, Any] = {
            "documents": {
                "total": 0,
                "active": 0,
                "archived": 0,
                "deleted": 0,
                "last_updated_at": None,
                "by_source_type": {},
            },
            "chunks": {
                "total": 0,
                "avg_per_document": 0.0,
                "max_per_document": 0,
                "last_created_at": None,
            },
            "summaries": {
                "total": 0,
                "with_model_name": 0,
                "last_updated_at": None,
            },
            "chunk_embeddings": {
                "total": 0,
                "ready": 0,
                "failed": 0,
                "stale": 0,
                "last_updated_at": None,
            },
            "summary_embeddings": {
                "total": 0,
                "ready": 0,
                "failed": 0,
                "stale": 0,
                "last_updated_at": None,
            },
            "query_log": {
                "total": 0,
                "cache_hits": 0,
                "cache_hit_ratio": 0.0,
                "last_24h": 0,
                "last_7d": 0,
                "unique_users": 0,
                "last_query_at": None,
            },
            "corpus_version": {
                "total_versions": 0,
                "last_reason": None,
                "last_created_at": None,
            },
        }

        with common_database.get_db_connection() as conn:
            with common_database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT
                        COUNT(*) AS total,
                        SUM(CASE WHEN status='active' THEN 1 ELSE 0 END) AS active,
                        SUM(CASE WHEN status='archived' THEN 1 ELSE 0 END) AS archived,
                        SUM(CASE WHEN status='deleted' THEN 1 ELSE 0 END) AS deleted,
                        MAX(updated_at) AS last_updated_at
                    FROM rag_documents
                    """
                )
                row = cursor.fetchone() or {}
                stats["documents"].update({
                    "total": int(row.get("total") or 0),
                    "active": int(row.get("active") or 0),
                    "archived": int(row.get("archived") or 0),
                    "deleted": int(row.get("deleted") or 0),
                    "last_updated_at": row.get("last_updated_at"),
                })

                cursor.execute(
                    """
                    SELECT source_type, COUNT(*) AS cnt
                    FROM rag_documents
                    GROUP BY source_type
                    ORDER BY cnt DESC
                    """
                )
                by_source_type: Dict[str, int] = {}
                for src_row in cursor.fetchall() or []:
                    source_type = str(src_row.get("source_type") or "unknown")
                    by_source_type[source_type] = int(src_row.get("cnt") or 0)
                stats["documents"]["by_source_type"] = by_source_type

                cursor.execute(
                    """
                    SELECT COUNT(*) AS total, MAX(created_at) AS last_created_at
                    FROM rag_chunks
                    """
                )
                row = cursor.fetchone() or {}
                stats["chunks"].update({
                    "total": int(row.get("total") or 0),
                    "last_created_at": row.get("last_created_at"),
                })

                cursor.execute(
                    """
                    SELECT
                        AVG(chunk_count) AS avg_per_document,
                        MAX(chunk_count) AS max_per_document
                    FROM (
                        SELECT document_id, COUNT(*) AS chunk_count
                        FROM rag_chunks
                        GROUP BY document_id
                    ) t
                    """
                )
                row = cursor.fetchone() or {}
                stats["chunks"].update({
                    "avg_per_document": round(float(row.get("avg_per_document") or 0.0), 2),
                    "max_per_document": int(row.get("max_per_document") or 0),
                })

                cursor.execute(
                    """
                    SELECT
                        COUNT(*) AS total,
                        SUM(CASE WHEN model_name IS NOT NULL AND model_name <> '' THEN 1 ELSE 0 END) AS with_model_name,
                        MAX(updated_at) AS last_updated_at
                    FROM rag_document_summaries
                    """
                )
                row = cursor.fetchone() or {}
                stats["summaries"].update({
                    "total": int(row.get("total") or 0),
                    "with_model_name": int(row.get("with_model_name") or 0),
                    "last_updated_at": row.get("last_updated_at"),
                })

                cursor.execute(
                    """
                    SELECT
                        COUNT(*) AS total,
                        SUM(CASE WHEN embedding_status='ready' THEN 1 ELSE 0 END) AS ready,
                        SUM(CASE WHEN embedding_status='failed' THEN 1 ELSE 0 END) AS failed,
                        SUM(CASE WHEN embedding_status='stale' THEN 1 ELSE 0 END) AS stale,
                        MAX(updated_at) AS last_updated_at
                    FROM rag_chunk_embeddings
                    """
                )
                row = cursor.fetchone() or {}
                stats["chunk_embeddings"].update({
                    "total": int(row.get("total") or 0),
                    "ready": int(row.get("ready") or 0),
                    "failed": int(row.get("failed") or 0),
                    "stale": int(row.get("stale") or 0),
                    "last_updated_at": row.get("last_updated_at"),
                })

                cursor.execute(
                    """
                    SELECT
                        COUNT(*) AS total,
                        SUM(CASE WHEN embedding_status='ready' THEN 1 ELSE 0 END) AS ready,
                        SUM(CASE WHEN embedding_status='failed' THEN 1 ELSE 0 END) AS failed,
                        SUM(CASE WHEN embedding_status='stale' THEN 1 ELSE 0 END) AS stale,
                        MAX(updated_at) AS last_updated_at
                    FROM rag_summary_embeddings
                    """
                )
                row = cursor.fetchone() or {}
                stats["summary_embeddings"].update({
                    "total": int(row.get("total") or 0),
                    "ready": int(row.get("ready") or 0),
                    "failed": int(row.get("failed") or 0),
                    "stale": int(row.get("stale") or 0),
                    "last_updated_at": row.get("last_updated_at"),
                })

                cursor.execute(
                    """
                    SELECT
                        COUNT(*) AS total,
                        SUM(CASE WHEN cache_hit = 1 THEN 1 ELSE 0 END) AS cache_hits,
                        SUM(CASE WHEN created_at >= (NOW() - INTERVAL 1 DAY) THEN 1 ELSE 0 END) AS last_24h,
                        SUM(CASE WHEN created_at >= (NOW() - INTERVAL 7 DAY) THEN 1 ELSE 0 END) AS last_7d,
                        COUNT(DISTINCT user_id) AS unique_users,
                        MAX(created_at) AS last_query_at
                    FROM rag_query_log
                    """
                )
                row = cursor.fetchone() or {}
                total_queries = int(row.get("total") or 0)
                cache_hits = int(row.get("cache_hits") or 0)
                stats["query_log"].update({
                    "total": total_queries,
                    "cache_hits": cache_hits,
                    "cache_hit_ratio": round(cache_hits / total_queries, 4) if total_queries > 0 else 0.0,
                    "last_24h": int(row.get("last_24h") or 0),
                    "last_7d": int(row.get("last_7d") or 0),
                    "unique_users": int(row.get("unique_users") or 0),
                    "last_query_at": row.get("last_query_at"),
                })

                cursor.execute(
                    """
                    SELECT COUNT(*) AS total_versions
                    FROM rag_corpus_version
                    """
                )
                row = cursor.fetchone() or {}
                stats["corpus_version"]["total_versions"] = int(row.get("total_versions") or 0)

                cursor.execute(
                    """
                    SELECT reason, created_at
                    FROM rag_corpus_version
                    ORDER BY id DESC
                    LIMIT 1
                    """
                )
                row = cursor.fetchone() or {}
                stats["corpus_version"].update({
                    "last_reason": row.get("reason"),
                    "last_created_at": row.get("created_at"),
                })

        return stats

    @router.get("/documents")
    async def rag_documents(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=200),
        q: Optional[str] = Query(None, max_length=500),
        status: Optional[str] = Query(None),
        source_type: Optional[str] = Query(None, max_length=64),
        has_summary: Optional[bool] = Query(None),
        sort_by: str = Query("updated_at"),
        sort_order: str = Query("desc"),
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> Dict[str, Any]:
        """Вернуть список RAG-документов с фильтрами, пагинацией и агрегированной статистикой."""

        del user

        allowed_statuses = {"active", "archived", "deleted"}
        normalized_status = str(status or "").strip().lower() or None
        if normalized_status and normalized_status not in allowed_statuses:
            raise HTTPException(400, "status должен быть одним из: active, archived, deleted")

        normalized_source_type = str(source_type or "").strip() or None
        normalized_query = str(q or "").strip() or None

        sort_map = {
            "updated_at": "d.updated_at",
            "created_at": "d.created_at",
            "filename": "d.filename",
            "status": "d.status",
            "source_type": "d.source_type",
            "chunks": "chunk_count",
            "chunk_embeddings_ready": "chunk_embeddings_ready",
            "summary_embeddings_ready": "summary_embeddings_ready",
        }
        normalized_sort_by = str(sort_by or "").strip().lower()
        sort_expr = sort_map.get(normalized_sort_by, "d.updated_at")

        normalized_sort_order = str(sort_order or "").strip().lower()
        if normalized_sort_order not in {"asc", "desc"}:
            normalized_sort_order = "desc"
        sort_direction = "ASC" if normalized_sort_order == "asc" else "DESC"

        where_parts: List[str] = []
        where_params: List[Any] = []

        if normalized_status:
            where_parts.append("d.status = %s")
            where_params.append(normalized_status)

        if normalized_source_type:
            where_parts.append("d.source_type = %s")
            where_params.append(normalized_source_type)

        if normalized_query:
            like_value = f"%{normalized_query}%"
            where_parts.append("(d.filename LIKE %s OR d.source_url LIKE %s OR COALESCE(ds.summary_text, '') LIKE %s)")
            where_params.extend([like_value, like_value, like_value])

        if has_summary is True:
            where_parts.append("ds.id IS NOT NULL")
        elif has_summary is False:
            where_parts.append("ds.id IS NULL")

        where_sql = ""
        if where_parts:
            where_sql = "WHERE " + " AND ".join(where_parts)

        base_from = f"""
            FROM rag_documents d
            LEFT JOIN rag_document_summaries ds ON ds.document_id = d.id
            LEFT JOIN (
                SELECT document_id, COUNT(*) AS chunk_count
                FROM rag_chunks
                GROUP BY document_id
            ) c ON c.document_id = d.id
            LEFT JOIN (
                SELECT
                    document_id,
                    SUM(CASE WHEN embedding_status='ready' THEN 1 ELSE 0 END) AS ready_count,
                    SUM(CASE WHEN embedding_status='failed' THEN 1 ELSE 0 END) AS failed_count,
                    SUM(CASE WHEN embedding_status='stale' THEN 1 ELSE 0 END) AS stale_count
                FROM rag_chunk_embeddings
                GROUP BY document_id
            ) ce ON ce.document_id = d.id
            LEFT JOIN (
                SELECT
                    document_id,
                    SUM(CASE WHEN embedding_status='ready' THEN 1 ELSE 0 END) AS ready_count,
                    SUM(CASE WHEN embedding_status='failed' THEN 1 ELSE 0 END) AS failed_count,
                    SUM(CASE WHEN embedding_status='stale' THEN 1 ELSE 0 END) AS stale_count
                FROM rag_summary_embeddings
                GROUP BY document_id
            ) se ON se.document_id = d.id
            {where_sql}
        """

        offset = (page - 1) * page_size

        def _to_iso(value: Any) -> Optional[str]:
            if isinstance(value, datetime):
                return value.isoformat()
            if value is None:
                return None
            return str(value)

        result: Dict[str, Any] = {
            "items": [],
            "page": page,
            "page_size": page_size,
            "total": 0,
            "stats": {
                "documents_total": 0,
                "status_counts": {"active": 0, "archived": 0, "deleted": 0},
                "source_type_counts": {},
                "total_chunks": 0,
                "avg_chunks_per_document": 0.0,
                "documents_with_summary": 0,
                "chunk_embeddings": {"ready": 0, "failed": 0, "stale": 0},
                "summary_embeddings": {"ready": 0, "failed": 0, "stale": 0},
                "last_document_updated_at": None,
            },
            "filters": {
                "q": normalized_query,
                "status": normalized_status,
                "source_type": normalized_source_type,
                "has_summary": has_summary,
                "sort_by": normalized_sort_by if normalized_sort_by in sort_map else "updated_at",
                "sort_order": normalized_sort_order,
            },
        }

        with common_database.get_db_connection() as conn:
            with common_database.get_cursor(conn) as cursor:
                cursor.execute(
                    f"""
                    SELECT COUNT(*) AS total
                    {base_from}
                    """,
                    tuple(where_params),
                )
                count_row = cursor.fetchone() or {}
                total_docs = int(count_row.get("total") or 0)
                result["total"] = total_docs
                result["stats"]["documents_total"] = total_docs

                cursor.execute(
                    f"""
                    SELECT
                        d.id,
                        d.filename,
                        d.source_type,
                        d.source_url,
                        d.uploaded_by,
                        d.status,
                        d.content_hash,
                        d.created_at,
                        d.updated_at,
                        COALESCE(c.chunk_count, 0) AS chunk_count,
                        CASE WHEN ds.id IS NULL THEN 0 ELSE 1 END AS has_summary,
                        ds.model_name AS summary_model_name,
                        ds.updated_at AS summary_updated_at,
                        COALESCE(ce.ready_count, 0) AS chunk_embeddings_ready,
                        COALESCE(ce.failed_count, 0) AS chunk_embeddings_failed,
                        COALESCE(ce.stale_count, 0) AS chunk_embeddings_stale,
                        COALESCE(se.ready_count, 0) AS summary_embeddings_ready,
                        COALESCE(se.failed_count, 0) AS summary_embeddings_failed,
                        COALESCE(se.stale_count, 0) AS summary_embeddings_stale
                    {base_from}
                    ORDER BY {sort_expr} {sort_direction}, d.id DESC
                    LIMIT %s OFFSET %s
                    """,
                    tuple([*where_params, page_size, offset]),
                )
                rows = cursor.fetchall() or []

                result["items"] = [
                    {
                        "id": int(row.get("id") or 0),
                        "filename": str(row.get("filename") or ""),
                        "source_type": str(row.get("source_type") or ""),
                        "source_url": row.get("source_url"),
                        "uploaded_by": int(row.get("uploaded_by") or 0),
                        "status": str(row.get("status") or "active"),
                        "content_hash": str(row.get("content_hash") or ""),
                        "created_at": _to_iso(row.get("created_at")),
                        "updated_at": _to_iso(row.get("updated_at")),
                        "chunk_count": int(row.get("chunk_count") or 0),
                        "has_summary": bool(int(row.get("has_summary") or 0)),
                        "summary_model_name": row.get("summary_model_name"),
                        "summary_updated_at": _to_iso(row.get("summary_updated_at")),
                        "chunk_embeddings": {
                            "ready": int(row.get("chunk_embeddings_ready") or 0),
                            "failed": int(row.get("chunk_embeddings_failed") or 0),
                            "stale": int(row.get("chunk_embeddings_stale") or 0),
                        },
                        "summary_embeddings": {
                            "ready": int(row.get("summary_embeddings_ready") or 0),
                            "failed": int(row.get("summary_embeddings_failed") or 0),
                            "stale": int(row.get("summary_embeddings_stale") or 0),
                        },
                    }
                    for row in rows
                ]

                cursor.execute(
                    f"""
                    SELECT
                        SUM(CASE WHEN d.status='active' THEN 1 ELSE 0 END) AS active_docs,
                        SUM(CASE WHEN d.status='archived' THEN 1 ELSE 0 END) AS archived_docs,
                        SUM(CASE WHEN d.status='deleted' THEN 1 ELSE 0 END) AS deleted_docs,
                        SUM(COALESCE(c.chunk_count, 0)) AS total_chunks,
                        AVG(COALESCE(c.chunk_count, 0)) AS avg_chunks_per_document,
                        SUM(CASE WHEN ds.id IS NOT NULL THEN 1 ELSE 0 END) AS documents_with_summary,
                        SUM(COALESCE(ce.ready_count, 0)) AS chunk_embeddings_ready,
                        SUM(COALESCE(ce.failed_count, 0)) AS chunk_embeddings_failed,
                        SUM(COALESCE(ce.stale_count, 0)) AS chunk_embeddings_stale,
                        SUM(COALESCE(se.ready_count, 0)) AS summary_embeddings_ready,
                        SUM(COALESCE(se.failed_count, 0)) AS summary_embeddings_failed,
                        SUM(COALESCE(se.stale_count, 0)) AS summary_embeddings_stale,
                        MAX(d.updated_at) AS last_document_updated_at
                    {base_from}
                    """,
                    tuple(where_params),
                )
                agg_row = cursor.fetchone() or {}
                result["stats"].update({
                    "status_counts": {
                        "active": int(agg_row.get("active_docs") or 0),
                        "archived": int(agg_row.get("archived_docs") or 0),
                        "deleted": int(agg_row.get("deleted_docs") or 0),
                    },
                    "total_chunks": int(agg_row.get("total_chunks") or 0),
                    "avg_chunks_per_document": round(float(agg_row.get("avg_chunks_per_document") or 0.0), 2),
                    "documents_with_summary": int(agg_row.get("documents_with_summary") or 0),
                    "chunk_embeddings": {
                        "ready": int(agg_row.get("chunk_embeddings_ready") or 0),
                        "failed": int(agg_row.get("chunk_embeddings_failed") or 0),
                        "stale": int(agg_row.get("chunk_embeddings_stale") or 0),
                    },
                    "summary_embeddings": {
                        "ready": int(agg_row.get("summary_embeddings_ready") or 0),
                        "failed": int(agg_row.get("summary_embeddings_failed") or 0),
                        "stale": int(agg_row.get("summary_embeddings_stale") or 0),
                    },
                    "last_document_updated_at": _to_iso(agg_row.get("last_document_updated_at")),
                })

                cursor.execute(
                    f"""
                    SELECT d.source_type, COUNT(*) AS cnt
                    {base_from}
                    GROUP BY d.source_type
                    ORDER BY cnt DESC
                    """,
                    tuple(where_params),
                )
                source_counts: Dict[str, int] = {}
                for src_row in cursor.fetchall() or []:
                    source_key = str(src_row.get("source_type") or "unknown")
                    source_counts[source_key] = int(src_row.get("cnt") or 0)
                result["stats"]["source_type_counts"] = source_counts

        return result

    return router


# ---------------------------------------------------------------------------
# Подроутер: Статистика
# ---------------------------------------------------------------------------


def _build_stats_router() -> APIRouter:
    router = APIRouter(tags=["gk-stats"])

    @router.get("/overview")
    async def stats_overview(
        group_id: Optional[int] = Query(None),
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> Dict[str, Any]:
        """Обзорная статистика GK."""
        from admin_web.modules.gk_knowledge import db_stats
        raw = db_stats.get_overview_stats(group_id=group_id)
        return _normalize_overview_payload(raw)

    @router.get("/timeline")
    async def stats_timeline(
        group_id: Optional[int] = Query(None),
        days: int = Query(30, ge=1, le=365),
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> Dict[str, Any]:
        """Временные ряды по дням."""
        from admin_web.modules.gk_knowledge import db_stats
        raw = db_stats.get_timeline_stats(group_id=group_id, days=days)
        return _normalize_timeline_payload(raw)

    @router.get("/distribution")
    async def stats_distribution(
        group_id: Optional[int] = Query(None),
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> List[Dict[str, Any]]:
        """Распределение Q&A-пар по уверенности."""
        from admin_web.modules.gk_knowledge import db_stats
        raw = db_stats.get_confidence_distribution(group_id=group_id)
        return _normalize_distribution_payload(raw)

    return router


# ---------------------------------------------------------------------------
# Подроутер: Q&A-пары
# ---------------------------------------------------------------------------


def _build_qa_pairs_router() -> APIRouter:
    router = APIRouter(tags=["gk-qa-pairs"])

    @router.get("")
    async def list_qa_pairs(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        group_id: Optional[int] = Query(None),
        extraction_type: Optional[str] = Query(None, pattern=r"^(thread_reply|llm_inferred)$"),
        search_text: Optional[str] = Query(None, min_length=1, max_length=500),
        expert_status: Optional[str] = Query(None, pattern=r"^(approved|rejected|unvalidated)$"),
        approved: Optional[bool] = Query(None),
        vector_indexed: Optional[bool] = Query(None),
        min_confidence: Optional[float] = Query(None, ge=0.0, le=1.0),
        max_confidence: Optional[float] = Query(None, ge=0.0, le=1.0),
        sort_by: str = Query("created_at", pattern=r"^(created_at|confidence|id|group_id|expert_status|extraction_type)$"),
        sort_order: str = Query("desc", pattern=r"^(asc|desc)$"),
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> Dict[str, Any]:
        """Список Q&A-пар с фильтрацией и пагинацией."""
        from admin_web.modules.gk_knowledge import db_qa_pairs
        rows, total = db_qa_pairs.get_qa_pairs_list(
            page=page, page_size=page_size, group_id=group_id,
            extraction_type=extraction_type, search_text=search_text,
            expert_status=expert_status, approved=approved,
            vector_indexed=vector_indexed,
            min_confidence=min_confidence, max_confidence=max_confidence,
            sort_by=sort_by, sort_order=sort_order,
        )
        pairs = [_row_to_pair_detail(r) for r in rows]
        return {
            "pairs": [p.model_dump() for p in pairs],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    @router.get("/{pair_id}")
    async def get_qa_pair(
        pair_id: int,
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> QAPairDetail:
        """Получить детальные данные одной Q&A-пары для каталога."""
        from admin_web.modules.gk_knowledge import db_expert_validation as ev_db
        from admin_web.modules.gk_knowledge import db_qa_pairs

        row = db_qa_pairs.get_qa_pair_detail(pair_id)
        if not row:
            raise HTTPException(404, "Q&A-пара не найдена")

        pair = _row_to_pair_detail(row)
        if pair.group_id:
            pair.group_title = ev_db.get_group_title(pair.group_id)
        return pair

    return router


# ---------------------------------------------------------------------------
# Подроутер: Экспертная валидация
# ---------------------------------------------------------------------------


def _build_expert_validation_router() -> APIRouter:
    router = APIRouter(tags=["gk-expert-validation"])

    @router.get("/pairs")
    async def list_pairs(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        group_id: Optional[int] = Query(None),
        extraction_type: Optional[str] = Query(None, pattern=r"^(thread_reply|llm_inferred)$"),
        question_text: Optional[str] = Query(None, min_length=1, max_length=500),
        expert_status: Optional[str] = Query(None, pattern=r"^(approved|rejected|unvalidated)$"),
        min_confidence: Optional[float] = Query(None, ge=0.0, le=1.0),
        max_confidence: Optional[float] = Query(None, ge=0.0, le=1.0),
        review_low_confidence_first: bool = Query(False),
        sort_by: str = Query("created_at", pattern=r"^(created_at|confidence|id|group_id|expert_status)$"),
        sort_order: str = Query("desc", pattern=r"^(asc|desc)$"),
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> QAPairListResponse:
        """Список Q&A-пар для экспертной валидации."""
        from admin_web.modules.gk_knowledge import db_expert_validation as ev_db
        rows, total = ev_db.get_qa_pairs_for_validation(
            page=page, page_size=page_size, group_id=group_id,
            extraction_type=extraction_type, question_text=question_text,
            expert_status=expert_status,
            min_confidence=min_confidence, max_confidence=max_confidence,
            review_low_confidence_first=review_low_confidence_first,
            sort_by=sort_by, sort_order=sort_order,
            expert_telegram_id=user.telegram_id,
        )
        pairs = [_row_to_pair_detail(r) for r in rows]
        stats = ev_db.get_validation_stats(group_id=group_id)
        return QAPairListResponse(
            pairs=pairs, total=total, page=page, page_size=page_size,
            stats=ExpertValidationStats(**stats),
        )

    @router.get("/pairs/{pair_id}")
    async def get_pair(
        pair_id: int,
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> QAPairDetail:
        """Детальные данные Q&A-пары с цепочкой."""
        from admin_web.modules.gk_knowledge import db_expert_validation as ev_db
        row = ev_db.get_qa_pair_detail(pair_id)
        if not row:
            raise HTTPException(404, "Q&A-пара не найдена")
        pair = _row_to_pair_detail(row)
        chain = ev_db.get_chain_messages(pair_id)
        pair.chain_messages = [_row_to_chain_message(m) for m in chain]
        if pair.group_id:
            pair.group_title = ev_db.get_group_title(pair.group_id)
        existing = ev_db.get_expert_verdict(pair_id, user.telegram_id)
        if existing:
            pair.existing_verdict = existing["verdict"]
            pair.existing_comment = existing.get("comment")
        return pair

    @router.get("/pairs/{pair_id}/chain")
    async def get_chain(
        pair_id: int,
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> List[ChainMessage]:
        """Цепочка сообщений для Q&A-пары."""
        from admin_web.modules.gk_knowledge import db_expert_validation as ev_db
        chain = ev_db.get_chain_messages(pair_id)
        if not chain:
            return []
        return [_row_to_chain_message(m) for m in chain]

    @router.post("/validate")
    async def validate_pair(
        body: ExpertValidationRequest,
        user: WebUser = Depends(require_permission("gk_knowledge", "edit")),
    ) -> Dict[str, Any]:
        """Сохранить экспертный вердикт."""
        from admin_web.modules.gk_knowledge import db_expert_validation as ev_db
        pair = ev_db.get_qa_pair_detail(body.qa_pair_id)
        if not pair:
            raise HTTPException(404, "Q&A-пара не найдена")
        validation_id = ev_db.store_expert_verdict(
            qa_pair_id=body.qa_pair_id,
            expert_telegram_id=user.telegram_id,
            verdict=body.verdict.value,
            comment=body.comment,
        )
        return {
            "validation_id": validation_id,
            "qa_pair_id": body.qa_pair_id,
            "verdict": body.verdict.value,
            "message": "Вердикт сохранён",
        }

    @router.get("/pairs/{pair_id}/history")
    async def get_pair_history(
        pair_id: int,
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> List[Dict[str, Any]]:
        """История валидации Q&A-пары."""
        from admin_web.modules.gk_knowledge import db_expert_validation as ev_db
        history = ev_db.get_validation_history(pair_id)
        for entry in history:
            for key in ("created_at", "updated_at"):
                if entry.get(key) and isinstance(entry[key], datetime):
                    entry[key] = entry[key].isoformat()
        return history

    @router.get("/stats")
    async def get_ev_stats(
        group_id: Optional[int] = Query(None),
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> ExpertValidationStats:
        """Статистика экспертной валидации."""
        from admin_web.modules.gk_knowledge import db_expert_validation as ev_db
        stats = ev_db.get_validation_stats(group_id=group_id)
        return ExpertValidationStats(**stats)

    @router.get("/groups")
    async def get_ev_groups(
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> List[Dict[str, Any]]:
        """Список групп с количеством Q&A-пар."""
        from admin_web.modules.gk_knowledge import db_expert_validation as ev_db
        return ev_db.get_collected_groups()

    return router


# ---------------------------------------------------------------------------
# Подроутер: Тестер промптов
# ---------------------------------------------------------------------------


def _build_prompt_tester_router() -> APIRouter:
    router = APIRouter(tags=["gk-prompt-tester"])

    @router.get("/supported-models")
    async def get_supported_models(
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> Dict[str, Any]:
        """Список поддерживаемых моделей для выпадающего списка Prompt Tester."""
        return {
            "models": get_supported_deepseek_models(),
            "default_model": ai_settings.get_active_gk_responder_model() or None,
        }

    @router.get("/prompts")
    async def list_prompts(
        active_only: bool = Query(True),
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> List[Dict[str, Any]]:
        """Список промптов извлечения."""
        from admin_web.modules.gk_knowledge import db_prompt_tester as pt_db
        return pt_db.get_prompts(active_only=active_only)

    @router.get("/stats")
    async def prompt_tester_stats(
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> Dict[str, Any]:
        """Агрегированная статистика тестера промптов по всем сессиям."""
        from admin_web.modules.gk_knowledge import db_prompt_tester as pt_db
        return pt_db.get_global_prompt_stats()

    @router.post("/prompts")
    async def create_prompt(
        body: Dict[str, Any],
        user: WebUser = Depends(require_permission("gk_knowledge", "edit")),
    ) -> Dict[str, Any]:
        """Создать промпт."""
        from admin_web.modules.gk_knowledge import db_prompt_tester as pt_db
        prompt_text = (body.get("user_prompt") or body.get("system_prompt") or "").strip()
        if not prompt_text:
            raise HTTPException(400, "Поле user_prompt обязательно")
        prompt_id = pt_db.create_prompt(
            label=body["label"],
            user_prompt=prompt_text,
            extraction_type=body.get("extraction_type", "llm_inferred"),
            model_name=body.get("model_name"),
            temperature=body.get("temperature", 0.3),
            created_by_telegram_id=user.telegram_id,
        )
        return {"id": prompt_id, "message": "Промпт создан"}

    @router.put("/prompts/{prompt_id}")
    async def update_prompt(
        prompt_id: int,
        body: Dict[str, Any],
        user: WebUser = Depends(require_permission("gk_knowledge", "edit")),
    ) -> Dict[str, Any]:
        """Обновить промпт."""
        from admin_web.modules.gk_knowledge import db_prompt_tester as pt_db
        pt_db.update_prompt(
            prompt_id,
            label=body.get("label"),
            user_prompt=body.get("user_prompt") if "user_prompt" in body else None,
            system_prompt=body.get("system_prompt") if "system_prompt" in body else None,
            extraction_type=body.get("extraction_type"),
            model_name=body.get("model_name"),
            temperature=body.get("temperature"),
        )
        return {"message": "Промпт обновлён"}

    @router.delete("/prompts/{prompt_id}")
    async def delete_prompt(
        prompt_id: int,
        user: WebUser = Depends(require_permission("gk_knowledge", "edit")),
    ) -> Dict[str, Any]:
        """Деактивировать промпт."""
        from admin_web.modules.gk_knowledge import db_prompt_tester as pt_db
        pt_db.delete_prompt(prompt_id)
        return {"message": "Промпт деактивирован"}

    @router.get("/sessions")
    async def list_sessions(
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> List[Dict[str, Any]]:
        """Список сессий тестирования."""
        from admin_web.modules.gk_knowledge import db_prompt_tester as pt_db
        sessions = pt_db.get_sessions()
        # Сериализация datetime
        for s in sessions:
            for key in ("created_at", "updated_at"):
                if s.get(key) and isinstance(s[key], datetime):
                    s[key] = s[key].isoformat()
        return sessions

    @router.post("/sessions/estimate")
    async def estimate_session(
        body: Dict[str, Any],
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> Dict[str, Any]:
        """Оценить объём сессии тестирования без запуска генерации."""
        from admin_web.modules.gk_knowledge import db_prompt_tester as pt_db

        raw_prompt_ids = body.get("prompt_ids", [])
        if not isinstance(raw_prompt_ids, list):
            raise HTTPException(400, "prompt_ids должен быть массивом")

        normalized_prompt_ids: List[int] = []
        for pid in raw_prompt_ids:
            try:
                prompt_id = int(pid)
            except (TypeError, ValueError):
                continue
            if prompt_id > 0 and prompt_id not in normalized_prompt_ids:
                normalized_prompt_ids.append(prompt_id)

        chains_count = int(body.get("chains_count") or body.get("message_count") or 20)
        if chains_count < 1 or chains_count > 1000:
            raise HTTPException(400, "chains_count должен быть в диапазоне 1..1000")

        source_rows = pt_db.get_source_pairs_for_session(
            limit=chains_count,
            source_group_id=body.get("source_group_id"),
            source_date_from=body.get("source_date_from"),
            source_date_to=body.get("source_date_to"),
        )
        effective_chains_count = len(source_rows)
        prompt_count = len(normalized_prompt_ids)

        return {
            "prompt_count": prompt_count,
            "requested_chains_count": chains_count,
            "effective_chains_count": effective_chains_count,
            "expected_comparisons": pt_db.estimate_comparisons(prompt_count, effective_chains_count),
            "can_create": prompt_count >= 2 and effective_chains_count >= 1,
        }

    @router.post("/sessions")
    async def create_session(
        body: Dict[str, Any],
        background_tasks: BackgroundTasks,
        user: WebUser = Depends(require_permission("gk_knowledge", "edit")),
    ) -> Dict[str, Any]:
        """Создать сессию тестирования."""
        from admin_web.modules.gk_knowledge import db_prompt_tester as pt_db

        raw_prompt_ids = body.get("prompt_ids", [])
        if not isinstance(raw_prompt_ids, list):
            raise HTTPException(400, "prompt_ids должен быть массивом")

        prompt_ids: List[int] = []
        for pid in raw_prompt_ids:
            try:
                prompt_id = int(pid)
            except (TypeError, ValueError):
                continue
            if prompt_id > 0 and prompt_id not in prompt_ids:
                prompt_ids.append(prompt_id)

        if len(prompt_ids) < 2:
            raise HTTPException(400, "Необходимо минимум 2 промпта для сравнения")

        chains_count = int(body.get("chains_count") or body.get("message_count") or 20)
        if chains_count < 1 or chains_count > 1000:
            raise HTTPException(400, "chains_count должен быть в диапазоне 1..1000")

        source_rows = pt_db.get_source_pairs_for_session(
            limit=chains_count,
            source_group_id=body.get("source_group_id"),
            source_date_from=body.get("source_date_from"),
            source_date_to=body.get("source_date_to"),
        )
        if len(source_rows) < 1:
            raise HTTPException(400, "Недостаточно цепочек для теста (нужно >= 1)")

        # Получить снимок конфигурации промптов
        prompts_snapshot = []
        for pid in prompt_ids:
            p = pt_db.get_prompt_by_id(pid)
            if not p:
                raise HTTPException(404, f"Промпт #{pid} не найден")
            prompts_snapshot.append({
                "id": p["id"],
                "label": p["label"],
                "user_prompt": p.get("system_prompt", ""),
                "extraction_type": p["extraction_type"],
                "model_name": p["model_name"],
                "temperature": p["temperature"],
            })

        session_id = pt_db.create_session(
            name=body["name"],
            prompt_ids=prompt_ids,
            judge_mode=body.get("judge_mode", "human"),
            source_group_id=body.get("source_group_id"),
            source_date_from=body.get("source_date_from"),
            source_date_to=body.get("source_date_to"),
            chains_count=len(source_rows),
            source_messages_snapshot=[int(row["id"]) for row in source_rows if row.get("id") is not None],
            prompts_config_snapshot=prompts_snapshot,
            created_by_telegram_id=user.telegram_id,
        )

        background_tasks.add_task(
            _generate_gk_prompt_tester_session,
            session_id=session_id,
            prompts_snapshot=prompts_snapshot,
            source_rows=source_rows,
        )

        return {
            "id": session_id,
            "message": "Сессия создана, генерация запущена",
            "chains_count": len(source_rows),
            "expected_comparisons": pt_db.estimate_comparisons(len(prompt_ids), len(source_rows)),
        }

    @router.get("/sessions/{session_id}")
    async def get_session(
        session_id: int,
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> Dict[str, Any]:
        """Детали сессии."""
        from admin_web.modules.gk_knowledge import db_prompt_tester as pt_db
        session = pt_db.get_session_by_id(session_id)
        if not session:
            raise HTTPException(404, "Сессия не найдена")
        for key in ("created_at", "updated_at"):
            if session.get(key) and isinstance(session[key], datetime):
                session[key] = session[key].isoformat()
        return session

    @router.get("/sessions/{session_id}/compare")
    async def get_next_comparison(
        session_id: int,
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> Dict[str, Any]:
        """Следующее слепое сравнение для голосования."""
        from admin_web.modules.gk_knowledge import db_prompt_tester as pt_db
        comparison = pt_db.get_next_comparison(session_id, voter_telegram_id=user.telegram_id)
        if not comparison:
            return {"has_more": False}

        question_a = (comparison.get("question_a") or "").strip()
        answer_a = (comparison.get("answer_a") or "").strip()
        question_b = (comparison.get("question_b") or "").strip()
        answer_b = (comparison.get("answer_b") or "").strip()

        return {
            "has_more": True,
            "comparison_id": comparison.get("comparison_id"),
            "generation_a_text": f"[ВОПРОС]\n{question_a}\n\n[ОТВЕТ]\n{answer_a}",
            "generation_b_text": f"[ВОПРОС]\n{question_b}\n\n[ОТВЕТ]\n{answer_b}",
            "source_context": None,
            "progress_total": int(comparison.get("progress_total") or 0),
            "progress_voted": int(comparison.get("progress_voted") or 0),
        }

    @router.post("/sessions/{session_id}/vote")
    async def vote(
        session_id: int,
        body: Dict[str, Any],
        user: WebUser = Depends(require_permission("gk_knowledge", "edit")),
    ) -> Dict[str, Any]:
        """Голосование: выбрать A, B, tie или skip."""
        from admin_web.modules.gk_knowledge import db_prompt_tester as pt_db
        comparison_id = body.get("comparison_id")
        winner = body.get("winner")
        if not comparison_id or winner not in ("a", "b", "tie", "skip"):
            raise HTTPException(400, "Некорректные данные голосования")
        ok = pt_db.submit_vote(
            comparison_id=comparison_id,
            winner=winner,
            expected_session_id=session_id,
            voter_telegram_id=user.telegram_id,
            voter_type="human",
        )
        if not ok:
            raise HTTPException(409, "Голос уже учтён или сравнение не найдено")
        return {"message": "Голос учтён"}

    @router.get("/sessions/{session_id}/results")
    async def get_results(
        session_id: int,
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> Dict[str, Any]:
        """Результаты сессии: Elo + Win Rate."""
        from admin_web.modules.gk_knowledge import db_prompt_tester as pt_db
        raw = pt_db.get_session_results(session_id)
        session = pt_db.get_session_by_id(session_id)

        total_comparisons = int((session or {}).get("total_comparisons") or 0)
        voted_comparisons = int((session or {}).get("voted_count") or 0)

        prompts: List[Dict[str, Any]] = []
        for item in raw.get("prompt_results", []):
            prompts.append({
                "prompt_id": int(item.get("prompt_id") or 0),
                "label": item.get("prompt_label") or "",
                "elo": float(item.get("elo") or 0),
                "elo_delta": float(item.get("elo_delta") or 0),
                "wins": int(item.get("wins") or 0),
                "losses": int(item.get("losses") or 0),
                "ties": int(item.get("ties") or 0),
                "skips": int(item.get("skips") or 0),
                "matches": int(item.get("matches") or 0),
                "score": float(item.get("score") or 0.0),
                "win_rate": float(item.get("win_rate") or 0.0) / 100.0,
                "loss_rate": float(item.get("loss_rate") or 0.0) / 100.0,
            })

        return {
            "session_id": session_id,
            "total_comparisons": total_comparisons,
            "voted_comparisons": voted_comparisons,
            "prompts": prompts,
        }

    @router.post("/sessions/{session_id}/abandon")
    async def abandon_session(
        session_id: int,
        user: WebUser = Depends(require_permission("gk_knowledge", "edit")),
    ) -> Dict[str, Any]:
        """Отменить сессию."""
        from admin_web.modules.gk_knowledge import db_prompt_tester as pt_db
        pt_db.update_session_status(session_id, "abandoned")
        return {"message": "Сессия отменена"}

    @router.get("/sessions/{session_id}/generations")
    async def get_generations(
        session_id: int,
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> List[Dict[str, Any]]:
        """Все генерации сессии."""
        from admin_web.modules.gk_knowledge import db_prompt_tester as pt_db
        gens = pt_db.get_generations_for_session(session_id)
        for g in gens:
            if g.get("generated_at") and isinstance(g["generated_at"], datetime):
                g["generated_at"] = g["generated_at"].isoformat()
        return gens

    return router


def _build_final_prompt_tester_router() -> APIRouter:
    """Подроутер тестера финального промпта ответа пользователю."""
    router = APIRouter(tags=["gk-final-prompt-tester"])

    @router.get("/supported-models")
    async def get_supported_models(
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> Dict[str, Any]:
        """Список поддерживаемых моделей для final prompt tester."""
        return {
            "models": get_supported_deepseek_models(),
            "default_model": ai_settings.get_active_gk_responder_model() or None,
        }

    @router.get("/prompts")
    async def list_prompts(
        active_only: bool = Query(True),
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> List[Dict[str, Any]]:
        """Список финальных промптов."""
        from admin_web.modules.gk_knowledge import db_final_prompt_tester as fpt_db
        return fpt_db.get_prompts(active_only=active_only)

    @router.get("/stats")
    async def final_prompt_tester_stats(
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> Dict[str, Any]:
        """Агрегированная статистика final prompt tester."""
        from admin_web.modules.gk_knowledge import db_final_prompt_tester as fpt_db
        return fpt_db.get_global_prompt_stats()

    @router.post("/prompts")
    async def create_prompt(
        body: Dict[str, Any],
        user: WebUser = Depends(require_permission("gk_knowledge", "edit")),
    ) -> Dict[str, Any]:
        """Создать промпт финального ответа."""
        from admin_web.modules.gk_knowledge import db_final_prompt_tester as fpt_db
        from src.group_knowledge.qa_search import _ANSWER_PROMPT_BASE

        prompt_template = str(body.get("prompt_template") or body.get("prompt_text") or "").strip()
        if not prompt_template:
            prompt_template = _ANSWER_PROMPT_BASE

        prompt_id = fpt_db.create_prompt(
            label=str(body.get("label") or "Новый финальный промпт").strip() or "Новый финальный промпт",
            prompt_template=prompt_template,
            model_name=(str(body.get("model_name") or "").strip() or None),
            temperature=float(body.get("temperature") or 0.3),
            created_by_telegram_id=user.telegram_id,
        )
        return {"id": prompt_id, "message": "Промпт создан"}

    @router.post("/prompts/{prompt_id}/clone")
    async def clone_prompt(
        prompt_id: int,
        user: WebUser = Depends(require_permission("gk_knowledge", "edit")),
    ) -> Dict[str, Any]:
        """Клонировать существующий финальный промпт."""
        from admin_web.modules.gk_knowledge import db_final_prompt_tester as fpt_db

        try:
            cloned_id = fpt_db.clone_prompt(prompt_id, created_by_telegram_id=user.telegram_id)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

        return {"id": cloned_id, "message": "Промпт клонирован"}

    @router.put("/prompts/{prompt_id}")
    async def update_prompt(
        prompt_id: int,
        body: Dict[str, Any],
        user: WebUser = Depends(require_permission("gk_knowledge", "edit")),
    ) -> Dict[str, Any]:
        """Обновить финальный промпт."""
        from admin_web.modules.gk_knowledge import db_final_prompt_tester as fpt_db

        model_name_value = body.get("model_name") if "model_name" in body else None
        if isinstance(model_name_value, str):
            model_name_value = model_name_value.strip() or None

        fpt_db.update_prompt(
            prompt_id,
            label=body.get("label"),
            prompt_template=body.get("prompt_template") if "prompt_template" in body else None,
            model_name=model_name_value,
            temperature=body.get("temperature"),
        )
        return {"message": "Промпт обновлён"}

    @router.delete("/prompts/{prompt_id}")
    async def delete_prompt(
        prompt_id: int,
        user: WebUser = Depends(require_permission("gk_knowledge", "edit")),
    ) -> Dict[str, Any]:
        """Деактивировать финальный промпт."""
        from admin_web.modules.gk_knowledge import db_final_prompt_tester as fpt_db

        fpt_db.delete_prompt(prompt_id)
        return {"message": "Промпт деактивирован"}

    @router.delete("/prompts/{prompt_id}/purge")
    async def purge_prompt(
        prompt_id: int,
        user: WebUser = Depends(require_permission("gk_knowledge", "edit")),
    ) -> Dict[str, Any]:
        """Удалить неактивный финальный промпт навсегда (с проверкой зависимостей)."""
        _ = user
        from admin_web.modules.gk_knowledge import db_final_prompt_tester as fpt_db

        try:
            ok = fpt_db.purge_inactive_prompt(prompt_id)
            if not ok:
                raise HTTPException(500, "Не удалось удалить промпт")
            return {"message": "Промпт удалён навсегда"}
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.get("/sessions")
    async def list_sessions(
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> List[Dict[str, Any]]:
        """Список сессий final prompt tester."""
        from admin_web.modules.gk_knowledge import db_final_prompt_tester as fpt_db

        sessions = fpt_db.get_sessions()
        for session in sessions:
            for key in ("created_at", "updated_at"):
                if session.get(key) and isinstance(session[key], datetime):
                    session[key] = session[key].isoformat()
        return sessions

    @router.post("/sessions/estimate")
    async def estimate_session(
        body: Dict[str, Any],
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> Dict[str, Any]:
        """Оценить объём сессии final prompt tester без запуска генерации."""
        from admin_web.modules.gk_knowledge import db_final_prompt_tester as fpt_db

        raw_prompt_ids = body.get("prompt_ids", [])
        if not isinstance(raw_prompt_ids, list):
            raise HTTPException(400, "prompt_ids должен быть массивом")

        prompt_ids: List[int] = []
        for pid in raw_prompt_ids:
            try:
                prompt_id = int(pid)
            except (TypeError, ValueError):
                continue
            if prompt_id > 0 and prompt_id not in prompt_ids:
                prompt_ids.append(prompt_id)

        questions = _normalize_final_tester_questions(body)
        question_count = len(questions)

        return {
            "prompt_count": len(prompt_ids),
            "requested_question_count": question_count,
            "effective_question_count": question_count,
            "expected_comparisons": fpt_db.estimate_comparisons(len(prompt_ids), question_count),
            "can_create": len(prompt_ids) >= 2 and question_count >= 1,
        }

    @router.post("/sessions")
    async def create_session(
        body: Dict[str, Any],
        user: WebUser = Depends(require_permission("gk_knowledge", "edit")),
    ) -> Dict[str, Any]:
        """Создать сессию final prompt tester и запустить генерацию в фоне."""
        from admin_web.modules.gk_knowledge import db_final_prompt_tester as fpt_db

        raw_prompt_ids = body.get("prompt_ids", [])
        if not isinstance(raw_prompt_ids, list):
            raise HTTPException(400, "prompt_ids должен быть массивом")

        prompt_ids: List[int] = []
        for pid in raw_prompt_ids:
            try:
                prompt_id = int(pid)
            except (TypeError, ValueError):
                continue
            if prompt_id > 0 and prompt_id not in prompt_ids:
                prompt_ids.append(prompt_id)

        if len(prompt_ids) < 2:
            raise HTTPException(400, "Необходимо минимум 2 промпта для сравнения")

        questions = _normalize_final_tester_questions(body)
        if len(questions) < 1:
            raise HTTPException(400, "Добавь минимум 1 тестовый вопрос")

        prompts_snapshot: List[Dict[str, Any]] = []
        for pid in prompt_ids:
            prompt_row = fpt_db.get_prompt_by_id(pid)
            if not prompt_row:
                raise HTTPException(404, f"Промпт #{pid} не найден")
            prompts_snapshot.append(
                {
                    "id": int(prompt_row.get("id") or pid),
                    "label": str(prompt_row.get("label") or f"Промпт #{pid}"),
                    "prompt_template": str(prompt_row.get("prompt_template") or "").strip(),
                    "model_name": str(prompt_row.get("model_name") or "").strip() or None,
                    "temperature": float(prompt_row.get("temperature") or 0.3),
                }
            )

        source_group_id = body.get("source_group_id")
        if source_group_id is not None:
            try:
                source_group_id = int(source_group_id)
            except (TypeError, ValueError) as exc:
                raise HTTPException(400, "source_group_id должен быть числом") from exc

        try:
            session_id = fpt_db.create_session(
                name=str(body.get("name") or "Final answer prompt test").strip() or "Final answer prompt test",
                prompt_ids=prompt_ids,
                questions_snapshot=questions,
                source_group_id=source_group_id,
                judge_mode=str(body.get("judge_mode") or "human"),
                prompts_config_snapshot=prompts_snapshot,
                created_by_telegram_id=user.telegram_id,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

        _spawn_gk_final_prompt_tester_generation(
            session_id=session_id,
            prompts_snapshot=prompts_snapshot,
            questions=questions,
            source_group_id=source_group_id,
        )

        return {
            "id": session_id,
            "message": "Сессия создана, генерация запущена",
            "question_count": len(questions),
            "expected_comparisons": fpt_db.estimate_comparisons(len(prompt_ids), len(questions)),
        }

    @router.post("/sessions/{session_id}/clone")
    async def clone_session(
        session_id: int,
        user: WebUser = Depends(require_permission("gk_knowledge", "edit")),
    ) -> Dict[str, Any]:
        """Клонировать финальную сессию в статус draft без автозапуска."""
        from admin_web.modules.gk_knowledge import db_final_prompt_tester as fpt_db

        source_session = fpt_db.get_session_by_id(session_id)
        if not source_session:
            raise HTTPException(404, "Сессия не найдена")

        prompt_ids = [int(pid) for pid in (source_session.get("prompt_ids") or []) if int(pid) > 0]
        if len(prompt_ids) < 2:
            raise HTTPException(400, "В исходной сессии должно быть минимум 2 промпта")

        questions = [str(q or "").strip() for q in (source_session.get("questions_snapshot") or []) if str(q or "").strip()]
        if len(questions) < 1:
            raise HTTPException(400, "В исходной сессии нет тестовых вопросов")

        raw_prompts_snapshot = source_session.get("prompts_config_snapshot")
        prompts_snapshot: List[Dict[str, Any]] = []
        if isinstance(raw_prompts_snapshot, list):
            for item in raw_prompts_snapshot:
                if not isinstance(item, dict):
                    continue
                prompt_id = int(item.get("id") or 0)
                if prompt_id <= 0:
                    continue
                prompts_snapshot.append(
                    {
                        "id": prompt_id,
                        "label": str(item.get("label") or f"Промпт #{prompt_id}"),
                        "prompt_template": str(item.get("prompt_template") or "").strip(),
                        "model_name": str(item.get("model_name") or "").strip() or None,
                        "temperature": float(item.get("temperature") or 0.3),
                    }
                )

        if not prompts_snapshot:
            for pid in prompt_ids:
                prompt_row = fpt_db.get_prompt_by_id(pid)
                if not prompt_row:
                    raise HTTPException(404, f"Промпт #{pid} не найден")
                prompts_snapshot.append(
                    {
                        "id": int(prompt_row.get("id") or pid),
                        "label": str(prompt_row.get("label") or f"Промпт #{pid}"),
                        "prompt_template": str(prompt_row.get("prompt_template") or "").strip(),
                        "model_name": str(prompt_row.get("model_name") or "").strip() or None,
                        "temperature": float(prompt_row.get("temperature") or 0.3),
                    }
                )

        source_group_id = source_session.get("source_group_id")
        if source_group_id is not None:
            source_group_id = int(source_group_id)

        source_name = str(source_session.get("name") or f"Session #{session_id}").strip() or f"Session #{session_id}"
        clone_suffix = " (clone)"
        max_session_name = 255
        base_name = source_name
        if len(base_name) + len(clone_suffix) > max_session_name:
            base_name = base_name[:max_session_name - len(clone_suffix)]
        cloned_name = f"{base_name}{clone_suffix}"

        try:
            new_session_id = fpt_db.create_session(
                name=cloned_name,
                prompt_ids=prompt_ids,
                questions_snapshot=questions,
                source_group_id=source_group_id,
                status="draft",
                judge_mode=str(source_session.get("judge_mode") or "human"),
                prompts_config_snapshot=prompts_snapshot,
                created_by_telegram_id=user.telegram_id,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

        return {
            "id": new_session_id,
            "message": "Сессия клонирована в черновик",
            "question_count": len(questions),
            "expected_comparisons": fpt_db.estimate_comparisons(len(prompt_ids), len(questions)),
        }

    @router.post("/sessions/{session_id}/start")
    async def start_session(
        session_id: int,
        user: WebUser = Depends(require_permission("gk_knowledge", "edit")),
    ) -> Dict[str, Any]:
        """Запустить генерацию для сессии в статусе draft."""
        _ = user
        from admin_web.modules.gk_knowledge import db_final_prompt_tester as fpt_db

        session = fpt_db.get_session_by_id(session_id)
        if not session:
            raise HTTPException(404, "Сессия не найдена")

        status = str(session.get("status") or "")
        if status != "draft":
            raise HTTPException(409, "Запуск доступен только для сессий в статусе draft")

        prompt_ids = [int(pid) for pid in (session.get("prompt_ids") or []) if int(pid) > 0]
        if len(prompt_ids) < 2:
            raise HTTPException(400, "В сессии должно быть минимум 2 промпта")

        questions = [str(q or "").strip() for q in (session.get("questions_snapshot") or []) if str(q or "").strip()]
        if len(questions) < 1:
            raise HTTPException(400, "В сессии нет тестовых вопросов")

        raw_prompts_snapshot = session.get("prompts_config_snapshot")
        prompts_snapshot: List[Dict[str, Any]] = []
        if isinstance(raw_prompts_snapshot, list):
            for item in raw_prompts_snapshot:
                if not isinstance(item, dict):
                    continue
                prompt_id = int(item.get("id") or 0)
                if prompt_id <= 0:
                    continue
                prompts_snapshot.append(
                    {
                        "id": prompt_id,
                        "label": str(item.get("label") or f"Промпт #{prompt_id}"),
                        "prompt_template": str(item.get("prompt_template") or "").strip(),
                        "model_name": str(item.get("model_name") or "").strip() or None,
                        "temperature": float(item.get("temperature") or 0.3),
                    }
                )

        if not prompts_snapshot:
            for pid in prompt_ids:
                prompt_row = fpt_db.get_prompt_by_id(pid)
                if not prompt_row:
                    raise HTTPException(404, f"Промпт #{pid} не найден")
                prompts_snapshot.append(
                    {
                        "id": int(prompt_row.get("id") or pid),
                        "label": str(prompt_row.get("label") or f"Промпт #{pid}"),
                        "prompt_template": str(prompt_row.get("prompt_template") or "").strip(),
                        "model_name": str(prompt_row.get("model_name") or "").strip() or None,
                        "temperature": float(prompt_row.get("temperature") or 0.3),
                    }
                )

        source_group_id = session.get("source_group_id")
        if source_group_id is not None:
            source_group_id = int(source_group_id)

        if not fpt_db.update_session_status(session_id, "generating"):
            raise HTTPException(500, "Не удалось перевести сессию в статус generating")

        _spawn_gk_final_prompt_tester_generation(
            session_id=session_id,
            prompts_snapshot=prompts_snapshot,
            questions=questions,
            source_group_id=source_group_id,
        )

        return {
            "id": session_id,
            "message": "Генерация сессии запущена",
            "question_count": len(questions),
            "expected_comparisons": fpt_db.estimate_comparisons(len(prompt_ids), len(questions)),
        }

    @router.put("/sessions/{session_id}")
    async def update_session(
        session_id: int,
        body: Dict[str, Any],
        user: WebUser = Depends(require_permission("gk_knowledge", "edit")),
    ) -> Dict[str, Any]:
        """Обновить draft-сессию final prompt tester."""
        _ = user
        from admin_web.modules.gk_knowledge import db_final_prompt_tester as fpt_db

        session = fpt_db.get_session_by_id(session_id)
        if not session:
            raise HTTPException(404, "Сессия не найдена")

        if str(session.get("status") or "") != "draft":
            raise HTTPException(409, "Редактирование доступно только для draft-сессий")

        raw_prompt_ids = body.get("prompt_ids", [])
        if not isinstance(raw_prompt_ids, list):
            raise HTTPException(400, "prompt_ids должен быть массивом")

        prompt_ids: List[int] = []
        for pid in raw_prompt_ids:
            try:
                prompt_id = int(pid)
            except (TypeError, ValueError):
                continue
            if prompt_id > 0 and prompt_id not in prompt_ids:
                prompt_ids.append(prompt_id)

        if len(prompt_ids) < 2:
            raise HTTPException(400, "Необходимо минимум 2 промпта для сравнения")

        questions = _normalize_final_tester_questions(body)
        if len(questions) < 1:
            raise HTTPException(400, "Добавь минимум 1 тестовый вопрос")

        prompts_snapshot: List[Dict[str, Any]] = []
        for pid in prompt_ids:
            prompt_row = fpt_db.get_prompt_by_id(pid)
            if not prompt_row:
                raise HTTPException(404, f"Промпт #{pid} не найден")
            prompts_snapshot.append(
                {
                    "id": int(prompt_row.get("id") or pid),
                    "label": str(prompt_row.get("label") or f"Промпт #{pid}"),
                    "prompt_template": str(prompt_row.get("prompt_template") or "").strip(),
                    "model_name": str(prompt_row.get("model_name") or "").strip() or None,
                    "temperature": float(prompt_row.get("temperature") or 0.3),
                }
            )

        source_group_id = body.get("source_group_id")
        if source_group_id is not None:
            try:
                source_group_id = int(source_group_id)
            except (TypeError, ValueError) as exc:
                raise HTTPException(400, "source_group_id должен быть числом") from exc

        name = str(body.get("name") or "").strip() or str(session.get("name") or f"Session #{session_id}")
        try:
            ok = fpt_db.update_draft_session(
                session_id=session_id,
                name=name,
                prompt_ids=prompt_ids,
                questions_snapshot=questions,
                source_group_id=source_group_id,
                prompts_config_snapshot=prompts_snapshot,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        if not ok:
            raise HTTPException(409, "Не удалось обновить draft-сессию")

        return {
            "message": "Черновик сессии обновлён",
            "question_count": len(questions),
            "expected_comparisons": fpt_db.estimate_comparisons(len(prompt_ids), len(questions)),
        }

    @router.get("/sessions/{session_id}")
    async def get_session(
        session_id: int,
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> Dict[str, Any]:
        """Детали финальной сессии."""
        from admin_web.modules.gk_knowledge import db_final_prompt_tester as fpt_db

        session = fpt_db.get_session_by_id(session_id)
        if not session:
            raise HTTPException(404, "Сессия не найдена")
        for key in ("created_at", "updated_at"):
            if session.get(key) and isinstance(session[key], datetime):
                session[key] = session[key].isoformat()
        return session

    @router.get("/sessions/{session_id}/compare")
    async def get_next_comparison(
        session_id: int,
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> Dict[str, Any]:
        """Следующее слепое сравнение final prompt tester."""
        from admin_web.modules.gk_knowledge import db_final_prompt_tester as fpt_db

        comparison = fpt_db.get_next_comparison(session_id, voter_telegram_id=user.telegram_id)
        if not comparison:
            return {"has_more": False}

        answer_a = str(comparison.get("answer_a") or "").strip() or "(Пустой ответ)"
        answer_b = str(comparison.get("answer_b") or "").strip() or "(Пустой ответ)"

        conf_a = comparison.get("confidence_a")
        conf_b = comparison.get("confidence_b")
        conf_a_text = f"{float(conf_a):.2f}" if conf_a is not None else "—"
        conf_b_text = f"{float(conf_b):.2f}" if conf_b is not None else "—"

        generation_a_text = (
            f"[is_relevant={bool(comparison.get('is_relevant_a'))}, confidence={conf_a_text}]\n"
            f"{answer_a}"
        )
        generation_b_text = (
            f"[is_relevant={bool(comparison.get('is_relevant_b'))}, confidence={conf_b_text}]\n"
            f"{answer_b}"
        )

        return {
            "has_more": True,
            "comparison_id": int(comparison.get("comparison_id") or 0),
            "source_context": str(comparison.get("user_question") or "").strip() or None,
            "generation_a_text": generation_a_text,
            "generation_b_text": generation_b_text,
            "progress_total": int(comparison.get("progress_total") or 0),
            "progress_voted": int(comparison.get("progress_voted") or 0),
        }

    @router.post("/sessions/{session_id}/vote")
    async def vote(
        session_id: int,
        body: Dict[str, Any],
        user: WebUser = Depends(require_permission("gk_knowledge", "edit")),
    ) -> Dict[str, Any]:
        """Голосование: выбрать A, B, tie или skip."""
        from admin_web.modules.gk_knowledge import db_final_prompt_tester as fpt_db

        comparison_id = body.get("comparison_id")
        winner = body.get("winner")
        if not comparison_id or winner not in ("a", "b", "tie", "skip"):
            raise HTTPException(400, "Некорректные данные голосования")

        ok = fpt_db.submit_vote(
            comparison_id=int(comparison_id),
            winner=str(winner),
            expected_session_id=session_id,
            voter_telegram_id=user.telegram_id,
            voter_type="human",
        )
        if not ok:
            raise HTTPException(409, "Голос уже учтён или сравнение не найдено")
        return {"message": "Голос учтён"}

    @router.get("/sessions/{session_id}/results")
    async def get_results(
        session_id: int,
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> Dict[str, Any]:
        """Результаты final prompt tester по сессии."""
        from admin_web.modules.gk_knowledge import db_final_prompt_tester as fpt_db

        raw = fpt_db.get_session_results(session_id)
        session = fpt_db.get_session_by_id(session_id)

        total_comparisons = int((session or {}).get("total_comparisons") or 0)
        voted_comparisons = int((session or {}).get("voted_count") or 0)

        prompts: List[Dict[str, Any]] = []
        for item in raw.get("prompt_results", []):
            prompts.append(
                {
                    "prompt_id": int(item.get("prompt_id") or 0),
                    "label": item.get("label") or "",
                    "elo": float(item.get("elo") or 0),
                    "elo_delta": float(item.get("elo_delta") or 0),
                    "wins": int(item.get("wins") or 0),
                    "losses": int(item.get("losses") or 0),
                    "ties": int(item.get("ties") or 0),
                    "skips": int(item.get("skips") or 0),
                    "matches": int(item.get("matches") or 0),
                    "score": float(item.get("score") or 0.0),
                    "win_rate": float(item.get("win_rate") or 0.0),
                    "loss_rate": max(0.0, 1.0 - float(item.get("win_rate") or 0.0)),
                }
            )

        return {
            "session_id": session_id,
            "total_comparisons": total_comparisons,
            "voted_comparisons": voted_comparisons,
            "prompts": prompts,
        }

    @router.post("/sessions/{session_id}/abandon")
    async def abandon_session(
        session_id: int,
        user: WebUser = Depends(require_permission("gk_knowledge", "edit")),
    ) -> Dict[str, Any]:
        """Отменить сессию final prompt tester."""
        from admin_web.modules.gk_knowledge import db_final_prompt_tester as fpt_db

        fpt_db.update_session_status(session_id, "abandoned")
        return {"message": "Сессия отменена"}

    @router.delete("/sessions/{session_id}")
    async def delete_session(
        session_id: int,
        user: WebUser = Depends(require_permission("gk_knowledge", "edit")),
    ) -> Dict[str, Any]:
        """Удалить abandoned-сессию final prompt tester."""
        _ = user
        from admin_web.modules.gk_knowledge import db_final_prompt_tester as fpt_db

        session = fpt_db.get_session_by_id(session_id)
        if not session:
            raise HTTPException(404, "Сессия не найдена")

        if str(session.get("status") or "") != "abandoned":
            raise HTTPException(409, "Удалять можно только сессии в статусе abandoned")

        if not fpt_db.delete_session(session_id):
            raise HTTPException(500, "Не удалось удалить сессию")

        return {"message": "Сессия удалена"}

    return router


# ---------------------------------------------------------------------------
# Подроутер: Группы
# ---------------------------------------------------------------------------


def _build_groups_router() -> APIRouter:
    router = APIRouter(tags=["gk-groups"])

    @router.get("")
    async def list_groups(
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> List[Dict[str, Any]]:
        """Список мониторируемых групп."""
        from admin_web.modules.gk_knowledge import db_groups
        rows = db_groups.get_groups_list()
        return [_normalize_group_payload(row) for row in rows]

    @router.get("/{group_id}/stats")
    async def get_group_stats(
        group_id: int,
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> Dict[str, Any]:
        """Детальная статистика группы."""
        from admin_web.modules.gk_knowledge import db_groups
        stats = db_groups.get_group_detail_stats(group_id)
        if not stats:
            raise HTTPException(404, "Группа не найдена")
        return _normalize_group_detail_payload(stats)

    return router


# ---------------------------------------------------------------------------
# Подроутер: Message Browser
# ---------------------------------------------------------------------------


def _build_messages_router() -> APIRouter:
    """Подроутер браузера сообщений Group Knowledge."""
    router = APIRouter(tags=["gk-messages"])

    @router.get("/browser")
    async def get_messages_browser(
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=10, le=200),
        group_id: Optional[int] = Query(None),
        sender_id: Optional[int] = Query(None),
        processed: Optional[bool] = Query(None),
        is_question: Optional[bool] = Query(None),
        analyzed: Optional[bool] = Query(None),
        in_chain: Optional[bool] = Query(None),
        search: Optional[str] = Query(None),
        date_from: Optional[str] = Query(None),
        date_to: Optional[str] = Query(None),
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> Dict[str, Any]:
        """Получить страницу сообщений с фильтрами для Message Browser."""
        _ = user
        from admin_web.modules.gk_knowledge import db_messages_browser

        from_ts, to_ts = _parse_date_boundaries(date_from, date_to)

        items, total = db_messages_browser.list_messages(
            page=page,
            page_size=page_size,
            group_id=group_id,
            sender_id=sender_id,
            processed=processed,
            is_question=is_question,
            analyzed=analyzed,
            in_chain=in_chain,
            search=search,
            message_date_from=from_ts,
            message_date_to=to_ts,
        )

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    @router.get("/senders")
    async def get_message_senders(
        group_id: Optional[int] = Query(None),
        search: Optional[str] = Query(None),
        limit: int = Query(200, ge=20, le=500),
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> List[Dict[str, Any]]:
        """Получить список отправителей для фильтра Message Browser."""
        _ = user
        from admin_web.modules.gk_knowledge import db_messages_browser

        return db_messages_browser.list_senders(
            group_id=group_id,
            search=search,
            limit=limit,
        )

    @router.get("/chain")
    async def get_message_chain(
        group_id: int = Query(...),
        telegram_message_id: int = Query(...),
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> Dict[str, Any]:
        """Получить реконструированную цепочку для сообщения."""
        _ = user
        from admin_web.modules.gk_knowledge import db_qa_analyzer_sandbox as sandbox_db

        chain = sandbox_db.get_chain_for_message(group_id=group_id, telegram_message_id=telegram_message_id)
        return {
            "items": chain,
            "count": len(chain),
        }

    return router


# ---------------------------------------------------------------------------
# Подроутер: Лог автоответчика
# ---------------------------------------------------------------------------


def _build_responder_router() -> APIRouter:
    router = APIRouter(tags=["gk-responder"])

    @router.get("/log")
    async def get_log(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        group_id: Optional[int] = Query(None),
        dry_run: Optional[bool] = Query(None),
        min_confidence: Optional[float] = Query(None, ge=0.0, le=1.0),
        sort_by: str = Query("responded_at", pattern=r"^(responded_at|confidence|id)$"),
        sort_order: str = Query("desc", pattern=r"^(asc|desc)$"),
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> Dict[str, Any]:
        """Лог автоответчика с фильтрацией."""
        from admin_web.modules.gk_knowledge import db_responder
        rows, total = db_responder.get_responder_log(
            page=page, page_size=page_size, group_id=group_id,
            dry_run=dry_run, min_confidence=min_confidence,
            sort_by=sort_by, sort_order=sort_order,
        )
        return {"entries": rows, "total": total, "page": page, "page_size": page_size}

    @router.get("/summary")
    async def get_summary(
        group_id: Optional[int] = Query(None),
        date_from: Optional[str] = Query(None),
        date_to: Optional[str] = Query(None),
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> Dict[str, Any]:
        """Сводная статистика автоответчика."""
        from admin_web.modules.gk_knowledge import db_responder
        date_from_ts, date_to_ts = _parse_date_boundaries(date_from, date_to)
        raw = db_responder.get_responder_summary(
            group_id=group_id,
            date_from_ts=date_from_ts,
            date_to_ts=date_to_ts,
        )
        return _normalize_responder_summary_payload(raw)

    return router


# ---------------------------------------------------------------------------
# Подроутер: Очередь изображений
# ---------------------------------------------------------------------------


def _build_images_router() -> APIRouter:
    router = APIRouter(tags=["gk-images"])

    @router.get("/status")
    async def image_status(
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> Dict[str, int]:
        """Статус очереди изображений."""
        from admin_web.modules.gk_knowledge import db_images
        return db_images.get_image_queue_status()

    @router.get("/list")
    async def image_list(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        status: Optional[int] = Query(None, ge=0, le=3),
        sort_order: str = Query("desc", pattern=r"^(asc|desc)$"),
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> Dict[str, Any]:
        """Список элементов очереди."""
        from admin_web.modules.gk_knowledge import db_images
        rows, total = db_images.get_image_queue_list(
            page=page, page_size=page_size, status=status, sort_order=sort_order,
        )
        return {"items": rows, "total": total, "page": page, "page_size": page_size}

    @router.get("/{queue_id}/preview")
    async def image_preview(
        queue_id: int,
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> FileResponse:
        """Вернуть превью изображения из очереди по ID."""
        from admin_web.modules.gk_knowledge import db_images

        item = db_images.get_image_queue_item(queue_id)
        if not item:
            raise HTTPException(404, "Изображение не найдено")

        image_path_raw = str(item.get("image_path") or "").strip()
        if not image_path_raw:
            raise HTTPException(404, "У изображения отсутствует путь к файлу")

        image_path = Path(image_path_raw).expanduser().resolve()
        storage_root = Path(ai_settings.GK_IMAGE_STORAGE_PATH).expanduser().resolve()

        try:
            image_path.relative_to(storage_root)
        except Exception as exc:
            logger.warning(
                "Блокировка доступа к файлу вне GK_IMAGE_STORAGE_PATH: queue_id=%s path=%s error=%s",
                queue_id,
                image_path,
                exc,
            )
            raise HTTPException(403, "Доступ к файлу запрещён") from exc

        if not image_path.is_file():
            raise HTTPException(404, "Файл изображения не найден")

        media_type, _ = mimetypes.guess_type(str(image_path))
        return FileResponse(path=str(image_path), media_type=media_type or "application/octet-stream")

    @router.post("/upload")
    async def upload_image(
        image: UploadFile = File(...),
        group_id: int = Form(0),
        sender_name: str = Form("Admin Web"),
        user: WebUser = Depends(require_permission("gk_knowledge", "edit")),
    ) -> Dict[str, Any]:
        """Загрузить изображение вручную и поставить в очередь обработки."""
        from src.group_knowledge import database as gk_db
        from src.group_knowledge.models import GroupMessage

        filename = (image.filename or "").strip()
        if not filename:
            raise HTTPException(400, "Не удалось определить имя файла")

        suffix = Path(filename).suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
            raise HTTPException(400, "Поддерживаются только изображения: JPG, PNG, WEBP, BMP")

        now_ts = int(time.time())
        date_str = datetime.fromtimestamp(now_ts).strftime("%Y-%m-%d")
        target_dir = Path(ai_settings.GK_IMAGE_STORAGE_PATH).expanduser().resolve() / "manual_uploads" / date_str
        target_dir.mkdir(parents=True, exist_ok=True)

        safe_name = f"manual_{uuid.uuid4().hex}{suffix}"
        target_path = target_dir / safe_name

        file_bytes = await image.read()
        if not file_bytes:
            raise HTTPException(400, "Пустой файл")
        if len(file_bytes) > 20 * 1024 * 1024:
            raise HTTPException(400, "Размер файла превышает 20MB")

        target_path.write_bytes(file_bytes)

        synthetic_tg_message_id = int(time.time() * 1000)
        msg = GroupMessage(
            telegram_message_id=synthetic_tg_message_id,
            group_id=group_id,
            group_title="Manual Uploads",
            sender_id=user.telegram_id,
            sender_name=(sender_name or "Admin Web")[:255],
            message_text="",
            caption="[manual-upload]",
            has_image=True,
            image_path=str(target_path),
            image_description=None,
            reply_to_message_id=None,
            message_date=now_ts,
            collected_at=now_ts,
            processed=0,
            is_question=False,
        )

        try:
            message_id = gk_db.store_message(msg)
            queue_id = gk_db.enqueue_image(message_id, str(target_path))
            return {
                "message": "Изображение загружено и добавлено в очередь",
                "queue_id": queue_id,
                "message_id": message_id,
                "image_path": str(target_path),
            }
        except Exception as exc:
            logger.error("Ошибка загрузки изображения в очередь GK: %s", exc, exc_info=True)
            try:
                target_path.unlink(missing_ok=True)
            except Exception:
                pass
            raise HTTPException(500, "Не удалось сохранить изображение") from exc

    return router


# ---------------------------------------------------------------------------
# Подроутер: Отдельный image prompt tester
# ---------------------------------------------------------------------------


def _build_image_prompt_tester_router() -> APIRouter:
    router = APIRouter(tags=["gk-image-prompt-tester"])

    @router.get("/supported-models")
    async def get_supported_models(
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> Dict[str, Any]:
        """Список поддерживаемых моделей для image prompt tester."""
        return {
            "models": get_supported_gigachat_models(),
            "default_model": ai_settings.get_active_gk_image_description_model() or None,
        }

    @router.get("/prompts")
    async def list_prompts(
        active_only: bool = Query(True),
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> List[Dict[str, Any]]:
        """Список image-промптов."""
        from admin_web.modules.gk_knowledge import db_image_prompt_tester as ipt_db
        return ipt_db.get_prompts(active_only=active_only)

    @router.get("/stats")
    async def image_prompt_tester_stats(
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> Dict[str, Any]:
        """Агрегированная статистика image prompt tester по всем сессиям."""
        from admin_web.modules.gk_knowledge import db_image_prompt_tester as ipt_db
        return ipt_db.get_global_prompt_stats()

    @router.post("/prompts")
    async def create_prompt(
        body: Dict[str, Any],
        user: WebUser = Depends(require_permission("gk_knowledge", "edit")),
    ) -> Dict[str, Any]:
        """Создать image-промпт."""
        from admin_web.modules.gk_knowledge import db_image_prompt_tester as ipt_db

        prompt_text = str(body.get("prompt_text") or "").strip()
        if not prompt_text:
            raise HTTPException(400, "Поле prompt_text обязательно")

        prompt_id = ipt_db.create_prompt(
            label=str(body.get("label") or "Новый промпт").strip() or "Новый промпт",
            prompt_text=prompt_text,
            model_name=(str(body.get("model_name") or "").strip() or None),
            temperature=float(body.get("temperature") or 0.3),
            created_by_telegram_id=user.telegram_id,
        )
        return {"id": prompt_id, "message": "Промпт создан"}

    @router.put("/prompts/{prompt_id}")
    async def update_prompt(
        prompt_id: int,
        body: Dict[str, Any],
        user: WebUser = Depends(require_permission("gk_knowledge", "edit")),
    ) -> Dict[str, Any]:
        """Обновить image-промпт."""
        from admin_web.modules.gk_knowledge import db_image_prompt_tester as ipt_db

        model_name_value = body.get("model_name") if "model_name" in body else None
        if isinstance(model_name_value, str):
            model_name_value = model_name_value.strip() or None

        ipt_db.update_prompt(
            prompt_id,
            label=body.get("label"),
            prompt_text=body.get("prompt_text") if "prompt_text" in body else None,
            model_name=model_name_value,
            temperature=body.get("temperature"),
        )
        return {"message": "Промпт обновлён"}

    @router.delete("/prompts/{prompt_id}")
    async def delete_prompt(
        prompt_id: int,
        user: WebUser = Depends(require_permission("gk_knowledge", "edit")),
    ) -> Dict[str, Any]:
        """Деактивировать image-промпт."""
        from admin_web.modules.gk_knowledge import db_image_prompt_tester as ipt_db
        ipt_db.delete_prompt(prompt_id)
        return {"message": "Промпт деактивирован"}

    @router.get("/sessions")
    async def list_sessions(
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> List[Dict[str, Any]]:
        """Список image-сессий тестирования."""
        from admin_web.modules.gk_knowledge import db_image_prompt_tester as ipt_db
        sessions = ipt_db.get_sessions()
        for session in sessions:
            for key in ("created_at", "updated_at"):
                if session.get(key) and isinstance(session[key], datetime):
                    session[key] = session[key].isoformat()
        return sessions

    @router.post("/sessions/estimate")
    async def estimate_session(
        body: Dict[str, Any],
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> Dict[str, Any]:
        """Оценить объём image-сессии без запуска генерации."""
        from admin_web.modules.gk_knowledge import db_image_prompt_tester as ipt_db

        raw_prompt_ids = body.get("prompt_ids", [])
        if not isinstance(raw_prompt_ids, list):
            raise HTTPException(400, "prompt_ids должен быть массивом")

        normalized_prompt_ids: List[int] = []
        for pid in raw_prompt_ids:
            try:
                prompt_id = int(pid)
            except (TypeError, ValueError):
                continue
            if prompt_id > 0 and prompt_id not in normalized_prompt_ids:
                normalized_prompt_ids.append(prompt_id)

        image_count = int(body.get("image_count") or body.get("chains_count") or 20)
        if image_count < 2 or image_count > 1000:
            raise HTTPException(400, "image_count должен быть в диапазоне 2..1000")

        source_rows = ipt_db.get_source_images_for_session(
            limit=image_count,
            source_group_id=body.get("source_group_id"),
            source_date_from=body.get("source_date_from"),
            source_date_to=body.get("source_date_to"),
        )
        effective_image_count = len(source_rows)
        prompt_count = len(normalized_prompt_ids)

        return {
            "prompt_count": prompt_count,
            "requested_image_count": image_count,
            "effective_image_count": effective_image_count,
            "expected_comparisons": ipt_db.estimate_comparisons(prompt_count, effective_image_count),
            "can_create": prompt_count >= 2 and effective_image_count >= 2,
        }

    @router.post("/sessions")
    async def create_session(
        body: Dict[str, Any],
        background_tasks: BackgroundTasks,
        user: WebUser = Depends(require_permission("gk_knowledge", "edit")),
    ) -> Dict[str, Any]:
        """Создать image-сессию и запустить генерацию описаний в фоне."""
        from admin_web.modules.gk_knowledge import db_image_prompt_tester as ipt_db

        prompt_ids = body.get("prompt_ids", [])
        if not isinstance(prompt_ids, list):
            raise HTTPException(400, "prompt_ids должен быть массивом")

        normalized_prompt_ids: List[int] = []
        for pid in prompt_ids:
            try:
                value = int(pid)
            except (TypeError, ValueError):
                continue
            if value > 0 and value not in normalized_prompt_ids:
                normalized_prompt_ids.append(value)

        if len(normalized_prompt_ids) < 2:
            raise HTTPException(400, "Необходимо минимум 2 промпта для сравнения")

        image_count = int(body.get("image_count") or body.get("chains_count") or 20)
        if image_count < 2 or image_count > 1000:
            raise HTTPException(400, "image_count должен быть в диапазоне 2..1000")

        source_rows = ipt_db.get_source_images_for_session(
            limit=image_count,
            source_group_id=body.get("source_group_id"),
            source_date_from=body.get("source_date_from"),
            source_date_to=body.get("source_date_to"),
        )
        if len(source_rows) < 2:
            raise HTTPException(400, "Недостаточно изображений для теста (нужно >= 2)")

        prompts_snapshot: List[Dict[str, Any]] = []
        for pid in normalized_prompt_ids:
            prompt_row = ipt_db.get_prompt_by_id(pid)
            if not prompt_row:
                raise HTTPException(404, f"Промпт #{pid} не найден")
            prompts_snapshot.append(
                {
                    "id": int(prompt_row.get("id") or pid),
                    "label": str(prompt_row.get("label") or f"Промпт #{pid}"),
                    "prompt_text": str(prompt_row.get("prompt_text") or "").strip() or GK_IMAGE_PROMPT_TESTER_DEFAULT_PROMPT,
                    "model_name": str(prompt_row.get("model_name") or "").strip() or None,
                    "temperature": float(prompt_row.get("temperature") or 0.3),
                }
            )

        session_id = ipt_db.create_session(
            name=str(body.get("name") or "Image prompt test").strip() or "Image prompt test",
            prompt_ids=normalized_prompt_ids,
            source_group_id=body.get("source_group_id"),
            source_date_from=body.get("source_date_from"),
            source_date_to=body.get("source_date_to"),
            image_count=len(source_rows),
            source_image_ids_snapshot=[int(row.get("id") or 0) for row in source_rows if int(row.get("id") or 0) > 0],
            prompts_config_snapshot=prompts_snapshot,
            created_by_telegram_id=user.telegram_id,
        )

        background_tasks.add_task(
            _generate_gk_image_prompt_tester_session,
            session_id=session_id,
            prompts_snapshot=prompts_snapshot,
            source_rows=source_rows,
        )

        return {
            "id": session_id,
            "message": "Сессия создана, генерация запущена",
            "image_count": len(source_rows),
            "expected_comparisons": ipt_db.estimate_comparisons(len(normalized_prompt_ids), len(source_rows)),
        }

    @router.get("/sessions/{session_id}")
    async def get_session(
        session_id: int,
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> Dict[str, Any]:
        """Детали image-сессии."""
        from admin_web.modules.gk_knowledge import db_image_prompt_tester as ipt_db
        session = ipt_db.get_session_by_id(session_id)
        if not session:
            raise HTTPException(404, "Сессия не найдена")
        for key in ("created_at", "updated_at"):
            if session.get(key) and isinstance(session[key], datetime):
                session[key] = session[key].isoformat()
        return session

    @router.get("/sessions/{session_id}/compare")
    async def get_next_comparison(
        session_id: int,
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> Dict[str, Any]:
        """Следующее слепое сравнение для image-сессии."""
        from admin_web.modules.gk_knowledge import db_image_prompt_tester as ipt_db

        comparison = ipt_db.get_next_comparison(session_id)
        if not comparison:
            return {"has_more": False}

        image_queue_id = int(comparison.get("image_queue_id") or 0)

        return {
            "has_more": True,
            "comparison_id": int(comparison.get("comparison_id") or 0),
            "image_queue_id": image_queue_id,
            "image_preview_url": f"/api/gk-knowledge/images/{image_queue_id}/preview" if image_queue_id > 0 else None,
            "generation_a_text": str(comparison.get("generated_a") or "").strip(),
            "generation_b_text": str(comparison.get("generated_b") or "").strip(),
            "progress_total": int(comparison.get("progress_total") or 0),
            "progress_voted": int(comparison.get("progress_voted") or 0),
        }

    @router.post("/sessions/{session_id}/vote")
    async def vote(
        session_id: int,
        body: Dict[str, Any],
        user: WebUser = Depends(require_permission("gk_knowledge", "edit")),
    ) -> Dict[str, Any]:
        """Голосование: выбрать A, B, tie или skip для image-сравнения."""
        from admin_web.modules.gk_knowledge import db_image_prompt_tester as ipt_db

        comparison_id = body.get("comparison_id")
        winner = body.get("winner")
        if not comparison_id or winner not in ("a", "b", "tie", "skip"):
            raise HTTPException(400, "Некорректные данные голосования")

        ok = ipt_db.submit_vote(
            comparison_id=int(comparison_id),
            winner=str(winner),
            expected_session_id=session_id,
            voter_telegram_id=user.telegram_id,
        )
        if not ok:
            raise HTTPException(409, "Голос уже учтён или сравнение не найдено")
        return {"message": "Голос учтён"}

    @router.get("/sessions/{session_id}/results")
    async def get_results(
        session_id: int,
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> Dict[str, Any]:
        """Результаты image-сессии: Elo + Win Rate."""
        from admin_web.modules.gk_knowledge import db_image_prompt_tester as ipt_db

        raw = ipt_db.get_session_results(session_id)
        session = ipt_db.get_session_by_id(session_id)

        total_comparisons = int((session or {}).get("total_comparisons") or 0)
        voted_comparisons = int((session or {}).get("voted_count") or 0)

        prompts: List[Dict[str, Any]] = []
        for item in raw.get("prompt_results", []):
            prompts.append(
                {
                    "prompt_id": int(item.get("prompt_id") or 0),
                    "label": item.get("label") or "",
                    "elo": float(item.get("elo") or 0),
                    "elo_delta": float(item.get("elo_delta") or 0),
                    "wins": int(item.get("wins") or 0),
                    "losses": int(item.get("losses") or 0),
                    "ties": int(item.get("ties") or 0),
                    "skips": int(item.get("skips") or 0),
                    "matches": int(item.get("matches") or 0),
                    "score": float(item.get("score") or 0.0),
                    "win_rate": float(item.get("win_rate") or 0.0),
                    "loss_rate": max(0.0, 1.0 - float(item.get("win_rate") or 0.0)),
                }
            )

        return {
            "session_id": session_id,
            "total_comparisons": total_comparisons,
            "voted_comparisons": voted_comparisons,
            "prompts": prompts,
        }

    @router.post("/sessions/{session_id}/abandon")
    async def abandon_session(
        session_id: int,
        user: WebUser = Depends(require_permission("gk_knowledge", "edit")),
    ) -> Dict[str, Any]:
        """Отменить image-сессию."""
        from admin_web.modules.gk_knowledge import db_image_prompt_tester as ipt_db
        ipt_db.update_session_status(session_id, "abandoned")
        return {"message": "Сессия отменена"}

    return router


# ---------------------------------------------------------------------------
# Подроутер: Песочница анализатора Q&A
# ---------------------------------------------------------------------------


def _build_qa_analyzer_sandbox_router() -> APIRouter:
    """Подроутер для интерактивного тестирования промптов анализатора Q&A."""
    router = APIRouter(tags=["gk-qa-analyzer-sandbox"])

    @router.get("/search")
    async def sandbox_search(
        q: str = Query("", min_length=3, max_length=500),
        group_id: Optional[int] = Query(None),
        limit: int = Query(50, ge=1, le=100),
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> List[Dict[str, Any]]:
        """Полнотекстовый поиск сообщений по тексту (LIKE)."""
        from admin_web.modules.gk_knowledge import db_qa_analyzer_sandbox as sandbox_db
        return sandbox_db.search_messages(q, group_id=group_id, limit=limit)

    @router.get("/chain")
    async def sandbox_chain(
        group_id: int = Query(...),
        telegram_message_id: int = Query(...),
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> List[Dict[str, Any]]:
        """Реконструировать цепочку обсуждения для сообщения (алгоритм QAAnalyzer)."""
        from admin_web.modules.gk_knowledge import db_qa_analyzer_sandbox as sandbox_db
        chain = sandbox_db.get_chain_for_message(group_id, telegram_message_id)
        if not chain:
            raise HTTPException(404, "Сообщение не найдено или цепочка пуста")
        return chain

    @router.get("/supported-models")
    async def sandbox_supported_models(
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> Dict[str, Any]:
        """Список доступных моделей для анализа."""
        return {
            "models": get_supported_deepseek_models(),
            "default_model": ai_settings.get_active_gk_analysis_model() or None,
        }

    @router.get("/default-prompt")
    async def sandbox_default_prompt(
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> Dict[str, Any]:
        """Вернуть промпт и системный промпт по умолчанию для thread-валидации."""
        from src.group_knowledge.qa_analyzer import THREAD_VALIDATION_PROMPT
        return {
            "prompt_template": THREAD_VALIDATION_PROMPT,
            "system_prompt": GK_PROMPT_TESTER_SYSTEM_PROMPT,
            "question_confidence_threshold": ai_settings.get_active_gk_analysis_question_confidence_threshold(),
        }

    @router.post("/run")
    async def sandbox_run(
        body: Dict[str, Any],
        user: WebUser = Depends(require_permission("gk_knowledge", "edit")),
    ) -> Dict[str, Any]:
        """Запустить анализ цепочки с указанным промптом и моделью."""
        from admin_web.modules.gk_knowledge import db_qa_analyzer_sandbox as sandbox_db
        from src.group_knowledge.qa_analyzer import QAAnalyzer

        group_id = body.get("group_id")
        telegram_message_id = body.get("telegram_message_id")
        prompt_template = (body.get("prompt_template") or "").strip()
        system_prompt = (body.get("system_prompt") or GK_PROMPT_TESTER_SYSTEM_PROMPT).strip()
        model = (body.get("model") or "").strip() or None
        temperature = body.get("temperature")
        question_confidence_threshold = body.get("question_confidence_threshold")

        if not group_id or not telegram_message_id:
            raise HTTPException(400, "group_id и telegram_message_id обязательны")
        if not prompt_template:
            raise HTTPException(400, "prompt_template не может быть пустым")

        # Реконструировать цепочку.
        chain = sandbox_db.get_chain_for_message(group_id, telegram_message_id)
        if not chain:
            raise HTTPException(404, "Цепочка не найдена")

        # Преобразовать словари обратно в GroupMessage для _format_thread_context.
        from src.group_knowledge.models import GroupMessage as GM

        chain_messages: List[GM] = []
        for c in chain:
            chain_messages.append(GM(
                telegram_message_id=c["telegram_message_id"],
                sender_name=c.get("sender_name"),
                sender_id=c.get("sender_id"),
                message_text=c.get("message_text") or "",
                caption=c.get("caption"),
                has_image=c.get("has_image", False),
                image_description=c.get("image_description"),
                reply_to_message_id=c.get("reply_to_message_id"),
                message_date=c.get("message_date", 0),
                is_question=c.get("is_question"),
                question_confidence=c.get("question_confidence"),
            ))

        if not chain_messages:
            raise HTTPException(400, "Цепочка пуста")

        # Определить вопросное сообщение (аналогично _select_chain_question_message).
        analyzer = QAAnalyzer(model_name=model)
        question_message = analyzer._select_chain_question_message(
            chain_messages[0], chain_messages,
        )

        # Форматировать контекст цепочки.
        thread_context = QAAnalyzer._format_thread_context(chain_messages)

        # Подставить переменные в промпт.
        conf_threshold = question_confidence_threshold
        if conf_threshold is None:
            conf_threshold = ai_settings.get_active_gk_analysis_question_confidence_threshold()

        try:
            acronyms_section = analyzer.build_acronyms_section(int(group_id) if group_id else 0)
            rendered_prompt = prompt_template.format(
                question=question_message.full_text[:2000],
                thread_context=thread_context[:6000],
                question_confidence_threshold=f"{float(conf_threshold):.2f}",
                acronyms_section=acronyms_section,
            )
        except KeyError as exc:
            raise HTTPException(
                400,
                f"Ошибка подстановки переменных в промпте: неизвестная переменная {exc}",
            ) from exc

        # Вызвать LLM.
        provider_name = ai_settings.get_active_gk_text_provider()
        if not is_provider_registered(provider_name):
            logger.warning(
                "GK QA Sandbox: провайдер '%s' не зарегистрирован, используем deepseek",
                provider_name,
            )
            provider_name = "deepseek"
        provider = get_provider(provider_name)
        request_started = time.perf_counter()

        chat_kwargs: Dict[str, Any] = {
            "messages": [{"role": "user", "content": rendered_prompt}],
            "system_prompt": system_prompt,
            "purpose": "gk_validation",
            "response_format": {"type": "json_object"},
        }
        if model:
            chat_kwargs["model_override"] = model
        if temperature is not None:
            chat_kwargs["temperature_override"] = float(temperature)

        try:
            raw_response = await provider.chat(**chat_kwargs)
        except Exception as exc:
            logger.error("Ошибка LLM в sandbox: %s", exc, exc_info=True)
            raise HTTPException(502, f"Ошибка LLM: {exc}")

        elapsed_ms = int((time.perf_counter() - request_started) * 1000)

        # Распарсить ответ.
        parsed = QAAnalyzer._parse_json_response(raw_response)

        return {
            "raw_response": raw_response,
            "parsed": parsed,
            "rendered_prompt": rendered_prompt,
            "system_prompt": system_prompt,
            "thread_context": thread_context,
            "chain": chain,
            "question_message_id": question_message.telegram_message_id,
            "model": model or ai_settings.get_active_gk_analysis_model(),
            "temperature": temperature,
            "duration_ms": elapsed_ms,
        }

    return router


# ---------------------------------------------------------------------------
# Подроутер: Песочница поиска
# ---------------------------------------------------------------------------


def _build_search_router() -> APIRouter:
    router = APIRouter(tags=["gk-search"])

    @router.get("/supported-models")
    async def search_supported_models(
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> Dict[str, Any]:
        """Список доступных моделей для песочницы поиска."""
        active_provider = ai_settings.get_active_gk_text_provider()
        models = _build_text_provider_model_options().get(active_provider, [])
        default_model = ai_settings.get_active_gk_responder_model() or None
        if default_model and default_model not in models:
            models = [*models, default_model]
        return {
            "models": models,
            "default_model": default_model,
        }

    @router.post("/query")
    async def search_query(
        request: Request,
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> Dict[str, Any]:
        """Выполнить гибридный поиск по Q&A-корпусу."""
        from admin_web.modules.gk_knowledge import search_service

        content_type = (request.headers.get("content-type") or "").lower()
        image_upload: Optional[UploadFile] = None

        if "multipart/form-data" in content_type:
            form_data = await request.form()
            payload: Dict[str, Any] = dict(form_data)
            raw_image = form_data.get("image")
            if raw_image is not None and hasattr(raw_image, "read"):
                image_upload = raw_image
        else:
            payload = await request.json()

        query = str(payload.get("query") or "").strip()
        if len(query) > 1000:
            raise HTTPException(400, "Запрос слишком длинный (макс. 1000 символов)")

        image_description = ""
        if image_upload is not None:
            image_description = await _describe_uploaded_image_for_search(image_upload)
            if image_description:
                if query:
                    query = f"{query}\n[Суть по изображению: {image_description[:1200]}]"
                else:
                    query = f"[Суть по изображению: {image_description[:1200]}]"

        if not query:
            raise HTTPException(400, "Пустой поисковый запрос")

        try:
            top_k = min(int(payload.get("top_k", 10)), 50)
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, "top_k должен быть целым числом") from exc
        raw_group_id = payload.get("group_id")
        group_id = int(raw_group_id) if raw_group_id not in (None, "", "null") else None
        model_override = str(payload.get("model") or "").strip() or None
        temperature_override: Optional[float] = None
        if payload.get("temperature") not in (None, ""):
            try:
                temperature_override = float(payload.get("temperature"))
            except (TypeError, ValueError) as exc:
                raise HTTPException(400, "temperature должен быть числом") from exc
            if not 0.0 <= temperature_override <= 2.0:
                raise HTTPException(400, "temperature должен быть в диапазоне 0.0..2.0")
        request_started = time.perf_counter()
        search_result = await search_service.hybrid_search_with_answer(
            query,
            top_k=top_k,
            group_id=group_id,
            model_override=model_override,
            temperature_override=temperature_override,
        )
        elapsed_ms = int((time.perf_counter() - request_started) * 1000)
        results = search_result["results"]
        return {
            "query": query,
            "results": results,
            "result_count": len(results),
            "answer_preview": search_result["answer_preview"],
            "progress_stages": search_result.get("progress_stages", []),
            "duration_ms": elapsed_ms,
            "image_description": image_description or None,
        }

    return router


# ---------------------------------------------------------------------------
# Подроутер: Термины и аббревиатуры
# ---------------------------------------------------------------------------

# Хранилище статуса текущих сканирований (in-memory).
_term_scan_tasks: Dict[str, Dict[str, Any]] = {}


def _append_scan_progress_event(scan_batch_id: str, event: Dict[str, Any]) -> None:
    """Добавить событие прогресса в in-memory задачу сканирования."""
    task = _term_scan_tasks.get(scan_batch_id)
    if not task:
        return

    normalized_event = {
        "stage": str(event.get("stage") or "unknown"),
        "message": str(event.get("message") or ""),
        "percent": max(0.0, min(100.0, float(event.get("percent") or 0.0))),
        "updated_at": event.get("updated_at") or datetime.utcnow().isoformat(),
    }
    for key, value in event.items():
        if key not in normalized_event:
            normalized_event[key] = value

    task["progress"] = normalized_event
    progress_log = task.get("progress_log") or []
    progress_log.append(normalized_event)
    if len(progress_log) > 200:
        progress_log = progress_log[-200:]
    task["progress_log"] = progress_log


def _row_to_term_detail(row: Dict[str, Any]) -> TermDetail:
    """Преобразовать строку БД в TermDetail."""
    created_at = row.get("created_at")
    if isinstance(created_at, datetime):
        created_at = created_at.isoformat()
    updated_at = row.get("updated_at")
    if isinstance(updated_at, datetime):
        updated_at = updated_at.isoformat()
    expert_validated_at = row.get("expert_validated_at")
    if isinstance(expert_validated_at, datetime):
        expert_validated_at = expert_validated_at.isoformat()

    return TermDetail(
        id=row["id"],
        group_id=row.get("group_id", 0),
        term=row.get("term", ""),
        definition=row.get("definition"),
        source=row.get("source", "llm_discovered"),
        status=row.get("status", "pending"),
        confidence=row.get("confidence"),
        llm_model_used=row.get("llm_model_used"),
        scan_batch_id=row.get("scan_batch_id"),
        expert_status=row.get("expert_status"),
        expert_validated_at=expert_validated_at,
        created_at=created_at,
        updated_at=updated_at,
        existing_verdict=row.get("existing_verdict"),
        existing_comment=row.get("existing_comment"),
        has_definition=row.get("definition") is not None,
        message_count=int(row.get("message_count") or 0),
        message_count_updated_at=(
            row["message_count_updated_at"].isoformat()
            if isinstance(row.get("message_count_updated_at"), datetime)
            else row.get("message_count_updated_at")
        ),
    )


def _build_terms_router() -> APIRouter:
    router = APIRouter(tags=["gk-terms"])

    @router.get("/list")
    async def list_terms(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        group_id: Optional[int] = Query(None),
        has_definition: Optional[bool] = Query(None),
        status: Optional[str] = Query(None, pattern=r"^(pending|approved|rejected)$"),
        min_confidence: Optional[float] = Query(None, ge=0.0, le=1.0),
        search_text: Optional[str] = Query(None, min_length=1, max_length=200),
        search: Optional[str] = Query(None, min_length=1, max_length=200),
        expert_status: Optional[str] = Query(None, pattern=r"^(approved|rejected|unvalidated)$"),
        sort_by: str = Query("created_at", pattern=r"^(created_at|term|confidence|id|group_id|status|message_count)$"),
        sort_order: str = Query("desc", pattern=r"^(asc|desc)$"),
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> TermListResponse:
        """Список терминов с фильтрами и пагинацией."""
        from admin_web.modules.gk_knowledge import db_terms

        effective_search_text = search_text if search_text is not None else search

        rows, total, stats = db_terms.get_terms_for_validation(
            page=page, page_size=page_size, group_id=group_id,
            has_definition=has_definition, status=status, search_text=effective_search_text,
            min_confidence=min_confidence,
            expert_status=expert_status,
            sort_by=sort_by, sort_order=sort_order,
            expert_telegram_id=user.telegram_id,
        )
        terms = [_row_to_term_detail(r) for r in rows]
        return TermListResponse(
            terms=terms, total=total, page=page, page_size=page_size,
            stats=TermValidationStats(**stats),
        )

    @router.get("/stats")
    async def get_term_stats(
        group_id: Optional[int] = Query(None),
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> TermValidationStats:
        """Статистика терминов."""
        from admin_web.modules.gk_knowledge import db_terms
        stats = db_terms.get_term_validation_stats(group_id=group_id)
        return TermValidationStats(**stats)

    @router.get("/groups")
    async def get_term_groups(
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> List[Dict[str, Any]]:
        """Список групп с количеством терминов."""
        from admin_web.modules.gk_knowledge import db_terms
        return db_terms.get_groups_with_term_counts()

    @router.get("/{term_id}")
    async def get_term(
        term_id: int,
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> TermDetail:
        """Детали термина."""
        from admin_web.modules.gk_knowledge import db_terms
        row = db_terms.get_term_detail(term_id)
        if not row:
            raise HTTPException(404, "Термин не найден")
        detail = _row_to_term_detail(row)
        # Подгрузить название группы
        if detail.group_id and detail.group_id != 0:
            from admin_web.modules.gk_knowledge import db_expert_validation as ev_db
            detail.group_title = ev_db.get_group_title(detail.group_id)
        elif detail.group_id == 0:
            detail.group_title = "Глобальные (legacy)"
        # Подгрузить вердикт текущего эксперта
        existing = db_terms.get_term_verdict(term_id, user.telegram_id)
        if existing:
            detail.existing_verdict = existing["verdict"]
            detail.existing_comment = existing.get("comment")
        return detail

    @router.post("/validate")
    async def validate_term(
        body: TermValidationRequest,
        user: WebUser = Depends(require_permission("gk_knowledge", "edit")),
    ) -> Dict[str, Any]:
        """Сохранить вердикт эксперта по термину."""
        from admin_web.modules.gk_knowledge import db_terms
        row = db_terms.get_term_detail(body.term_id)
        if not row:
            raise HTTPException(404, "Термин не найден")
        validation_id = db_terms.store_term_verdict(
            term_id=body.term_id,
            expert_telegram_id=user.telegram_id,
            verdict=body.verdict.value,
            comment=body.comment,
            edited_term=body.edited_term,
            edited_definition=body.edited_definition,
        )
        db_terms.invalidate_groups_cache()
        return {
            "validation_id": validation_id,
            "term_id": body.term_id,
            "verdict": body.verdict.value,
            "message": "Вердикт сохранён",
        }

    @router.get("/{term_id}/history")
    async def get_term_history(
        term_id: int,
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> List[Dict[str, Any]]:
        """История валидации термина."""
        from admin_web.modules.gk_knowledge import db_terms
        history = db_terms.get_term_validation_history(term_id)
        for entry in history:
            for key in ("created_at", "updated_at"):
                if entry.get(key) and isinstance(entry[key], datetime):
                    entry[key] = entry[key].isoformat()
        return history

    @router.get("/{term_id}/usage-messages")
    async def get_term_usage_messages(
        term_id: int,
        limit: int = Query(10, ge=1, le=50),
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> List[Dict[str, Any]]:
        """Вернуть примеры сообщений, где встречается термин."""
        from admin_web.modules.gk_knowledge import db_terms

        row = db_terms.get_term_detail(term_id)
        if not row:
            raise HTTPException(404, "Термин не найден")

        messages = db_terms.get_term_usage_messages(
            group_id=int(row.get("group_id") or 0),
            term=str(row.get("term") or ""),
            limit=limit,
        )
        return messages

    @router.post("/scan")
    async def trigger_scan(
        body: TermScanRequest,
        user: WebUser = Depends(require_permission("gk_knowledge", "edit")),
    ) -> Dict[str, Any]:
        """Запустить LLM-сканирование терминов в фоне."""
        from src.group_knowledge.term_miner import TermMiner, recount_term_usage

        miner = TermMiner()
        scan_batch_id = str(uuid.uuid4())
        queued_progress = {
            "stage": "queued",
            "message": "Сканирование поставлено в очередь",
            "percent": 0,
            "updated_at": datetime.utcnow().isoformat(),
        }

        # Сохранить состояние в in-memory хранилище.
        _term_scan_tasks[scan_batch_id] = {
            "scan_batch_id": scan_batch_id,
            "group_id": body.group_id,
            "date_from": body.date_from,
            "date_to": body.date_to,
            "status": "queued",
            "started_at": datetime.now().isoformat(),
            "finished_at": None,
            "progress": queued_progress,
            "progress_log": [],
            "result": None,
        }
        _append_scan_progress_event(scan_batch_id, queued_progress)

        async def _run_scan() -> None:
            try:
                _term_scan_tasks[scan_batch_id]["status"] = "running"
                result = await miner.scan_group_messages(
                    group_id=body.group_id,
                    date_from=body.date_from,
                    date_to=body.date_to,
                    progress_callback=lambda event: _append_scan_progress_event(scan_batch_id, event),
                    scan_batch_id=scan_batch_id,
                )

                # Автоматический пересчёт message_count после успешного сканирования.
                _append_scan_progress_event(
                    scan_batch_id,
                    {
                        "stage": "recount_started",
                        "message": "Запуск автоматического пересчёта message_count",
                        "percent": 95,
                        "updated_at": datetime.utcnow().isoformat(),
                    },
                )

                async def _on_recount_progress(event: Dict[str, Any]) -> None:
                    recount_percent = float(event.get("percent") or 0.0)
                    # Сжимаем прогресс пересчёта в диапазон 95..100,
                    # чтобы не конфликтовать с основным прогрессом сканирования.
                    mapped_percent = 95.0 + (max(0.0, min(100.0, recount_percent)) * 0.05)
                    _append_scan_progress_event(
                        scan_batch_id,
                        {
                            "stage": f"recount_{event.get('stage', 'running')}",
                            "message": event.get("message", "Пересчёт message_count"),
                            "percent": mapped_percent,
                            "updated_at": event.get("updated_at") or datetime.utcnow().isoformat(),
                        },
                    )

                recount_result = await recount_term_usage(
                    group_id=body.group_id,
                    progress_callback=_on_recount_progress,
                )

                result["recount"] = recount_result
                _term_scan_tasks[scan_batch_id]["result"] = result
                _term_scan_tasks[scan_batch_id]["status"] = "completed"
                _term_scan_tasks[scan_batch_id]["finished_at"] = datetime.now().isoformat()
            except Exception as exc:
                logger.error("Ошибка сканирования терминов: %s", exc, exc_info=True)
                _term_scan_tasks[scan_batch_id]["status"] = "failed"
                _term_scan_tasks[scan_batch_id]["error"] = str(exc)
                _term_scan_tasks[scan_batch_id]["finished_at"] = datetime.now().isoformat()
                _append_scan_progress_event(
                    scan_batch_id,
                    {
                        "stage": "failed",
                        "message": f"Сканирование завершилось ошибкой: {exc}",
                        "percent": 100,
                        "updated_at": datetime.utcnow().isoformat(),
                    },
                )

        # Запустить как asyncio task.
        asyncio.ensure_future(_run_scan())

        return {
            "scan_batch_id": scan_batch_id,
            "status": "running",
            "message": "Сканирование запущено",
        }

    @router.get("/scan/{batch_id}/status")
    async def get_scan_status(
        batch_id: str,
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> Dict[str, Any]:
        """Статус сканирования терминов."""
        task = _term_scan_tasks.get(batch_id)
        if not task:
            raise HTTPException(404, "Задача сканирования не найдена")
        return task

    @router.post("/add")
    async def add_term(
        body: AddTermRequest,
        user: WebUser = Depends(require_permission("gk_knowledge", "edit")),
    ) -> Dict[str, Any]:
        """Добавить термин вручную."""
        from admin_web.modules.gk_knowledge import db_terms
        add_result = db_terms.add_term_manually(
            group_id=body.group_id,
            term=body.term,
            definition=body.definition,
        )
        if not add_result:
            raise HTTPException(500, "Не удалось добавить термин")
        db_terms.invalidate_groups_cache()
        msg = "Термин обновлён (уже существовал)" if add_result.get("was_duplicate") else "Термин добавлен"
        return {
            "term_id": add_result["term_id"],
            "message": msg,
            "was_duplicate": add_result.get("was_duplicate", False),
        }

    @router.delete("/{term_id}")
    async def remove_term(
        term_id: int,
        user: WebUser = Depends(require_permission("gk_knowledge", "edit")),
    ) -> Dict[str, Any]:
        """Удалить термин."""
        from admin_web.modules.gk_knowledge import db_terms
        deleted = db_terms.delete_term(term_id)
        if not deleted:
            raise HTTPException(404, "Термин не найден")
        db_terms.invalidate_groups_cache()
        return {"deleted": True, "term_id": term_id}

    # Хранилище статуса текущих пересчётов (in-memory).
    _term_recount_tasks: Dict[str, Dict[str, Any]] = {}

    @router.post("/recount")
    async def trigger_recount(
        body: TermRecountRequest,
        user: WebUser = Depends(require_permission("gk_knowledge", "edit")),
    ) -> Dict[str, Any]:
        """Запустить пересчёт message_count терминов по сообщениям группы."""
        from src.group_knowledge.term_miner import recount_term_usage

        task_id = str(uuid.uuid4())

        _term_recount_tasks[task_id] = {
            "task_id": task_id,
            "group_id": body.group_id,
            "status": "running",
            "started_at": datetime.now().isoformat(),
            "finished_at": None,
            "progress": {
                "stage": "queued",
                "message": "Пересчёт поставлен в очередь",
                "percent": 0,
                "updated_at": datetime.utcnow().isoformat(),
            },
            "result": None,
        }

        def _on_progress(event: Dict[str, Any]) -> None:
            task = _term_recount_tasks.get(task_id)
            if task:
                task["progress"] = event

        async def _run_recount() -> None:
            try:
                result = await recount_term_usage(
                    group_id=body.group_id,
                    progress_callback=_on_progress,
                )
                _term_recount_tasks[task_id]["result"] = result
                _term_recount_tasks[task_id]["status"] = "completed"
                _term_recount_tasks[task_id]["finished_at"] = datetime.now().isoformat()
            except Exception as exc:
                logger.error("Ошибка пересчёта message_count: %s", exc, exc_info=True)
                _term_recount_tasks[task_id]["status"] = "failed"
                _term_recount_tasks[task_id]["error"] = str(exc)
                _term_recount_tasks[task_id]["finished_at"] = datetime.now().isoformat()

        asyncio.ensure_future(_run_recount())

        return {
            "task_id": task_id,
            "status": "running",
            "message": "Пересчёт запущен",
        }

    @router.get("/recount/{task_id}/status")
    async def get_recount_status(
        task_id: str,
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> Dict[str, Any]:
        """Статус пересчёта message_count."""
        task = _term_recount_tasks.get(task_id)
        if not task:
            raise HTTPException(404, "Задача пересчёта не найдена")
        return task

    @router.post("/actions/reset")
    async def reset_terms_data(
        body: TermResetRequest,
        user: WebUser = Depends(require_permission("gk_knowledge", "edit")),
    ) -> Dict[str, Any]:
        """Полностью очистить термины и историю их валидаций."""
        from admin_web.modules.gk_knowledge import db_terms

        confirmation = (body.confirmation_text or "").strip()
        if confirmation != "NUKE_TERMS":
            raise HTTPException(400, "Неверная фраза подтверждения")

        reset_result = db_terms.reset_terms_and_validations()
        db_terms.invalidate_groups_cache()
        return {
            "message": "Таблицы терминов очищены",
            **reset_result,
        }

    return router
