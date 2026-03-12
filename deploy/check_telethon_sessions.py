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

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


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

    try:
        launch_config = _load_launch_config(project_dir)
    except Exception as exc:
        print(f"[SESSIONS] ОШИБКА: не удалось прочитать launch_config.json: {exc}")
        return 3

    enabled_map = _enabled_processes(launch_config)

    required_missing: List[SessionRequirement] = []
    required_present: List[SessionRequirement] = []

    for key, req in REQUIREMENTS.items():
        if not enabled_map.get(key, False):
            continue
        if _session_file_exists(project_dir, req.session_basename):
            required_present.append(req)
        else:
            required_missing.append(req)

    optional_missing: List[SessionRequirement] = []
    for req in OPTIONAL_SESSIONS:
        if not _session_file_exists(project_dir, req.session_basename):
            optional_missing.append(req)

    print("[SESSIONS] Проверка Telethon-сессий")
    if required_present:
        for req in required_present:
            print(f"[SESSIONS] OK: {req.session_basename}.session ({req.description})")

    if required_missing:
        print("[SESSIONS] ВНИМАНИЕ: отсутствуют обязательные сессии для включённых процессов:")
        for req in required_missing:
            print(f"  - {req.session_basename}.session ({req.description})")
            print(f"    Создать: {req.setup_command}")
        print("[SESSIONS] Подсказка: можно скопировать *.session файлы с предыдущего сервера.")
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
