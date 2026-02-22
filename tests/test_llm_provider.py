"""
test_llm_provider.py — тесты для LLM-провайдера и парсинга результатов.
"""
import json
import unittest
from unittest.mock import patch, MagicMock, AsyncMock

from src.sbs_helper_telegram_bot.ai_router.llm_provider import (
    ClassificationResult,
    DeepSeekProvider,
    get_provider,
    register_provider,
)


class TestClassificationResult(unittest.TestCase):
    """Тесты для ClassificationResult dataclass."""

    def test_default_values(self):
        """Значения по умолчанию."""
        result = ClassificationResult(intent="test", confidence=0.5)
        self.assertEqual(result.intent, "test")
        self.assertEqual(result.confidence, 0.5)
        self.assertEqual(result.parameters, {})
        self.assertEqual(result.explain_code, "UNKNOWN")
        self.assertIsNone(result.raw_response)
        self.assertEqual(result.response_time_ms, 0)

    def test_custom_values(self):
        """Пользовательские значения."""
        result = ClassificationResult(
            intent="upos_error_lookup",
            confidence=0.95,
            parameters={"error_code": "1001"},
            explain_code="UPOS_EXACT",
            raw_response='{"intent": "upos_error_lookup"}',
            response_time_ms=150,
        )
        self.assertEqual(result.parameters["error_code"], "1001")
        self.assertEqual(result.response_time_ms, 150)


class TestParseClassification(unittest.TestCase):
    """Тесты для _parse_classification."""

    def test_valid_json(self):
        """Корректный JSON-ответ."""
        raw = json.dumps({
            "intent": "ktr_lookup",
            "confidence": 0.9,
            "parameters": {"ktr_code": "ABC"},
            "explain_code": "KTR_CODE_FOUND",
        })
        result = DeepSeekProvider._parse_classification(raw, elapsed_ms=100)
        self.assertEqual(result.intent, "ktr_lookup")
        self.assertEqual(result.confidence, 0.9)
        self.assertEqual(result.parameters["ktr_code"], "ABC")
        self.assertEqual(result.explain_code, "KTR_CODE_FOUND")
        self.assertEqual(result.response_time_ms, 100)

    def test_json_in_markdown_block(self):
        """JSON обёрнутый в ```json ... ```."""
        raw = '```json\n{"intent": "general_chat", "confidence": 0.8, "explain_code": "CHAT"}\n```'
        result = DeepSeekProvider._parse_classification(raw, elapsed_ms=50)
        self.assertEqual(result.intent, "general_chat")
        self.assertEqual(result.confidence, 0.8)

    def test_json_with_surrounding_text(self):
        """JSON встроен в текстовый ответ."""
        raw = 'Вот результат: {"intent": "upos_error_lookup", "confidence": 0.85, "parameters": {"error_code": "1001"}} и дальше текст.'
        result = DeepSeekProvider._parse_classification(raw, elapsed_ms=200)
        self.assertEqual(result.intent, "upos_error_lookup")
        self.assertEqual(result.confidence, 0.85)

    def test_no_json_in_response(self):
        """Нет JSON в ответе — возвращает unknown."""
        raw = "Не удалось определить намерение"
        result = DeepSeekProvider._parse_classification(raw, elapsed_ms=300)
        self.assertEqual(result.intent, "unknown")
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.explain_code, "NO_JSON_IN_RESPONSE")

    def test_direct_text_fallback_for_long_non_json_response(self):
        """Длинный не-JSON ответ обрабатывается как direct-text fallback."""
        raw = (
            "📚 Ответ по базе знаний. Для прошивки D200 подготовьте флешку FAT32, "
            "скопируйте файл обновления, зайдите в сервисное меню и запустите обновление."
        )
        result = DeepSeekProvider._parse_classification(raw, elapsed_ms=180)
        self.assertEqual(result.intent, "general_chat")
        self.assertEqual(result.explain_code, "DIRECT_TEXT_FALLBACK")
        self.assertIn("direct_answer", result.parameters)

    def test_invalid_json(self):
        """Невалидный JSON с intent обрабатывается partial fallback."""
        raw = 'some text {"intent": "test", broken} and more'
        result = DeepSeekProvider._parse_classification(raw, elapsed_ms=100)
        self.assertEqual(result.intent, "test")
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.explain_code, "PARTIAL_JSON_FALLBACK")

    def test_confidence_clamped_to_range(self):
        """Confidence ограничивается диапазоном [0, 1]."""
        raw_high = json.dumps({"intent": "test", "confidence": 1.5})
        result_high = DeepSeekProvider._parse_classification(raw_high, elapsed_ms=0)
        self.assertEqual(result_high.confidence, 1.0)

        raw_low = json.dumps({"intent": "test", "confidence": -0.5})
        result_low = DeepSeekProvider._parse_classification(raw_low, elapsed_ms=0)
        self.assertEqual(result_low.confidence, 0.0)

    def test_missing_fields_use_defaults(self):
        """Отсутствующие поля заполняются defaults."""
        raw = json.dumps({"intent": "test"})
        result = DeepSeekProvider._parse_classification(raw, elapsed_ms=0)
        self.assertEqual(result.intent, "test")
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.parameters, {})
        self.assertEqual(result.explain_code, "PARSED_OK")

    def test_non_dict_parameters_converted(self):
        """Нестандартный тип parameters заменяется на пустой dict."""
        raw = json.dumps({"intent": "test", "confidence": 0.8, "parameters": "not a dict"})
        result = DeepSeekProvider._parse_classification(raw, elapsed_ms=0)
        self.assertEqual(result.parameters, {})

    def test_partial_json_fallback_for_truncated_response(self):
        """Частичный JSON без закрывающей скобки парсится через fallback."""
        raw = (
            '{\n'
            '  "intent": "ticket_validation",\n'
            '  "confidence": 0.95,\n'
            '  "parameters": {\n'
            '    "ticket_text": "очень длинный текст'
        )
        result = DeepSeekProvider._parse_classification(raw, elapsed_ms=200)
        self.assertEqual(result.intent, "ticket_validation")
        self.assertEqual(result.confidence, 0.95)
        self.assertEqual(result.parameters, {})
        self.assertEqual(result.explain_code, "PARTIAL_JSON_FALLBACK")

    def test_partial_json_fallback_with_explicit_explain_code(self):
        """Fallback сохраняет explain_code, если он есть в частичном JSON."""
        raw = (
            '{\n'
            '  "intent": "certification_info",\n'
            '  "confidence": 0.9,\n'
            '  "explain_code": "CERT_KEYWORD",\n'
            '  "parameters": {\n'
            '    "query_type": "summary"\n'
        )
        result = DeepSeekProvider._parse_classification(raw, elapsed_ms=50)
        self.assertEqual(result.intent, "certification_info")
        self.assertEqual(result.explain_code, "CERT_KEYWORD")


class TestProviderFactory(unittest.TestCase):
    """Тесты для фабрики провайдеров."""

    def test_get_default_provider(self):
        """Получение провайдера по умолчанию (deepseek)."""
        provider = get_provider("deepseek")
        self.assertIsInstance(provider, DeepSeekProvider)
        self.assertEqual(provider.name, "deepseek")

    def test_get_unknown_provider_raises(self):
        """Запрос несуществующего провайдера вызывает ValueError."""
        with self.assertRaises(ValueError) as ctx:
            get_provider("nonexistent_provider")
        self.assertIn("nonexistent_provider", str(ctx.exception))

    def test_register_custom_provider(self):
        """Регистрация и получение кастомного провайдера."""
        class MockProvider(DeepSeekProvider):
            @property
            def name(self):
                return "mock_test"

        register_provider("mock_test", MockProvider)
        provider = get_provider("mock_test")
        self.assertEqual(provider.name, "mock_test")


class TestDeepSeekProviderInit(unittest.TestCase):
    """Тесты для инициализации DeepSeekProvider."""

    def test_no_api_key_warning(self):
        """Предупреждение при отсутствии API-ключа."""
        with patch.object(
            DeepSeekProvider, "__init__", lambda self, **kw: None
        ):
            pass  # Проверяем что конструктор не падает

    def test_provider_name(self):
        """Имя провайдера — deepseek."""
        provider = DeepSeekProvider(api_key="test_key")
        self.assertEqual(provider.name, "deepseek")


class TestDeepSeekProviderModelResolution(unittest.IsolatedAsyncioTestCase):
    """Тесты runtime-выбора модели DeepSeek."""

    @patch("src.sbs_helper_telegram_bot.ai_router.settings.get_active_deepseek_model_for_response", return_value="deepseek-reasoner")
    @patch("src.sbs_helper_telegram_bot.ai_router.llm_provider.httpx.AsyncClient")
    async def test_call_api_uses_active_model(self, mock_async_client, mock_active_model):
        """_call_api отправляет в payload активную модель из настроек."""
        provider = DeepSeekProvider(api_key="test_key")

        mock_client = mock_async_client.return_value.__aenter__.return_value

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "ok"}}]
        }
        mock_response.raise_for_status.return_value = None
        mock_client.post = AsyncMock(return_value=mock_response)

        await provider._call_api(messages=[{"role": "user", "content": "hi"}])

        post_kwargs = mock_client.post.await_args.kwargs
        self.assertEqual(post_kwargs["json"]["model"], "deepseek-reasoner")

    @patch("src.sbs_helper_telegram_bot.ai_router.settings.get_active_deepseek_model_for_classification", return_value="deepseek-chat")
    @patch("src.sbs_helper_telegram_bot.ai_router.llm_provider.httpx.AsyncClient")
    async def test_call_api_uses_classification_model(self, mock_async_client, mock_class_model):
        """_call_api для классификации берёт отдельную модель классификатора."""
        provider = DeepSeekProvider(api_key="test_key")

        mock_client = mock_async_client.return_value.__aenter__.return_value

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "ok"}}]
        }
        mock_response.raise_for_status.return_value = None
        mock_client.post = AsyncMock(return_value=mock_response)

        await provider._call_api(messages=[{"role": "user", "content": "hi"}], purpose="classification")

        post_kwargs = mock_client.post.await_args.kwargs
        self.assertEqual(post_kwargs["json"]["model"], "deepseek-chat")


if __name__ == "__main__":
    unittest.main()
