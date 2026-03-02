"""
test_rag_summary_fallback.py — тесты summary-fallback и JSON-парсинга RAG-ответов.
"""

import json
import unittest
from unittest.mock import AsyncMock, patch

from src.sbs_helper_telegram_bot.ai_router.messages import (
    AI_PROGRESS_STAGE_RAG_AUGMENTED_REQUEST_STARTED,
    AI_PROGRESS_STAGE_RAG_CACHE_HIT,
    AI_PROGRESS_STAGE_RAG_FALLBACK_STARTED,
    AI_PROGRESS_STAGE_RAG_PREFILTER_STARTED,
)
from src.sbs_helper_telegram_bot.ai_router.prompts import (
    build_rag_fallback_prompt,
    build_rag_prompt,
)
from src.sbs_helper_telegram_bot.ai_router.rag_service import (
    RagAnswer,
    RagKnowledgeService,
)


class TestParseRagJsonResponse(unittest.TestCase):
    """Тесты парсинга JSON-ответа RAG LLM."""

    def test_valid_json_answered_true(self):
        """Валидный JSON с question_answered=true."""
        raw = json.dumps({"answer": "SLA 4 часа", "question_answered": True})
        answer, answered = RagKnowledgeService._parse_rag_json_response(raw)
        self.assertEqual(answer, "SLA 4 часа")
        self.assertTrue(answered)

    def test_valid_json_answered_false(self):
        """Валидный JSON с question_answered=false."""
        raw = json.dumps({"answer": "Не найдено", "question_answered": False})
        answer, answered = RagKnowledgeService._parse_rag_json_response(raw)
        self.assertEqual(answer, "Не найдено")
        self.assertFalse(answered)

    def test_markdown_wrapped_json(self):
        """JSON обёрнутый в markdown code fence."""
        inner = json.dumps({"answer": "Ответ по SLA", "question_answered": True})
        raw = f"```json\n{inner}\n```"
        answer, answered = RagKnowledgeService._parse_rag_json_response(raw)
        self.assertEqual(answer, "Ответ по SLA")
        self.assertTrue(answered)

    def test_markdown_wrapped_json_answered_false(self):
        """JSON с question_answered=false обёрнутый в markdown code fence."""
        inner = json.dumps({"answer": "Нет данных", "question_answered": False})
        raw = f"```json\n{inner}\n```"
        answer, answered = RagKnowledgeService._parse_rag_json_response(raw)
        self.assertEqual(answer, "Нет данных")
        self.assertFalse(answered)

    def test_invalid_json_fallback_to_raw(self):
        """Невалидный JSON — fallback к сырому тексту с answered=True."""
        raw = "Это обычный текст, не JSON"
        answer, answered = RagKnowledgeService._parse_rag_json_response(raw)
        self.assertEqual(answer, raw)
        self.assertTrue(answered)

    def test_missing_question_answered_defaults_to_true(self):
        """Отсутствующий question_answered по умолчанию True."""
        raw = json.dumps({"answer": "Ответ без флага"})
        answer, answered = RagKnowledgeService._parse_rag_json_response(raw)
        self.assertEqual(answer, "Ответ без флага")
        self.assertTrue(answered)

    def test_missing_answer_field_uses_raw(self):
        """Отсутствующий answer — используется сырая строка."""
        raw = json.dumps({"question_answered": False})
        answer, answered = RagKnowledgeService._parse_rag_json_response(raw)
        self.assertEqual(answer, raw.strip())
        self.assertFalse(answered)

    def test_empty_string(self):
        """Пустая строка."""
        answer, answered = RagKnowledgeService._parse_rag_json_response("")
        self.assertEqual(answer, "")
        self.assertTrue(answered)

    def test_none_input(self):
        """None на входе."""
        answer, answered = RagKnowledgeService._parse_rag_json_response(None)
        self.assertEqual(answer, "")
        self.assertTrue(answered)

    def test_question_answered_string_false(self):
        """question_answered как строка 'false'."""
        raw = '{"answer": "текст", "question_answered": "false"}'
        answer, answered = RagKnowledgeService._parse_rag_json_response(raw)
        self.assertEqual(answer, "текст")
        self.assertFalse(answered)

    def test_question_answered_string_true(self):
        """question_answered как строка 'true'."""
        raw = '{"answer": "текст", "question_answered": "true"}'
        answer, answered = RagKnowledgeService._parse_rag_json_response(raw)
        self.assertEqual(answer, "текст")
        self.assertTrue(answered)

    def test_embedded_json_object_in_text(self):
        """JSON-объект внутри текста."""
        raw = 'Вот ответ: {"answer": "найден", "question_answered": true} конец'
        answer, answered = RagKnowledgeService._parse_rag_json_response(raw)
        self.assertEqual(answer, "найден")
        self.assertTrue(answered)

    def test_json_with_code_fences_inside_answer(self):
        """JSON-ответ, где поле answer содержит markdown code fences (bash/shell блоки).

        Регрессионный тест: ранее _JSON_CODE_FENCE_RE.search() ломал парсинг,
        подхватывая первый code-fence внутри строки answer и возвращая вместо
        полного JSON только тело bash-блока.
        """
        answer_text = (
            "Установите пакет:\n"
            "```bash\n"
            "sudo apt-get install -y x5-pos-upos-kozen\n"
            "```\n"
            "После установки выполните сверку итогов."
        )
        raw = json.dumps({"answer": answer_text, "question_answered": True})
        answer, answered = RagKnowledgeService._parse_rag_json_response(raw)
        self.assertEqual(answer, answer_text)
        self.assertTrue(answered)

    def test_json_with_multiple_code_fences_inside_answer(self):
        """JSON с несколькими code-fence блоками в поле answer должен парситься корректно."""
        answer_text = (
            "Шаг 1:\n```bash\nsudo apt-get update\n```\n"
            "Шаг 2:\n```bash\nsudo apt-get install x5-pos-upos-kozen\n```"
        )
        raw = json.dumps({"answer": answer_text, "question_answered": True})
        answer, answered = RagKnowledgeService._parse_rag_json_response(raw)
        self.assertEqual(answer, answer_text)
        self.assertTrue(answered)


class TestAnswerQuestionFallback(unittest.IsolatedAsyncioTestCase):
    """Тесты fallback-логики в answer_question."""

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_hyde_enabled", return_value=False)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._get_corpus_version", return_value=3)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._retrieve_context_for_question")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._log_query")
    @patch("src.sbs_helper_telegram_bot.ai_router.llm_provider.get_provider")
    async def test_answer_question_json_mode_answered(
        self,
        mock_get_provider,
        mock_log_query,
        mock_retrieve,
        mock_version,
        _mock_hyde,
    ):
        """Основной RAG-ответ с question_answered=true возвращает RagAnswer(is_fallback=False)."""
        service = RagKnowledgeService(cache_ttl_seconds=300)
        mock_retrieve.return_value = (
            [(1.2, "reglament.txt", "SLA 4 часа", 1)],
            ["[Summary | reglament.txt]\nСводка по SLA"],
        )

        provider = AsyncMock()
        provider.chat.return_value = json.dumps(
            {"answer": "SLA составляет 4 часа", "question_answered": True}
        )
        mock_get_provider.return_value = provider

        result = await service.answer_question("Какой SLA?", user_id=77)

        self.assertIsInstance(result, RagAnswer)
        self.assertEqual(result.text, "SLA составляет 4 часа")
        self.assertFalse(result.is_fallback)
        provider.chat.assert_awaited_once()
        # Проверить, что передан response_format
        call_kwargs = provider.chat.await_args.kwargs
        self.assertEqual(call_kwargs.get("response_format"), {"type": "json_object"})

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_SUMMARY_FALLBACK_ENABLED", True)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_hyde_enabled", return_value=False)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._get_corpus_version", return_value=3)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._retrieve_context_for_question")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._retrieve_summaries_for_fallback")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._log_query")
    @patch("src.sbs_helper_telegram_bot.ai_router.llm_provider.get_provider")
    async def test_answer_question_fallback_triggered(
        self,
        mock_get_provider,
        mock_log_query,
        mock_retrieve_summaries,
        mock_retrieve,
        mock_version,
        _mock_hyde,
    ):
        """Fallback срабатывает когда LLM возвращает question_answered=false."""
        service = RagKnowledgeService(cache_ttl_seconds=300)
        mock_retrieve.return_value = (
            [(0.5, "doc.txt", "Текст чанка", 1)],
            [],
        )
        mock_retrieve_summaries.return_value = [
            "[Summary | overview.pdf]\nОбзор процессов обслуживания",
        ]

        primary_response = json.dumps(
            {"answer": "Не найдено", "question_answered": False}
        )
        fallback_response = "Точной информации нет, но есть связанные данные об обслуживании."

        provider = AsyncMock()
        provider.chat.side_effect = [primary_response, fallback_response]
        mock_get_provider.return_value = provider

        result = await service.answer_question("Расскажи про обслуживание", user_id=88)

        self.assertIsInstance(result, RagAnswer)
        self.assertEqual(result.text, fallback_response)
        self.assertTrue(result.is_fallback)
        # Два вызова chat: основной + fallback
        self.assertEqual(provider.chat.await_count, 2)
        # Первый вызов с JSON mode
        first_call_kwargs = provider.chat.await_args_list[0].kwargs
        self.assertEqual(first_call_kwargs.get("response_format"), {"type": "json_object"})
        self.assertEqual(first_call_kwargs.get("purpose"), "rag_answer")
        # Второй вызов без JSON mode (fallback)
        second_call_kwargs = provider.chat.await_args_list[1].kwargs
        self.assertIsNone(second_call_kwargs.get("response_format"))
        self.assertEqual(second_call_kwargs.get("purpose"), "rag_fallback")

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_SUMMARY_FALLBACK_ENABLED", False)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_hyde_enabled", return_value=False)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._get_corpus_version", return_value=3)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._retrieve_context_for_question")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._log_query")
    @patch("src.sbs_helper_telegram_bot.ai_router.llm_provider.get_provider")
    async def test_answer_question_fallback_disabled_returns_none(
        self,
        mock_get_provider,
        mock_log_query,
        mock_retrieve,
        mock_version,
        _mock_hyde,
    ):
        """С выключенным fallback при question_answered=false возвращается RagAnswer(text=None)."""
        service = RagKnowledgeService(cache_ttl_seconds=300)
        mock_retrieve.return_value = (
            [(0.5, "doc.txt", "Текст чанка", 1)],
            [],
        )

        provider = AsyncMock()
        provider.chat.return_value = json.dumps(
            {"answer": "Не найдено", "question_answered": False}
        )
        mock_get_provider.return_value = provider

        result = await service.answer_question("Неизвестный вопрос", user_id=99)

        self.assertIsInstance(result, RagAnswer)
        self.assertIsNone(result.text)
        self.assertFalse(result.is_fallback)
        # Только один вызов chat (основной, без fallback)
        provider.chat.assert_awaited_once()

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_hyde_enabled", return_value=False)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._get_corpus_version", return_value=3)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._retrieve_context_for_question")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._log_query")
    @patch("src.sbs_helper_telegram_bot.ai_router.llm_provider.get_provider")
    async def test_answer_question_no_fallback_on_answered(
        self,
        mock_get_provider,
        mock_log_query,
        mock_retrieve,
        mock_version,
        _mock_hyde,
    ):
        """При question_answered=true fallback не вызывается."""
        service = RagKnowledgeService(cache_ttl_seconds=300)
        mock_retrieve.return_value = (
            [(1.5, "guide.pdf", "Порядок замены ФН", 2)],
            [],
        )

        provider = AsyncMock()
        provider.chat.return_value = json.dumps(
            {"answer": "Замена ФН выполняется в 3 этапа", "question_answered": True}
        )
        mock_get_provider.return_value = provider

        result = await service.answer_question("Как заменить ФН?", user_id=55)

        self.assertEqual(result.text, "Замена ФН выполняется в 3 этапа")
        self.assertFalse(result.is_fallback)
        provider.chat.assert_awaited_once()

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_SUMMARY_FALLBACK_ENABLED", True)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_hyde_enabled", return_value=False)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._get_corpus_version", return_value=3)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._retrieve_context_for_question")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._retrieve_summaries_for_fallback")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._log_query")
    @patch("src.sbs_helper_telegram_bot.ai_router.llm_provider.get_provider")
    async def test_answer_question_fallback_no_summaries_returns_none(
        self,
        mock_get_provider,
        mock_log_query,
        mock_retrieve_summaries,
        mock_retrieve,
        mock_version,
        _mock_hyde,
    ):
        """Fallback при отсутствии summary возвращает RagAnswer(text=None)."""
        service = RagKnowledgeService(cache_ttl_seconds=300)
        mock_retrieve.return_value = (
            [(0.3, "doc.txt", "Нерелевантный текст", 1)],
            [],
        )
        mock_retrieve_summaries.return_value = []

        provider = AsyncMock()
        provider.chat.return_value = json.dumps(
            {"answer": "Не найдено", "question_answered": False}
        )
        mock_get_provider.return_value = provider

        result = await service.answer_question("Совсем неизвестная тема", user_id=100)

        self.assertIsInstance(result, RagAnswer)
        self.assertIsNone(result.text)
        # Только основной вызов (fallback запросил summary, но не нашёл → нет второго LLM-вызова)
        provider.chat.assert_awaited_once()

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_SUMMARY_FALLBACK_ENABLED", True)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_hyde_enabled", return_value=False)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._get_corpus_version", return_value=3)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._retrieve_context_for_question")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._retrieve_summaries_for_fallback")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._log_query")
    @patch("src.sbs_helper_telegram_bot.ai_router.llm_provider.get_provider")
    async def test_answer_question_zero_chunks_triggers_fallback(
        self,
        mock_get_provider,
        mock_log_query,
        mock_retrieve_summaries,
        mock_retrieve,
        mock_version,
        _mock_hyde,
    ):
        """Nуль чанков (пустой retrieval) сразу переходит к summary-fallback."""
        service = RagKnowledgeService(cache_ttl_seconds=300)
        mock_retrieve.return_value = ([], [])
        mock_retrieve_summaries.return_value = [
            "[Summary | manual.pdf]\nРуководство по эксплуатации оборудования",
        ]

        fallback_answer = "Точных данных нет, но есть руководство по эксплуатации."
        provider = AsyncMock()
        provider.chat.return_value = fallback_answer
        mock_get_provider.return_value = provider

        result = await service.answer_question("Как работает оборудование?", user_id=66)

        self.assertIsInstance(result, RagAnswer)
        self.assertEqual(result.text, fallback_answer)
        self.assertTrue(result.is_fallback)
        # Один вызов — только fallback (нет основного JSON-запроса, т.к. чанков нет)
        provider.chat.assert_awaited_once()
        call_kwargs = provider.chat.await_args.kwargs
        self.assertEqual(call_kwargs.get("purpose"), "rag_fallback")

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_SUMMARY_FALLBACK_ENABLED", True)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_hyde_enabled", return_value=False)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._get_corpus_version", return_value=5)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._retrieve_context_for_question")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._retrieve_summaries_for_fallback")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._log_query")
    @patch("src.sbs_helper_telegram_bot.ai_router.llm_provider.get_provider")
    async def test_fallback_progress_stage_emitted(
        self,
        mock_get_provider,
        mock_log_query,
        mock_retrieve_summaries,
        mock_retrieve,
        mock_version,
        _mock_hyde,
    ):
        """При fallback эмитится прогресс-стадия RAG_FALLBACK_STARTED."""
        service = RagKnowledgeService(cache_ttl_seconds=300)
        mock_retrieve.return_value = (
            [(0.5, "doc.txt", "текст", 1)],
            [],
        )
        mock_retrieve_summaries.return_value = [
            "[Summary | doc.pdf]\nОписание процессов",
        ]

        provider = AsyncMock()
        provider.chat.side_effect = [
            json.dumps({"answer": "нет", "question_answered": False}),
            "Вот обзор процессов...",
        ]
        mock_get_provider.return_value = provider

        progress = AsyncMock()
        result = await service.answer_question("Процессы?", user_id=77, on_progress=progress)

        self.assertTrue(result.is_fallback)
        # Проверить наличие fallback-стадии
        stages = [call.args[0] for call in progress.await_args_list]
        self.assertIn(AI_PROGRESS_STAGE_RAG_PREFILTER_STARTED, stages)
        self.assertIn(AI_PROGRESS_STAGE_RAG_AUGMENTED_REQUEST_STARTED, stages)
        self.assertIn(AI_PROGRESS_STAGE_RAG_FALLBACK_STARTED, stages)

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_hyde_enabled", return_value=False)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._get_corpus_version", return_value=3)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._retrieve_context_for_question")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._log_query")
    @patch("src.sbs_helper_telegram_bot.ai_router.llm_provider.get_provider")
    async def test_answer_question_cache_preserves_fallback_flag(
        self,
        mock_get_provider,
        mock_log_query,
        mock_retrieve,
        mock_version,
        _mock_hyde,
    ):
        """Кэш сохраняет и восстанавливает флаг is_fallback."""
        service = RagKnowledgeService(cache_ttl_seconds=300)
        mock_retrieve.return_value = (
            [(1.5, "doc.txt", "текст", 1)],
            [],
        )

        provider = AsyncMock()
        provider.chat.return_value = json.dumps(
            {"answer": "Тестовый ответ", "question_answered": True}
        )
        mock_get_provider.return_value = provider

        first = await service.answer_question("Тест?", user_id=77)
        self.assertFalse(first.is_fallback)

        # Второй вызов — из кэша
        second = await service.answer_question("Тест?", user_id=77)
        self.assertEqual(second.text, "Тестовый ответ")
        self.assertFalse(second.is_fallback)
        # LLM вызван только один раз
        provider.chat.assert_awaited_once()

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_hyde_enabled", return_value=False)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._get_corpus_version", return_value=3)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._retrieve_context_for_question")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._log_query")
    @patch("src.sbs_helper_telegram_bot.ai_router.llm_provider.get_provider")
    async def test_answer_question_json_parse_failure_treated_as_answered(
        self,
        mock_get_provider,
        mock_log_query,
        mock_retrieve,
        mock_version,
        _mock_hyde,
    ):
        """Если JSON ответ невалиден, он используется как есть с is_fallback=False."""
        service = RagKnowledgeService(cache_ttl_seconds=300)
        mock_retrieve.return_value = (
            [(1.0, "doc.txt", "текст", 1)],
            [],
        )

        provider = AsyncMock()
        raw_text = "Просто текстовый ответ без JSON"
        provider.chat.return_value = raw_text
        mock_get_provider.return_value = provider

        result = await service.answer_question("Вопрос?", user_id=99)

        self.assertEqual(result.text, raw_text)
        self.assertFalse(result.is_fallback)
        provider.chat.assert_awaited_once()


class TestChatResponseFormat(unittest.IsolatedAsyncioTestCase):
    """Тесты передачи response_format через chat()."""

    async def test_chat_forwards_response_format_to_call_api(self):
        """response_format передаётся в _call_api из chat()."""
        from src.sbs_helper_telegram_bot.ai_router.llm_provider import DeepSeekProvider

        provider = DeepSeekProvider(api_key="test_key")
        provider._call_api = AsyncMock(return_value="ok")

        await provider.chat(
            messages=[{"role": "user", "content": "test"}],
            system_prompt="sys",
            purpose="rag_answer",
            response_format={"type": "json_object"},
        )

        call_kwargs = provider._call_api.await_args.kwargs
        self.assertEqual(call_kwargs.get("response_format"), {"type": "json_object"})

    async def test_chat_without_response_format(self):
        """Без response_format _call_api получает None."""
        from src.sbs_helper_telegram_bot.ai_router.llm_provider import DeepSeekProvider

        provider = DeepSeekProvider(api_key="test_key")
        provider._call_api = AsyncMock(return_value="ok")

        await provider.chat(
            messages=[{"role": "user", "content": "test"}],
            system_prompt="sys",
        )

        call_kwargs = provider._call_api.await_args.kwargs
        self.assertIsNone(call_kwargs.get("response_format"))


class TestBuildRagFallbackPrompt(unittest.TestCase):
    """Тесты промпта для summary fallback."""

    def test_contains_summary_blocks(self):
        """Fallback-промпт содержит summary-блоки."""
        blocks = [
            "[Summary | doc1.pdf]\nОписание процесса A",
            "[Summary | doc2.pdf]\nОписание процесса B",
        ]
        prompt = build_rag_fallback_prompt(blocks)
        self.assertIn("Описание процесса A", prompt)
        self.assertIn("Описание процесса B", prompt)

    def test_contains_fallback_instructions(self):
        """Fallback-промпт содержит инструкции о честном признании."""
        prompt = build_rag_fallback_prompt(["[Summary | doc.pdf]\nТекст"])
        self.assertIn("точная информация", prompt.lower())

    def test_no_markdown_rule(self):
        """Fallback-промпт запрещает Markdown."""
        prompt = build_rag_fallback_prompt(["[Summary | doc.pdf]\nТекст"])
        self.assertIn("Markdown", prompt)


class TestBuildRagPromptJsonInstructions(unittest.TestCase):
    """Тесты обновлённого RAG-промпта с JSON-инструкциями."""

    def test_contains_json_format_instruction(self):
        """RAG-промпт содержит инструкцию возвращать JSON."""
        prompt = build_rag_prompt(["[Блок 1 | doc.txt]\nТекст"])
        self.assertIn("question_answered", prompt)
        self.assertIn("answer", prompt)
        self.assertIn("JSON", prompt)

    def test_contains_context_blocks(self):
        """RAG-промпт содержит контекстные блоки."""
        prompt = build_rag_prompt(["[Блок 1 | doc.txt]\nТекст чанка"])
        self.assertIn("Текст чанка", prompt)

    def test_contains_summary_blocks(self):
        """RAG-промпт содержит summary если переданы."""
        prompt = build_rag_prompt(
            ["[Блок 1 | doc.txt]\nТекст"],
            summary_blocks=["[Summary | doc.txt]\nСводка"],
        )
        self.assertIn("Сводка", prompt)


class TestRagAnswerDataclass(unittest.TestCase):
    """Тесты dataclass RagAnswer."""

    def test_defaults(self):
        """По умолчанию is_fallback=False."""
        answer = RagAnswer(text="test")
        self.assertEqual(answer.text, "test")
        self.assertFalse(answer.is_fallback)

    def test_none_text(self):
        """text может быть None."""
        answer = RagAnswer(text=None)
        self.assertIsNone(answer.text)
        self.assertFalse(answer.is_fallback)

    def test_fallback_flag(self):
        """is_fallback=True для fallback-ответов."""
        answer = RagAnswer(text="обзор", is_fallback=True)
        self.assertEqual(answer.text, "обзор")
        self.assertTrue(answer.is_fallback)

    def test_truthiness_with_text(self):
        """RagAnswer с текстом truthy (text проверяется отдельно)."""
        answer = RagAnswer(text="ответ")
        self.assertIsNotNone(answer.text)

    def test_truthiness_without_text(self):
        """RagAnswer без текста: text is None."""
        answer = RagAnswer(text=None)
        self.assertIsNone(answer.text)
