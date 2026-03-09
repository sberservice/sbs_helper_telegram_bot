"""API для управления конфигурациями групп GK и The Helper.

Предоставляет CRUD-эндпоинты для:
- config/gk_groups.json (Group Knowledge)
- config/helper_groups.json (The Helper)
- Получение списка собранных групп из БД
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from admin_web.core.models import WebUser
from admin_web.core.rbac import require_permission

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Пути к конфигурациям
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
GK_GROUPS_CONFIG_PATH = PROJECT_ROOT / "config" / "gk_groups.json"
HELPER_GROUPS_CONFIG_PATH = PROJECT_ROOT / "config" / "helper_groups.json"


# ---------------------------------------------------------------------------
# Модели
# ---------------------------------------------------------------------------


class GroupEntry(BaseModel):
    """Одна группа в конфигурации."""
    id: int = Field(..., description="Telegram ID группы")
    title: str = Field("", description="Название группы")


class TestTargetGroup(BaseModel):
    """Группа назначения для redirect test mode."""
    id: int = Field(..., description="Telegram ID группы")
    title: str = Field("", description="Название группы")
    participants: Optional[int] = Field(None, description="Число участников")


class GKGroupsConfig(BaseModel):
    """Полная конфигурация GK-групп."""
    groups: List[GroupEntry] = Field(default_factory=list)
    test_target_group: Optional[TestTargetGroup] = None


class HelperGroupsConfig(BaseModel):
    """Полная конфигурация Helper-групп."""
    groups: List[GroupEntry] = Field(default_factory=list)


class GroupAddRequest(BaseModel):
    """Запрос на добавление группы."""
    id: int = Field(..., description="Telegram ID группы")
    title: str = Field("", description="Название группы")


class CollectedGroupInfo(BaseModel):
    """Информация о группе из БД (собранные сообщения)."""
    group_id: int
    group_title: Optional[str] = None
    message_count: int = 0
    first_message: Optional[str] = None
    last_message: Optional[str] = None


# ---------------------------------------------------------------------------
# Утилиты для работы с JSON-конфигами
# ---------------------------------------------------------------------------


def _load_json_config(path: Path) -> Dict[str, Any]:
    """Загрузить JSON-конфиг из файла."""
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
        logger.error("Некорректный формат %s: ожидался dict", path)
        return {}
    except (json.JSONDecodeError, IOError) as exc:
        logger.error("Ошибка чтения %s: %s", path, exc)
        return {}


def _save_json_config(path: Path, data: Dict[str, Any]) -> None:
    """Сохранить JSON-конфиг в файл."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    logger.info("Конфигурация сохранена: %s", path)


# ---------------------------------------------------------------------------
# Роутер
# ---------------------------------------------------------------------------


def build_groups_router() -> APIRouter:
    """Создать роутер для управления группами."""
    router = APIRouter(prefix="/groups", tags=["process-manager-groups"])

    # ===== GK Groups =====

    @router.get("/gk")
    async def get_gk_groups(
        user: WebUser = Depends(require_permission("process_manager")),
    ) -> Dict[str, Any]:
        """Получить конфигурацию GK-групп."""
        data = _load_json_config(GK_GROUPS_CONFIG_PATH)
        config = GKGroupsConfig(
            groups=[GroupEntry(**g) for g in data.get("groups", [])],
            test_target_group=(
                TestTargetGroup(**data["test_target_group"])
                if data.get("test_target_group")
                else None
            ),
        )
        return config.model_dump()

    @router.put("/gk")
    async def update_gk_groups(
        config: GKGroupsConfig,
        user: WebUser = Depends(require_permission("process_manager", "edit")),
    ) -> Dict[str, Any]:
        """Полностью обновить конфигурацию GK-групп."""
        data: Dict[str, Any] = {
            "groups": [g.model_dump() for g in config.groups],
        }
        if config.test_target_group:
            data["test_target_group"] = config.test_target_group.model_dump(
                exclude_none=True,
            )
        _save_json_config(GK_GROUPS_CONFIG_PATH, data)
        logger.info(
            "GK groups обновлены через admin panel: %d групп, user=%d",
            len(config.groups), user.telegram_id,
        )
        return data

    @router.post("/gk/add")
    async def add_gk_group(
        group: GroupAddRequest,
        user: WebUser = Depends(require_permission("process_manager", "edit")),
    ) -> Dict[str, Any]:
        """Добавить группу в GK-конфигурацию."""
        data = _load_json_config(GK_GROUPS_CONFIG_PATH)
        groups = data.get("groups", [])

        # Проверить дубликат
        if any(int(g.get("id", 0)) == group.id for g in groups):
            raise HTTPException(
                status_code=409,
                detail=f"Группа {group.id} уже есть в конфигурации",
            )

        groups.append({"id": group.id, "title": group.title})
        data["groups"] = groups
        _save_json_config(GK_GROUPS_CONFIG_PATH, data)
        logger.info(
            "GK group добавлена: id=%d title=%s user=%d",
            group.id, group.title, user.telegram_id,
        )
        return {"groups": groups}

    @router.delete("/gk/{group_id}")
    async def remove_gk_group(
        group_id: int,
        user: WebUser = Depends(require_permission("process_manager", "edit")),
    ) -> Dict[str, Any]:
        """Удалить группу из GK-конфигурации."""
        data = _load_json_config(GK_GROUPS_CONFIG_PATH)
        groups = data.get("groups", [])
        original_len = len(groups)
        groups = [g for g in groups if int(g.get("id", 0)) != group_id]

        if len(groups) == original_len:
            raise HTTPException(
                status_code=404,
                detail=f"Группа {group_id} не найдена в конфигурации",
            )

        data["groups"] = groups
        _save_json_config(GK_GROUPS_CONFIG_PATH, data)
        logger.info(
            "GK group удалена: id=%d user=%d",
            group_id, user.telegram_id,
        )
        return {"groups": groups}

    @router.put("/gk/test-target")
    async def set_gk_test_target(
        group: TestTargetGroup,
        user: WebUser = Depends(require_permission("process_manager", "edit")),
    ) -> Dict[str, Any]:
        """Установить test target group для GK redirect test mode."""
        data = _load_json_config(GK_GROUPS_CONFIG_PATH)

        # Проверить, не боевая ли это группа
        configured_ids = {int(g["id"]) for g in data.get("groups", [])}
        if group.id in configured_ids:
            raise HTTPException(
                status_code=400,
                detail="Нельзя использовать боевую группу как test target",
            )

        data["test_target_group"] = group.model_dump(exclude_none=True)
        _save_json_config(GK_GROUPS_CONFIG_PATH, data)
        logger.info(
            "GK test target group установлена: id=%d title=%s user=%d",
            group.id, group.title, user.telegram_id,
        )
        return {"test_target_group": data["test_target_group"]}

    @router.delete("/gk/test-target")
    async def clear_gk_test_target(
        user: WebUser = Depends(require_permission("process_manager", "edit")),
    ) -> Dict[str, Any]:
        """Очистить test target group для GK."""
        data = _load_json_config(GK_GROUPS_CONFIG_PATH)
        data.pop("test_target_group", None)
        _save_json_config(GK_GROUPS_CONFIG_PATH, data)
        logger.info("GK test target group очищена: user=%d", user.telegram_id)
        return {"test_target_group": None}

    # ===== Helper Groups =====

    @router.get("/helper")
    async def get_helper_groups(
        user: WebUser = Depends(require_permission("process_manager")),
    ) -> Dict[str, Any]:
        """Получить конфигурацию Helper-групп."""
        data = _load_json_config(HELPER_GROUPS_CONFIG_PATH)
        config = HelperGroupsConfig(
            groups=[GroupEntry(**g) for g in data.get("groups", [])],
        )
        return config.model_dump()

    @router.put("/helper")
    async def update_helper_groups(
        config: HelperGroupsConfig,
        user: WebUser = Depends(require_permission("process_manager", "edit")),
    ) -> Dict[str, Any]:
        """Полностью обновить конфигурацию Helper-групп."""
        data: Dict[str, Any] = {
            "groups": [g.model_dump() for g in config.groups],
        }
        _save_json_config(HELPER_GROUPS_CONFIG_PATH, data)
        logger.info(
            "Helper groups обновлены через admin panel: %d групп, user=%d",
            len(config.groups), user.telegram_id,
        )
        return data

    @router.post("/helper/add")
    async def add_helper_group(
        group: GroupAddRequest,
        user: WebUser = Depends(require_permission("process_manager", "edit")),
    ) -> Dict[str, Any]:
        """Добавить группу в Helper-конфигурацию."""
        data = _load_json_config(HELPER_GROUPS_CONFIG_PATH)
        groups = data.get("groups", [])

        if any(int(g.get("id", 0)) == group.id for g in groups):
            raise HTTPException(
                status_code=409,
                detail=f"Группа {group.id} уже есть в конфигурации",
            )

        groups.append({"id": group.id, "title": group.title})
        data["groups"] = groups
        _save_json_config(HELPER_GROUPS_CONFIG_PATH, data)
        logger.info(
            "Helper group добавлена: id=%d title=%s user=%d",
            group.id, group.title, user.telegram_id,
        )
        return {"groups": groups}

    @router.delete("/helper/{group_id}")
    async def remove_helper_group(
        group_id: int,
        user: WebUser = Depends(require_permission("process_manager", "edit")),
    ) -> Dict[str, Any]:
        """Удалить группу из Helper-конфигурации."""
        data = _load_json_config(HELPER_GROUPS_CONFIG_PATH)
        groups = data.get("groups", [])
        original_len = len(groups)
        groups = [g for g in groups if int(g.get("id", 0)) != group_id]

        if len(groups) == original_len:
            raise HTTPException(
                status_code=404,
                detail=f"Группа {group_id} не найдена в конфигурации",
            )

        data["groups"] = groups
        _save_json_config(HELPER_GROUPS_CONFIG_PATH, data)
        logger.info(
            "Helper group удалена: id=%d user=%d",
            group_id, user.telegram_id,
        )
        return {"groups": groups}

    # ===== Collected Groups (из БД) =====

    @router.get("/collected")
    async def get_collected_groups(
        user: WebUser = Depends(require_permission("process_manager")),
    ) -> List[Dict[str, Any]]:
        """Получить список групп из БД (из таблицы gk_messages)."""
        try:
            from src.group_knowledge import database as gk_db
            rows = gk_db.get_collected_groups()
            result = []
            for row in rows:
                result.append({
                    "group_id": row.get("group_id"),
                    "group_title": row.get("group_title"),
                    "message_count": row.get("message_count", 0),
                    "first_message": (
                        row["first_message"].isoformat()
                        if row.get("first_message") else None
                    ),
                    "last_message": (
                        row["last_message"].isoformat()
                        if row.get("last_message") else None
                    ),
                })
            return result
        except Exception as exc:
            logger.error(
                "Ошибка получения собранных групп: %s", exc, exc_info=True,
            )
            raise HTTPException(
                status_code=500,
                detail=f"Ошибка получения данных: {exc}",
            ) from exc

    return router
