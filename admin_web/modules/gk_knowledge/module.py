"""WebModule-класс модуля Group Knowledge.

Регистрируется в admin_web/core/app.py и предоставляет
единый FastAPI-роутер со всеми подмодулями GK.
"""

from __future__ import annotations

from admin_web.modules.base import WebModule
from fastapi import APIRouter


class GKKnowledgeModule(WebModule):
    """Модуль Group Knowledge — управление и аналитика GK-подсистемы."""

    @property
    def key(self) -> str:
        return "gk_knowledge"

    @property
    def name(self) -> str:
        return "Group Knowledge"

    @property
    def icon(self) -> str:
        return "🧠"

    @property
    def order(self) -> int:
        return 5

    @property
    def description(self) -> str:
        return "Аналитика, валидация и тестирование Q&A из Telegram-групп"

    def get_router(self) -> APIRouter:
        """Собрать главный роутер из подмодулей."""
        from admin_web.modules.gk_knowledge.router import build_gk_router
        return build_gk_router()
