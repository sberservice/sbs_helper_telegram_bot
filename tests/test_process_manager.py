"""
test_process_manager.py — тесты модуля «Менеджер процессов».

Покрывает:
- Реестр процессов (registry)
- Pydantic-модели
- Вспомогательные функции супервизора
- Класс модуля (если fastapi доступен)
"""

import json
import os
import unittest
from collections import deque
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from admin_web.modules.process_manager.models import (
    FlagDefinition,
    FlagType,
    PresetDefinition,
    ProcessDefinition,
    ProcessesByCategoryResponse,
    ProcessHistoryResponse,
    ProcessRegistryResponse,
    ProcessRunRecord,
    ProcessStartRequest,
    ProcessStatus,
    ProcessStatusResponse,
    ProcessType,
    StopReason,
)

# Проверка наличия необходимых зависимостей для расширенных тестов
try:
    import mysql.connector  # noqa: F401
    _HAS_MYSQL = True
except ImportError:
    _HAS_MYSQL = False

try:
    import fastapi  # noqa: F401
    _HAS_FASTAPI = True
except ImportError:
    _HAS_FASTAPI = False


# ===================================================================
# Тесты моделей (Pydantic)
# ===================================================================


class TestProcessModels(unittest.TestCase):
    """Тесты Pydantic-моделей менеджера процессов."""

    def test_process_type_enum(self):
        """Значения перечисления ProcessType."""
        self.assertEqual(ProcessType.DAEMON, "daemon")
        self.assertEqual(ProcessType.ONE_SHOT, "one_shot")

    def test_process_status_enum_values(self):
        """Все ожидаемые статусы существуют."""
        expected = {"running", "stopped", "crashed", "starting", "stopping", "unknown"}
        actual = {s.value for s in ProcessStatus}
        self.assertEqual(expected, actual)

    def test_flag_type_enum_values(self):
        """Все ожидаемые типы флагов существуют."""
        expected = {"bool", "int", "string", "choice"}
        actual = {t.value for t in FlagType}
        self.assertEqual(expected, actual)

    def test_stop_reason_enum_values(self):
        """Все ожидаемые причины остановки существуют."""
        expected = {"manual", "auto_restart", "crash", "shutdown", "system_restart"}
        actual = {r.value for r in StopReason}
        self.assertEqual(expected, actual)

    def test_flag_definition_bool(self):
        """Определение булевого флага."""
        flag = FlagDefinition(name="--live", flag_type=FlagType.BOOL, description="Live mode")
        self.assertEqual(flag.name, "--live")
        self.assertEqual(flag.flag_type, FlagType.BOOL)
        self.assertIsNone(flag.choices)
        self.assertFalse(flag.required)

    def test_flag_definition_choice(self):
        """Флаг с ограниченным набором значений."""
        flag = FlagDefinition(
            name="--mode",
            flag_type=FlagType.CHOICE,
            choices=["fast", "slow", "auto"],
            default="auto",
        )
        self.assertEqual(flag.choices, ["fast", "slow", "auto"])
        self.assertEqual(flag.default, "auto")

    def test_preset_definition(self):
        """Определение пресета."""
        preset = PresetDefinition(
            name="Live collect",
            description="Сбор с автоответчиком",
            flags=["--live"],
            icon="🔴",
        )
        self.assertEqual(preset.name, "Live collect")
        self.assertEqual(preset.flags, ["--live"])

    def test_process_definition_minimal(self):
        """Минимальное определение процесса — только обязательные поля."""
        proc = ProcessDefinition(
            key="test_proc",
            name="Test Process",
            command=["python", "-c", "pass"],
        )
        self.assertEqual(proc.key, "test_proc")
        self.assertEqual(proc.process_type, ProcessType.DAEMON)
        self.assertTrue(proc.singleton)
        self.assertFalse(proc.auto_restart)
        self.assertEqual(proc.flags, [])
        self.assertEqual(proc.presets, [])

    def test_process_definition_full(self):
        """Полное определение процесса со всеми полями."""
        proc = ProcessDefinition(
            key="gk_collector",
            name="GK Collector",
            description="Сборщик",
            icon="📡",
            category="GK",
            process_type=ProcessType.DAEMON,
            command=["python", "scripts/gk_collector.py"],
            singleton=True,
            auto_restart=True,
            max_restart_attempts=5,
            restart_delay_seconds=10,
            flags=[
                FlagDefinition(name="--live", flag_type=FlagType.BOOL),
            ],
            presets=[
                PresetDefinition(name="Live", flags=["--live"]),
            ],
        )
        self.assertEqual(proc.max_restart_attempts, 5)
        self.assertEqual(len(proc.flags), 1)
        self.assertEqual(len(proc.presets), 1)

    def test_start_request_empty(self):
        """Запрос запуска без пресета и флагов (дефолтный)."""
        req = ProcessStartRequest()
        self.assertIsNone(req.preset)
        self.assertIsNone(req.flags)

    def test_start_request_with_preset(self):
        """Запрос запуска с пресетом."""
        req = ProcessStartRequest(preset="Live collect")
        self.assertEqual(req.preset, "Live collect")
        self.assertIsNone(req.flags)

    def test_start_request_with_flags(self):
        """Запрос запуска с произвольными флагами."""
        req = ProcessStartRequest(flags=["--live", "--test-mode"])
        self.assertEqual(req.flags, ["--live", "--test-mode"])
        self.assertIsNone(req.preset)

    def test_status_response_stopped(self):
        """Ответ статуса остановленного процесса."""
        resp = ProcessStatusResponse(
            key="test",
            name="Test",
            icon="📦",
            category="Core",
            process_type=ProcessType.ONE_SHOT,
            status=ProcessStatus.STOPPED,
        )
        self.assertIsNone(resp.pid)
        self.assertIsNone(resp.uptime_seconds)
        self.assertEqual(resp.description, "")

    def test_status_response_running(self):
        """Ответ статуса работающего процесса."""
        resp = ProcessStatusResponse(
            key="bot",
            name="Bot",
            icon="🤖",
            category="Core",
            process_type=ProcessType.DAEMON,
            status=ProcessStatus.RUNNING,
            pid=12345,
            uptime_seconds=3661.5,
            current_flags=["--verbose"],
            current_preset="Debug",
        )
        self.assertEqual(resp.pid, 12345)
        self.assertAlmostEqual(resp.uptime_seconds, 3661.5)
        self.assertEqual(resp.current_preset, "Debug")

    def test_categories_response_serialization(self):
        """Группировка процессов по категориям сериализуется корректно."""
        proc1 = ProcessStatusResponse(
            key="bot", name="Bot", icon="🤖", category="Core",
            process_type=ProcessType.DAEMON, status=ProcessStatus.RUNNING,
        )
        proc2 = ProcessStatusResponse(
            key="gk", name="GK", icon="📡", category="GK",
            process_type=ProcessType.DAEMON, status=ProcessStatus.STOPPED,
        )
        resp = ProcessesByCategoryResponse(categories={"Core": [proc1], "GK": [proc2]})
        data = resp.model_dump()
        self.assertIn("Core", data["categories"])
        self.assertIn("GK", data["categories"])
        self.assertEqual(len(data["categories"]["Core"]), 1)

    def test_run_record_serialization(self):
        """Запись запуска сериализуется корректно."""
        rec = ProcessRunRecord(
            id=1,
            process_key="bot",
            pid=1234,
            flags=["--live"],
            preset_name="Live",
            started_at="2025-01-01T00:00:00",
            stopped_at="2025-01-01T01:00:00",
            exit_code=0,
            status="stopped",
            stop_reason="manual",
        )
        data = rec.model_dump()
        self.assertEqual(data["process_key"], "bot")
        self.assertEqual(data["exit_code"], 0)

    def test_history_response_pagination(self):
        """Ответ с историей содержит метаданные пагинации."""
        resp = ProcessHistoryResponse(
            runs=[],
            total=100,
            page=3,
            page_size=25,
        )
        self.assertEqual(resp.total, 100)
        self.assertEqual(resp.page, 3)


# ===================================================================
# Тесты реестра процессов
# ===================================================================


class TestProcessRegistry(unittest.TestCase):
    """Тесты реестра процессов."""

    def test_registry_not_empty(self):
        """Реестр содержит хотя бы один процесс."""
        from admin_web.modules.process_manager.registry import get_process_registry
        registry = get_process_registry()
        self.assertGreater(len(registry), 0)

    def test_all_keys_unique(self):
        """Все ключи процессов уникальны (dict гарантирует, но проверим vs PROCESS_DEFINITIONS)."""
        from admin_web.modules.process_manager.registry import PROCESS_DEFINITIONS
        keys = [p.key for p in PROCESS_DEFINITIONS]
        self.assertEqual(len(keys), len(set(keys)), "Дублирующиеся ключи в реестре")

    def test_all_commands_non_empty(self):
        """Все процессы имеют непустую команду запуска."""
        from admin_web.modules.process_manager.registry import get_process_registry
        for key, proc in get_process_registry().items():
            self.assertTrue(
                len(proc.command) > 0,
                f"Процесс {key} имеет пустую команду",
            )

    def test_core_processes_present(self):
        """Ключевые core-процессы присутствуют в реестре."""
        from admin_web.modules.process_manager.registry import get_process_registry
        keys = set(get_process_registry().keys())
        for expected in ["telegram_bot", "image_queue", "soos_queue", "health_check_daemon"]:
            self.assertIn(expected, keys, f"Core-процесс {expected} не найден")

    def test_gk_collector_present(self):
        """GK collector присутствует и имеет пресеты."""
        from admin_web.modules.process_manager.registry import get_process_definition
        gk = get_process_definition("gk_collector")
        self.assertIsNotNone(gk)
        self.assertGreater(len(gk.presets), 0, "GK collector должен иметь пресеты")
        self.assertGreater(len(gk.flags), 0, "GK collector должен иметь флаги")

    def test_get_process_definition_returns_none(self):
        """Запрос несуществующего процесса возвращает None."""
        from admin_web.modules.process_manager.registry import get_process_definition
        result = get_process_definition("nonexistent_process")
        self.assertIsNone(result)

    def test_get_processes_by_category(self):
        """Процессы группируются по категориям без потерь."""
        from admin_web.modules.process_manager.registry import (
            get_process_registry,
            get_processes_by_category,
        )
        total = len(get_process_registry())
        by_cat = get_processes_by_category()
        total_in_cats = sum(len(procs) for procs in by_cat.values())
        self.assertEqual(total, total_in_cats, "Количество процессов не совпадает")

    def test_preset_flags_are_strings(self):
        """Флаги в пресетах — строки."""
        from admin_web.modules.process_manager.registry import get_process_registry
        for key, proc in get_process_registry().items():
            for preset in proc.presets:
                for flag in preset.flags:
                    self.assertIsInstance(flag, str, f"{key}/{preset.name}: флаг не строка")

    def test_category_order_covers_all(self):
        """CATEGORY_ORDER содержит все используемые категории."""
        from admin_web.modules.process_manager.registry import (
            CATEGORY_ORDER,
            get_process_registry,
        )
        used_categories = {p.category for p in get_process_registry().values()}
        for cat in used_categories:
            self.assertIn(cat, CATEGORY_ORDER, f"Категория {cat} не в CATEGORY_ORDER")

    def test_daemon_processes_have_correct_type(self):
        """Процессы из Core имеют тип daemon."""
        from admin_web.modules.process_manager.registry import get_process_registry
        for key, proc in get_process_registry().items():
            if proc.category == "Core":
                self.assertEqual(
                    proc.process_type,
                    ProcessType.DAEMON,
                    f"Core-процесс {key} должен быть daemon",
                )


# ===================================================================
# Тесты утилит супервизора
# ===================================================================


@unittest.skipUnless(_HAS_MYSQL, "mysql-connector-python не установлен")
class TestSupervisorUtils(unittest.TestCase):
    """Тесты вспомогательных функций супервизора."""

    def test_pid_alive_nonexistent(self):
        """Несуществующий PID не считается живым."""
        from admin_web.modules.process_manager.supervisor import _is_pid_alive
        # PID 999999999 скорее всего не существует
        self.assertFalse(_is_pid_alive(999999999))

    def test_pid_alive_zero(self):
        """PID 0 не считается живым."""
        from admin_web.modules.process_manager.supervisor import _is_pid_alive
        self.assertFalse(_is_pid_alive(0))

    def test_pid_alive_negative(self):
        """Отрицательный PID не считается живым."""
        from admin_web.modules.process_manager.supervisor import _is_pid_alive
        self.assertFalse(_is_pid_alive(-1))

    def test_pid_alive_current_process(self):
        """PID текущего процесса жив."""
        import os
        from admin_web.modules.process_manager.supervisor import _is_pid_alive
        self.assertTrue(_is_pid_alive(os.getpid()))

    def test_pid_file_path(self):
        """PID-файл формирует правильный путь."""
        from admin_web.modules.process_manager.supervisor import _pid_file_path
        path = _pid_file_path("telegram_bot")
        self.assertIn("archie_pm_telegram_bot.pid", str(path))

    def test_managed_process_uptime_when_stopped(self):
        """Uptime None для остановленного процесса."""
        from admin_web.modules.process_manager.supervisor import ManagedProcess
        mp = ManagedProcess(key="test", status=ProcessStatus.STOPPED)
        self.assertIsNone(mp.uptime_seconds)

    def test_managed_process_uptime_when_running(self):
        """Uptime вычисляется для запущенного процесса."""
        from admin_web.modules.process_manager.supervisor import ManagedProcess
        mp = ManagedProcess(
            key="test",
            status=ProcessStatus.RUNNING,
            started_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )
        self.assertIsNotNone(mp.uptime_seconds)
        self.assertGreater(mp.uptime_seconds, 0)

    def test_managed_process_output_buffer(self):
        """Буфер вывода ограничен размером."""
        from admin_web.modules.process_manager.supervisor import ManagedProcess
        mp = ManagedProcess(key="test")
        # Добавляем больше строк, чем лимит буфера (1000)
        for i in range(1100):
            mp.add_output_line(f"line {i}")
        self.assertEqual(len(mp.output_buffer), 1000)
        # Первая строка должна быть line 100 (первые 100 вытеснены)
        self.assertIn("line 100", mp.output_buffer[0]["line"])

    def test_managed_process_output_has_timestamp(self):
        """Каждая строка вывода содержит timestamp."""
        from admin_web.modules.process_manager.supervisor import ManagedProcess
        mp = ManagedProcess(key="test")
        mp.add_output_line("hello")
        entry = mp.output_buffer[0]
        self.assertIn("timestamp", entry)
        self.assertIn("line", entry)
        self.assertEqual(entry["line"], "hello")


# ===================================================================
# Тесты модуля (регистрация)
# ===================================================================


@unittest.skipUnless(_HAS_FASTAPI and _HAS_MYSQL, "fastapi или mysql не установлены")
class TestProcessManagerModule(unittest.TestCase):
    """Тесты класса модуля ProcessManagerModule."""

    def test_module_properties(self):
        """Модуль имеет корректные метаданные."""
        from admin_web.modules.process_manager.module import ProcessManagerModule
        mod = ProcessManagerModule()
        self.assertEqual(mod.key, "process_manager")
        self.assertEqual(mod.name, "Менеджер процессов")
        self.assertEqual(mod.icon, "⚙️")
        self.assertIsNotNone(mod.description)

    def test_module_has_router(self):
        """Модуль предоставляет маршрутизатор."""
        from admin_web.modules.process_manager.module import ProcessManagerModule
        mod = ProcessManagerModule()
        router = mod.get_router()
        self.assertIsNotNone(router)


# ===================================================================
# Тесты новых полей PresetDefinition
# ===================================================================


class TestPresetDefinitionExtended(unittest.TestCase):
    """Тесты расширенных полей PresetDefinition."""

    def test_preset_requires_form_default(self):
        """По умолчанию requires_form=False, form_type=None, hidden=False."""
        preset = PresetDefinition(name="Default", flags=[])
        self.assertFalse(preset.requires_form)
        self.assertIsNone(preset.form_type)
        self.assertFalse(preset.hidden)

    def test_preset_requires_form(self):
        """Пресет с requires_form и form_type."""
        preset = PresetDefinition(
            name="Test mode",
            flags=["--test-mode"],
            requires_form=True,
            form_type="gk_test_mode",
        )
        self.assertTrue(preset.requires_form)
        self.assertEqual(preset.form_type, "gk_test_mode")
        self.assertFalse(preset.hidden)

    def test_preset_hidden(self):
        """Скрытый пресет."""
        preset = PresetDefinition(
            name="Manage groups",
            flags=["--manage-groups"],
            hidden=True,
        )
        self.assertTrue(preset.hidden)

    def test_preset_serialization_includes_new_fields(self):
        """Новые поля присутствуют в сериализованном виде."""
        preset = PresetDefinition(
            name="Form preset",
            flags=["--test-mode"],
            requires_form=True,
            form_type="gk_test_mode",
            hidden=False,
        )
        data = preset.model_dump()
        self.assertIn("requires_form", data)
        self.assertIn("form_type", data)
        self.assertIn("hidden", data)
        self.assertTrue(data["requires_form"])
        self.assertEqual(data["form_type"], "gk_test_mode")


class TestStartRequestFormData(unittest.TestCase):
    """Тесты ProcessStartRequest с form_data."""

    def test_start_request_with_form_data(self):
        """Запрос запуска с пресетом и form_data."""
        req = ProcessStartRequest(
            preset="Test mode",
            form_data={"test-real-group-id": 123, "test-group-id": 456},
        )
        self.assertEqual(req.preset, "Test mode")
        self.assertIsNotNone(req.form_data)
        self.assertEqual(req.form_data["test-real-group-id"], 123)
        self.assertEqual(req.form_data["test-group-id"], 456)

    def test_start_request_form_data_default_none(self):
        """form_data по умолчанию None."""
        req = ProcessStartRequest()
        self.assertIsNone(req.form_data)

    def test_start_request_form_data_serialization(self):
        """form_data сериализуется в JSON."""
        req = ProcessStartRequest(
            preset="Redirect test",
            form_data={"redirect-group-id": 789},
        )
        data = req.model_dump()
        self.assertEqual(data["form_data"]["redirect-group-id"], 789)


# ===================================================================
# Тесты реестра — новые поля пресетов
# ===================================================================


class TestRegistryFormPresets(unittest.TestCase):
    """Тесты реестра — пресеты с requires_form."""

    def test_gk_collector_test_mode_preset(self):
        """У GK Collector пресет Test mode имеет requires_form=True."""
        from admin_web.modules.process_manager.registry import get_process_definition
        defn = get_process_definition("gk_collector")
        self.assertIsNotNone(defn)
        test_preset = next(
            (p for p in defn.presets if p.name == "Test mode"), None,
        )
        self.assertIsNotNone(test_preset)
        self.assertTrue(test_preset.requires_form)
        self.assertEqual(test_preset.form_type, "gk_test_mode")

    def test_gk_collector_redirect_preset(self):
        """У GK Collector пресет Redirect test имеет requires_form=True."""
        from admin_web.modules.process_manager.registry import get_process_definition
        defn = get_process_definition("gk_collector")
        redirect_preset = next(
            (p for p in defn.presets if p.name == "Redirect test"), None,
        )
        self.assertIsNotNone(redirect_preset)
        self.assertTrue(redirect_preset.requires_form)
        self.assertEqual(redirect_preset.form_type, "gk_redirect_test")

    def test_gk_responder_test_mode_preset(self):
        """У GK Responder пресет Test mode имеет requires_form=True."""
        from admin_web.modules.process_manager.registry import get_process_definition
        defn = get_process_definition("gk_responder")
        self.assertIsNotNone(defn)
        test_preset = next(
            (p for p in defn.presets if p.name == "Test mode"), None,
        )
        self.assertIsNotNone(test_preset)
        self.assertTrue(test_preset.requires_form)
        self.assertEqual(test_preset.form_type, "gk_test_mode")

    def test_gk_delete_has_form_preset(self):
        """У GK Delete Group Data есть пресет с формой."""
        from admin_web.modules.process_manager.registry import get_process_definition
        defn = get_process_definition("gk_delete_group_data")
        self.assertIsNotNone(defn)
        self.assertTrue(len(defn.presets) >= 1)
        delete_preset = defn.presets[0]
        self.assertTrue(delete_preset.requires_form)
        self.assertEqual(delete_preset.form_type, "gk_delete_group")

    def test_normal_presets_no_form(self):
        """Обычные пресеты не требуют формы."""
        from admin_web.modules.process_manager.registry import get_process_definition
        defn = get_process_definition("gk_collector")
        live_preset = next(
            (p for p in defn.presets if p.name == "Live"), None,
        )
        self.assertIsNotNone(live_preset)
        self.assertFalse(live_preset.requires_form)
        self.assertIsNone(live_preset.form_type)
        self.assertFalse(live_preset.hidden)

    def test_gk_collector_has_new_flags(self):
        """GK Collector содержит новые неинтерактивные флаги в реестре."""
        from admin_web.modules.process_manager.registry import get_process_definition
        defn = get_process_definition("gk_collector")
        flag_names = {f.name for f in defn.flags}
        self.assertIn("--test-real-group-id", flag_names)
        self.assertIn("--test-group-id", flag_names)
        self.assertIn("--redirect-group-id", flag_names)

    def test_gk_responder_has_new_flags(self):
        """GK Responder содержит новые неинтерактивные флаги в реестре."""
        from admin_web.modules.process_manager.registry import get_process_definition
        defn = get_process_definition("gk_responder")
        flag_names = {f.name for f in defn.flags}
        self.assertIn("--test-real-group-id", flag_names)
        self.assertIn("--test-group-id", flag_names)

    def test_rag_ops_wizard_removed(self):
        """wizard убран из choices подкоманды rag_ops."""
        from admin_web.modules.process_manager.registry import get_process_definition
        defn = get_process_definition("rag_ops")
        subcmd_flag = next((f for f in defn.flags if f.name == "subcommand"), None)
        self.assertIsNotNone(subcmd_flag)
        self.assertNotIn("wizard", subcmd_flag.choices)

    def test_gk_analyzer_has_unprocessed_except_today(self):
        """У GK Analyzer есть нужные флаги и пресеты, включая rebuild без сегодня."""
        from admin_web.modules.process_manager.registry import get_process_definition

        defn = get_process_definition("gk_analyzer")
        self.assertIsNotNone(defn)

        flag_names = {f.name for f in defn.flags}
        self.assertIn("--all-unprocessed-except-today", flag_names)

        preset_names = {p.name for p in defn.presets}
        self.assertIn("Необработанные (без сегодня)", preset_names)
        self.assertIn("Rebuild (без сегодня)", preset_names)


class TestSupervisorOneShotCompletion(unittest.TestCase):
    """Тесты корректного завершения one-shot процессов."""

    def test_one_shot_exit_zero_marked_stopped_not_crashed(self):
        """One-shot процесс с exit_code=0 не должен помечаться как crashed."""
        from admin_web.modules.process_manager.models import ProcessType
        from admin_web.modules.process_manager.supervisor import ManagedProcess, ProcessSupervisor

        supervisor = ProcessSupervisor.__new__(ProcessSupervisor)
        supervisor._processes = {}
        supervisor._lock = __import__("threading").Lock()
        supervisor._shutdown_event = __import__("threading").Event()
        supervisor._monitor_thread = None

        process = MagicMock()
        process.poll.return_value = 0
        process.returncode = 0

        managed = ManagedProcess(key="gk_analyzer")
        managed.status = ProcessStatus.RUNNING
        managed.process = process
        managed.pid = 1234
        managed.run_id = 77
        supervisor._processes["gk_analyzer"] = managed

        with patch("admin_web.modules.process_manager.supervisor.pm_db") as mock_db, \
             patch("admin_web.modules.process_manager.supervisor._remove_pid_file") as mock_remove_pid, \
             patch("admin_web.modules.process_manager.supervisor.get_process_registry") as mock_registry:
            mock_registry.return_value = {
                "gk_analyzer": SimpleNamespace(
                    process_type=ProcessType.ONE_SHOT,
                    auto_restart=False,
                    max_restart_attempts=0,
                    restart_delay_seconds=0,
                ),
            }

            supervisor._check_processes()

        mock_db.finish_run_record.assert_called_once_with(
            77,
            exit_code=0,
            status="stopped",
            stop_reason="completed",
        )
        mock_remove_pid.assert_called_once_with("gk_analyzer")
        self.assertEqual(managed.status, ProcessStatus.STOPPED)


# ===================================================================
# Тесты groups_api — утилиты JSON
# ===================================================================


class TestGroupsApiUtils(unittest.TestCase):
    """Тесты утилит чтения/записи JSON-конфигов."""

    def setUp(self):
        """Создать временный файл."""
        import tempfile
        self._tmpdir = tempfile.mkdtemp()
        self._tmpfile = os.path.join(self._tmpdir, "test_groups.json")

    def tearDown(self):
        """Удалить временные файлы."""
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_load_nonexistent(self):
        """Загрузка несуществующего файла возвращает пустой dict."""
        from pathlib import Path
        from admin_web.modules.process_manager.groups_api import _load_json_config
        result = _load_json_config(Path("/nonexistent/path.json"))
        self.assertEqual(result, {})

    def test_save_and_load(self):
        """Сохранение и загрузка JSON-конфига."""
        from pathlib import Path
        from admin_web.modules.process_manager.groups_api import (
            _load_json_config,
            _save_json_config,
        )
        data = {"groups": [{"id": -123, "title": "Test"}]}
        path = Path(self._tmpfile)
        _save_json_config(path, data)
        loaded = _load_json_config(path)
        self.assertEqual(loaded["groups"][0]["id"], -123)
        self.assertEqual(loaded["groups"][0]["title"], "Test")

    def test_load_invalid_json(self):
        """Загрузка повреждённого JSON возвращает пустой dict."""
        from pathlib import Path
        from admin_web.modules.process_manager.groups_api import _load_json_config
        path = Path(self._tmpfile)
        with open(path, "w") as f:
            f.write("{invalid json")
        result = _load_json_config(path)
        self.assertEqual(result, {})

    def test_load_non_dict_json(self):
        """Загрузка JSON с массивом вместо объекта возвращает пустой dict."""
        from pathlib import Path
        from admin_web.modules.process_manager.groups_api import _load_json_config
        path = Path(self._tmpfile)
        with open(path, "w") as f:
            f.write("[1, 2, 3]")
        result = _load_json_config(path)
        self.assertEqual(result, {})

    def test_normalize_test_targets_supports_legacy_single_group(self):
        """Legacy test_target_group попадает в нормализованный список."""
        from admin_web.modules.process_manager.groups_api import _normalize_test_target_groups

        data = {
            "test_target_group": {
                "id": -1001,
                "title": "Legacy target",
            },
        }
        targets, active = _normalize_test_target_groups(data)

        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0].id, -1001)
        self.assertIsNotNone(active)
        self.assertEqual(active.id, -1001)

    def test_normalize_test_targets_deduplicates_list_and_active(self):
        """Нормализация убирает дубликат активной группы в списке."""
        from admin_web.modules.process_manager.groups_api import _normalize_test_target_groups

        data = {
            "test_target_groups": [
                {"id": -1001, "title": "Target 1"},
                {"id": -1002, "title": "Target 2"},
            ],
            "test_target_group": {"id": -1002, "title": "Target 2"},
        }
        targets, active = _normalize_test_target_groups(data)

        self.assertEqual([t.id for t in targets], [-1001, -1002])
        self.assertIsNotNone(active)
        self.assertEqual(active.id, -1002)


# ===================================================================
# Тесты persist (восстановление при перезагрузке)
# ===================================================================


class TestStartRequestPersist(unittest.TestCase):
    """Тесты ProcessStartRequest с полем persist."""

    def test_persist_default_none(self):
        """persist по умолчанию None."""
        req = ProcessStartRequest()
        self.assertIsNone(req.persist)

    def test_persist_true(self):
        """persist=True явно задано."""
        req = ProcessStartRequest(
            preset="Live сбор", persist=True,
        )
        self.assertTrue(req.persist)

    def test_persist_false(self):
        """persist=False — не сохранять desired state."""
        req = ProcessStartRequest(
            preset="Redirect test", persist=False,
        )
        self.assertFalse(req.persist)

    def test_persist_serialization(self):
        """persist корректно сериализуется в JSON."""
        req = ProcessStartRequest(persist=True)
        data = req.model_dump()
        self.assertIn("persist", data)
        self.assertTrue(data["persist"])

        req2 = ProcessStartRequest(persist=False)
        data2 = req2.model_dump()
        self.assertFalse(data2["persist"])


class TestRestoreDesiredStateFlags(unittest.TestCase):
    """Тест: _restore_desired_state заполняет in-memory флаги для работающих процессов."""

    def test_running_process_gets_flags_from_desired_state(self):
        """Если процесс уже запущен, его in-memory флаги заполняются из DB."""
        from admin_web.modules.process_manager.supervisor import (
            ManagedProcess,
            ProcessSupervisor,
        )

        supervisor = ProcessSupervisor.__new__(ProcessSupervisor)
        supervisor._processes = {}
        supervisor._lock = __import__("threading").Lock()
        supervisor._shutdown_event = __import__("threading").Event()
        supervisor._monitor_thread = None
        supervisor._project_root = "/tmp/fake_project"

        # Имитировать запущенный процесс (как после _scan_pid_files)
        managed = ManagedProcess(key="gk_collector")
        managed.status = ProcessStatus.RUNNING
        managed.pid = 12345
        managed.flags = []
        managed.preset_name = None
        managed.started_by = None
        supervisor._processes["gk_collector"] = managed

        # Имитировать desired state из DB
        desired_states = [{
            "process_key": "gk_collector",
            "flags_json": json.dumps(["--redirect-test-mode", "--live", "--redirect-group-id", "-5197204255"]),
            "preset_name": "Redirect test",
            "started_by": 9000000000000001,
        }]

        with patch("admin_web.modules.process_manager.supervisor.pm_db") as mock_db, \
             patch("admin_web.modules.process_manager.supervisor.get_process_registry") as mock_reg:
            mock_db.get_desired_states.return_value = desired_states
            mock_reg.return_value = {"gk_collector": MagicMock()}

            supervisor._restore_desired_state()

        # Проверить, что in-memory данные заполнены
        self.assertEqual(
            managed.flags,
            ["--redirect-test-mode", "--live", "--redirect-group-id", "-5197204255"],
        )
        self.assertEqual(managed.preset_name, "Redirect test")
        self.assertEqual(managed.started_by, 9000000000000001)

    def test_stopped_process_gets_restarted_with_flags(self):
        """Если процесс не запущен, _restore_desired_state вызывает _do_start с флагами."""
        from admin_web.modules.process_manager.supervisor import (
            ManagedProcess,
            ProcessSupervisor,
        )

        supervisor = ProcessSupervisor.__new__(ProcessSupervisor)
        supervisor._processes = {}
        supervisor._lock = __import__("threading").Lock()
        supervisor._shutdown_event = __import__("threading").Event()
        supervisor._monitor_thread = None
        supervisor._project_root = "/tmp/fake_project"

        managed = ManagedProcess(key="gk_collector")
        managed.status = ProcessStatus.STOPPED
        supervisor._processes["gk_collector"] = managed

        desired_states = [{
            "process_key": "gk_collector",
            "flags_json": json.dumps(["--live"]),
            "preset_name": "Live сбор",
            "started_by": 123,
        }]

        with patch("admin_web.modules.process_manager.supervisor.pm_db") as mock_db, \
             patch("admin_web.modules.process_manager.supervisor.get_process_registry") as mock_reg, \
             patch.object(supervisor, "_do_start") as mock_start:
            mock_db.get_desired_states.return_value = desired_states
            mock_reg.return_value = {"gk_collector": MagicMock()}

            supervisor._restore_desired_state()

        mock_start.assert_called_once_with("gk_collector", ["--live"], "Live сбор", 123)
        self.assertEqual(managed.flags, ["--live"])


class TestGroupsApiDatetimeSerialization(unittest.TestCase):
    """Тесты сериализации дат для collected groups API."""

    def test_to_iso_datetime_supports_datetime(self):
        """datetime сериализуется через isoformat без изменений."""
        from admin_web.modules.process_manager.groups_api import _to_iso_datetime

        value = datetime(2026, 3, 10, 9, 19, 15, tzinfo=timezone.utc)
        self.assertEqual(_to_iso_datetime(value), value.isoformat())

    def test_to_iso_datetime_supports_unix_timestamp_int(self):
        """Целочисленный unix timestamp корректно преобразуется в ISO UTC."""
        from admin_web.modules.process_manager.groups_api import _to_iso_datetime

        result = _to_iso_datetime(1741598355)
        self.assertEqual(result, "2025-03-10T09:19:15+00:00")

    def test_to_iso_datetime_supports_unix_timestamp_ms_int(self):
        """Unix timestamp в миллисекундах корректно нормализуется."""
        from admin_web.modules.process_manager.groups_api import _to_iso_datetime

        result = _to_iso_datetime(1741598355000)
        self.assertEqual(result, "2025-03-10T09:19:15+00:00")

    def test_to_iso_datetime_supports_numeric_string_timestamp(self):
        """Строковый timestamp из БД также обрабатывается корректно."""
        from admin_web.modules.process_manager.groups_api import _to_iso_datetime

        result = _to_iso_datetime("1741598355")
        self.assertEqual(result, "2025-03-10T09:19:15+00:00")

    def test_to_iso_datetime_returns_plain_string(self):
        """Нечисловые строки возвращаются как есть (после trim)."""
        from admin_web.modules.process_manager.groups_api import _to_iso_datetime

        self.assertEqual(_to_iso_datetime("  2026-03-10 09:19:15  "), "2026-03-10 09:19:15")


if __name__ == "__main__":
    unittest.main()
