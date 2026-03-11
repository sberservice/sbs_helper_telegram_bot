"""Тесты CLI-логики scripts/gk_collector.py."""

import argparse
import asyncio
import importlib.util
import signal
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "gk_collector.py"
SPEC = importlib.util.spec_from_file_location("gk_collector_module_for_tests", SCRIPT_PATH)
GK_COLLECTOR = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader

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
    SPEC.loader.exec_module(GK_COLLECTOR)


class TestGKCollectorCli(unittest.TestCase):
    """Тесты daemon collector с встроенным responder."""

    def test_extract_qa_query(self):
        """Команда /qa распознаётся и извлекает текст вопроса."""
        self.assertEqual(
            GK_COLLECTOR._extract_qa_query("/qa как починить терминал"),
            "как починить терминал",
        )
        self.assertIsNone(GK_COLLECTOR._extract_qa_query("как починить терминал"))

    def test_run_collector_initializes_responder_bridge(self):
        """Daemon collector поднимает встроенный responder и bridge при обычном запуске."""
        args = argparse.Namespace(
            manage_groups=False,
            backfill=False,
            days=7,
            force=False,
            live=False,
            test_mode=False,
            redirect_test_mode=False,
            collect_only=False,
        )
        mock_client = AsyncMock()
        mock_client.on = lambda *_args, **_kwargs: (lambda func: func)
        mock_client.__bool__ = lambda self: True

        async def _run():
            with patch.object(GK_COLLECTOR, "load_groups_config", return_value=[{"id": -1001, "title": "Real"}]):
                with patch.object(GK_COLLECTOR, "start_telegram_client_with_logging", AsyncMock(return_value=mock_client)):
                    with patch.object(GK_COLLECTOR, "disconnect_client_quietly", AsyncMock()):
                        with patch.object(GK_COLLECTOR, "MessageCollector") as mock_collector_cls:
                            mock_collector = mock_collector_cls.return_value
                            mock_collector.group_ids = {-1001}
                            mock_collector.resolve_group_ids = AsyncMock()
                            mock_collector.sync_missed_messages = AsyncMock(return_value=0)
                            mock_collector.handle_new_message = AsyncMock(return_value=None)
                            with patch.object(GK_COLLECTOR, "GroupResponder") as mock_responder_cls:
                                with patch.object(GK_COLLECTOR, "CollectorResponderBridge") as mock_bridge_cls:
                                    mock_bridge_cls.return_value.stop = AsyncMock()
                                    with patch("signal.signal"):
                                        with patch.object(GK_COLLECTOR.asyncio, "sleep", new=AsyncMock(side_effect=[asyncio.CancelledError()])):
                                            try:
                                                await GK_COLLECTOR.run_collector(args)
                                            except asyncio.CancelledError:
                                                pass

            return mock_responder_cls, mock_bridge_cls

        mock_responder_cls, mock_bridge_cls = asyncio.run(_run())
        mock_responder_cls.assert_called_once()
        mock_bridge_cls.assert_called_once()

    def test_run_collector_syncs_missed_messages_before_listener(self):
        """Перед запуском listener collector добирает пропущенные сообщения."""
        args = argparse.Namespace(
            manage_groups=False,
            backfill=False,
            days=7,
            force=False,
            live=False,
            test_mode=False,
            redirect_test_mode=False,
            collect_only=False,
        )
        mock_client = AsyncMock()
        mock_client.on = lambda *_args, **_kwargs: (lambda func: func)
        mock_client.__bool__ = lambda self: True

        async def _run():
            with patch.object(GK_COLLECTOR, "load_groups_config", return_value=[{"id": -1001, "title": "Real"}]):
                with patch.object(GK_COLLECTOR, "start_telegram_client_with_logging", AsyncMock(return_value=mock_client)):
                    with patch.object(GK_COLLECTOR, "disconnect_client_quietly", AsyncMock()):
                        with patch.object(GK_COLLECTOR, "MessageCollector") as mock_collector_cls:
                            mock_collector = mock_collector_cls.return_value
                            mock_collector.group_ids = {-1001}
                            mock_collector.resolve_group_ids = AsyncMock()
                            mock_collector.sync_missed_messages = AsyncMock(return_value=3)
                            mock_collector.handle_new_message = AsyncMock(return_value=None)
                            with patch.object(GK_COLLECTOR, "GroupResponder"):
                                with patch.object(GK_COLLECTOR, "CollectorResponderBridge") as mock_bridge_cls:
                                    mock_bridge_cls.return_value.stop = AsyncMock()
                                    with patch("signal.signal"):
                                        with patch.object(GK_COLLECTOR.asyncio, "sleep", new=AsyncMock(side_effect=[asyncio.CancelledError()])):
                                            try:
                                                await GK_COLLECTOR.run_collector(args)
                                            except asyncio.CancelledError:
                                                pass
            return mock_collector.sync_missed_messages

        mock_sync = asyncio.run(_run())
        mock_sync.assert_awaited_once_with()

    def test_test_mode_forces_live_replies_without_live_flag(self):
        """В test-mode автоответчик работает не в dry-run даже без --live."""
        args = argparse.Namespace(
            manage_groups=False,
            backfill=False,
            days=7,
            force=False,
            live=False,
            test_mode=True,
            redirect_test_mode=False,
            collect_only=False,
        )
        mock_client = AsyncMock()
        mock_client.on = lambda *_args, **_kwargs: (lambda func: func)
        mock_client.__bool__ = lambda self: True

        async def _run():
            with patch.object(GK_COLLECTOR, "load_groups_config", return_value=[{"id": -1001, "title": "Real"}]):
                with patch.object(GK_COLLECTOR, "start_telegram_client_with_logging", AsyncMock(return_value=mock_client)):
                    with patch.object(GK_COLLECTOR, "disconnect_client_quietly", AsyncMock()):
                        with patch.object(
                            GK_COLLECTOR,
                            "_select_test_mode_mapping",
                            AsyncMock(
                                return_value={
                                    "listen_groups": [{"id": -2002, "title": "Test"}],
                                    "group_mapping": {-2002: -1001},
                                    "real_group": {"id": -1001, "title": "Real"},
                                    "test_group": {"id": -2002, "title": "Test"},
                                }
                            ),
                        ):
                            with patch.object(GK_COLLECTOR, "MessageCollector") as mock_collector_cls:
                                mock_collector = mock_collector_cls.return_value
                                mock_collector.group_ids = {-2002}
                                mock_collector.resolve_group_ids = AsyncMock()
                                mock_collector.sync_missed_messages = AsyncMock(return_value=0)
                                mock_collector.handle_new_message = AsyncMock(return_value=None)
                                with patch.object(GK_COLLECTOR, "GroupResponder") as mock_responder_cls:
                                    with patch.object(GK_COLLECTOR, "CollectorResponderBridge") as mock_bridge_cls:
                                        mock_bridge_cls.return_value.stop = AsyncMock()
                                        with patch("signal.signal"):
                                            with patch.object(
                                                GK_COLLECTOR.asyncio,
                                                "sleep",
                                                new=AsyncMock(side_effect=[asyncio.CancelledError()]),
                                            ):
                                                try:
                                                    await GK_COLLECTOR.run_collector(args)
                                                except asyncio.CancelledError:
                                                    pass

            return mock_responder_cls

        mock_responder_cls = asyncio.run(_run())
        mock_responder_cls.assert_called_once_with(
            dry_run=False,
            test_group_mapping={-2002: -1001},
            redirect_output_group=None,
        )

    def test_redirect_test_mode_forces_send_to_configured_group(self):
        """Redirect test mode слушает боевые группы и перенаправляет ответы в общую test group."""
        args = argparse.Namespace(
            manage_groups=False,
            backfill=False,
            days=7,
            force=False,
            live=False,
            test_mode=False,
            redirect_test_mode=True,
            collect_only=False,
        )
        mock_client = AsyncMock()
        mock_client.on = lambda *_args, **_kwargs: (lambda func: func)
        mock_client.__bool__ = lambda self: True

        async def _run():
            groups = [{"id": -1001, "title": "Real"}]
            redirect_group = {"id": -3003, "title": "GK Test Output"}
            with patch.object(GK_COLLECTOR, "load_groups_config", return_value=groups):
                with patch.object(GK_COLLECTOR, "start_telegram_client_with_logging", AsyncMock(return_value=mock_client)):
                    with patch.object(GK_COLLECTOR, "disconnect_client_quietly", AsyncMock()):
                        with patch.object(
                            GK_COLLECTOR,
                            "_resolve_redirect_test_group",
                            AsyncMock(return_value=redirect_group),
                        ):
                            with patch.object(GK_COLLECTOR, "MessageCollector") as mock_collector_cls:
                                mock_collector = mock_collector_cls.return_value
                                mock_collector.group_ids = {-1001}
                                mock_collector.resolve_group_ids = AsyncMock()
                                mock_collector.sync_missed_messages = AsyncMock(return_value=0)
                                mock_collector.handle_new_message = AsyncMock(return_value=None)
                                with patch.object(GK_COLLECTOR, "GroupResponder") as mock_responder_cls:
                                    with patch.object(GK_COLLECTOR, "CollectorResponderBridge") as mock_bridge_cls:
                                        mock_bridge_cls.return_value.stop = AsyncMock()
                                        with patch("signal.signal"):
                                            with patch.object(
                                                GK_COLLECTOR.asyncio,
                                                "sleep",
                                                new=AsyncMock(side_effect=[asyncio.CancelledError()]),
                                            ):
                                                try:
                                                    await GK_COLLECTOR.run_collector(args)
                                                except asyncio.CancelledError:
                                                    pass

            return mock_responder_cls, mock_collector_cls

        mock_responder_cls, mock_collector_cls = asyncio.run(_run())
        mock_collector_cls.assert_called_once()
        mock_responder_cls.assert_called_once_with(
            dry_run=False,
            test_group_mapping={},
            redirect_output_group={"id": -3003, "title": "GK Test Output"},
        )

    def test_run_collector_sigint_stops_backfill_collector(self):
        """SIGINT в backfill-режиме прокидывается в MessageCollector.stop."""
        args = argparse.Namespace(
            manage_groups=False,
            backfill=True,
            days=7,
            force=False,
            live=False,
            test_mode=False,
            redirect_test_mode=False,
            collect_only=False,
        )
        mock_client = AsyncMock()
        mock_client.__bool__ = lambda self: True

        async def _run():
            signal_handlers = {}

            def register_signal(sig, handler):
                signal_handlers[sig] = handler

            with patch.object(GK_COLLECTOR, "load_groups_config", return_value=[{"id": -1001, "title": "Real"}]):
                with patch.object(GK_COLLECTOR, "start_telegram_client_with_logging", AsyncMock(return_value=mock_client)):
                    with patch.object(GK_COLLECTOR, "disconnect_client_quietly", AsyncMock()):
                        with patch.object(GK_COLLECTOR, "ImageProcessor") as mock_image_processor_cls:
                            mock_image_processor = mock_image_processor_cls.return_value
                            mock_image_processor.process_queue = AsyncMock(return_value=0)
                            with patch.object(GK_COLLECTOR, "MessageCollector") as mock_collector_cls:
                                mock_collector = mock_collector_cls.return_value
                                mock_collector.group_ids = {-1001}
                                mock_collector.resolve_group_ids = AsyncMock()

                                async def backfill_side_effect(*_args, **_kwargs):
                                    signal_handlers[signal.SIGINT](signal.SIGINT, None)
                                    return 0

                                mock_collector.backfill_messages = AsyncMock(side_effect=backfill_side_effect)
                                with patch.object(GK_COLLECTOR, "GroupResponder") as mock_responder_cls:
                                    mock_responder_cls.return_value.preload_search_resources.return_value = {}
                                    with patch.object(GK_COLLECTOR, "CollectorResponderBridge") as mock_bridge_cls:
                                        mock_bridge_cls.return_value.stop = AsyncMock()
                                        with patch("signal.signal", side_effect=register_signal):
                                            await GK_COLLECTOR.run_collector(args)
            return mock_collector

        mock_collector = asyncio.run(_run())
        mock_collector.stop.assert_called()

    def test_run_collector_calls_preload_on_startup(self):
        """Перед запуском listener collector вызывает прогрев поисковых ресурсов responder."""
        args = argparse.Namespace(
            manage_groups=False,
            backfill=False,
            days=7,
            force=False,
            live=False,
            test_mode=False,
            redirect_test_mode=False,
            collect_only=False,
        )
        mock_client = AsyncMock()
        mock_client.on = lambda *_args, **_kwargs: (lambda func: func)
        mock_client.__bool__ = lambda self: True

        async def _run():
            with patch.object(GK_COLLECTOR, "load_groups_config", return_value=[{"id": -1001, "title": "Real"}]):
                with patch.object(GK_COLLECTOR, "start_telegram_client_with_logging", AsyncMock(return_value=mock_client)):
                    with patch.object(GK_COLLECTOR, "disconnect_client_quietly", AsyncMock()):
                        with patch.object(GK_COLLECTOR, "MessageCollector") as mock_collector_cls:
                            mock_collector = mock_collector_cls.return_value
                            mock_collector.group_ids = {-1001}
                            mock_collector.resolve_group_ids = AsyncMock()
                            mock_collector.sync_missed_messages = AsyncMock(return_value=0)
                            mock_collector.handle_new_message = AsyncMock(return_value=None)
                            with patch.object(GK_COLLECTOR, "GroupResponder") as mock_responder_cls:
                                mock_responder = mock_responder_cls.return_value
                                mock_responder.preload_search_resources.return_value = {
                                    "corpus_pairs": 10,
                                    "corpus_signature": (10, 100, 1700000000),
                                    "vector_model_preloaded": True,
                                }
                                with patch.object(GK_COLLECTOR, "CollectorResponderBridge") as mock_bridge_cls:
                                    mock_bridge_cls.return_value.stop = AsyncMock()
                                    with patch("signal.signal"):
                                        with patch.object(GK_COLLECTOR.asyncio, "sleep", new=AsyncMock(side_effect=[asyncio.CancelledError()])):
                                            try:
                                                await GK_COLLECTOR.run_collector(args)
                                            except asyncio.CancelledError:
                                                pass
            return mock_responder

        mock_responder = asyncio.run(_run())
        mock_responder.preload_search_resources.assert_called_once_with(preload_vector_model=True)

    def test_fill_missing_is_question_mode_does_not_start_telegram(self):
        """Режим заполнения missing is_question работает без запуска Telethon-клиента."""
        args = argparse.Namespace(
            manage_groups=False,
            backfill=False,
            fill_missing_is_question=True,
            days=7,
            force=False,
            fill_days=30,
            fill_limit=100,
            group_id=-1001,
            live=False,
            test_mode=False,
            redirect_test_mode=False,
            collect_only=False,
        )

        async def _run():
            with patch.object(GK_COLLECTOR, "load_groups_config", return_value=[{"id": -1001, "title": "Real"}]):
                with patch.object(GK_COLLECTOR, "start_telegram_client_with_logging", AsyncMock()) as mock_start:
                    with patch.object(GK_COLLECTOR, "MessageCollector") as mock_collector_cls:
                        mock_collector = mock_collector_cls.return_value
                        mock_collector.fill_missing_question_classification = AsyncMock(return_value=12)
                        await GK_COLLECTOR._run_fill_missing_is_question(args)
            return mock_start, mock_collector_cls

        mock_start, mock_collector_cls = asyncio.run(_run())

        mock_start.assert_not_called()
        mock_collector_cls.assert_called_once_with(client=None, groups=[{"id": -1001, "title": "Real"}])
        mock_collector_cls.return_value.fill_missing_question_classification.assert_awaited_once_with(
            group_id=-1001,
            days=30,
            limit=100,
        )


if __name__ == "__main__":
    unittest.main()
