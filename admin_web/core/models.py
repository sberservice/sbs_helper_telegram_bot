"""Pydantic-модели аутентификации и RBAC веб-платформы."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Роли и права
# ---------------------------------------------------------------------------

class WebRole(str, Enum):
    """Роли пользователей веб-платформы."""

    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    EXPERT = "expert"
    VIEWER = "viewer"


class ModulePermission(BaseModel):
    """Права доступа к конкретному модулю."""

    module_key: str
    can_view: bool = False
    can_edit: bool = False


# ---------------------------------------------------------------------------
# Пользователь
# ---------------------------------------------------------------------------

class WebUser(BaseModel):
    """Аутентифицированный пользователь веб-платформы."""

    telegram_id: int
    telegram_username: Optional[str] = None
    telegram_first_name: Optional[str] = None
    telegram_last_name: Optional[str] = None
    telegram_photo_url: Optional[str] = None
    auth_method: str = "telegram"
    local_account_id: Optional[int] = None
    role: WebRole = WebRole.VIEWER
    permissions: List[ModulePermission] = Field(default_factory=list)

    @property
    def display_name(self) -> str:
        """Отображаемое имя пользователя."""
        parts = []
        if self.telegram_first_name:
            parts.append(self.telegram_first_name)
        if self.telegram_last_name:
            parts.append(self.telegram_last_name)
        if parts:
            return " ".join(parts)
        if self.telegram_username:
            return f"@{self.telegram_username}"
        return str(self.telegram_id)

    def has_permission(self, module_key: str, access_type: str = "view") -> bool:
        """Проверить, есть ли у пользователя доступ к модулю."""
        if self.role == WebRole.SUPER_ADMIN:
            return True
        for perm in self.permissions:
            if perm.module_key == module_key:
                if access_type == "view":
                    return perm.can_view
                if access_type == "edit":
                    return perm.can_edit
                return False
        return False


# ---------------------------------------------------------------------------
# Запросы аутентификации
# ---------------------------------------------------------------------------

class TelegramAuthData(BaseModel):
    """Данные аутентификации от Telegram Login Widget."""

    id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None
    photo_url: Optional[str] = None
    auth_date: int
    hash: str


class AuthResponse(BaseModel):
    """Ответ на успешную аутентификацию."""

    success: bool
    user: Optional[WebUser] = None
    session_token: Optional[str] = None
    message: str = ""


class DevLoginRequest(BaseModel):
    """Запрос аутентификации в dev-режиме (без Telegram)."""

    telegram_id: int = Field(..., description="Telegram ID для эмуляции")
    first_name: str = Field("Dev", description="Имя")


class PasswordLoginRequest(BaseModel):
    """Запрос аутентификации по логину/паролю."""

    login: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=256)


class CreateLocalAccountRequest(BaseModel):
    """Запрос создания локального password-аккаунта."""

    login: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=1, max_length=256)
    role: WebRole = WebRole.VIEWER
    linked_telegram_id: Optional[int] = None
    display_name: Optional[str] = Field(None, max_length=255)
    is_active: bool = True


class ResetLocalAccountPasswordRequest(BaseModel):
    """Запрос сброса пароля локального аккаунта."""

    new_password: str = Field(..., min_length=1, max_length=256)


class LocalAccountResponse(BaseModel):
    """Данные локального password-аккаунта."""

    id: int
    login: str
    principal_telegram_id: int
    linked_telegram_id: Optional[int] = None
    display_name: Optional[str] = None
    is_active: bool = True
    failed_attempts: int = 0
    locked_until: Optional[Any] = None
    created_at: Optional[Any] = None
    updated_at: Optional[Any] = None
    role: WebRole = WebRole.VIEWER


# ---------------------------------------------------------------------------
# Экспертная валидация
# ---------------------------------------------------------------------------

class ExpertVerdict(str, Enum):
    """Вердикт эксперта по Q&A-паре."""

    APPROVED = "approved"
    REJECTED = "rejected"
    SKIPPED = "skipped"


class ExpertValidationRequest(BaseModel):
    """Запрос на валидацию Q&A-пары экспертом."""

    qa_pair_id: int
    verdict: ExpertVerdict
    comment: Optional[str] = Field(None, max_length=2000)


class ChainMessage(BaseModel):
    """Сообщение из цепочки обсуждения."""

    telegram_message_id: int
    sender_name: Optional[str] = None
    sender_id: Optional[int] = None
    message_text: Optional[str] = None
    caption: Optional[str] = None
    image_description: Optional[str] = None
    has_image: bool = False
    reply_to_message_id: Optional[int] = None
    message_date: int = 0
    is_question: Optional[bool] = None
    question_confidence: Optional[float] = None


class QAPairDetail(BaseModel):
    """Детальные данные Q&A-пары для экспертной валидации."""

    id: int
    question_text: str
    answer_text: str
    question_message_id: Optional[int] = None
    answer_message_id: Optional[int] = None
    group_id: Optional[int] = None
    group_title: Optional[str] = None
    extraction_type: str = ""
    confidence: float = 0.0
    llm_model_used: Optional[str] = None
    llm_request_payload: Optional[str] = None
    created_at: Optional[Any] = None
    approved: int = 1
    expert_status: Optional[str] = None
    expert_validated_at: Optional[Any] = None
    chain_messages: List[ChainMessage] = Field(default_factory=list)
    existing_verdict: Optional[str] = None
    existing_comment: Optional[str] = None


class ExpertValidationStats(BaseModel):
    """Статистика экспертной валидации."""

    total_pairs: int = 0
    validated_pairs: int = 0
    approved_pairs: int = 0
    rejected_pairs: int = 0
    skipped_pairs: int = 0
    unvalidated_pairs: int = 0
    approval_rate: float = 0.0


class QAPairListResponse(BaseModel):
    """Ответ со списком Q&A-пар для валидации."""

    pairs: List[QAPairDetail]
    total: int
    page: int
    page_size: int
    stats: ExpertValidationStats


# ---------------------------------------------------------------------------
# Термины и аббревиатуры
# ---------------------------------------------------------------------------

class TermVerdict(str, Enum):
    """Вердикт эксперта по термину."""

    APPROVED = "approved"
    REJECTED = "rejected"
    EDITED = "edited"


class TermValidationRequest(BaseModel):
    """Запрос на валидацию термина экспертом."""

    term_id: int
    verdict: TermVerdict
    comment: Optional[str] = Field(None, max_length=2000)
    edited_term: Optional[str] = Field(None, max_length=100)
    edited_definition: Optional[str] = Field(None, max_length=2000)


class TermDetail(BaseModel):
    """Детальные данные термина."""

    id: int
    group_id: int = 0
    group_title: Optional[str] = None
    term: str
    definition: Optional[str] = None
    source: str = "llm_discovered"
    status: str = "pending"
    confidence: Optional[float] = None
    llm_model_used: Optional[str] = None
    scan_batch_id: Optional[str] = None
    expert_status: Optional[str] = None
    expert_validated_at: Optional[Any] = None
    created_at: Optional[Any] = None
    updated_at: Optional[Any] = None
    existing_verdict: Optional[str] = None
    existing_comment: Optional[str] = None
    has_definition: bool = False
    message_count: int = 0
    message_count_updated_at: Optional[Any] = None


class TermValidationStats(BaseModel):
    """Статистика терминов."""

    total: int = 0
    pending: int = 0
    approved: int = 0
    rejected: int = 0
    with_definition: int = 0
    without_definition: int = 0


class TermListResponse(BaseModel):
    """Ответ со списком терминов."""

    terms: List[TermDetail]
    total: int
    page: int
    page_size: int
    stats: TermValidationStats


class AddTermRequest(BaseModel):
    """Запрос на ручное добавление термина."""

    group_id: int = 0
    term: str = Field(..., min_length=1, max_length=100)
    definition: Optional[str] = Field(None, max_length=2000)


class TermScanRequest(BaseModel):
    """Запрос на сканирование терминов."""

    group_id: int
    date_from: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    date_to: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")


class TermRecountRequest(BaseModel):
    """Запрос на пересчёт message_count терминов."""

    group_id: int


class TermResetRequest(BaseModel):
    """Запрос на полную очистку терминов и их валидаций."""

    confirmation_text: str = Field(..., min_length=1, max_length=64)
