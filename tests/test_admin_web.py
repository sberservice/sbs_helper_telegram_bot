"""
test_admin_web.py — тесты веб-платформы SBS Archie Admin.

Покрывает:
- Модели RBAC (WebUser, WebRole, ModulePermission)
- Аутентификацию Telegram Login Widget (HMAC-верификацию)
- Конвертацию строк БД в Pydantic-модели
"""
import hashlib
import hmac
import asyncio
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from admin_web.core.models import (
    ChainMessage,
    ExpertValidationRequest,
    ExpertValidationStats,
    ExpertVerdict,
    ModulePermission,
    QAPairDetail,
    QAPairListResponse,
    TelegramAuthData,
    WebRole,
    WebUser,
)

# Предзагрузка модуля auth (нужно для @patch)
try:
    import admin_web.core.auth as _auth_module
    _HAS_AUTH = True
except ImportError:
    _HAS_AUTH = False

# Проверка наличия fastapi
try:
    __import__("fastapi")
    _HAS_FASTAPI = True
except ImportError:
    _HAS_FASTAPI = False


def _run_async(coro):
    """Запустить coroutine в изолированном event loop."""
    return asyncio.run(coro)


class TestWebUserPermissions(unittest.TestCase):
    """Тесты проверки прав доступа через WebUser."""

    def test_super_admin_has_all_permissions(self):
        """super_admin имеет полный доступ к любому модулю."""
        user = WebUser(
            telegram_id=123,
            role=WebRole.SUPER_ADMIN,
            permissions=[],
        )
        self.assertTrue(user.has_permission("expert_validation", "view"))
        self.assertTrue(user.has_permission("expert_validation", "edit"))
        self.assertTrue(user.has_permission("prompt_tester", "view"))
        self.assertTrue(user.has_permission("unknown_module", "edit"))

    def test_viewer_can_view_assigned_module(self):
        """viewer может просматривать назначенные модули."""
        user = WebUser(
            telegram_id=456,
            role=WebRole.VIEWER,
            permissions=[
                ModulePermission(
                    module_key="expert_validation",
                    can_view=True,
                    can_edit=False,
                ),
            ],
        )
        self.assertTrue(user.has_permission("expert_validation", "view"))
        self.assertFalse(user.has_permission("expert_validation", "edit"))

    def test_viewer_cannot_access_unassigned_module(self):
        """viewer не может видеть незакреплённый модуль."""
        user = WebUser(
            telegram_id=789,
            role=WebRole.VIEWER,
            permissions=[],
        )
        self.assertFalse(user.has_permission("expert_validation", "view"))
        self.assertFalse(user.has_permission("prompt_tester", "view"))

    def test_expert_can_edit_assigned_module(self):
        """expert может редактировать назначенный модуль."""
        user = WebUser(
            telegram_id=111,
            role=WebRole.EXPERT,
            permissions=[
                ModulePermission(
                    module_key="expert_validation",
                    can_view=True,
                    can_edit=True,
                ),
            ],
        )
        self.assertTrue(user.has_permission("expert_validation", "view"))
        self.assertTrue(user.has_permission("expert_validation", "edit"))

    def test_display_name_full(self):
        """Составление display_name при наличии имени и фамилии."""
        user = WebUser(
            telegram_id=1,
            telegram_first_name="Ivan",
            telegram_last_name="Petrov",
            role=WebRole.VIEWER,
        )
        self.assertEqual(user.display_name, "Ivan Petrov")

    def test_display_name_username_fallback(self):
        """Фолбэк display_name к username."""
        user = WebUser(
            telegram_id=1,
            telegram_username="ivanpetrov",
            role=WebRole.VIEWER,
        )
        self.assertEqual(user.display_name, "@ivanpetrov")

    def test_display_name_id_fallback(self):
        """Фолбэк display_name к telegram_id."""
        user = WebUser(telegram_id=99999, role=WebRole.VIEWER)
        self.assertEqual(user.display_name, "99999")


class TestWebRoleEnum(unittest.TestCase):
    """Тесты перечисления ролей."""

    def test_all_roles_exist(self):
        """Все необходимые роли определены."""
        roles = [r.value for r in WebRole]
        self.assertIn("super_admin", roles)
        self.assertIn("admin", roles)
        self.assertIn("expert", roles)
        self.assertIn("viewer", roles)

    def test_role_from_string(self):
        """Конвертация строки в роль."""
        self.assertEqual(WebRole("super_admin"), WebRole.SUPER_ADMIN)
        self.assertEqual(WebRole("expert"), WebRole.EXPERT)


class TestTelegramAuthVerification(unittest.TestCase):
    """Тесты верификации HMAC от Telegram Login Widget."""

    _BOT_TOKEN = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"

    def _make_valid_auth_data(self) -> TelegramAuthData:
        """Создать валидные данные аутентификации с корректным хешем."""
        auth_date = int(time.time())
        fields = {
            "id": "42",
            "first_name": "Test",
            "auth_date": str(auth_date),
        }
        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(fields.items())
        )
        secret_key = hashlib.sha256(self._BOT_TOKEN.encode()).digest()
        hash_val = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256,
        ).hexdigest()

        return TelegramAuthData(
            id=42,
            first_name="Test",
            auth_date=auth_date,
            hash=hash_val,
        )

    @unittest.skipUnless(_HAS_AUTH, "admin_web.core.auth не загружен")
    def test_valid_hmac_accepted(self):
        """Корректный HMAC-хеш проходит верификацию."""
        with patch.object(_auth_module, "_get_bot_token", return_value=self._BOT_TOKEN):
            data = self._make_valid_auth_data()
            self.assertTrue(_auth_module.verify_telegram_auth(data))

    @unittest.skipUnless(_HAS_AUTH, "admin_web.core.auth не загружен")
    def test_invalid_hmac_rejected(self):
        """Неверный HMAC-хеш отклоняется."""
        with patch.object(_auth_module, "_get_bot_token", return_value=self._BOT_TOKEN):
            data = TelegramAuthData(
                id=42,
                first_name="Test",
                auth_date=int(time.time()),
                hash="invalid_hash_value",
            )
            self.assertFalse(_auth_module.verify_telegram_auth(data))

    @unittest.skipUnless(_HAS_AUTH, "admin_web.core.auth не загружен")
    def test_expired_auth_rejected(self):
        """Истёкшие данные аутентификации отклоняются."""
        with patch.object(_auth_module, "_get_bot_token", return_value=self._BOT_TOKEN):
            data = TelegramAuthData(
                id=42,
                first_name="Test",
                auth_date=int(time.time()) - 100_000,  # Истёк
                hash="irrelevant",
            )
            self.assertFalse(_auth_module.verify_telegram_auth(data))

    @unittest.skipUnless(_HAS_AUTH, "admin_web.core.auth не загружен")
    def test_different_token_rejected(self):
        """HMAC с другим bot token отклоняется."""
        # Хеш рассчитан для _BOT_TOKEN, но верификация идёт с другим
        data = self._make_valid_auth_data()
        with patch.object(_auth_module, "_get_bot_token", return_value="999999:WRONG-TOKEN"):
            self.assertFalse(_auth_module.verify_telegram_auth(data))


class TestPasswordAuthUtilities(unittest.TestCase):
    """Тесты утилит password-аутентификации."""

    @unittest.skipUnless(_HAS_AUTH, "admin_web.core.auth не загружен")
    def test_password_policy_rejects_short_password(self):
        """Короткий пароль не проходит policy."""
        msg = _auth_module.validate_password_policy("Ab1!")
        self.assertIsNotNone(msg)

    @unittest.skipUnless(_HAS_AUTH, "admin_web.core.auth не загружен")
    def test_password_policy_requires_digit(self):
        """Пароль без цифры не проходит policy."""
        msg = _auth_module.validate_password_policy("Abcdef!ghi")
        self.assertIsNotNone(msg)

    @unittest.skipUnless(_HAS_AUTH, "admin_web.core.auth не загружен")
    def test_password_policy_accepts_strong_password(self):
        """Сложный пароль проходит policy."""
        msg = _auth_module.validate_password_policy("StrongPass1!")
        self.assertIsNone(msg)

    def test_password_hash_roundtrip(self):
        """Пароль корректно хешируется и проверяется."""
        from admin_web.core import db as web_db

        hashed = web_db.hash_password("StrongPass1!")
        self.assertTrue(hashed.startswith("pbkdf2_sha256$"))
        self.assertTrue(web_db.verify_password("StrongPass1!", hashed))
        self.assertFalse(web_db.verify_password("WrongPass1!", hashed))


class TestExpertValidationModels(unittest.TestCase):
    """Тесты Pydantic-моделей экспертной валидации."""

    def test_expert_verdict_enum(self):
        """Все вердикты определены."""
        self.assertEqual(ExpertVerdict.APPROVED.value, "approved")
        self.assertEqual(ExpertVerdict.REJECTED.value, "rejected")
        self.assertEqual(ExpertVerdict.SKIPPED.value, "skipped")

    def test_validation_request_valid(self):
        """Корректный запрос валидации создаётся."""
        req = ExpertValidationRequest(
            qa_pair_id=42,
            verdict=ExpertVerdict.APPROVED,
            comment="Хороший ответ",
        )
        self.assertEqual(req.qa_pair_id, 42)
        self.assertEqual(req.verdict, ExpertVerdict.APPROVED)
        self.assertEqual(req.comment, "Хороший ответ")

    def test_validation_request_optional_comment(self):
        """Комментарий необязателен в запросе валидации."""
        req = ExpertValidationRequest(
            qa_pair_id=1,
            verdict=ExpertVerdict.REJECTED,
        )
        self.assertIsNone(req.comment)

    def test_chain_message_defaults(self):
        """Значения по умолчанию в ChainMessage."""
        msg = ChainMessage(telegram_message_id=100)
        self.assertFalse(msg.has_image)
        self.assertIsNone(msg.sender_name)
        self.assertEqual(msg.message_date, 0)
        self.assertIsNone(msg.is_question)

    def test_qa_pair_detail_chain_default(self):
        """chain_messages по умолчанию пустой список."""
        pair = QAPairDetail(
            id=1,
            question_text="Как?",
            answer_text="Так.",
        )
        self.assertEqual(pair.chain_messages, [])
        self.assertIsNone(pair.existing_verdict)
        self.assertIsNone(pair.llm_request_payload)

    def test_stats_model(self):
        """Модель статистики с значениями по умолчанию."""
        stats = ExpertValidationStats()
        self.assertEqual(stats.total_pairs, 0)
        self.assertEqual(stats.approval_rate, 0.0)

    def test_list_response_model(self):
        """Модель ответа списка пар."""
        resp = QAPairListResponse(
            pairs=[],
            total=0,
            page=1,
            page_size=20,
            stats=ExpertValidationStats(),
        )
        self.assertEqual(resp.total, 0)
        self.assertEqual(resp.page, 1)


@unittest.skipUnless(_HAS_FASTAPI, "FastAPI не установлен")
class TestWebModuleBase(unittest.TestCase):
    """Тесты абстрактной базы модуля."""

    def test_api_prefix_generation(self):
        """API prefix генерируется из ключа модуля."""
        from admin_web.modules.base import WebModule

        class TestModule(WebModule):
            @property
            def key(self) -> str:
                return "test_module"

            @property
            def name(self) -> str:
                return "Test Module"

            def get_router(self):
                from fastapi import APIRouter
                return APIRouter()

        mod = TestModule()
        self.assertEqual(mod.api_prefix, "/api/test-module")
        self.assertEqual(mod.icon, "📦")
        self.assertEqual(mod.order, 100)


@unittest.skipUnless(_HAS_FASTAPI, "FastAPI не установлен")
class TestExpertValidationModule(unittest.TestCase):
    """Тесты свойств модуля экспертной валидации (обратная совместимость)."""

    def test_module_properties(self):
        """Свойства модуля заданы корректно."""
        from admin_web.modules.expert_validation.router import ExpertValidationModule

        mod = ExpertValidationModule()
        self.assertEqual(mod.key, "expert_validation")
        self.assertEqual(mod.api_prefix, "/api/expert-validation")
        self.assertEqual(mod.icon, "🔍")
        self.assertIsInstance(mod.order, int)

    def test_router_has_routes(self):
        """Роутер модуля содержит маршруты."""
        from admin_web.modules.expert_validation.router import ExpertValidationModule

        mod = ExpertValidationModule()
        router = mod.get_router()
        route_paths = [route.path for route in router.routes]
        self.assertIn("/pairs", route_paths)
        self.assertIn("/validate", route_paths)
        self.assertIn("/stats", route_paths)
        self.assertIn("/groups", route_paths)


@unittest.skipUnless(_HAS_FASTAPI, "FastAPI не установлен")
class TestGKKnowledgeModule(unittest.TestCase):
    """Тесты свойств модуля Group Knowledge."""

    def test_module_properties(self):
        """Свойства модуля GK Knowledge заданы корректно."""
        from admin_web.modules.gk_knowledge.module import GKKnowledgeModule

        mod = GKKnowledgeModule()
        self.assertEqual(mod.key, "gk_knowledge")
        self.assertEqual(mod.api_prefix, "/api/gk-knowledge")
        self.assertEqual(mod.icon, "🧠")
        self.assertIsInstance(mod.order, int)

    def test_router_has_sub_routes(self):
        """Роутер модуля содержит подмаршруты всех вкладок."""
        from admin_web.modules.gk_knowledge.module import GKKnowledgeModule

        mod = GKKnowledgeModule()
        router = mod.get_router()
        route_paths = [route.path for route in router.routes]
        # Подроутеры присоединены как sub-router — в пути входят их маршруты.
        # Проверяем ключевые маршруты.
        self.assertTrue(
            any("/stats" in p for p in route_paths),
            f"'/stats' не найден в маршрутах: {route_paths}"
        )
        self.assertTrue(
            any("/expert-validation" in p for p in route_paths),
            f"'/expert-validation' не найден в маршрутах: {route_paths}"
        )
        self.assertTrue(
            any("/qa-pairs" in p for p in route_paths),
            f"'/qa-pairs' не найден в маршрутах: {route_paths}"
        )
        self.assertTrue(
            any("/groups" in p for p in route_paths),
            f"'/groups' не найден в маршрутах: {route_paths}"
        )
        self.assertTrue(
            any("/search" in p for p in route_paths),
            f"'/search' не найден в маршрутах: {route_paths}"
        )


@unittest.skipUnless(_HAS_FASTAPI, "FastAPI не установлен")
class TestGKPromptTesterHelpers(unittest.TestCase):
    """Тесты вспомогательных функций GK Prompt Tester."""

    def test_get_supported_deepseek_models_uses_settings_without_duplicates(self):
        """Список моделей берётся из настроек и не содержит дублей."""
        from admin_web.modules.gk_knowledge import router as gk_router

        with patch.object(gk_router.ai_settings, "ALLOWED_DEEPSEEK_MODELS", ("deepseek-chat", "deepseek-reasoner")):
            with patch.object(gk_router.ai_settings, "GK_RESPONDER_MODEL", "deepseek-chat"):
                with patch.object(gk_router.ai_settings, "GK_ANALYSIS_MODEL", "deepseek-reasoner"):
                    models = gk_router.get_supported_deepseek_models()

        self.assertEqual(models, ["deepseek-chat", "deepseek-reasoner"])

    def test_get_supported_deepseek_models_appends_custom_models(self):
        """Кастомные модели из GK-настроек добавляются к поддерживаемому списку."""
        from admin_web.modules.gk_knowledge import router as gk_router

        with patch.object(gk_router.ai_settings, "ALLOWED_DEEPSEEK_MODELS", ("deepseek-chat",)):
            with patch.object(gk_router.ai_settings, "GK_RESPONDER_MODEL", "deepseek-custom-a"):
                with patch.object(gk_router.ai_settings, "GK_ANALYSIS_MODEL", "deepseek-custom-b"):
                    models = gk_router.get_supported_deepseek_models()

        self.assertEqual(models, ["deepseek-chat", "deepseek-custom-a", "deepseek-custom-b"])

    def test_render_user_prompt_with_placeholders(self):
        """Плейсхолдеры корректно подставляются в user_prompt."""
        from admin_web.modules.gk_knowledge.router import _render_gk_user_prompt

        template = "Пара #{pair_id} в группе {group_id}:\n{chain_context}"
        source = {
            "id": 101,
            "group_id": -100123,
            "question_text": "Q",
            "answer_text": "A",
        }
        rendered = _render_gk_user_prompt(template, source, "ctx")
        self.assertIn("#101", rendered)
        self.assertIn("-100123", rendered)
        self.assertIn("ctx", rendered)

    def test_render_user_prompt_supports_qa_analyzer_placeholders(self):
        """Шаблон из QAAnalyzer получает thread_context и question_confidence_threshold."""
        from admin_web.modules.gk_knowledge.router import _render_gk_user_prompt

        template = "Вопрос: {question}\nЦепочка:\n{thread_context}\nПорог: {question_confidence_threshold}"
        source = {
            "id": 101,
            "group_id": -100123,
            "question_text": "Почему не пускает в ФНС?",
            "answer_text": "Нужно другое действие",
        }
        rendered = _render_gk_user_prompt(template, source, "[1] user: текст")
        self.assertIn("Почему не пускает в ФНС?", rendered)
        self.assertIn("[1] user: текст", rendered)
        self.assertNotIn("{thread_context}", rendered)
        self.assertNotIn("{question_confidence_threshold}", rendered)

    def test_extract_generated_pair_from_json(self):
        """JSON-ответ с question/answer успешно парсится."""
        from admin_web.modules.gk_knowledge.router import _extract_generated_pair

        parsed = _extract_generated_pair('{"question":"Q1","answer":"A1","confidence":0.77}')
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["question"], "Q1")
        self.assertEqual(parsed["answer"], "A1")
        self.assertAlmostEqual(parsed["confidence"], 0.77)

    def test_extract_generated_pair_rejects_invalid_payload(self):
        """Невалидный payload отклоняется."""
        from admin_web.modules.gk_knowledge.router import _extract_generated_pair

        self.assertIsNone(_extract_generated_pair('{"foo":"bar"}'))


class TestGKSearchService(unittest.TestCase):
    """Тесты обёртки песочницы поиска Group Knowledge."""

    def test_hybrid_search_uses_qasearch_service(self):
        """Песочница поиска использует `QASearchService` и возвращает нормализованный результат."""
        from admin_web.modules.gk_knowledge import search_service
        from src.group_knowledge.models import QAPair

        pair = QAPair(
            id=15,
            question_text="Ошибка 1001 на терминале",
            answer_text="Перезагрузите терминал и обновите конфиг",
            group_id=-1001234,
            extraction_type="thread_reply",
            confidence=0.93,
        )
        pair.search_bm25_score = 1.75
        pair.search_vector_score = 0.82

        fake_service = MagicMock()
        fake_service.search = AsyncMock(return_value=[pair])

        with patch("src.group_knowledge.qa_search.QASearchService", return_value=fake_service):
            with patch.object(search_service.ai_settings, "GK_HYBRID_ENABLED", True):
                with patch.object(search_service.ai_settings, "GK_SEARCH_CANDIDATES_PER_METHOD", 10):
                    results = _run_async(search_service.hybrid_search("ошибка 1001", top_k=5))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["qa_pair_id"], 15)
        self.assertEqual(results[0]["question"], pair.question_text)
        self.assertEqual(results[0]["answer"], pair.answer_text)
        self.assertEqual(results[0]["bm25_score"], 1.75)
        self.assertEqual(results[0]["vector_score"], 0.82)
        fake_service.search.assert_awaited_once_with("ошибка 1001", top_k=5)

    def test_hybrid_search_returns_empty_list_on_import_error(self):
        """Если `qa_search` недоступен, обёртка возвращает пустой список."""
        from admin_web.modules.gk_knowledge import search_service

        with patch("builtins.__import__", side_effect=ImportError("qa_search missing")):
            results = _run_async(search_service.hybrid_search("ошибка", top_k=5))

        self.assertEqual(results, [])

    def test_hybrid_search_with_answer_returns_final_message(self):
        """Песочница возвращает не только документы, но и итоговый ответ автоответчика."""
        from admin_web.modules.gk_knowledge import search_service
        from src.group_knowledge.models import QAPair

        pair = QAPair(
          id=15,
          question_text="Ошибка 1001 на терминале",
          answer_text="Перезагрузите терминал и обновите конфиг",
          group_id=-1001234,
          extraction_type="thread_reply",
          confidence=0.93,
        )
        pair.search_bm25_score = 1.75
        pair.search_vector_score = 0.82

        fake_service = MagicMock()
        fake_service.search = AsyncMock(return_value=[pair])
        fake_service.answer_question_from_pairs = AsyncMock(return_value={
            "answer": "Перезагрузите терминал и обновите конфиг",
            "confidence": 0.91,
            "primary_source_link": "https://t.me/c/1234567890/555",
            "source_pair_ids": [15],
            "source_message_links": ["https://t.me/c/1234567890/555"],
        })
        fake_service.format_answer_for_user.return_value = (
            "**Отвечает робот Арчи**: Перезагрузите терминал и обновите конфиг\n\n"
            "Похожий случай в группе, ссылка на ответ: https://t.me/c/1234567890/555"
        )

        with patch("src.group_knowledge.qa_search.QASearchService", return_value=fake_service):
            with patch.object(search_service.ai_settings, "GK_HYBRID_ENABLED", True):
                with patch.object(search_service.ai_settings, "GK_SEARCH_CANDIDATES_PER_METHOD", 10):
                    with patch.object(search_service.ai_settings, "GK_RESPONDER_CONFIDENCE_THRESHOLD", 0.8):
                        result = _run_async(search_service.hybrid_search_with_answer("ошибка 1001", top_k=5))

        self.assertEqual(len(result["results"]), 1)
        self.assertTrue(result["answer_preview"]["would_send"])
        self.assertEqual(
            result["answer_preview"]["final_answer_text"],
            "**Отвечает робот Арчи**: Перезагрузите терминал и обновите конфиг\n\n"
            "Похожий случай в группе, ссылка на ответ: https://t.me/c/1234567890/555",
        )
        fake_service.search.assert_awaited_once_with("ошибка 1001", top_k=5)
        fake_service.answer_question_from_pairs.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
