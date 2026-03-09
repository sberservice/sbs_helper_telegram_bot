"""Главное FastAPI-приложение единой веб-платформы SBS Archie.

Объединяет все модули (экспертная валидация, prompt tester) под единой
аутентификацией и RBAC. Предоставляет:
- Telegram Login Widget аутентификацию
- API для управления ролями
- Монтирование модулей как sub-routers
- Раздачу React SPA frontend

Запуск: python -m admin_web
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Добавляем корень проекта в sys.path
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from admin_web.core import db as web_db
from admin_web.core.auth import (
    SESSION_COOKIE_NAME,
    authenticate_password_login,
    create_authenticated_session,
    get_current_user,
    get_optional_user,
    is_dev_mode,
    is_password_auth_enabled,
    validate_password_policy,
    verify_telegram_auth,
)
from admin_web.core.models import (
    AuthResponse,
    CreateLocalAccountRequest,
    DevLoginRequest,
    LocalAccountResponse,
    PasswordLoginRequest,
    ResetLocalAccountPasswordRequest,
    TelegramAuthData,
    WebRole,
    WebUser,
)
from admin_web.core.rbac import require_role
from admin_web.modules.base import WebModule
from admin_web.modules.gk_knowledge.module import GKKnowledgeModule
from admin_web.modules.process_manager.module import ProcessManagerModule

logger = logging.getLogger(__name__)

app = FastAPI(
    title="SBS Archie Admin",
    description="Единая веб-платформа администрирования SBS Archie",
    version="1.0.0",
)

# CORS для dev-сервера React (Vite)
_FRONTEND_DEV_PORT = os.getenv("ADMIN_WEB_FRONTEND_DEV_PORT", "5174")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        f"http://localhost:{_FRONTEND_DEV_PORT}",
        f"http://127.0.0.1:{_FRONTEND_DEV_PORT}",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Реестр модулей
# ---------------------------------------------------------------------------

_MODULES: List[WebModule] = []


def register_module(module: WebModule) -> None:
    """Зарегистрировать модуль в приложении."""
    router = module.get_router()
    app.include_router(router, prefix=module.api_prefix)
    _MODULES.append(module)
    logger.info(
        "Модуль зарегистрирован: key=%s name=%s prefix=%s",
        module.key, module.name, module.api_prefix,
    )


# Регистрация модулей
register_module(ProcessManagerModule())
register_module(GKKnowledgeModule())

# Prompt tester как sub-application (если доступен)
try:
    from prompt_tester.backend.app import app as _prompt_tester_app
    app.mount("/prompt-tester", _prompt_tester_app)
    logger.info("Prompt Tester подключён как sub-application на /prompt-tester")
except ImportError:
    logger.warning("Prompt Tester не найден, пропускаем монтирование")


# ---------------------------------------------------------------------------
# Статика (React build)
# ---------------------------------------------------------------------------

_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


@app.on_event("startup")
async def _mount_static() -> None:
    """Подключить статику React-билда."""
    if _FRONTEND_DIST.is_dir():
        app.mount(
            "/assets",
            StaticFiles(directory=str(_FRONTEND_DIST / "assets")),
            name="admin-assets",
        )
        logger.info("Статика React подключена из %s", _FRONTEND_DIST)
    else:
        logger.warning(
            "React build не найден: %s — запустите: cd admin_web/frontend && npm run build",
            _FRONTEND_DIST,
        )

    # Вызов startup-хуков модулей
    for module in _MODULES:
        module.on_startup()

    # Очистка истёкших сессий при старте
    web_db.cleanup_expired_sessions()


@app.on_event("shutdown")
async def _shutdown() -> None:
    """Хуки завершения модулей."""
    for module in _MODULES:
        module.on_shutdown()


# ---------------------------------------------------------------------------
# API: Аутентификация
# ---------------------------------------------------------------------------


@app.post("/api/auth/telegram")
async def auth_telegram(
    data: TelegramAuthData,
    request: Request,
    response: Response,
) -> AuthResponse:
    """
    Аутентификация через Telegram Login Widget.

    Принимает данные от виджета, верифицирует HMAC-хеш,
    создаёт сессию и устанавливает cookie.
    """
    if not verify_telegram_auth(data):
        raise HTTPException(401, "Неверные данные аутентификации Telegram")

    token = create_authenticated_session(data, request)
    user = web_db.build_web_user(
        telegram_id=data.id,
        telegram_username=data.username,
        telegram_first_name=data.first_name,
        telegram_last_name=data.last_name,
        telegram_photo_url=data.photo_url,
    )

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=72 * 3600,
        secure=request.url.scheme == "https",
    )

    return AuthResponse(
        success=True,
        user=user,
        session_token=token,
        message="Аутентификация успешна",
    )


@app.post("/api/auth/dev-login")
async def dev_login(
    body: DevLoginRequest,
    request: Request,
    response: Response,
) -> AuthResponse:
    """
    Dev-режим: аутентификация без Telegram-верификации.

    Доступен только при ADMIN_WEB_DEV_MODE=true.
    """
    if not is_dev_mode():
        raise HTTPException(403, "Dev-режим отключён")

    data = TelegramAuthData(
        id=body.telegram_id,
        first_name=body.first_name,
        auth_date=int(__import__("time").time()),
        hash="dev_mode",
    )

    token = create_authenticated_session(data, request)
    user = web_db.build_web_user(
        telegram_id=body.telegram_id,
        telegram_first_name=body.first_name,
    )

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=72 * 3600,
    )

    return AuthResponse(
        success=True,
        user=user,
        session_token=token,
        message="Dev-аутентификация успешна",
    )


@app.post("/api/auth/password-login")
async def password_login(
    body: PasswordLoginRequest,
    request: Request,
    response: Response,
) -> AuthResponse:
    """Аутентификация по логину/паролю с lockout/rate-limit."""
    user, token = authenticate_password_login(body, request)

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=72 * 3600,
        secure=request.url.scheme == "https",
    )

    return AuthResponse(
        success=True,
        user=user,
        session_token=token,
        message="Аутентификация успешна",
    )


@app.post("/api/auth/logout")
async def logout(
    request: Request,
    response: Response,
    _user: WebUser = Depends(get_current_user),
) -> Dict[str, str]:
    """Выход: деактивация сессии и удаление cookie."""
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if session_token:
        web_db.invalidate_session(session_token)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"message": "Выход выполнен"}


@app.get("/api/auth/me")
async def get_me(user: WebUser = Depends(get_current_user)) -> WebUser:
    """Получить данные текущего пользователя."""
    return user


@app.get("/api/auth/check")
async def check_auth(
    user: Optional[WebUser] = Depends(get_optional_user),
) -> Dict[str, Any]:
    """Проверить статус аутентификации (без 401 ошибки)."""
    if user:
        return {
            "authenticated": True,
            "user": user.model_dump(),
        }
    return {
        "authenticated": False,
        "dev_mode": is_dev_mode(),
    }


@app.get("/api/auth/config")
async def get_auth_config() -> Dict[str, Any]:
    """Получить конфигурацию аутентификации для фронтенда."""
    from src.common.constants.telegram import TELEGRAM_TOKEN

    # Извлекаем bot_id из токена (первая часть до :)
    bot_id = TELEGRAM_TOKEN.split(":")[0] if ":" in TELEGRAM_TOKEN else ""
    bot_username = (
        os.getenv("ADMIN_WEB_TELEGRAM_BOT_USERNAME")
        or os.getenv("TELEGRAM_BOT_USERNAME")
        or ""
    ).strip().lstrip("@")

    return {
        "dev_mode": is_dev_mode(),
        "bot_id": bot_id,
        "bot_username": bot_username,
        "password_auth_enabled": is_password_auth_enabled(),
    }


# ---------------------------------------------------------------------------
# API: Навигация модулей
# ---------------------------------------------------------------------------


@app.get("/api/modules")
async def list_modules(
    user: WebUser = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """Получить список доступных модулей для текущего пользователя."""
    result = []
    for module in sorted(_MODULES, key=lambda m: m.order):
        if user.has_permission(module.key, "view"):
            result.append({
                "key": module.key,
                "name": module.name,
                "icon": module.icon,
                "description": module.description,
                "api_prefix": module.api_prefix,
                "can_edit": user.has_permission(module.key, "edit"),
            })

    # Добавляем prompt tester если доступен и есть права
    if user.has_permission("prompt_tester", "view"):
        result.append({
            "key": "prompt_tester",
            "name": "Prompt Tester",
            "icon": "⚡",
            "description": "A/B тестирование промптов",
            "api_prefix": "/prompt-tester/api",
            "can_edit": user.has_permission("prompt_tester", "edit"),
            "external_url": "/prompt-tester/",
        })

    return result


# ---------------------------------------------------------------------------
# API: Управление ролями (только super_admin)
# ---------------------------------------------------------------------------


@app.get("/api/admin/roles")
async def list_roles(
    _user: WebUser = Depends(require_role(WebRole.SUPER_ADMIN)),
) -> List[Dict[str, Any]]:
    """Получить список всех пользователей с ролями."""
    roles = web_db.list_user_roles()
    for r in roles:
        for key in ("created_at", "updated_at"):
            if r.get(key) and isinstance(r[key], datetime):
                r[key] = r[key].isoformat()
    return roles


@app.post("/api/admin/roles")
async def set_role(
    telegram_id: int = Query(...),
    role: str = Query(..., pattern=r"^(super_admin|admin|expert|viewer)$"),
    user: WebUser = Depends(require_role(WebRole.SUPER_ADMIN)),
) -> Dict[str, str]:
    """Назначить роль пользователю."""
    web_role = WebRole(role)
    success = web_db.set_user_role(
        telegram_id=telegram_id,
        role=web_role,
        created_by=user.telegram_id,
    )
    if not success:
        raise HTTPException(500, "Ошибка назначения роли")
    return {"message": f"Роль {role} назначена пользователю {telegram_id}"}


@app.delete("/api/admin/roles/{telegram_id}")
async def delete_role(
    telegram_id: int,
    _user: WebUser = Depends(require_role(WebRole.SUPER_ADMIN)),
) -> Dict[str, str]:
    """Удалить роль пользователя."""
    success = web_db.delete_user_role(telegram_id)
    if not success:
        raise HTTPException(404, "Роль не найдена")
    return {"message": f"Роль пользователя {telegram_id} удалена"}


@app.get("/api/admin/local-accounts")
async def list_local_accounts(
    _user: WebUser = Depends(require_role(WebRole.SUPER_ADMIN)),
) -> List[LocalAccountResponse]:
    """Получить список локальных password-аккаунтов."""
    rows = web_db.list_local_accounts()
    result: List[LocalAccountResponse] = []
    for row in rows:
        for key in ("created_at", "updated_at", "locked_until"):
            if row.get(key) and isinstance(row[key], datetime):
                row[key] = row[key].isoformat()
        result.append(LocalAccountResponse(**row, role=WebRole(row.get("role") or WebRole.VIEWER.value)))
    return result


@app.post("/api/admin/local-accounts")
async def create_local_account(
    body: CreateLocalAccountRequest,
    user: WebUser = Depends(require_role(WebRole.SUPER_ADMIN)),
) -> LocalAccountResponse:
    """Создать локальный password-аккаунт (только super_admin)."""
    policy_error = validate_password_policy(body.password)
    if policy_error:
        raise HTTPException(status_code=400, detail=policy_error)

    password_hash = web_db.hash_password(body.password)
    try:
        row = web_db.create_local_account(
            login=body.login,
            password_hash=password_hash,
            role=body.role,
            created_by=user.telegram_id,
            linked_telegram_id=body.linked_telegram_id,
            display_name=body.display_name,
            is_active=body.is_active,
        )
    except Exception as exc:
        if "Duplicate entry" in str(exc):
            raise HTTPException(status_code=409, detail="Логин уже существует") from exc
        raise

    for key in ("created_at", "updated_at", "locked_until"):
        if row.get(key) and isinstance(row[key], datetime):
            row[key] = row[key].isoformat()
    return LocalAccountResponse(**row, role=body.role)


@app.post("/api/admin/local-accounts/{local_account_id}/reset-password")
async def reset_local_account_password(
    local_account_id: int,
    body: ResetLocalAccountPasswordRequest,
    user: WebUser = Depends(require_role(WebRole.SUPER_ADMIN)),
) -> Dict[str, str]:
    """Сбросить пароль локального аккаунта (только super_admin)."""
    policy_error = validate_password_policy(body.new_password)
    if policy_error:
        raise HTTPException(status_code=400, detail=policy_error)

    password_hash = web_db.hash_password(body.new_password)
    ok = web_db.update_local_account_password(
        local_account_id,
        password_hash=password_hash,
        updated_by=user.telegram_id,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Локальный аккаунт не найден")
    return {"message": "Пароль обновлён"}


@app.post("/api/admin/local-accounts/{local_account_id}/activate")
async def activate_local_account(
    local_account_id: int,
    is_active: bool = Query(...),
    user: WebUser = Depends(require_role(WebRole.SUPER_ADMIN)),
) -> Dict[str, str]:
    """Активировать/деактивировать локальный аккаунт."""
    ok = web_db.set_local_account_active(local_account_id, is_active, user.telegram_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Локальный аккаунт не найден")
    return {"message": "Статус аккаунта обновлён"}


# ---------------------------------------------------------------------------
# Главная страница и SPA fallback
# ---------------------------------------------------------------------------


@app.get("/")
async def serve_index() -> FileResponse:
    """Главная страница — React SPA."""
    index_file = _FRONTEND_DIST / "index.html"
    if index_file.is_file():
        return FileResponse(str(index_file))
    raise HTTPException(
        404,
        "React build не найден. Запустите: cd admin_web/frontend && npm run build",
    )


@app.get("/{full_path:path}")
async def serve_spa(full_path: str) -> FileResponse:
    """Catch-all для React SPA роутинга."""
    if full_path.startswith("api/"):
        raise HTTPException(404, "API endpoint не найден")
    if full_path.startswith("prompt-tester"):
        raise HTTPException(404, "Prompt Tester endpoint не найден")

    file_path = _FRONTEND_DIST / full_path
    if file_path.is_file():
        return FileResponse(str(file_path))

    index_file = _FRONTEND_DIST / "index.html"
    if index_file.is_file():
        return FileResponse(str(index_file))
    raise HTTPException(404, "React build не найден")


# ---------------------------------------------------------------------------
# Точка входа
# ---------------------------------------------------------------------------


def main() -> None:
    """Запустить сервер."""
    import uvicorn

    log_format = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    logging.basicConfig(level=logging.INFO, format=log_format, datefmt=date_format)

    port = int(os.getenv("ADMIN_WEB_PORT", "8090"))
    host = os.getenv("ADMIN_WEB_HOST", "127.0.0.1")

    logger.info("Запуск SBS Archie Admin Web: http://%s:%d", host, port)
    if is_dev_mode():
        logger.warning("⚠ Dev-режим включён: Telegram-верификация отключена")

    uvicorn.run(
        "admin_web.core.app:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
        access_log=True,
        log_config={
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": log_format,
                    "datefmt": date_format,
                },
                "access": {
                    "()": "uvicorn.logging.AccessFormatter",
                    "fmt": '%(asctime)s %(levelname)s %(name)s: %(client_addr)s - "%(request_line)s" %(status_code)s',
                    "datefmt": date_format,
                },
            },
            "handlers": {
                "default": {
                    "formatter": "default",
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stderr",
                },
                "access": {
                    "formatter": "access",
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stdout",
                },
            },
            "loggers": {
                "uvicorn": {"handlers": ["default"], "level": "INFO"},
                "uvicorn.error": {"level": "INFO"},
                "uvicorn.access": {
                    "handlers": ["access"],
                    "level": "INFO",
                    "propagate": False,
                },
            },
        },
    )


if __name__ == "__main__":
    main()
