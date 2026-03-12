"""API-роутер модуля управления процессами.

Эндпоинты для просмотра статусов, запуска/остановки процессов,
получения вывода, истории запусков, WebSocket для логов.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect

from admin_web.core.models import WebUser
from admin_web.core.rbac import require_permission
from admin_web.modules.process_manager import db as pm_db
from admin_web.modules.process_manager.models import (
    FlagDefinition,
    PresetDefinition,
    ProcessesByCategoryResponse,
    ProcessHistoryResponse,
    ProcessOutputResponse,
    ProcessRegistryResponse,
    ProcessRunRecord,
    ProcessStartRequest,
    ProcessStatus,
    ProcessStatusResponse,
)
from admin_web.modules.process_manager.registry import (
    CATEGORY_ORDER,
    get_process_definition,
    get_process_registry,
    get_processes_by_category,
)
from admin_web.modules.process_manager.supervisor import get_supervisor

logger = logging.getLogger(__name__)


def _build_status_response(
    process_key: str,
) -> ProcessStatusResponse:
    """Собрать ответ о статусе процесса из супервизора и реестра."""
    definition = get_process_definition(process_key)
    if not definition:
        raise HTTPException(status_code=404, detail=f"Процесс не найден: {process_key}")

    supervisor = get_supervisor()
    managed = supervisor.get_status(process_key)

    return ProcessStatusResponse(
        key=definition.key,
        name=definition.name,
        icon=definition.icon,
        category=definition.category,
        process_type=definition.process_type,
        status=managed.status,
        pid=managed.pid,
        uptime_seconds=managed.uptime_seconds,
        current_flags=managed.flags if managed.flags else None,
        current_preset=managed.preset_name,
        started_at=managed.started_at.isoformat() if managed.started_at else None,
        started_by=managed.started_by,
        exit_code=managed.exit_code,
        auto_restart=definition.auto_restart,
        singleton=definition.singleton,
        description=definition.description,
    )


def build_process_manager_router() -> APIRouter:
    """Создать и вернуть роутер менеджера процессов."""
    router = APIRouter(tags=["process-manager"])

    # --- Список процессов ---

    @router.get("/processes")
    async def list_processes(
        user: WebUser = Depends(require_permission("process_manager")),
    ) -> Dict[str, Any]:
        """Все процессы, сгруппированные по категориям вместе со статусами."""
        categories = get_processes_by_category()
        result: Dict[str, List[Dict[str, Any]]] = {}

        for cat_name in CATEGORY_ORDER:
            if cat_name not in categories:
                continue
            items = []
            for proc_def in categories[cat_name]:
                try:
                    status_resp = _build_status_response(proc_def.key)
                    items.append(status_resp.model_dump())
                except Exception as exc:
                    logger.warning(
                        "Ошибка получения статуса %s: %s", proc_def.key, exc,
                    )
            result[cat_name] = items

        return {"categories": result}

    # --- Статус одного процесса ---

    @router.get("/processes/{process_key}")
    async def get_process_status(
        process_key: str,
        user: WebUser = Depends(require_permission("process_manager")),
    ) -> Dict[str, Any]:
        """Статус одного процесса."""
        return _build_status_response(process_key).model_dump()

    # --- Реестр процесса (флаги, пресеты) ---

    @router.get("/processes/{process_key}/registry")
    async def get_process_registry_info(
        process_key: str,
        user: WebUser = Depends(require_permission("process_manager")),
    ) -> Dict[str, Any]:
        """Описание процесса: доступные флаги и пресеты."""
        definition = get_process_definition(process_key)
        if not definition:
            raise HTTPException(status_code=404, detail=f"Процесс не найден: {process_key}")

        return ProcessRegistryResponse(
            key=definition.key,
            name=definition.name,
            icon=definition.icon,
            category=definition.category,
            process_type=definition.process_type,
            description=definition.description,
            singleton=definition.singleton,
            auto_restart=definition.auto_restart,
            flags=[FlagDefinition(**f.model_dump()) for f in definition.flags],
            presets=[PresetDefinition(**p.model_dump()) for p in definition.presets],
        ).model_dump()

    # --- Запуск ---

    @router.post("/processes/{process_key}/start")
    async def start_process(
        process_key: str,
        body: ProcessStartRequest,
        user: WebUser = Depends(require_permission("process_manager", "edit")),
    ) -> Dict[str, Any]:
        """Запустить процесс с указанным пресетом или набором флагов."""
        definition = get_process_definition(process_key)
        if not definition:
            raise HTTPException(status_code=404, detail=f"Процесс не найден: {process_key}")

        # Определить флаги
        flags: List[str] = []
        preset_name: Optional[str] = None

        if body.preset:
            preset = next(
                (p for p in definition.presets if p.name == body.preset), None,
            )
            if not preset:
                raise HTTPException(
                    status_code=400,
                    detail=f"Пресет не найден: {body.preset}",
                )
            flags = list(preset.flags)
            preset_name = preset.name

            # Добавить данные из формы как CLI-флаги
            if body.form_data and preset.requires_form:
                for flag_name, flag_value in body.form_data.items():
                    if flag_value is None:
                        continue
                    cli_flag = f"--{flag_name}" if not flag_name.startswith("--") else flag_name
                    if isinstance(flag_value, bool):
                        if flag_value:
                            flags.append(cli_flag)
                    else:
                        flags.append(cli_flag)
                        flags.append(str(flag_value))

        elif body.flags is not None:
            flags = list(body.flags)
        # Если ни preset, ни flags — запуск без флагов

        try:
            supervisor = get_supervisor()
            managed = supervisor.start_process(
                process_key,
                flags=flags,
                preset_name=preset_name,
                started_by=user.telegram_id,
                persist=body.persist,
            )
            logger.info(
                "Процесс запущен из admin panel: key=%s pid=%s flags=%s user=%d",
                process_key, managed.pid, flags, user.telegram_id,
            )
            return _build_status_response(process_key).model_dump()
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        except Exception as exc:
            logger.error(
                "Ошибка запуска процесса %s: %s", process_key, exc, exc_info=True,
            )
            raise HTTPException(status_code=500, detail=f"Ошибка запуска: {exc}")

    # --- Остановка ---

    @router.post("/processes/{process_key}/stop")
    async def stop_process(
        process_key: str,
        user: WebUser = Depends(require_permission("process_manager", "edit")),
    ) -> Dict[str, Any]:
        """Остановить процесс."""
        try:
            supervisor = get_supervisor()
            supervisor.stop_process(
                process_key,
                reason="manual",
                stopped_by=user.telegram_id,
            )
            logger.info(
                "Процесс остановлен из admin panel: key=%s user=%d",
                process_key, user.telegram_id,
            )
            return _build_status_response(process_key).model_dump()
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        except Exception as exc:
            logger.error(
                "Ошибка остановки процесса %s: %s", process_key, exc, exc_info=True,
            )
            raise HTTPException(status_code=500, detail=f"Ошибка остановки: {exc}")

    # --- Рестарт ---

    @router.post("/processes/{process_key}/restart")
    async def restart_process(
        process_key: str,
        body: ProcessStartRequest,
        user: WebUser = Depends(require_permission("process_manager", "edit")),
    ) -> Dict[str, Any]:
        """Перезапустить процесс (с новыми или текущими флагами)."""
        definition = get_process_definition(process_key)
        if not definition:
            raise HTTPException(status_code=404, detail=f"Процесс не найден: {process_key}")

        flags: Optional[List[str]] = None
        preset_name: Optional[str] = None

        if body.preset:
            preset = next(
                (p for p in definition.presets if p.name == body.preset), None,
            )
            if not preset:
                raise HTTPException(
                    status_code=400, detail=f"Пресет не найден: {body.preset}",
                )
            flags = list(preset.flags)
            preset_name = preset.name
        elif body.flags is not None:
            flags = list(body.flags)

        try:
            supervisor = get_supervisor()
            supervisor.restart_process(
                process_key,
                flags=flags,
                preset_name=preset_name,
                restarted_by=user.telegram_id,
            )
            logger.info(
                "Процесс перезапущен из admin panel: key=%s user=%d",
                process_key, user.telegram_id,
            )
            return _build_status_response(process_key).model_dump()
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        except Exception as exc:
            logger.error(
                "Ошибка рестарта процесса %s: %s", process_key, exc, exc_info=True,
            )
            raise HTTPException(status_code=500, detail=f"Ошибка рестарта: {exc}")

    # --- История запусков ---

    @router.get("/processes/{process_key}/history")
    async def get_process_history(
        process_key: str,
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        status: Optional[str] = Query(None),
        user: WebUser = Depends(require_permission("process_manager")),
    ) -> Dict[str, Any]:
        """История запусков конкретного процесса."""
        definition = get_process_definition(process_key)
        if not definition:
            raise HTTPException(status_code=404, detail=f"Процесс не найден: {process_key}")

        runs, total = pm_db.get_run_history(
            process_key, page=page, page_size=page_size, status_filter=status,
        )

        formatted_runs = []
        for run in runs:
            flags = None
            if run.get("flags_json"):
                try:
                    flags = json.loads(run["flags_json"])
                except (json.JSONDecodeError, TypeError):
                    flags = None

            formatted_runs.append(ProcessRunRecord(
                id=run["id"],
                process_key=run["process_key"],
                pid=run.get("pid"),
                flags=flags,
                preset_name=run.get("preset_name"),
                started_by=run.get("started_by"),
                started_at=run.get("started_at"),
                stopped_at=run.get("stopped_at"),
                exit_code=run.get("exit_code"),
                status=run.get("status", "stopped"),
                stop_reason=run.get("stop_reason"),
            ).model_dump())

        return ProcessHistoryResponse(
            runs=formatted_runs,
            total=total,
            page=page,
            page_size=page_size,
        ).model_dump()

    # --- Общая история (все процессы) ---

    @router.get("/history")
    async def get_all_history(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        process_key: Optional[str] = Query(None),
        status: Optional[str] = Query(None),
        user: WebUser = Depends(require_permission("process_manager")),
    ) -> Dict[str, Any]:
        """История запусков всех процессов (с фильтрами)."""
        runs, total = pm_db.get_run_history(
            process_key, page=page, page_size=page_size, status_filter=status,
        )

        formatted_runs = []
        for run in runs:
            flags = None
            if run.get("flags_json"):
                try:
                    flags = json.loads(run["flags_json"])
                except (json.JSONDecodeError, TypeError):
                    flags = None

            formatted_runs.append(ProcessRunRecord(
                id=run["id"],
                process_key=run["process_key"],
                pid=run.get("pid"),
                flags=flags,
                preset_name=run.get("preset_name"),
                started_by=run.get("started_by"),
                started_at=run.get("started_at"),
                stopped_at=run.get("stopped_at"),
                exit_code=run.get("exit_code"),
                status=run.get("status", "stopped"),
                stop_reason=run.get("stop_reason"),
            ).model_dump())

        return ProcessHistoryResponse(
            runs=formatted_runs,
            total=total,
            page=page,
            page_size=page_size,
        ).model_dump()

    # --- Вывод процесса ---

    @router.get("/processes/{process_key}/output")
    async def get_process_output(
        process_key: str,
        last_n: int = Query(200, ge=1, le=1000),
        user: WebUser = Depends(require_permission("process_manager")),
    ) -> Dict[str, Any]:
        """Последние N строк вывода процесса из кольцевого буфера."""
        definition = get_process_definition(process_key)
        if not definition:
            raise HTTPException(status_code=404, detail=f"Процесс не найден: {process_key}")

        supervisor = get_supervisor()
        lines = supervisor.get_output(process_key, last_n=last_n)

        return ProcessOutputResponse(
            lines=lines,
            total_lines=len(lines),
        ).model_dump()

    # --- WebSocket: реалтайм логи ---

    @router.websocket("/processes/{process_key}/logs")
    async def websocket_logs(
        websocket: WebSocket,
        process_key: str,
    ) -> None:
        """WebSocket-эндпоинт для стриминга логов процесса в реальном времени."""
        definition = get_process_definition(process_key)
        if not definition:
            await websocket.close(code=4004, reason="Process not found")
            return

        await websocket.accept()

        supervisor = get_supervisor()
        managed = supervisor.get_status(process_key)

        # Отправить буферизованные строки
        existing_lines = supervisor.get_output(process_key, last_n=200)
        for entry in existing_lines:
            try:
                await websocket.send_json(entry)
            except Exception:
                return

        # Подписаться на новые строки
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        managed.subscribe(queue)

        try:
            while True:
                try:
                    entry = await asyncio.wait_for(queue.get(), timeout=30)
                    await websocket.send_json(entry)
                except asyncio.TimeoutError:
                    # Heartbeat
                    try:
                        await websocket.send_json({"type": "heartbeat"})
                    except Exception:
                        break
                except WebSocketDisconnect:
                    break
        except Exception as exc:
            logger.debug("WebSocket %s отключён: %s", process_key, exc)
        finally:
            managed.unsubscribe(queue)

    # --- Подключить роутер управления группами ---
    from admin_web.modules.process_manager.groups_api import build_groups_router
    router.include_router(build_groups_router())

    # --- Конфигурация запуска (launch_config.json) ---

    @router.get("/launch-config")
    async def get_launch_config(
        user: WebUser = Depends(require_permission("process_manager")),
    ) -> Dict[str, Any]:
        """Получить текущую конфигурацию автозапуска из deploy/launch_config.json.

        Результат обогащается данными из реестра (имя, иконка, категория, тип)
        для удобного отображения в UI.
        """
        supervisor = get_supervisor()
        config = supervisor.read_launch_config()
        processes_raw = config.get("processes", {})
        registry = get_process_registry()

        enriched: Dict[str, Any] = {}
        # Включить все daemon-процессы из реестра (не только те, что в конфиге).
        for key, definition in registry.items():
            if definition.process_type.value != "daemon":
                continue
            entry = processes_raw.get(key, {})
            enriched[key] = {
                "enabled": entry.get("enabled", False) if isinstance(entry, dict) else False,
                "flags": entry.get("flags", []) if isinstance(entry, dict) else [],
                "preset": entry.get("preset") if isinstance(entry, dict) else None,
                "name": definition.name,
                "icon": definition.icon,
                "category": definition.category,
                "description": definition.description,
                "available_presets": [
                    {"name": p.name, "description": p.description, "flags": p.flags, "icon": p.icon}
                    for p in definition.presets
                    if not p.hidden
                ],
                "available_flags": [
                    {
                        "name": f.name,
                        "flag_type": f.flag_type.value,
                        "description": f.description,
                        "default": f.default,
                    }
                    for f in definition.flags
                ],
            }

        return {
            "description": config.get("description", ""),
            "processes": enriched,
        }

    @router.put("/launch-config")
    async def update_launch_config(
        body: Dict[str, Any],
        user: WebUser = Depends(require_permission("process_manager", "edit")),
    ) -> Dict[str, Any]:
        """Сохранить конфигурацию автозапуска в deploy/launch_config.json."""
        supervisor = get_supervisor()
        try:
            supervisor.write_launch_config(body)
            logger.info(
                "launch_config.json обновлён: user=%d processes=%s",
                user.telegram_id,
                list(body.get("processes", {}).keys()),
            )
            return {"success": True, "message": "Конфигурация сохранена"}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except OSError as exc:
            logger.error("Ошибка записи launch_config.json: %s", exc, exc_info=True)
            raise HTTPException(status_code=500, detail=f"Ошибка записи: {exc}")

    @router.post("/launch-config/apply")
    async def apply_launch_config(
        user: WebUser = Depends(require_permission("process_manager", "edit")),
    ) -> Dict[str, Any]:
        """Применить конфигурацию запуска немедленно: запустить/остановить процессы."""
        supervisor = get_supervisor()
        actions = supervisor.apply_launch_config()
        logger.info(
            "launch_config применён: user=%d actions=%s",
            user.telegram_id, actions,
        )
        return {"success": True, "actions": actions}

    # --- Завершение работы (для deploy/stop.bat) ---

    @router.post("/shutdown")
    async def shutdown_all(
        user: WebUser = Depends(require_permission("process_manager", "edit")),
    ) -> Dict[str, Any]:
        """Остановить все управляемые процессы и завершить admin_web.

        Используется скриптом deploy/stop.bat для корректного завершения.
        """
        supervisor = get_supervisor()
        results = supervisor.stop_all_processes()
        logger.info(
            "shutdown: все процессы остановлены: user=%d results=%s",
            user.telegram_id, results,
        )

        # Запланировать остановку сервера через 2 секунды.
        async def _delayed_shutdown() -> None:
            await asyncio.sleep(2)
            logger.info("shutdown: завершение admin_web")
            os.kill(os.getpid(), signal.SIGTERM)

        asyncio.create_task(_delayed_shutdown())

        return {"success": True, "stopped": results}

    return router
