"""Абстрактный базовый класс модуля веб-платформы.

Каждый модуль веб-платформы наследуется от WebModule и предоставляет:
- Метаданные (ключ, название, иконка, порядок)
- FastAPI-роутер с API-эндпоинтами
- Требуемые права доступа

Модули регистрируются в app.py и монтируются автоматически.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from fastapi import APIRouter


class WebModule(ABC):
    """Базовый класс модуля веб-платформы."""

    @property
    @abstractmethod
    def key(self) -> str:
        """Уникальный ключ модуля (используется в RBAC и URL)."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Человекочитаемое название модуля."""
        ...

    @property
    def icon(self) -> str:
        """Иконка модуля (emoji или CSS-класс)."""
        return "📦"

    @property
    def order(self) -> int:
        """Порядок отображения в навигации (меньше = раньше)."""
        return 100

    @property
    def description(self) -> str:
        """Краткое описание модуля."""
        return ""

    @abstractmethod
    def get_router(self) -> APIRouter:
        """Создать и вернуть FastAPI-роутер модуля."""
        ...

    @property
    def api_prefix(self) -> str:
        """Префикс URL для API-эндпоинтов."""
        return f"/api/{self.key.replace('_', '-')}"

    def get_frontend_routes(self) -> list:
        """Маршруты фронтенда модуля (для навигации)."""
        return []

    def on_startup(self) -> None:
        """Хук инициализации при запуске приложения (опционально)."""
        pass

    def on_shutdown(self) -> None:
        """Хук завершения при остановке приложения (опционально)."""
        pass
