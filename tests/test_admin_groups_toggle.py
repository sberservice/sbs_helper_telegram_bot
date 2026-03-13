"""
Тесты для API-эндпоинтов включения/отключения групп.

Покрывает: toggle GK-групп, toggle Helper-групп,
загрузку/сохранение JSON-конфигурации с полем disabled.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class TestGroupsToggleLogic(unittest.TestCase):
    """Тесты логики переключения disabled-статуса групп в JSON-конфиге."""

    def _make_config_file(self, data: dict) -> str:
        """Создать временный JSON-файл с конфигом и вернуть путь."""
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False,
        )
        json.dump(data, f, ensure_ascii=False)
        f.close()
        return f.name

    def _load_config(self, path: str) -> dict:
        """Загрузить JSON-конфиг из файла."""
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def test_toggle_gk_group_disable(self):
        """Отключение GK-группы через toggle сохраняет disabled=true."""
        from admin_web.modules.process_manager.groups_api import (
            _load_json_config,
            _save_json_config,
        )

        config = {
            "groups": [
                {"id": -100, "title": "Group A"},
                {"id": -200, "title": "Group B"},
            ]
        }
        tmp_path = self._make_config_file(config)
        try:
            path = Path(tmp_path)
            data = _load_json_config(path)
            groups = data.get("groups", [])

            # Отключить группу -100
            for g in groups:
                if g["id"] == -100:
                    g["disabled"] = True
                    break

            data["groups"] = groups
            _save_json_config(path, data)

            # Проверить сохранённый конфиг
            saved = self._load_config(tmp_path)
            self.assertEqual(len(saved["groups"]), 2)
            g100 = next(g for g in saved["groups"] if g["id"] == -100)
            g200 = next(g for g in saved["groups"] if g["id"] == -200)
            self.assertTrue(g100.get("disabled", False))
            self.assertFalse(g200.get("disabled", False))
        finally:
            import os
            os.unlink(tmp_path)

    def test_toggle_gk_group_enable(self):
        """Включение ранее отключённой GK-группы сбрасывает disabled на false."""
        from admin_web.modules.process_manager.groups_api import (
            _load_json_config,
            _save_json_config,
        )

        config = {
            "groups": [
                {"id": -100, "title": "Disabled group", "disabled": True},
            ]
        }
        tmp_path = self._make_config_file(config)
        try:
            path = Path(tmp_path)
            data = _load_json_config(path)
            groups = data.get("groups", [])

            # Включить группу
            for g in groups:
                if g["id"] == -100:
                    g["disabled"] = False
                    break

            data["groups"] = groups
            _save_json_config(path, data)

            saved = self._load_config(tmp_path)
            g100 = saved["groups"][0]
            self.assertFalse(g100["disabled"])
        finally:
            import os
            os.unlink(tmp_path)

    def test_group_entry_model_disabled_default(self):
        """GroupEntry по умолчанию имеет disabled=False."""
        from admin_web.modules.process_manager.groups_api import GroupEntry

        entry = GroupEntry(id=-100, title="Test")
        self.assertFalse(entry.disabled)

    def test_group_entry_model_disabled_true(self):
        """GroupEntry принимает disabled=True."""
        from admin_web.modules.process_manager.groups_api import GroupEntry

        entry = GroupEntry(id=-100, title="Test", disabled=True)
        self.assertTrue(entry.disabled)

    def test_group_toggle_request_model(self):
        """GroupToggleRequest валидирует disabled поле."""
        from admin_web.modules.process_manager.groups_api import GroupToggleRequest

        req = GroupToggleRequest(disabled=True)
        self.assertTrue(req.disabled)

        req2 = GroupToggleRequest(disabled=False)
        self.assertFalse(req2.disabled)

    def test_groups_router_toggle_paths_use_fastapi_syntax(self):
        """Роуты toggle/remove групп используют корректный FastAPI path-синтаксис."""
        from admin_web.modules.process_manager.groups_api import build_groups_router

        router = build_groups_router()
        route_map = {
            (route.path, tuple(sorted(route.methods or [])))
            for route in router.routes
            if hasattr(route, "methods") and route.methods
        }

        self.assertIn(("/groups/gk/{group_id}/toggle", ("PATCH",)), route_map)
        self.assertIn(("/groups/helper/{group_id}/toggle", ("PATCH",)), route_map)
        self.assertIn(("/groups/gk/{group_id}", ("DELETE",)), route_map)
        self.assertIn(("/groups/helper/{group_id}", ("DELETE",)), route_map)

        for path, _methods in route_map:
            self.assertNotIn(":int", path)


if __name__ == "__main__":
    unittest.main()
