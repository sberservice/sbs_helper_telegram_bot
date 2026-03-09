"""Главный роутер модуля Group Knowledge.

Собирает подроутеры всех вкладок:
- /stats — статистика
- /qa-pairs — список Q&A-пар
- /expert-validation — экспертная валидация
- /prompt-tester — тестер промптов
- /groups — группы
- /responder — лог автоответчика
- /images — очередь изображений
- /search — песочница поиска
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from config import ai_settings
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from admin_web.core.models import (
    ChainMessage,
    ExpertValidationRequest,
    ExpertValidationStats,
    QAPairDetail,
    QAPairListResponse,
    WebUser,
)
from admin_web.core.rbac import require_permission
from src.core.ai.llm_provider import get_provider

logger = logging.getLogger(__name__)


GK_PROMPT_TESTER_SYSTEM_PROMPT = "Ты — помощник для анализа пар вопрос-ответ."


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

    try:
        for source_row in source_rows:
            pair_id = int(source_row.get("id") or 0)
            chain_messages: List[Dict[str, Any]] = ev_db.get_chain_messages(pair_id) if pair_id else []
            chain_context = _format_chain_context(chain_messages, source_row)

            for prompt_cfg in prompts_snapshot:
                user_template = (prompt_cfg.get("user_prompt") or "").strip()
                if not user_template:
                    continue

                prompt_text = _render_gk_user_prompt(user_template, source_row, chain_context)
                raw = await provider.chat(
                    messages=[{"role": "user", "content": prompt_text}],
                    system_prompt=GK_PROMPT_TESTER_SYSTEM_PROMPT,
                    purpose="gk_inference",
                    model_override=prompt_cfg.get("model_name"),
                    response_format={"type": "json_object"},
                )

                parsed = _extract_generated_pair(raw)
                if not parsed:
                    logger.warning(
                        "GK Prompt Tester: пустая/невалидная генерация: session=%d pair_id=%s prompt_id=%s",
                        session_id,
                        source_row.get("id"),
                        prompt_cfg.get("id"),
                    )
                    continue

                pt_db.save_generation(
                    session_id=session_id,
                    prompt_id=int(prompt_cfg["id"]),
                    question_text=parsed["question"],
                    answer_text=parsed["answer"],
                    confidence=parsed["confidence"],
                    extraction_type=str(prompt_cfg.get("extraction_type") or "llm_inferred"),
                    raw_llm_response=raw,
                )
                generated_count += 1
                await asyncio.sleep(0.15)

        comparisons_count = pt_db.create_comparisons_for_session(session_id)
        final_status = "judging" if comparisons_count > 0 else "completed"
        pt_db.update_session_status(session_id, final_status)
        logger.info(
            "GK Prompt Tester: генерация завершена: session=%d generations=%d comparisons=%d status=%s",
            session_id,
            generated_count,
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
    router.include_router(_build_search_router(), prefix="/search")

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
        return db_stats.get_overview_stats(group_id=group_id)

    @router.get("/timeline")
    async def stats_timeline(
        group_id: Optional[int] = Query(None),
        days: int = Query(30, ge=1, le=365),
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> Dict[str, Any]:
        """Временные ряды по дням."""
        from admin_web.modules.gk_knowledge import db_stats
        return db_stats.get_timeline_stats(group_id=group_id, days=days)

    @router.get("/distribution")
    async def stats_distribution(
        group_id: Optional[int] = Query(None),
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> List[Dict[str, Any]]:
        """Распределение Q&A-пар по уверенности."""
        from admin_web.modules.gk_knowledge import db_stats
        return db_stats.get_confidence_distribution(group_id=group_id)

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

    @router.post("/sessions")
    async def create_session(
        body: Dict[str, Any],
        background_tasks: BackgroundTasks,
        user: WebUser = Depends(require_permission("gk_knowledge", "edit")),
    ) -> Dict[str, Any]:
        """Создать сессию тестирования."""
        from admin_web.modules.gk_knowledge import db_prompt_tester as pt_db

        prompt_ids = body.get("prompt_ids", [])
        if len(prompt_ids) < 2:
            raise HTTPException(400, "Необходимо минимум 2 промпта для сравнения")

        chains_count = int(body.get("chains_count") or body.get("message_count") or 20)
        if chains_count < 2 or chains_count > 1000:
            raise HTTPException(400, "chains_count должен быть в диапазоне 2..1000")

        source_rows = pt_db.get_source_pairs_for_session(
            limit=chains_count,
            source_group_id=body.get("source_group_id"),
            source_date_from=body.get("source_date_from"),
            source_date_to=body.get("source_date_to"),
        )
        if len(source_rows) < 2:
            raise HTTPException(400, "Недостаточно цепочек для теста (нужно >= 2)")

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
                "wins": int(item.get("wins") or 0),
                "losses": int(item.get("losses") or 0),
                "ties": int(item.get("ties") or 0),
                "win_rate": float(item.get("win_rate") or 0.0) / 100.0,
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
        return db_groups.get_groups_list()

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
        return stats

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
        user: WebUser = Depends(require_permission("gk_knowledge")),
    ) -> Dict[str, Any]:
        """Сводная статистика автоответчика."""
        from admin_web.modules.gk_knowledge import db_responder
        return db_responder.get_responder_summary(group_id=group_id)

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
        search_result = await search_service.hybrid_search_with_answer(query, top_k=top_k)
        results = search_result["results"]
        return {
            "query": query,
            "results": results,
            "result_count": len(results),
            "answer_preview": search_result["answer_preview"],
        }

    return router
