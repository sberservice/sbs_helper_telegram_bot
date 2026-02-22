"""
test_ai_model_switch.py — тесты переключения модели DeepSeek через админ-интерфейс.
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from src.sbs_helper_telegram_bot.ai_router import settings as ai_settings


class TestAIModelSettings(unittest.TestCase):
    """Тесты функций настроек AI модели."""

    def test_normalize_deepseek_model(self):
        """Нормализация поддерживаемых/неподдерживаемых значений."""
        self.assertEqual(ai_settings.normalize_deepseek_model("deepseek-chat"), "deepseek-chat")
        self.assertEqual(ai_settings.normalize_deepseek_model("DEEPSEEK-REASONER"), "deepseek-reasoner")

        with patch("src.sbs_helper_telegram_bot.ai_router.settings.DEEPSEEK_MODEL", "deepseek-chat"):
            self.assertEqual(ai_settings.normalize_deepseek_model("unknown"), "deepseek-chat")

    @patch("src.common.bot_settings.get_setting", return_value="deepseek-reasoner")
    def test_get_active_deepseek_model_for_classification_from_db(self, mock_get_setting):
        """Модель классификации берётся из bot_settings."""
        model = ai_settings.get_active_deepseek_model_for_classification()
        self.assertEqual(model, "deepseek-reasoner")
        mock_get_setting.assert_called_once_with(ai_settings.AI_DEEPSEEK_MODEL_CLASSIFICATION_SETTING_KEY)

    @patch("src.common.bot_settings.get_setting", side_effect=[None, "deepseek-reasoner"])
    def test_get_active_deepseek_model_for_response_fallback_to_legacy(self, mock_get_setting):
        """Модель ответов использует legacy-ключ как fallback."""
        model = ai_settings.get_active_deepseek_model_for_response()
        self.assertEqual(model, "deepseek-reasoner")
        self.assertEqual(mock_get_setting.call_count, 2)

    @patch("src.common.bot_settings.get_setting", return_value="0")
    def test_is_rag_html_splitter_enabled_reads_disabled_value_from_db(self, mock_get_setting):
        """Флаг HTML splitter корректно читается из bot_settings как выключенный."""
        self.assertFalse(ai_settings.is_rag_html_splitter_enabled())
        mock_get_setting.assert_called_once_with(ai_settings.AI_RAG_HTML_SPLITTER_ENABLED_SETTING_KEY)


class TestAdminAISwitch(unittest.IsolatedAsyncioTestCase):
    """Тесты переключения модели в админ-панели."""

    @patch("src.sbs_helper_telegram_bot.bot_admin.admin_bot_part.reset_ai_router")
    @patch("src.sbs_helper_telegram_bot.bot_admin.admin_bot_part.bot_settings.set_setting")
    async def test_switch_ai_model_for_classification(self, mock_set_setting, mock_reset_router):
        """Переключение модели классификации записывает setting и обновляет UI."""
        from src.sbs_helper_telegram_bot.bot_admin.admin_bot_part import switch_ai_model, AI_MODEL_SETTINGS

        query = MagicMock()
        query.from_user.id = 777
        query.edit_message_text = AsyncMock()

        with patch(
            "src.sbs_helper_telegram_bot.bot_admin.admin_bot_part.ai_settings.get_active_deepseek_model_for_classification",
            return_value="deepseek-reasoner",
        ), patch(
            "src.sbs_helper_telegram_bot.bot_admin.admin_bot_part.ai_settings.get_active_deepseek_model_for_response",
            return_value="deepseek-chat",
        ), patch(
            "src.sbs_helper_telegram_bot.bot_admin.admin_bot_part.ai_settings.is_rag_html_splitter_enabled",
            return_value=True,
        ):
            state = await switch_ai_model(query, "deepseek-reasoner", "classification")

        self.assertEqual(state, AI_MODEL_SETTINGS)
        mock_set_setting.assert_called_once_with(
            ai_settings.AI_DEEPSEEK_MODEL_CLASSIFICATION_SETTING_KEY,
            "deepseek-reasoner",
            updated_by=777,
        )
        mock_reset_router.assert_called_once()
        query.edit_message_text.assert_awaited_once()

    @patch("src.sbs_helper_telegram_bot.bot_admin.admin_bot_part.reset_ai_router")
    @patch("src.sbs_helper_telegram_bot.bot_admin.admin_bot_part.bot_settings.set_setting")
    async def test_switch_ai_model_for_response(self, mock_set_setting, mock_reset_router):
        """Переключение модели ответов записывает setting и обновляет UI."""
        from src.sbs_helper_telegram_bot.bot_admin.admin_bot_part import switch_ai_model, AI_MODEL_SETTINGS

        query = MagicMock()
        query.from_user.id = 888
        query.edit_message_text = AsyncMock()

        with patch(
            "src.sbs_helper_telegram_bot.bot_admin.admin_bot_part.ai_settings.get_active_deepseek_model_for_classification",
            return_value="deepseek-chat",
        ), patch(
            "src.sbs_helper_telegram_bot.bot_admin.admin_bot_part.ai_settings.get_active_deepseek_model_for_response",
            return_value="deepseek-reasoner",
        ), patch(
            "src.sbs_helper_telegram_bot.bot_admin.admin_bot_part.ai_settings.is_rag_html_splitter_enabled",
            return_value=True,
        ):
            state = await switch_ai_model(query, "deepseek-reasoner", "response")

        self.assertEqual(state, AI_MODEL_SETTINGS)
        mock_set_setting.assert_called_once_with(
            ai_settings.AI_DEEPSEEK_MODEL_RESPONSE_SETTING_KEY,
            "deepseek-reasoner",
            updated_by=888,
        )
        mock_reset_router.assert_called_once()
        query.edit_message_text.assert_awaited_once()

    @patch("src.sbs_helper_telegram_bot.bot_admin.admin_bot_part.bot_settings.set_setting")
    async def test_toggle_ai_html_splitter_disable(self, mock_set_setting):
        """Отключение HTML splitter пишет настройку и обновляет UI."""
        from src.sbs_helper_telegram_bot.bot_admin.admin_bot_part import toggle_ai_html_splitter, AI_MODEL_SETTINGS

        query = MagicMock()
        query.from_user.id = 999
        query.edit_message_text = AsyncMock()

        with patch(
            "src.sbs_helper_telegram_bot.bot_admin.admin_bot_part.ai_settings.get_active_deepseek_model_for_classification",
            return_value="deepseek-chat",
        ), patch(
            "src.sbs_helper_telegram_bot.bot_admin.admin_bot_part.ai_settings.get_active_deepseek_model_for_response",
            return_value="deepseek-chat",
        ), patch(
            "src.sbs_helper_telegram_bot.bot_admin.admin_bot_part.ai_settings.is_rag_html_splitter_enabled",
            return_value=False,
        ):
            state = await toggle_ai_html_splitter(query, False)

        self.assertEqual(state, AI_MODEL_SETTINGS)
        mock_set_setting.assert_called_once_with(
            ai_settings.AI_RAG_HTML_SPLITTER_ENABLED_SETTING_KEY,
            "0",
            updated_by=999,
        )
        query.edit_message_text.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
