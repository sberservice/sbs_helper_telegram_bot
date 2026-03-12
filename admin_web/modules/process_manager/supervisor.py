"""Супервизор процессов SBS Archie.

Управляет жизненным циклом процессов: запуск, остановка, перезапуск,
мониторинг статуса.  Сохраняет желаемое состояние в БД для возможности
автоматического восстановления работы после перезагрузки системы.

Основные компоненты:
- ManagedProcess — представление одного управляемого процесса
- ProcessSupervisor — синглтон, управляющий всеми процессами
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional, Set, Tuple

from admin_web.modules.process_manager import db as pm_db
from admin_web.modules.process_manager.models import ProcessStatus, ProcessType, StopReason
from admin_web.modules.process_manager.registry import get_process_definition, get_process_registry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Константы
# ---------------------------------------------------------------------------

OUTPUT_BUFFER_MAX_LINES = 1000
PID_DIR = Path(tempfile.gettempdir())
PID_PREFIX = "archie_pm_"
RESTART_DELAY_SECONDS = 5
MAX_RESTART_ATTEMPTS = 3
STOP_TIMEOUT_SECONDS = 5
MONITOR_INTERVAL_SECONDS = 2


def _pid_file_path(process_key: str) -> Path:
    """Путь к PID-файлу процесса."""
    return PID_DIR / f"{PID_PREFIX}{process_key}.pid"


def _is_pid_alive(pid: int) -> bool:
    """Проверить, жив ли процесс по PID.

    На Unix использует os.kill(pid, 0) — сигнал 0 не убивает процесс.
    На Windows os.kill(pid, 0) использует OpenProcess, но может выбрасывать
    OSError вместо ProcessLookupError, поэтому обрабатываем оба варианта.
    """
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # Процесс жив, но нет прав на сигнал
    except OSError:
        # На Windows при отсутствии процесса может быть OSError
        return False


def _write_pid_file(process_key: str, pid: int) -> None:
    """Записать PID-файл."""
    path = _pid_file_path(process_key)
    try:
        path.write_text(str(pid), encoding="utf-8")
    except OSError as exc:
        logger.warning("Не удалось записать PID-файл %s: %s", path, exc)


def _read_pid_file(process_key: str) -> Optional[int]:
    """Прочитать PID из файла. Вернуть None если файл отсутствует или повреждён."""
    path = _pid_file_path(process_key)
    if not path.exists():
        return None
    try:
        content = path.read_text(encoding="utf-8").strip()
        return int(content) if content else None
    except (OSError, ValueError):
        return None


def _remove_pid_file(process_key: str) -> None:
    """Удалить PID-файл."""
    path = _pid_file_path(process_key)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Управляемый процесс
# ---------------------------------------------------------------------------


@dataclass
class ManagedProcess:
    """Представление одного управляемого процесса."""
    key: str
    process: Optional[subprocess.Popen] = None
    pid: Optional[int] = None
    run_id: Optional[int] = None
    flags: List[str] = field(default_factory=list)
    preset_name: Optional[str] = None
    started_by: Optional[int] = None
    started_at: Optional[datetime] = None
    status: ProcessStatus = ProcessStatus.STOPPED
    exit_code: Optional[int] = None
    restart_count: int = 0
    output_buffer: Deque[Dict[str, str]] = field(
        default_factory=lambda: deque(maxlen=OUTPUT_BUFFER_MAX_LINES),
    )
    _reader_thread: Optional[threading.Thread] = field(default=None, repr=False)
    _ws_subscribers: Set[asyncio.Queue] = field(default_factory=set, repr=False)

    @property
    def uptime_seconds(self) -> Optional[float]:
        """Время работы в секундах."""
        if self.status != ProcessStatus.RUNNING or not self.started_at:
            return None
        return (datetime.now(timezone.utc) - self.started_at).total_seconds()

    def add_output_line(self, line: str) -> None:
        """Добавить строку в буфер вывода и оповестить WebSocket-подписчиков."""
        ts = datetime.now(timezone.utc).isoformat()
        entry = {"timestamp": ts, "line": line}
        self.output_buffer.append(entry)

        # Оповестить подписчиков (неблокирующим образом)
        for queue in list(self._ws_subscribers):
            try:
                queue.put_nowait(entry)
            except asyncio.QueueFull:
                pass

    def subscribe(self, queue: asyncio.Queue) -> None:
        """Подписать WebSocket-клиента на вывод."""
        self._ws_subscribers.add(queue)

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        """Отписать WebSocket-клиента."""
        self._ws_subscribers.discard(queue)


# ---------------------------------------------------------------------------
# Супервизор
# ---------------------------------------------------------------------------


class ProcessSupervisor:
    """
    Синглтон-менеджер всех процессов SBS Archie.

    Отвечает за:
    - Запуск/остановку/рестарт процессов
    - Мониторинг статуса (опрос PID)
    - Авто-рестарт daemon-процессов при падении
    - Сохранение/восстановление желаемого состояния (persist через DB)
    - Буферизацию stdout/stderr
    - Оповещение WebSocket-подписчиков
    """

    _instance: Optional[ProcessSupervisor] = None

    def __new__(cls) -> ProcessSupervisor:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self._processes: Dict[str, ManagedProcess] = {}
        self._lock = threading.Lock()
        self._monitor_thread: Optional[threading.Thread] = None
        self._shutdown_event = threading.Event()
        self._project_root = str(Path(__file__).resolve().parent.parent.parent.parent)
        logger.info("ProcessSupervisor инициализирован: project_root=%s", self._project_root)

    # --- Публичный API ---

    def startup(self) -> None:
        """Инициализация при запуске приложения: очистка stale записей, восстановление."""
        stale_count = pm_db.cleanup_stale_running_records()
        if stale_count:
            logger.info(
                "Очищено stale записей process_runs: count=%d", stale_count,
            )

        # Инициализировать ManagedProcess для каждого процесса из реестра
        registry = get_process_registry()
        for key in registry:
            if key not in self._processes:
                self._processes[key] = ManagedProcess(key=key)

        # Проверить PID-файлы — обнаружить процессы, запущенные вне admin panel
        self._scan_pid_files()

        # Восстановить desired state: перезапустить процессы, которые должны работать
        self._restore_desired_state()

        # Запустить фоновый мониторинг
        self._shutdown_event.clear()
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="pm-monitor",
        )
        self._monitor_thread.start()
        logger.info("ProcessSupervisor startup завершён")

    def shutdown(self) -> None:
        """Остановка мониторинга. Процессы не останавливаются — they survive admin panel restart."""
        self._shutdown_event.set()
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=3)
        logger.info("ProcessSupervisor shutdown завершён")

    def start_process(
        self,
        process_key: str,
        *,
        flags: Optional[List[str]] = None,
        preset_name: Optional[str] = None,
        started_by: Optional[int] = None,
        persist: Optional[bool] = None,
    ) -> ManagedProcess:
        """
        Запустить процесс.

        Args:
            process_key: Ключ процесса из реестра.
            flags: CLI-флаги для запуска.
            preset_name: Название пресета (для логирования и UI).
            started_by: Telegram ID администратора.
            persist: Сохранять ли desired state для авто-восстановления
                     при перезагрузке сервера. None — авто (True для daemon).

        Returns:
            ManagedProcess с обновлённым статусом.

        Raises:
            ValueError: Если ключ не найден или singleton уже запущен.
        """
        definition = get_process_definition(process_key)
        if not definition:
            raise ValueError(f"Процесс не найден в реестре: {process_key}")

        with self._lock:
            managed = self._processes.get(process_key)
            if not managed:
                managed = ManagedProcess(key=process_key)
                self._processes[process_key] = managed

            # Проверка singleton
            if definition.singleton and managed.status == ProcessStatus.RUNNING:
                raise ValueError(
                    f"Процесс {process_key} уже запущен (singleton). "
                    f"PID={managed.pid}. Остановите перед повторным запуском.",
                )

            flags = flags or []
            managed.status = ProcessStatus.STARTING
            managed.flags = flags
            managed.preset_name = preset_name
            managed.started_by = started_by
            managed.exit_code = None
            managed.restart_count = 0
            managed.output_buffer.clear()

        # Фактический запуск
        self._do_start(process_key, flags, preset_name, started_by)

        # Сохранить desired state для авто-восстановления при перезагрузке
        should_persist = persist if persist is not None else (definition.process_type == ProcessType.DAEMON)
        if should_persist:
            pm_db.set_desired_state(
                process_key,
                should_run=True,
                flags_json=json.dumps(flags) if flags else None,
                preset_name=preset_name,
                started_by=started_by,
            )
        elif definition.process_type == ProcessType.DAEMON:
            # Явно запрошено persist=False — очистить предыдущий desired state
            pm_db.clear_desired_state(process_key)

        return self._processes[process_key]

    def stop_process(
        self,
        process_key: str,
        *,
        reason: str = "manual",
        stopped_by: Optional[int] = None,
    ) -> ManagedProcess:
        """
        Остановить процесс.

        Args:
            process_key: Ключ процесса.
            reason: Причина остановки.
            stopped_by: Telegram ID администратора.

        Returns:
            ManagedProcess с обновлённым статусом.
        """
        with self._lock:
            managed = self._processes.get(process_key)
            if not managed or managed.status != ProcessStatus.RUNNING:
                raise ValueError(f"Процесс {process_key} не запущен")
            managed.status = ProcessStatus.STOPPING

        self._do_stop(process_key, reason)

        # Очистить desired state
        pm_db.clear_desired_state(process_key)

        return self._processes[process_key]

    def restart_process(
        self,
        process_key: str,
        *,
        flags: Optional[List[str]] = None,
        preset_name: Optional[str] = None,
        restarted_by: Optional[int] = None,
    ) -> ManagedProcess:
        """Перезапустить процесс (stop + start)."""
        managed = self._processes.get(process_key)
        if managed and managed.status == ProcessStatus.RUNNING:
            self.stop_process(process_key, reason="restart", stopped_by=restarted_by)
            time.sleep(1)

        # Если flags не заданы, использовать предыдущие
        if flags is None and managed:
            flags = managed.flags
        if preset_name is None and managed:
            preset_name = managed.preset_name

        return self.start_process(
            process_key,
            flags=flags,
            preset_name=preset_name,
            started_by=restarted_by,
        )

    def get_status(self, process_key: str) -> ManagedProcess:
        """Получить текущий статус процесса."""
        managed = self._processes.get(process_key)
        if not managed:
            managed = ManagedProcess(key=process_key)
            self._processes[process_key] = managed
        return managed

    def get_all_statuses(self) -> Dict[str, ManagedProcess]:
        """Получить статусы всех процессов."""
        registry = get_process_registry()
        for key in registry:
            if key not in self._processes:
                self._processes[key] = ManagedProcess(key=key)
        return dict(self._processes)

    def get_output(self, process_key: str, last_n: int = 200) -> List[Dict[str, str]]:
        """Получить последние N строк вывода процесса."""
        managed = self._processes.get(process_key)
        if not managed:
            return []
        buf = list(managed.output_buffer)
        return buf[-last_n:]

    # --- Внутренние методы ---

    def _do_start(
        self,
        process_key: str,
        flags: List[str],
        preset_name: Optional[str],
        started_by: Optional[int],
    ) -> None:
        """Запустить процесс через subprocess.Popen."""
        definition = get_process_definition(process_key)
        if not definition:
            return

        cmd = list(definition.command) + flags
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        logger.info(
            "Запуск процесса: key=%s cmd=%s preset=%s started_by=%s",
            process_key, " ".join(cmd), preset_name, started_by,
        )

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=self._project_root,
                env=env,
            )
        except Exception as exc:
            logger.error(
                "Ошибка запуска процесса %s: %s", process_key, exc, exc_info=True,
            )
            managed = self._processes[process_key]
            managed.status = ProcessStatus.CRASHED
            managed.add_output_line(f"[ERROR] Ошибка запуска: {exc}")
            return

        now = datetime.now(timezone.utc)
        flags_json = json.dumps(flags) if flags else None

        run_id = pm_db.create_run_record(
            process_key=process_key,
            pid=proc.pid,
            flags_json=flags_json,
            preset_name=preset_name,
            started_by=started_by,
        )

        _write_pid_file(process_key, proc.pid)

        managed = self._processes[process_key]
        managed.process = proc
        managed.pid = proc.pid
        managed.run_id = run_id
        managed.started_at = now
        managed.status = ProcessStatus.RUNNING
        managed.add_output_line(
            f"[PM] Процесс запущен: PID={proc.pid} flags={flags} preset={preset_name}",
        )

        # Запустить поток чтения stdout
        reader = threading.Thread(
            target=self._read_output,
            args=(process_key,),
            daemon=True,
            name=f"pm-reader-{process_key}",
        )
        managed._reader_thread = reader
        reader.start()

        logger.info(
            "Процесс запущен: key=%s pid=%d run_id=%d",
            process_key, proc.pid, run_id,
        )

    def _do_stop(self, process_key: str, reason: str) -> None:
        """Остановить процесс: SIGTERM → wait → SIGKILL."""
        managed = self._processes.get(process_key)
        if not managed or not managed.process:
            # Попробовать через PID-файл
            pid = managed.pid if managed else _read_pid_file(process_key)
            if pid and _is_pid_alive(pid):
                try:
                    os.kill(pid, signal.SIGTERM)
                    time.sleep(STOP_TIMEOUT_SECONDS)
                    if _is_pid_alive(pid):
                        os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if managed:
                managed.status = ProcessStatus.STOPPED
                managed.process = None
                managed.pid = None
            _remove_pid_file(process_key)
            return

        proc = managed.process
        managed.add_output_line(f"[PM] Остановка процесса: reason={reason}")

        try:
            proc.terminate()
            try:
                proc.wait(timeout=STOP_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                logger.warning(
                    "Процесс %s не завершился за %ds, SIGKILL",
                    process_key, STOP_TIMEOUT_SECONDS,
                )
                proc.kill()
                proc.wait(timeout=3)
        except Exception as exc:
            logger.error(
                "Ошибка остановки процесса %s: %s", process_key, exc, exc_info=True,
            )

        exit_code = proc.returncode
        status = "killed" if reason == "manual" else "stopped"

        if managed.run_id:
            pm_db.finish_run_record(
                managed.run_id,
                exit_code=exit_code,
                status=status,
                stop_reason=reason,
            )

        managed.process = None
        managed.pid = None
        managed.status = ProcessStatus.STOPPED
        managed.exit_code = exit_code
        managed.add_output_line(
            f"[PM] Процесс остановлен: exit_code={exit_code} reason={reason}",
        )
        _remove_pid_file(process_key)

    def _read_output(self, process_key: str) -> None:
        """Фоновый поток: чтение stdout процесса в кольцевой буфер."""
        managed = self._processes.get(process_key)
        if not managed or not managed.process or not managed.process.stdout:
            return

        try:
            for line in managed.process.stdout:
                line = line.rstrip("\n")
                managed.add_output_line(line)
        except Exception as exc:
            logger.debug("Ошибка чтения stdout %s: %s", process_key, exc)
        finally:
            if managed.process:
                managed.process.stdout.close()

    def _monitor_loop(self) -> None:
        """Фоновый цикл: мониторинг состояния процессов, авто-рестарт."""
        while not self._shutdown_event.is_set():
            try:
                self._check_processes()
            except Exception as exc:
                logger.error("Ошибка в мониторинге процессов: %s", exc, exc_info=True)
            self._shutdown_event.wait(timeout=MONITOR_INTERVAL_SECONDS)

    def _check_processes(self) -> None:
        """Опросить все управляемые процессы, обнаружить падения."""
        registry = get_process_registry()

        for key, managed in list(self._processes.items()):
            if managed.status != ProcessStatus.RUNNING:
                continue

            alive = False
            if managed.process:
                alive = managed.process.poll() is None
            elif managed.pid:
                alive = _is_pid_alive(managed.pid)

            if alive:
                continue

            # Процесс упал
            exit_code = None
            if managed.process:
                exit_code = managed.process.returncode

            logger.warning(
                "Процесс упал: key=%s pid=%s exit_code=%s",
                key, managed.pid, exit_code,
            )

            if managed.run_id:
                definition = registry.get(key)
                one_shot_completed = bool(
                    definition
                    and definition.process_type == ProcessType.ONE_SHOT
                    and exit_code == 0
                )

                pm_db.finish_run_record(
                    managed.run_id,
                    exit_code=exit_code,
                    status="stopped" if one_shot_completed else "crashed",
                    stop_reason="completed" if one_shot_completed else "crash",
                )

            managed.exit_code = exit_code
            managed.process = None
            definition = registry.get(key)
            one_shot_completed = bool(
                definition
                and definition.process_type == ProcessType.ONE_SHOT
                and exit_code == 0
            )
            if one_shot_completed:
                managed.add_output_line(
                    f"[PM] Процесс завершён: exit_code={exit_code}",
                )
            else:
                managed.add_output_line(
                    f"[PM] Процесс упал: exit_code={exit_code}",
                )
            _remove_pid_file(key)

            # Авто-рестарт для daemon-процессов
            if (
                definition
                and definition.auto_restart
                and definition.process_type == ProcessType.DAEMON
                and managed.restart_count < definition.max_restart_attempts
            ):
                managed.restart_count += 1
                managed.status = ProcessStatus.STARTING
                delay = definition.restart_delay_seconds
                managed.add_output_line(
                    f"[PM] Авто-рестарт через {delay}с "
                    f"(попытка {managed.restart_count}/{definition.max_restart_attempts})",
                )
                logger.info(
                    "Авто-рестарт: key=%s attempt=%d/%d delay=%ds",
                    key, managed.restart_count, definition.max_restart_attempts, delay,
                )
                time.sleep(delay)
                self._do_start(
                    key,
                    managed.flags,
                    managed.preset_name,
                    managed.started_by,
                )
            else:
                managed.status = ProcessStatus.STOPPED if one_shot_completed else ProcessStatus.CRASHED
                if definition and managed.restart_count >= definition.max_restart_attempts:
                    managed.add_output_line(
                        f"[PM] Достигнут лимит авто-рестартов ({definition.max_restart_attempts})",
                    )

    def _scan_pid_files(self) -> None:
        """Обнаружить PID-файлы от предыдущих запусков и связаться с процессами."""
        registry = get_process_registry()
        for key in registry:
            pid = _read_pid_file(key)
            if pid is None:
                continue

            if _is_pid_alive(pid):
                managed = self._processes.get(key)
                if not managed:
                    managed = ManagedProcess(key=key)
                    self._processes[key] = managed

                managed.pid = pid
                managed.status = ProcessStatus.RUNNING
                managed.started_at = datetime.now(timezone.utc)
                managed.add_output_line(
                    f"[PM] Обнаружен работающий процесс: PID={pid} (из PID-файла)",
                )
                logger.info(
                    "Обнаружен работающий процесс: key=%s pid=%d", key, pid,
                )
            else:
                _remove_pid_file(key)
                logger.debug(
                    "Удалён stale PID-файл: key=%s pid=%d", key, pid,
                )

    def _restore_desired_state(self) -> None:
        """Восстановить процессы, которые должны быть запущены.

        Читает launch_config.json (если есть) и применяет конфигурацию
        к desired state в БД. Затем запускает все процессы с should_run=True.
        """
        # Фаза 1: применить launch_config.json, если он существует.
        self._apply_launch_config_to_desired_state()

        # Фаза 2: запустить процессы из desired state.
        desired_states = pm_db.get_desired_states()
        if not desired_states:
            logger.info("Нет процессов для автоматического восстановления")
            return

        registry = get_process_registry()
        for state in desired_states:
            process_key = state["process_key"]
            if process_key not in registry:
                logger.warning(
                    "Процесс из desired state не найден в реестре: %s", process_key,
                )
                continue

            managed = self._processes.get(process_key)
            if managed and managed.status == ProcessStatus.RUNNING:
                # Заполнить in-memory данные из DB, чтобы при авто-рестарте
                # использовались правильные флаги/пресет
                running_flags_json = state.get("flags_json")
                managed.flags = json.loads(running_flags_json) if running_flags_json else []
                managed.preset_name = state.get("preset_name")
                managed.started_by = state.get("started_by")
                logger.info(
                    "Процесс из desired state уже запущен: key=%s pid=%s flags=%s preset=%s",
                    process_key, managed.pid, managed.flags, managed.preset_name,
                )
                continue

            flags_json = state.get("flags_json")
            flags = json.loads(flags_json) if flags_json else []
            preset_name = state.get("preset_name")
            started_by = state.get("started_by")

            logger.info(
                "Восстановление процесса из desired state: key=%s flags=%s preset=%s",
                process_key, flags, preset_name,
            )

            try:
                if process_key not in self._processes:
                    self._processes[process_key] = ManagedProcess(key=process_key)
                managed = self._processes[process_key]
                managed.flags = flags
                managed.preset_name = preset_name
                managed.started_by = started_by
                managed.status = ProcessStatus.STARTING
                managed.add_output_line(
                    f"[PM] Автоматическое восстановление после рестарта системы",
                )
                self._do_start(process_key, flags, preset_name, started_by)
            except Exception as exc:
                logger.error(
                    "Ошибка восстановления процесса %s: %s",
                    process_key, exc, exc_info=True,
                )

    # -------------------------------------------------------------------
    # Launch config
    # -------------------------------------------------------------------

    LAUNCH_CONFIG_RELATIVE_PATH = os.path.join("deploy", "launch_config.json")

    def _get_launch_config_path(self) -> Path:
        """Путь к файлу конфигурации запуска."""
        return Path(self._project_root) / self.LAUNCH_CONFIG_RELATIVE_PATH

    def _apply_launch_config_to_desired_state(self) -> None:
        """Прочитать deploy/launch_config.json и синхронизировать с desired state в БД.

        При наличии файла: для каждого процесса с enabled=true устанавливает
        desired state, для enabled=false — очищает. Процессы, отсутствующие
        в конфиге, остаются без изменений (обратная совместимость).
        """
        config_path = self._get_launch_config_path()
        if not config_path.exists():
            logger.debug(
                "Файл launch_config.json не найден: %s — пропуск", config_path,
            )
            return

        try:
            raw = config_path.read_text(encoding="utf-8")
            config = json.loads(raw)
        except (OSError, json.JSONDecodeError) as exc:
            logger.error(
                "Ошибка чтения launch_config.json: %s — пропуск", exc,
            )
            return

        processes = config.get("processes", {})
        if not isinstance(processes, dict):
            logger.error("Некорректный формат launch_config.json: processes не dict")
            return

        registry = get_process_registry()
        applied = 0

        for process_key, entry in processes.items():
            if process_key not in registry:
                logger.warning(
                    "launch_config: неизвестный процесс '%s' — пропуск", process_key,
                )
                continue

            if not isinstance(entry, dict):
                logger.warning(
                    "launch_config: некорректная запись для '%s' — пропуск", process_key,
                )
                continue

            enabled = entry.get("enabled", False)
            flags = entry.get("flags", [])
            preset = entry.get("preset")

            if not isinstance(flags, list):
                flags = []

            if enabled:
                flags_json = json.dumps(flags) if flags else None
                pm_db.set_desired_state(
                    process_key,
                    should_run=True,
                    flags_json=flags_json,
                    preset_name=preset,
                    started_by=None,
                )
                logger.info(
                    "launch_config → desired state: key=%s enabled=%s flags=%s preset=%s",
                    process_key, enabled, flags, preset,
                )
            else:
                pm_db.clear_desired_state(process_key)
                logger.info(
                    "launch_config → desired state: key=%s enabled=%s (очищен)",
                    process_key, enabled,
                )
            applied += 1

        logger.info(
            "launch_config.json обработан: applied=%d entries=%d path=%s",
            applied, len(processes), config_path,
        )

    def read_launch_config(self) -> Dict[str, Any]:
        """Прочитать текущую конфигурацию запуска из файла.

        Returns:
            Содержимое launch_config.json или пустой конфиг.
        """
        config_path = self._get_launch_config_path()
        if not config_path.exists():
            return {"description": "", "processes": {}}

        try:
            raw = config_path.read_text(encoding="utf-8")
            return json.loads(raw)
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Ошибка чтения launch_config.json: %s", exc)
            return {"description": "", "processes": {}}

    def write_launch_config(self, config: Dict[str, Any]) -> None:
        """Записать конфигурацию запуска в файл.

        Args:
            config: Полная структура launch_config.json.

        Raises:
            ValueError: Если конфиг содержит неизвестные процессы.
            OSError: Если не удалось записать файл.
        """
        processes = config.get("processes", {})
        registry = get_process_registry()

        # Валидация ключей процессов.
        unknown_keys = [k for k in processes if k not in registry]
        if unknown_keys:
            raise ValueError(
                f"Неизвестные процессы в конфигурации: {', '.join(unknown_keys)}",
            )

        config_path = self._get_launch_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)

        raw = json.dumps(config, ensure_ascii=False, indent=4)
        config_path.write_text(raw + "\n", encoding="utf-8")
        logger.info("launch_config.json сохранён: path=%s", config_path)

    def apply_launch_config(self) -> Dict[str, str]:
        """Применить launch_config.json немедленно: запустить/остановить процессы.

        Returns:
            Словарь {process_key: action}, где action = 'started' | 'stopped' | 'unchanged'.
        """
        config = self.read_launch_config()
        processes = config.get("processes", {})
        registry = get_process_registry()
        actions: Dict[str, str] = {}

        for process_key, entry in processes.items():
            if process_key not in registry:
                continue

            enabled = entry.get("enabled", False)
            flags = entry.get("flags", [])
            preset_name = entry.get("preset")

            if not isinstance(flags, list):
                flags = []

            managed = self._processes.get(process_key)
            is_running = managed and managed.status == ProcessStatus.RUNNING

            if enabled and not is_running:
                try:
                    self.start_process(
                        process_key,
                        flags=flags,
                        preset_name=preset_name,
                        persist=True,
                    )
                    actions[process_key] = "started"
                except Exception as exc:
                    logger.error(
                        "apply_launch_config: ошибка запуска %s: %s",
                        process_key, exc, exc_info=True,
                    )
                    actions[process_key] = f"error: {exc}"
            elif not enabled and is_running:
                try:
                    self.stop_process(process_key, reason="launch_config_apply")
                    actions[process_key] = "stopped"
                except Exception as exc:
                    logger.error(
                        "apply_launch_config: ошибка остановки %s: %s",
                        process_key, exc, exc_info=True,
                    )
                    actions[process_key] = f"error: {exc}"
            else:
                actions[process_key] = "unchanged"

        logger.info("apply_launch_config завершён: actions=%s", actions)
        return actions

    def stop_all_processes(self) -> Dict[str, str]:
        """Остановить все запущенные процессы.

        Returns:
            Словарь {process_key: result}, где result = 'stopped' | 'error: ...'.
        """
        results: Dict[str, str] = {}
        for key, managed in list(self._processes.items()):
            if managed.status != ProcessStatus.RUNNING:
                continue
            try:
                self.stop_process(key, reason="shutdown")
                results[key] = "stopped"
            except Exception as exc:
                logger.error(
                    "stop_all_processes: ошибка остановки %s: %s",
                    key, exc, exc_info=True,
                )
                results[key] = f"error: {exc}"

        logger.info("stop_all_processes завершён: results=%s", results)
        return results


# ---------------------------------------------------------------------------
# Глобальный экземпляр
# ---------------------------------------------------------------------------

_supervisor: Optional[ProcessSupervisor] = None


def get_supervisor() -> ProcessSupervisor:
    """Получить глобальный экземпляр супервизора."""
    global _supervisor
    if _supervisor is None:
        _supervisor = ProcessSupervisor()
    return _supervisor
