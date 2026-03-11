"""
test_llm_provider.py — тесты для LLM-провайдера и парсинга результатов.
"""
import json
import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import httpx

from src.core.ai.llm_provider import (
    ClassificationResult,
    DeepSeekProvider,
    GigaChatProvider,
    LLMProviderTemporaryError,
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
        """Длинный не-JSON ответ больше не трактуется как direct-text fallback."""
        raw = (
            "📚 Ответ по базе знаний. Для прошивки D200 подготовьте флешку FAT32, "
            "скопируйте файл обновления, зайдите в сервисное меню и запустите обновление."
        )
        result = DeepSeekProvider._parse_classification(raw, elapsed_ms=180)
        self.assertEqual(result.intent, "unknown")
        self.assertEqual(result.explain_code, "NO_JSON_IN_RESPONSE")

    def test_invalid_intent_becomes_unknown(self):
        """Неподдерживаемый intent приводится к unknown."""
        raw = json.dumps({
            "intent": "some_random_intent",
            "confidence": 0.99,
            "parameters": {"x": 1},
            "explain_code": "PARSED_OK",
        })
        result = DeepSeekProvider._parse_classification(raw, elapsed_ms=25)
        self.assertEqual(result.intent, "unknown")
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.explain_code, "INVALID_INTENT")

    def test_invalid_json(self):
        """Невалидный JSON с intent обрабатывается partial fallback."""
        raw = 'some text {"intent": "test", broken} and more'
        result = DeepSeekProvider._parse_classification(raw, elapsed_ms=100)
        self.assertEqual(result.intent, "test")
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.explain_code, "PARTIAL_JSON_FALLBACK")

    def test_json_parse_fail_without_intent_or_direct_text(self):
        """Невалидный JSON без intent и без длинного текста даёт JSON_PARSE_FAIL."""
        raw = "результат {broken: true, value: }"
        result = DeepSeekProvider._parse_classification(raw, elapsed_ms=70)
        self.assertEqual(result.intent, "unknown")
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.explain_code, "JSON_PARSE_FAIL")

    def test_confidence_clamped_to_range(self):
        """Confidence ограничивается диапазоном [0, 1]."""
        raw_high = json.dumps({"intent": "general_chat", "confidence": 1.5})
        result_high = DeepSeekProvider._parse_classification(raw_high, elapsed_ms=0)
        self.assertEqual(result_high.confidence, 1.0)

        raw_low = json.dumps({"intent": "general_chat", "confidence": -0.5})
        result_low = DeepSeekProvider._parse_classification(raw_low, elapsed_ms=0)
        self.assertEqual(result_low.confidence, 0.0)

    def test_missing_fields_use_defaults(self):
        """Отсутствующие поля заполняются defaults."""
        raw = json.dumps({"intent": "general_chat"})
        result = DeepSeekProvider._parse_classification(raw, elapsed_ms=0)
        self.assertEqual(result.intent, "general_chat")
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.parameters, {})
        self.assertEqual(result.explain_code, "PARSED_OK")

    def test_non_dict_parameters_converted(self):
        """Нестандартный тип parameters заменяется на пустой dict."""
        raw = json.dumps({"intent": "general_chat", "confidence": 0.8, "parameters": "not a dict"})
        result = DeepSeekProvider._parse_classification(raw, elapsed_ms=0)
        self.assertEqual(result.parameters, {})

    def test_partial_json_fallback_for_truncated_response(self):
        """Частичный JSON без закрывающей скобки парсится через fallback."""
        raw = (
            '{\n'
            '  "intent": "ticket_soos",\n'
            '  "confidence": 0.95,\n'
            '  "parameters": {\n'
            '    "ticket_text": "очень длинный текст'
        )
        result = DeepSeekProvider._parse_classification(raw, elapsed_ms=200)
        self.assertEqual(result.intent, "ticket_soos")
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


class TestGigaChatProviderHelpers(unittest.TestCase):
    """Тесты вспомогательных методов GigaChatProvider."""

    def test_extract_uploaded_file_id_from_id(self):
        """Идентификатор берётся из поля id."""
        uploaded = MagicMock()
        uploaded.id = "file-123"
        uploaded.id_ = None

        result = GigaChatProvider._extract_uploaded_file_id(uploaded)
        self.assertEqual(result, "file-123")

    def test_extract_uploaded_file_id_from_id_underscore(self):
        """Идентификатор берётся из поля id_ для текущей версии SDK."""
        uploaded = MagicMock()
        uploaded.id = None
        uploaded.id_ = "file-456"

        result = GigaChatProvider._extract_uploaded_file_id(uploaded)
        self.assertEqual(result, "file-456")

    def test_extract_uploaded_file_id_from_model_dump(self):
        """Идентификатор берётся из model_dump(), если прямого атрибута нет."""
        uploaded = MagicMock()
        uploaded.id = None
        uploaded.id_ = None
        uploaded.model_dump.return_value = {"id_": "file-789"}

        result = GigaChatProvider._extract_uploaded_file_id(uploaded)
        self.assertEqual(result, "file-789")


class TestDeepSeekProviderModelResolution(unittest.IsolatedAsyncioTestCase):
    """Тесты runtime-выбора модели DeepSeek."""

    @patch("config.ai_settings.get_active_deepseek_model_for_response", return_value="deepseek-reasoner")
    @patch("src.core.ai.llm_provider.httpx.AsyncClient")
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

    @patch("src.core.ai.llm_provider.logger.info")
    @patch("src.core.ai.llm_provider.ai_settings.AI_LOG_MODEL_IO", True)
    @patch("src.core.ai.llm_provider.httpx.AsyncClient")
    async def test_call_api_logs_prompt_and_raw_response(self, mock_async_client, mock_logger_info):
        """При включённом флаге логируются prompt payload и сырой ответ модели."""
        provider = DeepSeekProvider(api_key="test_key")

        mock_client = mock_async_client.return_value.__aenter__.return_value
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "raw model response"}}]
        }
        mock_response.raise_for_status.return_value = None
        mock_client.post = AsyncMock(return_value=mock_response)

        await provider._call_api(messages=[{"role": "user", "content": "hi"}], purpose="response")

        logged_messages = [call.args[0] for call in mock_logger_info.call_args_list if call.args]
        self.assertTrue(any("LLM request payload:" in msg for msg in logged_messages))
        self.assertTrue(any("LLM raw response:" in msg for msg in logged_messages))

    @patch("config.ai_settings.get_active_deepseek_model_for_classification", return_value="deepseek-chat")
    @patch("src.core.ai.llm_provider.httpx.AsyncClient")
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

    @patch("config.ai_settings.get_active_deepseek_model_for_response", return_value="deepseek-chat")
    @patch("src.core.ai.llm_provider.httpx.AsyncClient")
    async def test_chat_uses_model_override_when_provided(self, mock_async_client, mock_response_model):
        """chat использует model_override для конкретного вызова."""
        provider = DeepSeekProvider(api_key="test_key")

        mock_client = mock_async_client.return_value.__aenter__.return_value
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "ok"}}]
        }
        mock_response.raise_for_status.return_value = None
        mock_client.post = AsyncMock(return_value=mock_response)

        result = await provider.chat(
            messages=[{"role": "user", "content": "hi"}],
            system_prompt="system",
            purpose="rag_summary",
            model_override="deepseek-reasoner",
        )

        self.assertEqual(result, "ok")
        post_kwargs = mock_client.post.await_args.kwargs
        self.assertEqual(post_kwargs["json"]["model"], "deepseek-reasoner")

    async def test_classify_uses_generation_params_from_settings(self):
        """classify использует temperature/max_tokens из ai_router.settings."""
        provider = DeepSeekProvider(api_key="test_key")
        provider._call_api = AsyncMock(return_value='{"intent":"general_chat","confidence":0.9}')

        with patch(
            "src.core.ai.llm_provider.ai_settings.LLM_CLASSIFICATION_TEMPERATURE",
            0.25,
        ), patch(
            "src.core.ai.llm_provider.ai_settings.LLM_CLASSIFICATION_MAX_TOKENS",
            2048,
        ):
            result = await provider.classify(
                messages=[{"role": "user", "content": "hi"}],
                system_prompt="system",
                user_id=42,
            )

        self.assertEqual(result.intent, "general_chat")
        call_kwargs = provider._call_api.await_args.kwargs
        self.assertEqual(call_kwargs["temperature"], 0.25)
        self.assertEqual(call_kwargs["max_tokens"], 2048)
        self.assertEqual(call_kwargs["response_format"], {"type": "json_object"})

    async def test_chat_uses_generation_params_from_settings(self):
        """chat использует temperature/max_tokens из ai_router.settings."""
        provider = DeepSeekProvider(api_key="test_key")
        provider._call_api = AsyncMock(return_value="ok")

        with patch(
            "src.core.ai.llm_provider.ai_settings.LLM_CHAT_TEMPERATURE",
            0.55,
        ), patch(
            "src.core.ai.llm_provider.ai_settings.LLM_CHAT_MAX_TOKENS",
            1536,
        ):
            result = await provider.chat(
                messages=[{"role": "user", "content": "hi"}],
                system_prompt="system",
                purpose="response",
            )

        self.assertEqual(result, "ok")
        call_kwargs = provider._call_api.await_args.kwargs
        self.assertEqual(call_kwargs["temperature"], 0.55)
        self.assertEqual(call_kwargs["max_tokens"], 1536)

    async def test_chat_uses_temperature_override_when_provided(self):
        """chat использует temperature_override для конкретного вызова."""
        provider = DeepSeekProvider(api_key="test_key")
        provider._call_api = AsyncMock(return_value="ok")

        with patch(
            "src.core.ai.llm_provider.ai_settings.LLM_CHAT_TEMPERATURE",
            0.55,
        ):
            result = await provider.chat(
                messages=[{"role": "user", "content": "hi"}],
                system_prompt="system",
                purpose="response",
                temperature_override=0.23,
            )

        self.assertEqual(result, "ok")
        call_kwargs = provider._call_api.await_args.kwargs
        self.assertEqual(call_kwargs["temperature"], 0.23)

    async def test_chat_prompt_tester_with_model_override_disables_fallback_and_uses_extra_retries(self):
        """Prompt tester с model_override не включает fallback и увеличивает число retry."""
        provider = DeepSeekProvider(api_key="test_key")
        provider._call_api = AsyncMock(return_value="ok")

        result = await provider.chat(
            messages=[{"role": "user", "content": "hi"}],
            system_prompt="system",
            purpose="gk_prompt_tester",
            model_override="deepseek-reasoner",
            allow_model_fallback=False,
        )

        self.assertEqual(result, "ok")
        call_kwargs = provider._call_api.await_args.kwargs
        self.assertEqual(call_kwargs["allow_empty_content_retry"], False)
        self.assertEqual(call_kwargs["max_attempts"], 4)

    @patch("config.ai_settings.get_active_deepseek_model_for_response", return_value="deepseek-reasoner")
    @patch("src.core.ai.llm_provider.httpx.AsyncClient")
    async def test_call_api_retries_with_chat_model_on_empty_reasoner_content(
        self,
        mock_async_client,
        mock_response_model,
    ):
        """При пустом ответе reasoner выполняется автоповтор на deepseek-chat."""
        provider = DeepSeekProvider(api_key="test_key")

        mock_client = mock_async_client.return_value.__aenter__.return_value

        first_response = MagicMock()
        first_response.json.return_value = {
            "choices": [{"message": {"content": ""}}]
        }
        first_response.raise_for_status.return_value = None

        second_response = MagicMock()
        second_response.json.return_value = {
            "choices": [{"message": {"content": "fallback answer"}}]
        }
        second_response.raise_for_status.return_value = None

        mock_client.post = AsyncMock(side_effect=[first_response, second_response])

        result = await provider._call_api(
            messages=[{"role": "user", "content": "hi"}],
            purpose="rag_answer",
        )

        self.assertEqual(result, "fallback answer")
        self.assertEqual(mock_client.post.await_count, 2)

        first_call_kwargs = mock_client.post.await_args_list[0].kwargs
        second_call_kwargs = mock_client.post.await_args_list[1].kwargs
        self.assertEqual(first_call_kwargs["json"]["model"], "deepseek-reasoner")
        self.assertEqual(second_call_kwargs["json"]["model"], "deepseek-chat")

    @patch("src.core.ai.llm_provider.httpx.AsyncClient")
    async def test_call_api_retries_once_on_timeout_and_succeeds(self, mock_async_client):
        """При таймауте выполняется один повтор, и успешный второй ответ возвращается."""
        provider = DeepSeekProvider(api_key="test_key", model="deepseek-chat")

        mock_client = mock_async_client.return_value.__aenter__.return_value

        success_response = MagicMock()
        success_response.json.return_value = {
            "choices": [{"message": {"content": "ok after retry"}}]
        }
        success_response.raise_for_status.return_value = None

        mock_client.post = AsyncMock(
            side_effect=[
                httpx.ReadTimeout(""),
                success_response,
            ]
        )

        result = await provider._call_api(messages=[{"role": "user", "content": "hi"}], purpose="chat")

        self.assertEqual(result, "ok after retry")
        self.assertEqual(mock_client.post.await_count, 2)

    @patch("src.core.ai.llm_provider.httpx.AsyncClient")
    async def test_call_api_timeout_raises_temporary_error_after_retry(self, mock_async_client):
        """После всех попыток (max_attempts=2) _call_api выбрасывает LLMProviderTemporaryError."""
        provider = DeepSeekProvider(api_key="test_key", model="deepseek-chat")

        mock_client = mock_async_client.return_value.__aenter__.return_value
        mock_client.post = AsyncMock(side_effect=httpx.ReadTimeout(""))

        with self.assertRaises(LLMProviderTemporaryError):
            await provider._call_api(messages=[{"role": "user", "content": "hi"}], purpose="chat")

        self.assertEqual(mock_client.post.await_count, 2)

    @patch("src.core.ai.llm_provider.httpx.AsyncClient")
    async def test_call_api_supports_structured_list_content(self, mock_async_client):
        """_call_api корректно извлекает текст из content в list-формате."""
        provider = DeepSeekProvider(api_key="test_key", model="deepseek-chat")

        mock_client = mock_async_client.return_value.__aenter__.return_value
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": [
                            {"type": "text", "text": "Первая строка"},
                            {"type": "text", "text": "Вторая строка"},
                        ]
                    }
                }
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_client.post = AsyncMock(return_value=mock_response)

        result = await provider._call_api(messages=[{"role": "user", "content": "hi"}], purpose="chat")

        self.assertEqual(result, "Первая строка\nВторая строка")

    @patch("src.core.ai.llm_provider.logger.warning")
    @patch("src.core.ai.llm_provider.ai_settings.AI_MODEL_IO_DB_LOG_ENABLED", True)
    @patch("src.core.ai.llm_provider.database.get_cursor")
    @patch("src.core.ai.llm_provider.database.get_db_connection")
    @patch("src.core.ai.llm_provider.httpx.AsyncClient")
    async def test_call_api_logs_and_persists_empty_content_diagnostics_without_retry(
        self,
        mock_async_client,
        mock_get_db_connection,
        mock_get_cursor,
        mock_logger_warning,
    ):
        """Пустой content логируется с диагностикой и пишется в БД как empty_content без fallback."""
        import asyncio

        provider = DeepSeekProvider(api_key="test_key", model="deepseek-chat")

        mock_client = mock_async_client.return_value.__aenter__.return_value
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "resp-empty-1",
            "usage": {"prompt_tokens": 11, "completion_tokens": 0, "total_tokens": 11},
            "choices": [
                {
                    "finish_reason": "length",
                    "message": {
                        "content": "   ",
                        "reasoning_content": "some reasoning",
                        "refusal": None,
                        "tool_calls": [{"id": "tool-1"}],
                    },
                }
            ],
        }
        mock_response.raise_for_status.return_value = None
        mock_response.elapsed.total_seconds.return_value = 0.12
        mock_client.post = AsyncMock(return_value=mock_response)

        mock_conn = mock_get_db_connection.return_value.__enter__.return_value
        self.assertIsNotNone(mock_conn)
        mock_cursor = mock_get_cursor.return_value.__enter__.return_value

        result = await provider._call_api(
            messages=[{"role": "user", "content": "hi"}],
            purpose="chat",
            allow_empty_content_retry=False,
        )

        self.assertEqual(result, "   ")

        await asyncio.sleep(0.1)

        self.assertTrue(mock_cursor.execute.called)
        sql_params = mock_cursor.execute.call_args.args[1]
        self.assertEqual(sql_params[7], "empty_content")
        self.assertIn('"finish_reason": "length"', sql_params[6])
        self.assertIn('"response_id": "resp-empty-1"', sql_params[6])

        empty_warnings = [
            call for call in mock_logger_warning.call_args_list
            if call.args and "DeepSeek returned empty content" in call.args[0]
        ]
        self.assertTrue(empty_warnings)
        diagnostics_payload = empty_warnings[0].args[3]
        self.assertIn('"finish_reason": "length"', diagnostics_payload)

    @patch("src.core.ai.llm_provider.ai_settings.AI_MODEL_IO_DB_LOG_ENABLED", True)
    @patch("src.core.ai.llm_provider.database.get_cursor")
    @patch("src.core.ai.llm_provider.database.get_db_connection")
    @patch("src.core.ai.llm_provider.httpx.AsyncClient")
    async def test_call_api_stores_masked_full_text_in_db(
        self,
        mock_async_client,
        mock_get_db_connection,
        mock_get_cursor,
    ):
        """Полные request/response сохраняются в БД с маскировкой PII."""
        import asyncio
        provider = DeepSeekProvider(api_key="test_key")

        mock_client = mock_async_client.return_value.__aenter__.return_value
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "email admin@test.ru phone +7 (999) 111-22-33"}}]
        }
        mock_response.raise_for_status.return_value = None
        mock_response.elapsed.total_seconds.return_value = 0.25
        mock_client.post = AsyncMock(return_value=mock_response)

        mock_conn = mock_get_db_connection.return_value.__enter__.return_value
        self.assertIsNotNone(mock_conn)
        mock_cursor = mock_get_cursor.return_value.__enter__.return_value

        await provider._call_api(
            messages=[{"role": "user", "content": "мой email admin@test.ru и телефон +7 (999) 111-22-33"}],
            purpose="chat",
            user_id=77,
        )

        # Дождаться завершения background-задач (fire-and-forget логирование)
        await asyncio.sleep(0.1)

        self.assertTrue(mock_cursor.execute.called)
        sql_params = mock_cursor.execute.call_args.args[1]
        self.assertEqual(sql_params[0], 77)
        self.assertEqual(sql_params[3], "chat")
        self.assertIn("[EMAIL_REDACTED]", sql_params[4])
        self.assertIn("[PHONE_REDACTED]", sql_params[4])
        self.assertNotIn("admin@test.ru", sql_params[4])
        self.assertNotIn("111-22-33", sql_params[4])

    @patch("src.core.ai.llm_provider.ai_settings.AI_MODEL_IO_DB_LOG_ENABLED", True)
    @patch("src.core.ai.llm_provider.database.get_db_connection", side_effect=Exception("db down"))
    @patch("src.core.ai.llm_provider.httpx.AsyncClient")
    async def test_call_api_db_log_failure_does_not_break_response(
        self,
        mock_async_client,
        mock_get_db_connection,
    ):
        """Ошибка записи full-text лога в БД не должна ломать основной ответ."""
        import asyncio
        provider = DeepSeekProvider(api_key="test_key", model="deepseek-chat")

        mock_client = mock_async_client.return_value.__aenter__.return_value
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "ok"}}]
        }
        mock_response.raise_for_status.return_value = None
        mock_client.post = AsyncMock(return_value=mock_response)

        result = await provider._call_api(messages=[{"role": "user", "content": "hi"}], purpose="chat")

        self.assertEqual(result, "ok")
        # Дождаться завершения background-задач (fire-and-forget логирование)
        await asyncio.sleep(0.1)
        self.assertTrue(mock_get_db_connection.called)

    @patch("src.core.ai.llm_provider.logger.exception")
    async def test_chat_logs_exception_type_for_empty_message(self, mock_logger_exception):
        """При пустом тексте исключения лог содержит тип ошибки и traceback."""
        provider = DeepSeekProvider(api_key="test_key")

        empty_exc = Exception()
        provider._call_api = AsyncMock(side_effect=empty_exc)

        with self.assertRaises(Exception):
            await provider.chat(
                messages=[{"role": "user", "content": "hi"}],
                system_prompt="sys",
                user_id=123,
                purpose="chat",
            )

        mock_logger_exception.assert_called_once()
        log_args = mock_logger_exception.call_args.args
        self.assertIn("DeepSeek chat error", log_args[0])
        self.assertEqual(log_args[1], "Exception")
        self.assertIs(log_args[2], empty_exc)


if __name__ == "__main__":
    unittest.main()
