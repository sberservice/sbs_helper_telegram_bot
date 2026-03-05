"""Pydantic-модели запросов и ответов API тестера промптов."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Промпты (CRUD)
# ---------------------------------------------------------------------------

class PromptCreate(BaseModel):
    """Запрос на создание пары промптов."""

    label: str = Field(..., min_length=1, max_length=255, description="Человекочитаемое название")
    system_prompt_template: str = Field(..., min_length=1, description="Шаблон system prompt")
    user_message: str = Field(..., min_length=1, description="User message для LLM")
    model_name: Optional[str] = Field(None, max_length=128, description="Override модели")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0, description="Override температуры")


class PromptUpdate(BaseModel):
    """Запрос на обновление пары промптов."""

    label: Optional[str] = Field(None, min_length=1, max_length=255)
    system_prompt_template: Optional[str] = Field(None, min_length=1)
    user_message: Optional[str] = Field(None, min_length=1)
    model_name: Optional[str] = Field(None, max_length=128)
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    # Специальный флаг для явного сброса значения в NULL
    clear_model_name: bool = Field(False, description="Сбросить model_name в NULL")
    clear_temperature: bool = Field(False, description="Сбросить temperature в NULL")


class PromptResponse(BaseModel):
    """Ответ с данными пары промптов."""

    id: int
    label: str
    system_prompt_template: str
    user_message: str
    model_name: Optional[str] = None
    temperature: Optional[float] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    usage_count: int = 0


# ---------------------------------------------------------------------------
# Сессии
# ---------------------------------------------------------------------------

class SessionCreate(BaseModel):
    """Запрос на создание тестовой сессии."""

    name: str = Field(..., min_length=1, max_length=255, description="Название сессии")
    prompt_ids: List[int] = Field(..., min_length=2, description="ID промптов для сравнения (минимум 2)")
    document_count: int = Field(10, ge=2, le=100, description="Количество документов")
    judge_mode: str = Field("human", pattern=r"^(human|llm|both)$", description="Режим оценки")


class SessionResponse(BaseModel):
    """Ответ со статусом сессии."""

    id: int
    name: str
    status: str
    prompt_ids_snapshot: List[int]
    prompts_config_snapshot: List[Dict[str, Any]]
    document_ids: List[int]
    total_comparisons: int
    completed_comparisons: int
    judge_mode: str
    created_at: datetime
    updated_at: datetime


class SessionListItem(BaseModel):
    """Краткая информация о сессии для списка."""

    id: int
    name: str
    status: str
    total_comparisons: int
    completed_comparisons: int
    judge_mode: str
    prompt_count: int
    document_count: int
    created_at: datetime


# ---------------------------------------------------------------------------
# Тестирование (голосование)
# ---------------------------------------------------------------------------

class ComparisonResponse(BaseModel):
    """Следующая пара для слепого сравнения."""

    document_id: int
    document_name: str
    generation_a: Dict[str, Any]  # {id, summary_text}
    generation_b: Dict[str, Any]  # {id, summary_text}
    progress: Dict[str, int]  # {completed, total}
    has_more: bool


class VoteRequest(BaseModel):
    """Запрос на голосование."""

    generation_a_id: int
    generation_b_id: int
    winner: str = Field(..., pattern=r"^(a|b|tie|skip)$", description="Результат: a, b, tie или skip")


# ---------------------------------------------------------------------------
# Документ
# ---------------------------------------------------------------------------

class DocumentContentResponse(BaseModel):
    """Содержимое документа для просмотра."""

    document_id: int
    filename: str
    source_type: str
    chunks: List[str]
    chunks_count: int


# ---------------------------------------------------------------------------
# Результаты
# ---------------------------------------------------------------------------

class PromptResult(BaseModel):
    """Результаты одного промпта в сессии."""

    prompt_id: int
    label: str
    model_name: Optional[str] = None
    temperature: Optional[float] = None
    wins: int = 0
    losses: int = 0
    ties: int = 0
    skips: int = 0
    win_rate: float = 0.0
    elo: float = 1500.0


class SessionResults(BaseModel):
    """Полные результаты сессии."""

    session_id: int
    session_name: str
    status: str
    human_results: List[PromptResult]
    llm_results: List[PromptResult]
    document_breakdown: List[Dict[str, Any]]


class AggregateResults(BaseModel):
    """Агрегированные результаты по нескольким сессиям."""

    prompt_results: List[PromptResult]
    sessions_count: int
    total_votes: int
