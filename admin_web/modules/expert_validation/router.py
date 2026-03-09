"""FastAPI-роутер модуля экспертной валидации Q&A-пар.

Предоставляет API для:
- Просмотра Q&A-пар с фильтрацией и пагинацией
- Реконструкции цепочки сообщений
- Сохранения экспертных вердиктов (hotkeys: Y/N/S)
- Статистики валидации
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from admin_web.core.models import (
    ChainMessage,
    ExpertValidationRequest,
    ExpertValidationStats,
    QAPairDetail,
    QAPairListResponse,
    WebUser,
)
from admin_web.core.rbac import require_permission
from admin_web.modules.base import WebModule
from admin_web.modules.expert_validation import db as ev_db

logger = logging.getLogger(__name__)


class ExpertValidationModule(WebModule):
    """Модуль экспертной валидации Q&A-пар Group Knowledge."""

    @property
    def key(self) -> str:
        return "expert_validation"

    @property
    def name(self) -> str:
        return "Экспертная валидация"

    @property
    def icon(self) -> str:
        return "🔍"

    @property
    def order(self) -> int:
        return 10

    @property
    def description(self) -> str:
        return "Валидация Q&A-пар из Group Knowledge экспертами"

    def get_router(self) -> APIRouter:
        """Создать роутер с эндпоинтами экспертной валидации."""
        router = APIRouter(tags=["expert-validation"])

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
            user: WebUser = Depends(require_permission("expert_validation")),
        ) -> QAPairListResponse:
            """Получить список Q&A-пар для валидации."""
            rows, total = ev_db.get_qa_pairs_for_validation(
                page=page,
                page_size=page_size,
                group_id=group_id,
                extraction_type=extraction_type,
                question_text=question_text,
                expert_status=expert_status,
                min_confidence=min_confidence,
                max_confidence=max_confidence,
                review_low_confidence_first=review_low_confidence_first,
                sort_by=sort_by,
                sort_order=sort_order,
                expert_telegram_id=user.telegram_id,
            )

            pairs = [_row_to_pair_detail(r) for r in rows]
            stats = ev_db.get_validation_stats(group_id=group_id)

            return QAPairListResponse(
                pairs=pairs,
                total=total,
                page=page,
                page_size=page_size,
                stats=ExpertValidationStats(**stats),
            )

        @router.get("/pairs/{pair_id}")
        async def get_pair(
            pair_id: int,
            user: WebUser = Depends(require_permission("expert_validation")),
        ) -> QAPairDetail:
            """Получить детальные данные Q&A-пары с цепочкой сообщений."""
            row = ev_db.get_qa_pair_detail(pair_id)
            if not row:
                raise HTTPException(404, "Q&A-пара не найдена")

            pair = _row_to_pair_detail(row)

            # Загрузить цепочку сообщений
            chain = ev_db.get_chain_messages(pair_id)
            pair.chain_messages = [_row_to_chain_message(m) for m in chain]

            # Загрузить название группы
            if pair.group_id:
                pair.group_title = ev_db.get_group_title(pair.group_id)

            # Загрузить существующий вердикт эксперта
            existing = ev_db.get_expert_verdict(pair_id, user.telegram_id)
            if existing:
                pair.existing_verdict = existing["verdict"]
                pair.existing_comment = existing.get("comment")

            return pair

        @router.get("/pairs/{pair_id}/chain")
        async def get_chain(
            pair_id: int,
            user: WebUser = Depends(require_permission("expert_validation")),
        ) -> List[ChainMessage]:
            """Получить цепочку сообщений для Q&A-пары."""
            chain = ev_db.get_chain_messages(pair_id)
            if not chain:
                # Не ошибка — пара может не иметь восстановимой цепочки
                return []
            return [_row_to_chain_message(m) for m in chain]

        @router.post("/validate")
        async def validate_pair(
            body: ExpertValidationRequest,
            user: WebUser = Depends(require_permission("expert_validation", "edit")),
        ) -> Dict[str, Any]:
            """Сохранить экспертный вердикт по Q&A-паре."""
            # Проверить существование пары
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
            user: WebUser = Depends(require_permission("expert_validation")),
        ) -> List[Dict[str, Any]]:
            """Получить историю валидации Q&A-пары (все эксперты)."""
            history = ev_db.get_validation_history(pair_id)
            # Сериализуем datetime
            for entry in history:
                for key in ("created_at", "updated_at"):
                    if entry.get(key) and isinstance(entry[key], datetime):
                        entry[key] = entry[key].isoformat()
            return history

        @router.get("/stats")
        async def get_stats(
            group_id: Optional[int] = Query(None),
            user: WebUser = Depends(require_permission("expert_validation")),
        ) -> ExpertValidationStats:
            """Получить статистику экспертной валидации."""
            stats = ev_db.get_validation_stats(group_id=group_id)
            return ExpertValidationStats(**stats)

        @router.get("/groups")
        async def get_groups(
            user: WebUser = Depends(require_permission("expert_validation")),
        ) -> List[Dict[str, Any]]:
            """Получить список групп с количеством Q&A-пар."""
            return ev_db.get_collected_groups()

        return router


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
