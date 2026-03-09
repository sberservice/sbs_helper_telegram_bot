"""WebModule-класс модуля управления процессами.

Регистрируется в admin_web/core/app.py и предоставляет
API для управления всеми скриптами и демонами SBS Archie.
"""

from __future__ import annotations

import logging

from admin_web.modules.base import WebModule
from fastapi import APIRouter

logger = logging.getLogger(__name__)


class ProcessManagerModule(WebModule):
    """Модуль управления процессами — запуск, остановка, мониторинг скриптов и демонов."""

    @property
    def key(self) -> str:
        return "process_manager"

    @property
    def name(self) -> str:
        return "Менеджер процессов"

    @property
    def icon(self) -> str:
        return "⚙️"

    @property
    def order(self) -> int:
        return 3

    @property
    def description(self) -> str:
        return "Управление скриптами и демонами: запуск, остановка, мониторинг, история"

    def get_router(self) -> APIRouter:
        """Собрать роутер менеджера процессов."""
        from admin_web.modules.process_manager.router import build_process_manager_router
        return build_process_manager_router()

    def on_startup(self) -> None:
        """Инициализация супервизора при запуске приложения."""
        from admin_web.modules.process_manager.supervisor import get_supervisor
        supervisor = get_supervisor()
        supervisor.startup()
        logger.info("ProcessManagerModule startup: супервизор инициализирован")

    def on_shutdown(self) -> None:
        """Остановка супервизора при завершении приложения."""
        from admin_web.modules.process_manager.supervisor import get_supervisor
        supervisor = get_supervisor()
        supervisor.shutdown()
        logger.info("ProcessManagerModule shutdown: супервизор остановлен")
