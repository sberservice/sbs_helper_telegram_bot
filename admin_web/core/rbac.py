"""Role-Based Access Control (RBAC) для веб-платформы.

Предоставляет FastAPI-зависимости для проверки прав доступа к модулям.
super_admin всегда имеет полный доступ.
"""

from __future__ import annotations

import logging
from typing import Callable

from fastapi import Depends, HTTPException

from admin_web.core.auth import get_current_user
from admin_web.core.models import WebRole, WebUser

logger = logging.getLogger(__name__)


def require_permission(
    module_key: str,
    access_type: str = "view",
) -> Callable:
    """
    Фабрика FastAPI-зависимостей для проверки прав доступа.

    Args:
        module_key: Ключ модуля (например, 'expert_validation', 'prompt_tester').
        access_type: Тип доступа ('view' или 'edit').

    Returns:
        FastAPI Depends, возвращающий WebUser если доступ разрешён.

    Raises:
        HTTPException 403 если доступ запрещён.

    Пример:
        @router.get("/api/expert/pairs")
        async def list_pairs(user: WebUser = Depends(require_permission("expert_validation"))):
            ...
    """
    async def _check(user: WebUser = Depends(get_current_user)) -> WebUser:
        if not user.has_permission(module_key, access_type):
            logger.warning(
                "Доступ запрещён: telegram_id=%d role=%s module=%s access=%s",
                user.telegram_id, user.role.value, module_key, access_type,
            )
            raise HTTPException(
                status_code=403,
                detail=f"Нет доступа к модулю '{module_key}' ({access_type})",
            )
        return user

    return _check


def require_role(*roles: WebRole) -> Callable:
    """
    Фабрика FastAPI-зависимостей для проверки роли пользователя.
    
    Пример:
        @router.post("/api/admin/roles")
        async def manage_roles(user: WebUser = Depends(require_role(WebRole.SUPER_ADMIN))):
            ...
    """
    async def _check(user: WebUser = Depends(get_current_user)) -> WebUser:
        if user.role not in roles and user.role != WebRole.SUPER_ADMIN:
            raise HTTPException(
                status_code=403,
                detail="Недостаточно прав для данного действия",
            )
        return user

    return _check


def require_authenticated() -> Callable:
    """
    FastAPI-зависимость, требующая только аутентификации (любая роль).

    Пример:
        @router.get("/api/me")
        async def me(user: WebUser = Depends(require_authenticated())):
            return user
    """
    async def _check(user: WebUser = Depends(get_current_user)) -> WebUser:
        return user

    return _check
