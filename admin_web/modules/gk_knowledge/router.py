"""Главный роутер модуля Group Knowledge.

Собирает подроутеры всех вкладок:
- /stats — статистика
- /qa-pairs — список Q&A-пар
- /expert-validation — экспертная валидация
- /prompt-tester — тестер промптов
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
import re
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import ai_settings
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
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
    TermScanRequest,
    TermValidationRequest,
    TermValidationStats,
    WebUser,
)
from admin_web.core.rbac import require_permission
from src.core.ai.llm_provider import get_provider

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

    for extra_model in (ai_settings.GK_RESPONDER_MODEL, ai_settings.GK_ANALYSIS_MODEL):
        normalized = str(extra_model or "").strip()
        if normalized and normalized not in models:
            models.append(normalized)

    return models


def get_supported_gigachat_models() -> List[str]:
    """Вернуть список поддерживаемых моделей GigaChat для image prompt tester."""
    candidates = [
        ai_settings.GK_IMAGE_DESCRIPTION_MODEL,
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


def _render_gk_user_prompt(template: str, source_row: Dict[str, Any], chain_context: str) -> str:
    """Подставить значения в пользовательский промпт для генерации Q&A."""
    values = {
        "pair_id": source_row.get("id", ""),
        "group_id": source_row.get("group_id", ""),
        "question": (source_row.get("question_text") or "").strip(),
        "answer": (source_row.get("answer_text") or "").strip(),
        "chain_context": chain_context,
        "thread_context": chain_context,
        "question_confidence_threshold": f"{ai_settings.GK_ANALYSIS_QUESTION_CONFIDENCE_THRESHOLD:.2f}",
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

    provider = get_provider("deepseek")
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


async def _generate_gk_image_prompt_tester_session(
    *,
    session_id: int,
    prompts_snapshot: List[Dict[str, Any]],
    source_rows: List[Dict[str, Any]],
) -> None:
    """Сгенерировать описания изображений и подготовить blind A/B сравнения сессии."""
    from admin_web.modules.gk_knowledge import db_image_prompt_tester as ipt_db
    from src.core.ai.llm_provider import GigaChatProvider

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

                model_name = str(prompt_cfg.get("model_name") or "").strip() or str(ai_settings.GK_IMAGE_DESCRIPTION_MODEL)
                provider = providers.get(model_name)
                if provider is None:
                    provider = GigaChatProvider(model=model_name)
                    providers[model_name] = provider

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
    router.include_router(_build_groups_router(), prefix="/groups")
    router.include_router(_build_responder_router(), prefix="/responder")
    router.include_router(_build_images_router(), prefix="/images")
    router.include_router(_build_image_prompt_tester_router(), prefix="/image-prompt-tester")
    router.include_router(_build_search_router(), prefix="/search")
    router.include_router(_build_qa_analyzer_sandbox_router(), prefix="/qa-analyzer-sandbox")
    router.include_router(_build_terms_router(), prefix="/terms")

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
            "default_model": str(ai_settings.GK_RESPONDER_MODEL or "").strip() or None,
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
            "default_model": str(ai_settings.GK_IMAGE_DESCRIPTION_MODEL or "").strip() or None,
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
            "default_model": str(ai_settings.GK_ANALYSIS_MODEL or "").strip() or None,
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
            "question_confidence_threshold": ai_settings.GK_ANALYSIS_QUESTION_CONFIDENCE_THRESHOLD,
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
            conf_threshold = ai_settings.GK_ANALYSIS_QUESTION_CONFIDENCE_THRESHOLD

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
        provider = get_provider("deepseek")
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
            "model": model or str(ai_settings.GK_ANALYSIS_MODEL or ""),
            "temperature": temperature,
            "duration_ms": elapsed_ms,
        }

    return router


# ---------------------------------------------------------------------------
# Подроутер: Песочница поиска
# ---------------------------------------------------------------------------


def _build_search_router() -> APIRouter:
    router = APIRouter(tags=["gk-search"])

    @router.post("/query")
    async def search_query(
        body: Dict[str, Any],
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> Dict[str, Any]:
        """Выполнить гибридный поиск по Q&A-корпусу."""
        from admin_web.modules.gk_knowledge import search_service

        query = body.get("query", "").strip()
        if not query:
            raise HTTPException(400, "Пустой поисковый запрос")
        if len(query) > 1000:
            raise HTTPException(400, "Запрос слишком длинный (макс. 1000 символов)")

        top_k = min(body.get("top_k", 10), 50)
        raw_group_id = body.get("group_id")
        group_id = int(raw_group_id) if raw_group_id is not None else None
        request_started = time.perf_counter()
        search_result = await search_service.hybrid_search_with_answer(
            query, top_k=top_k, group_id=group_id,
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
        sort_by: str = Query("created_at", pattern=r"^(created_at|term|confidence|id|group_id|status)$"),
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

    @router.post("/scan")
    async def trigger_scan(
        body: TermScanRequest,
        background_tasks: BackgroundTasks,
        user: WebUser = Depends(require_permission("gk_knowledge", "edit")),
    ) -> Dict[str, Any]:
        """Запустить LLM-сканирование терминов в фоне."""
        from src.group_knowledge.term_miner import TermMiner

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

    return router
