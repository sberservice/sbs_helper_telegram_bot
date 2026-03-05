"""Тесты для CLI-утилиты сравнения предложений в RAG."""

import io
import json
import sys
import types
import unittest
from contextlib import redirect_stdout

from src.sbs_helper_telegram_bot.ai_router import rag_similarity


class _FakeEmbeddingProvider:
    """Фейковый провайдер эмбеддингов для контролируемых тестов."""

    def __init__(self, embeddings):
        self._embeddings = embeddings

    def encode_texts(self, texts):
        return self._embeddings


class _BrokenEmbeddingProvider:
    """Фейковый провайдер, имитирующий ошибку получения эмбеддингов."""

    def encode_texts(self, texts):
        raise RuntimeError("model unavailable")


class TestRagSentenceSimilarity(unittest.TestCase):
    """Проверки расчёта similarity и CLI-вывода."""

    def test_calculate_sentence_similarity_with_embeddings(self):
        """Итоговая метрика включает семантическую компоненту при доступных эмбеддингах."""
        provider = _FakeEmbeddingProvider([[1.0, 0.0], [1.0, 0.0]])

        result = rag_similarity.calculate_sentence_similarity(
            "Сбой терминала в магазине",
            "Сбой терминала в магазине",
            embedding_provider=provider,
        )

        self.assertAlmostEqual(result["semantic_similarity"], 1.0, places=6)
        self.assertAlmostEqual(result["lexical_similarity"], 1.0, places=6)
        self.assertAlmostEqual(result["combined_similarity"], 1.0, places=6)

    def test_calculate_sentence_similarity_fallback_without_embeddings(self):
        """При ошибке embedding-провайдера возвращаются лексические/строковые метрики без падения."""
        result = rag_similarity.calculate_sentence_similarity(
            "Оплата по карте не проходит",
            "Карта не проходит при оплате",
            embedding_provider=_BrokenEmbeddingProvider(),
        )

        self.assertIsNone(result["semantic_similarity"])
        self.assertGreaterEqual(result["lexical_similarity"], 0.0)
        self.assertLessEqual(result["lexical_similarity"], 1.0)
        self.assertGreaterEqual(result["combined_similarity"], 0.0)
        self.assertLessEqual(result["combined_similarity"], 1.0)

    def test_cli_json_output(self):
        """JSON-режим CLI возвращает машинно-читаемый результат."""
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = rag_similarity.main(
                [
                    "--sentence-a",
                    "Ошибка связи",
                    "--sentence-b",
                    "Ошибка связи",
                    "--json",
                ]
            )

        self.assertEqual(exit_code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["verdict"], "похожи")
        self.assertIn("combined_similarity", payload)

    def test_cli_rejects_empty_sentences(self):
        """CLI отклоняет пустые предложения с кодом ошибки argparse."""
        with self.assertRaises(SystemExit) as cm:
            rag_similarity.main([
                "--sentence-a",
                "   ",
                "--sentence-b",
                "не пусто",
            ])
        self.assertEqual(cm.exception.code, 2)

    def test_cli_interactive_short_flag_without_args(self):
        """Флаг -i без доп. аргументов не должен падать на argparse."""
        fake_module = types.SimpleNamespace()
        captured = {}

        def fake_interactive_main(argv=None):
            captured["argv"] = argv
            return 0

        fake_module.main = fake_interactive_main
        original_module = sys.modules.get(
            "src.sbs_helper_telegram_bot.ai_router.rag_similarity_interactive"
        )
        sys.modules[
            "src.sbs_helper_telegram_bot.ai_router.rag_similarity_interactive"
        ] = fake_module

        try:
            exit_code = rag_similarity.main(["-i"])
        finally:
            if original_module is None:
                del sys.modules[
                    "src.sbs_helper_telegram_bot.ai_router.rag_similarity_interactive"
                ]
            else:
                sys.modules[
                    "src.sbs_helper_telegram_bot.ai_router.rag_similarity_interactive"
                ] = original_module

        self.assertEqual(exit_code, 0)
        self.assertEqual(captured["argv"], [])


if __name__ == "__main__":
    unittest.main()
