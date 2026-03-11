"""Тесты фоновой обработки изображений в отдельном потоке при backfill."""

import asyncio
import threading
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from src.group_knowledge.image_processor import ImageProcessor
from src.group_knowledge.models import ImageDescription


class TestProcessQueueLoopThreadingEvent(unittest.TestCase):
    """process_queue_loop поддерживает threading.Event для остановки."""

    def test_stops_on_threading_event(self):
        """Цикл останавливается при threading.Event.set()."""
        processor = ImageProcessor.__new__(ImageProcessor)
        processor._provider = MagicMock()
        processor._storage_path = "/tmp"

        stop = threading.Event()
        call_count = 0

        async def fake_process_queue(batch_size=5):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                stop.set()
            return 1

        processor.process_queue = fake_process_queue

        total = asyncio.run(
            processor.process_queue_loop(
                poll_interval=0.1,
                stop_event=stop,
                drain_remaining=False,
            )
        )
        self.assertGreaterEqual(call_count, 2)
        self.assertGreaterEqual(total, 2)

    def test_stops_on_asyncio_event(self):
        """Цикл останавливается при asyncio.Event.set() (обратная совместимость)."""
        processor = ImageProcessor.__new__(ImageProcessor)
        processor._provider = MagicMock()
        processor._storage_path = "/tmp"

        async def _run():
            stop = asyncio.Event()
            call_count_holder = [0]

            async def fake_process_queue(batch_size=5):
                call_count_holder[0] += 1
                if call_count_holder[0] >= 2:
                    stop.set()
                return 1

            processor.process_queue = fake_process_queue
            total = await processor.process_queue_loop(
                poll_interval=0.1,
                stop_event=stop,
                drain_remaining=False,
            )
            return total, call_count_holder[0]

        total, call_count = asyncio.run(_run())
        self.assertGreaterEqual(call_count, 2)
        self.assertGreaterEqual(total, 2)

    def test_drain_remaining_processes_leftover_images(self):
        """drain_remaining=True дообрабатывает оставшиеся изображения после stop."""
        processor = ImageProcessor.__new__(ImageProcessor)
        processor._provider = MagicMock()
        processor._storage_path = "/tmp"

        stop = threading.Event()
        stop.set()  # Уже остановлен — сразу переходим к drain

        drain_calls = 0

        async def fake_process_queue(batch_size=5):
            nonlocal drain_calls
            drain_calls += 1
            # Две порции изображений в drain, потом пусто
            if drain_calls <= 2:
                return 3
            return 0

        processor.process_queue = fake_process_queue

        total = asyncio.run(
            processor.process_queue_loop(
                poll_interval=0.1,
                stop_event=stop,
                drain_remaining=True,
            )
        )
        # Должны быть обработаны 2 батча по 3 = 6 штук при drain
        self.assertEqual(total, 6)
        self.assertEqual(drain_calls, 3)  # 2 с данными + 1 возвращающий 0

    def test_drain_remaining_false_does_not_process_leftovers(self):
        """drain_remaining=False не дообрабатывает после остановки."""
        processor = ImageProcessor.__new__(ImageProcessor)
        processor._provider = MagicMock()
        processor._storage_path = "/tmp"

        stop = threading.Event()
        stop.set()

        process_called = False

        async def fake_process_queue(batch_size=5):
            nonlocal process_called
            process_called = True
            return 1

        processor.process_queue = fake_process_queue

        total = asyncio.run(
            processor.process_queue_loop(
                poll_interval=0.1,
                stop_event=stop,
                drain_remaining=False,
            )
        )
        self.assertEqual(total, 0)
        self.assertFalse(process_called)

    def test_returns_total_count(self):
        """Метод возвращает общее число обработанных изображений."""
        processor = ImageProcessor.__new__(ImageProcessor)
        processor._provider = MagicMock()
        processor._storage_path = "/tmp"

        stop = threading.Event()
        call_count = 0

        async def fake_process_queue(batch_size=5):
            nonlocal call_count
            call_count += 1
            if call_count > 3:
                stop.set()
                return 0
            return 2

        processor.process_queue = fake_process_queue

        total = asyncio.run(
            processor.process_queue_loop(
                poll_interval=0.1,
                stop_event=stop,
                drain_remaining=False,
            )
        )
        self.assertEqual(total, 6)


class TestRunImageQueueInThread(unittest.TestCase):
    """Тесты вспомогательной функции _run_image_queue_in_thread."""

    def _load_gk_collector_module(self):
        """Загрузить gk_collector как модуль для тестирования."""
        import importlib.util
        import sys
        import types
        from pathlib import Path

        script_path = Path(__file__).resolve().parent.parent / "scripts" / "gk_collector.py"
        spec = importlib.util.spec_from_file_location("gk_collector_test_module", script_path)
        module = importlib.util.module_from_spec(spec)

        fake_telethon = types.ModuleType("telethon")
        fake_telethon.events = types.SimpleNamespace(
            NewMessage=lambda *args, **kwargs: None,
            ChatAction=lambda *args, **kwargs: None,
        )
        fake_tl = types.ModuleType("telethon.tl")
        fake_tl_types = types.ModuleType("telethon.tl.types")
        fake_tl_types.MessageActionChatMigrateTo = type("MessageActionChatMigrateTo", (), {})
        fake_tl.types = fake_tl_types
        fake_telethon.tl = fake_tl
        fake_utils = types.ModuleType("telethon.utils")
        fake_utils.get_peer_id = lambda entity: getattr(entity, "id", 0)
        fake_telethon.utils = fake_utils

        with patch.dict(sys.modules, {
            "telethon": fake_telethon,
            "telethon.tl": fake_tl,
            "telethon.tl.types": fake_tl_types,
            "telethon.utils": fake_utils,
        }):
            spec.loader.exec_module(module)
        return module

    def test_thread_processes_images_and_returns_count(self):
        """Фоновый поток обрабатывает изображения и возвращает результат."""
        gk_mod = self._load_gk_collector_module()

        processor = ImageProcessor.__new__(ImageProcessor)
        processor._provider = MagicMock()
        processor._storage_path = "/tmp"

        call_count = 0

        async def fake_process_queue(batch_size=5):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return 3
            return 0

        processor.process_queue = fake_process_queue

        stop_event = threading.Event()
        stop_event.set()  # Сразу сигналим — проверяем drain
        result_container: list[int] = []

        gk_mod._run_image_queue_in_thread(processor, stop_event, result_container)

        self.assertEqual(len(result_container), 1)
        self.assertEqual(result_container[0], 6)

    def test_thread_runs_in_separate_thread(self):
        """Функция корректно работает при запуске в threading.Thread."""
        gk_mod = self._load_gk_collector_module()

        processor = ImageProcessor.__new__(ImageProcessor)
        processor._provider = MagicMock()
        processor._storage_path = "/tmp"

        async def fake_process_queue(batch_size=5):
            return 0

        processor.process_queue = fake_process_queue

        stop_event = threading.Event()
        stop_event.set()
        result_container: list[int] = []

        thread = threading.Thread(
            target=gk_mod._run_image_queue_in_thread,
            args=(processor, stop_event, result_container),
            name="test-image-thread",
        )
        thread.start()
        thread.join(timeout=10)

        self.assertFalse(thread.is_alive())
        self.assertEqual(len(result_container), 1)
        self.assertEqual(result_container[0], 0)


if __name__ == "__main__":
    unittest.main()
