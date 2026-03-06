"""Тесты CLI-логики scripts/gk_responder.py."""

import argparse
import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "gk_responder.py"
SPEC = importlib.util.spec_from_file_location("gk_responder_module_for_tests", SCRIPT_PATH)
GK_RESPONDER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader

fake_telethon = types.ModuleType("telethon")
fake_telethon.events = types.SimpleNamespace(NewMessage=lambda *args, **kwargs: None)

with patch.dict(sys.modules, {"telethon": fake_telethon}):
    SPEC.loader.exec_module(GK_RESPONDER)


class TestGKResponderCli(unittest.TestCase):
    """Тесты интерактивного test mode responder."""

    def test_select_item_from_menu_returns_choice(self):
        """Меню выбора возвращает выбранный элемент."""
        items = [{"id": 1, "title": "A"}, {"id": 2, "title": "B"}]

        with patch("builtins.input", return_value="2"):
            selected = GK_RESPONDER._select_item_from_menu(
                items,
                prompt="Выберите",
                formatter=lambda item: item["title"],
            )

        self.assertEqual(selected["id"], 2)

    def test_select_test_mode_mapping_returns_mapping(self):
        """Test mode возвращает маппинг test group -> real group."""
        configured_groups = [{"id": -1001, "title": "Real Group"}]
        available_groups = [
            {"id": -1001, "title": "Real Group", "participants": 10},
            {"id": -1002, "title": "Test Group", "participants": 3},
        ]

        async def _run():
            with patch.object(GK_RESPONDER, "_get_available_groups", AsyncMock(return_value=available_groups)):
                with patch.object(
                    GK_RESPONDER,
                    "_select_item_from_menu",
                    side_effect=[configured_groups[0], available_groups[1]],
                ):
                    return await GK_RESPONDER._select_test_mode_mapping(object(), configured_groups)

        result = asyncio.run(_run())

        self.assertEqual(result["group_mapping"], {-1002: -1001})
        self.assertEqual(result["listen_groups"][0]["id"], -1002)

    def test_run_responder_ignores_non_qa_only_outside_test_mode(self):
        """В test mode responder не отфильтровывает сообщения без /qa на уровне скрипта."""
        args = argparse.Namespace(live=False, manage_groups=False, test_mode=True)
        mock_client = AsyncMock()
        mock_client.on = lambda *_args, **_kwargs: (lambda func: func)
        mock_client.__bool__ = lambda self: True

        async def _run():
            mock_responder_cls = None
            with patch.object(GK_RESPONDER, "load_groups_config", return_value=[{"id": -1001, "title": "Real"}]):
                with patch.object(GK_RESPONDER, "start_telegram_client_with_logging", AsyncMock(return_value=mock_client)):
                    with patch.object(GK_RESPONDER, "disconnect_client_quietly", AsyncMock()):
                        with patch.object(GK_RESPONDER, "_select_test_mode_mapping", AsyncMock(return_value={
                            "listen_groups": [{"id": -1002, "title": "Test"}],
                            "group_mapping": {-1002: -1001},
                            "real_group": {"id": -1001, "title": "Real"},
                            "test_group": {"id": -1002, "title": "Test"},
                        })):
                            with patch.object(GK_RESPONDER, "GroupResponder") as patched_responder_cls:
                                nonlocal_mock[0] = patched_responder_cls
                                mock_responder = patched_responder_cls.return_value
                                mock_responder.stop.return_value = None
                                with patch("signal.signal"):
                                    with patch.object(GK_RESPONDER.asyncio, "sleep", new=AsyncMock(side_effect=[asyncio.CancelledError()])):
                                        try:
                                            await GK_RESPONDER.run_responder(args)
                                        except asyncio.CancelledError:
                                            pass

        nonlocal_mock = [None]
        asyncio.run(_run())
        self.assertIsNotNone(nonlocal_mock[0])
        nonlocal_mock[0].assert_called_once()


if __name__ == "__main__":
    unittest.main()
