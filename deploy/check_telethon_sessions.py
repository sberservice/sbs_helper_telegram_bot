#!/usr/bin/env python3
"""Проверка Telethon-сессий для Windows-deploy.

Скрипт анализирует launch_config.json, определяет какие процессы с Telethon
включены для автозапуска, проверяет наличие соответствующих *.session файлов
и печатает оператору пошаговые инструкции по созданию недостающих сессий.

Коды возврата:
- 0: все необходимые сессии присутствуют
- 2: отсутствуют необходимые сессии
- 3: ошибка чтения конфигурации
"""

from __future__ import annotations

import asyncio
import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.common.constants.sync import TELETHON_API_HASH, TELETHON_API_ID
from src.group_knowledge.telethon_session import (
    build_telegram_client,
    disconnect_client_quietly,
)


@dataclass(frozen=True)
class SessionRequirement:
    """Описание требования к Telethon-сессии."""

    process_key: str
    session_basename: str
    setup_command: str
    description: str


REQUIREMENTS: Dict[str, SessionRequirement] = {
    "gk_collector": SessionRequirement(
        process_key="gk_collector",
        session_basename="gk_collector_session",
        setup_command="python scripts/gk_collector.py --manage-groups",
        description="Group Knowledge collector",
    ),
    "the_helper": SessionRequirement(
        process_key="the_helper",
        session_basename="helper_session",
        setup_command="python scripts/the_helper.py --manage-groups",
        description="The Helper listener",
    ),
}

OPTIONAL_SESSIONS: List[SessionRequirement] = [
    SessionRequirement(
        process_key="sync_chat_members",
        session_basename="chat_sync_session",
        setup_command="python scripts/sync_chat_members.py",
        description="Chat members sync (опционально)",
    ),
]


def _session_file_exists(project_dir: Path, session_basename: str) -> bool:
    """Проверить наличие файла Telethon-сессии в корне проекта."""
    return (project_dir / f"{session_basename}.session").exists()


async def _is_session_authorized(
    project_dir: Path,
    session_basename: str,
    api_id: int,
    api_hash: str,
    logger: logging.Logger,
) -> bool:
    """Проверить, что Telethon-сессия действительно авторизована."""
    session_path = str(project_dir / session_basename)
    client = build_telegram_client(session_path, api_id, api_hash, logger)
    try:
        await client.connect()
        return bool(await client.is_user_authorized())
    except Exception:
        return False
    finally:
        await disconnect_client_quietly(client)


def _load_launch_config(project_dir: Path) -> dict:
    """Загрузить deploy/launch_config.json."""
    config_path = project_dir / "deploy" / "launch_config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"Файл не найден: {config_path}")

    with config_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError("launch_config.json должен быть JSON-объектом")

    return data


def _enabled_processes(launch_config: dict) -> Dict[str, bool]:
    """Вернуть map process_key -> enabled."""
    processes = launch_config.get("processes", {})
    if not isinstance(processes, dict):
        return {}

    result: Dict[str, bool] = {}
    for process_key, cfg in processes.items():
        if not isinstance(cfg, dict):
            continue
        result[process_key] = bool(cfg.get("enabled", False))
    return result


def main() -> int:
    """Точка входа CLI."""
    parser = argparse.ArgumentParser(description="Проверка Telethon-сессий для deploy")
    parser.add_argument(
        "--project-dir",
        default=str(Path(__file__).resolve().parent.parent),
        help="Путь к корню проекта",
    )
    args = parser.parse_args()

    project_dir = Path(args.project_dir).resolve()
    os.chdir(project_dir)

    load_dotenv(project_dir / "config" / ".env")
    load_dotenv(project_dir / ".env")

    logger = logging.getLogger("deploy.check_telethon_sessions")

    try:
        launch_config = _load_launch_config(project_dir)
    except Exception as exc:
        print(f"[SESSIONS] ОШИБКА: не удалось прочитать launch_config.json: {exc}")
        return 3

    enabled_map = _enabled_processes(launch_config)

    has_telethon_creds = bool(TELETHON_API_ID) and bool(TELETHON_API_HASH)
    if not has_telethon_creds:
        print(
            "[SESSIONS] ПРЕДУПРЕЖДЕНИЕ: TELETHON_API_ID/TELETHON_API_HASH не заданы. "
            "Будет проверено только наличие файлов session без валидации авторизации."
        )

    required_missing: List[SessionRequirement] = []
    required_present: List[SessionRequirement] = []
    required_not_authorized: List[SessionRequirement] = []

    for key, req in REQUIREMENTS.items():
        if not enabled_map.get(key, False):
            continue

        exists = _session_file_exists(project_dir, req.session_basename)
        if not exists:
            required_missing.append(req)
            continue

        if has_telethon_creds:
            is_authorized = asyncio.run(
                _is_session_authorized(
                    project_dir=project_dir,
                    session_basename=req.session_basename,
                    api_id=TELETHON_API_ID,
                    api_hash=TELETHON_API_HASH,
                    logger=logger,
                )
            )
            if not is_authorized:
                required_not_authorized.append(req)
                continue

        if exists:
            required_present.append(req)

    optional_missing: List[SessionRequirement] = []
    for req in OPTIONAL_SESSIONS:
        if not _session_file_exists(project_dir, req.session_basename):
            optional_missing.append(req)

    print("[SESSIONS] Проверка Telethon-сессий")
    if required_present:
        for req in required_present:
            print(f"[SESSIONS] OK: {req.session_basename}.session ({req.description})")

    if required_not_authorized:
        print("[SESSIONS] ВНИМАНИЕ: найдены session-файлы без авторизации Telegram:")
        for req in required_not_authorized:
            print(f"  - {req.session_basename}.session ({req.description})")
            print(f"    Пересоздать: {req.setup_command}")

    if required_missing:
        print("[SESSIONS] ВНИМАНИЕ: отсутствуют обязательные сессии для включённых процессов:")
        for req in required_missing:
            print(f"  - {req.session_basename}.session ({req.description})")
            print(f"    Создать: {req.setup_command}")
        print("[SESSIONS] Подсказка: можно скопировать *.session файлы с предыдущего сервера.")

    if required_missing or required_not_authorized:
        return 2

    if optional_missing:
        print("[SESSIONS] Дополнительно отсутствуют опциональные сессии:")
        for req in optional_missing:
            print(f"  - {req.session_basename}.session ({req.description})")
            print(f"    Создать при необходимости: {req.setup_command}")

    print("[SESSIONS] Проверка завершена: обязательные сессии в порядке.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
