"""Тесты для интерактивного REPL сравнения предложений."""

import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from src.sbs_helper_telegram_bot.ai_router.rag_similarity_interactive import (
    SimilaritySession,
    _parse_input,
    run_interactive,
    _fmt_score,
    _bar,
    _verdict_str,
    _truncate,
)


class _FakeEmbeddingProvider:
    """Фейковый провайдер эмбеддингов для контролируемых тестов."""

    def __init__(self, embeddings=None):
        self._embeddings = embeddings or [[1.0, 0.0], [0.8, 0.6]]

    def encode_texts(self, texts):
        return self._embeddings

    def is_ready(self):
        return True


class _BrokenEmbeddingProvider:
    """Провайдер, имитирующий ошибку."""

    def encode_texts(self, texts):
        raise RuntimeError("model unavailable")

    def is_ready(self):
        return False


class TestParseInput(unittest.TestCase):
    """Проверки разбора пользовательского ввода."""

    def test_empty_input(self):
        """Пустая строка возвращает пустые команду и аргументы."""
        cmd, rest = _parse_input("")
        self.assertEqual(cmd, "")
        self.assertEqual(rest, "")

    def test_command_only(self):
        """Команда без аргументов."""
        cmd, rest = _parse_input("compare")
        self.assertEqual(cmd, "compare")
        self.assertEqual(rest, "")

    def test_command_with_args(self):
        """Команда с аргументами сохраняет остаток как есть."""
        cmd, rest = _parse_input("a Привет мир")
        self.assertEqual(cmd, "a")
        self.assertEqual(rest, "Привет мир")

    def test_case_insensitive_command(self):
        """Команда приводится к нижнему регистру."""
        cmd, rest = _parse_input("COMPARE")
        self.assertEqual(cmd, "compare")

    def test_whitespace_stripped(self):
        """Лидирующие и завершающие пробелы убираются."""
        cmd, rest = _parse_input("   threshold  0.5  ")
        self.assertEqual(cmd, "threshold")
        # split(maxsplit=1) сохраняет хвост как есть после первого разделителя
        self.assertEqual(rest.strip(), "0.5")


class TestFormatHelpers(unittest.TestCase):
    """Проверки вспомогательных функций форматирования."""

    def test_fmt_score_value(self):
        """Числовое значение форматируется 4 знаками после запятой."""
        result = _fmt_score(0.75)
        self.assertIn("0.7500", result)

    def test_fmt_score_none(self):
        """None показывается как 'н/д'."""
        result = _fmt_score(None)
        self.assertIn("н/д", result)

    def test_bar_full(self):
        """Полная шкала для 1.0."""
        result = _bar(1.0, length=10)
        self.assertEqual(result, "█" * 10)

    def test_bar_empty(self):
        """Пустая шкала для 0.0."""
        result = _bar(0.0, length=10)
        self.assertEqual(result, "░" * 10)

    def test_bar_none(self):
        """None показывает пустую шкалу."""
        result = _bar(None, length=10)
        self.assertEqual(result, "░" * 10)

    def test_verdict_above(self):
        """Вердикт 'похожи' при превышении порога."""
        result = _verdict_str(0.8, 0.7)
        self.assertIn("похожи", result)
        self.assertIn("✅", result)

    def test_verdict_below(self):
        """Вердикт 'не похожи' при значении ниже порога."""
        result = _verdict_str(0.5, 0.7)
        self.assertIn("не похожи", result)
        self.assertIn("❌", result)

    def test_truncate_short(self):
        """Короткий текст не обрезается."""
        self.assertEqual(_truncate("abc", 10), "abc")

    def test_truncate_long(self):
        """Длинный текст обрезается с многоточием."""
        result = _truncate("a" * 100, 20)
        self.assertEqual(len(result), 20)
        self.assertTrue(result.endswith("…"))


class TestSimilaritySession(unittest.TestCase):
    """Проверки команд сравнения в SimilaritySession."""

    def _make_session(self, **kwargs):
        """Создать сессию с фейковым выводом."""
        output = io.StringIO()
        kwargs.setdefault("output", output)
        session = SimilaritySession(**kwargs)
        session.provider = _FakeEmbeddingProvider()
        return session, output

    def test_compare_no_sentence_a(self):
        """Сравнение без предложения A выводит предупреждение."""
        session, output = self._make_session(sentence_b="тест")
        result = session.cmd_compare()
        self.assertIsNone(result)
        self.assertIn("Предложение A не задано", output.getvalue())

    def test_compare_no_sentence_b(self):
        """Сравнение без предложения B выводит предупреждение."""
        session, output = self._make_session(sentence_a="тест")
        result = session.cmd_compare()
        self.assertIsNone(result)
        self.assertIn("Предложение B не задано", output.getvalue())

    def test_compare_success(self):
        """Успешное сравнение возвращает результат и добавляет в историю."""
        session, output = self._make_session(
            sentence_a="Ошибка терминала",
            sentence_b="Терминал не работает",
        )
        result = session.cmd_compare()
        self.assertIsNotNone(result)
        self.assertIn("sentence_a", result)
        self.assertIn("combined_similarity", result)
        self.assertIn("verdict", result)
        self.assertIn("elapsed_sec", result)
        self.assertIn("timestamp", result)
        self.assertEqual(len(session.history), 1)
        self.assertEqual(session.history[0]["index"], 1)

    def test_compare_json_output(self):
        """JSON-вывод при compare выдаёт валидный JSON."""
        session, output = self._make_session(
            sentence_a="тест один",
            sentence_b="тест два",
        )
        session.json_output = True
        session.cmd_compare()
        payload = json.loads(output.getvalue())
        self.assertIn("combined_similarity", payload)

    def test_compare_increments_index(self):
        """Индексы записей в истории монотонно растут."""
        session, output = self._make_session(
            sentence_a="аба",
            sentence_b="баб",
        )
        session.cmd_compare()
        session.cmd_compare()
        self.assertEqual(session.history[0]["index"], 1)
        self.assertEqual(session.history[1]["index"], 2)

    def test_threshold_valid(self):
        """Установка допустимого порога."""
        session, output = self._make_session()
        session.cmd_threshold("0.5")
        self.assertAlmostEqual(session.threshold, 0.5)

    def test_threshold_invalid_not_number(self):
        """Нечисловой порог отклоняется."""
        session, output = self._make_session()
        session.cmd_threshold("abc")
        self.assertIn("числом", output.getvalue())

    def test_threshold_out_of_range(self):
        """Порог вне диапазона отклоняется."""
        session, output = self._make_session()
        session.cmd_threshold("2.0")
        self.assertIn("диапазон", output.getvalue())

    def test_metrics_set(self):
        """Установка подмножества метрик."""
        session, output = self._make_session()
        session.cmd_metrics(["lexical", "sequence"])
        self.assertEqual(session.active_metrics, {"lexical", "sequence"})

    def test_metrics_all(self):
        """Метрики 'all' устанавливают все три метрики."""
        session, output = self._make_session()
        session.active_metrics = {"lexical"}
        session.cmd_metrics(["all"])
        self.assertEqual(session.active_metrics, {"semantic", "lexical", "sequence"})

    def test_metrics_invalid(self):
        """Неизвестная метрика выводит предупреждение."""
        session, output = self._make_session()
        session.cmd_metrics(["bogus"])
        self.assertIn("Неизвестная метрика", output.getvalue())

    def test_metrics_show_current(self):
        """Без аргументов показывает текущие метрики."""
        session, output = self._make_session()
        session.cmd_metrics([])
        self.assertIn("Активные метрики", output.getvalue())

    def test_json_toggle(self):
        """Переключение JSON-вывода."""
        session, output = self._make_session()
        session.cmd_json_toggle("on")
        self.assertTrue(session.json_output)
        session.cmd_json_toggle("off")
        self.assertFalse(session.json_output)
        session.cmd_json_toggle("")  # toggle
        self.assertTrue(session.json_output)

    def test_settings(self):
        """Команда settings выводит текущие настройки."""
        session, output = self._make_session(
            sentence_a="привет",
            sentence_b="мир",
            threshold=0.6,
        )
        session.cmd_settings()
        text = output.getvalue()
        self.assertIn("привет", text)
        self.assertIn("мир", text)
        self.assertIn("0.6000", text)

    def test_history_empty(self):
        """Пустая история выводит сообщение."""
        session, output = self._make_session()
        session.cmd_history()
        self.assertIn("История пуста", output.getvalue())

    def test_history_list(self):
        """История показывает записи в табличном виде."""
        session, output = self._make_session(
            sentence_a="один",
            sentence_b="два",
        )
        session.cmd_compare()
        output.truncate(0)
        output.seek(0)
        session.cmd_history()
        text = output.getvalue()
        self.assertIn("#", text)

    def test_history_detail(self):
        """Детальный просмотр записи по номеру."""
        session, output = self._make_session(
            sentence_a="один",
            sentence_b="два",
        )
        session.cmd_compare()
        output.truncate(0)
        output.seek(0)
        session.cmd_history("1")
        text = output.getvalue()
        self.assertIn("один", text)

    def test_history_not_found(self):
        """Несуществующий номер записи выводит предупреждение."""
        session, output = self._make_session(
            sentence_a="один",
            sentence_b="два",
        )
        session.cmd_compare()  # добавить запись, чтобы история не была пуста
        output.truncate(0)
        output.seek(0)
        session.cmd_history("99")
        self.assertIn("не найдена", output.getvalue())

    def test_diff(self):
        """Команда diff показывает разницу между двумя записями."""
        session, output = self._make_session(
            sentence_a="один",
            sentence_b="два",
        )
        session.cmd_compare()
        session.sentence_b = "три"
        session.cmd_compare()
        output.truncate(0)
        output.seek(0)
        session.cmd_diff(["1", "2"])
        text = output.getvalue()
        self.assertIn("Сравнение #1 и #2", text)

    def test_diff_insufficient_args(self):
        """Diff без двух аргументов показывает подсказку."""
        session, output = self._make_session()
        session.cmd_diff(["1"])
        self.assertIn("Использование", output.getvalue())

    def test_last(self):
        """Команда last показывает последний результат."""
        session, output = self._make_session(
            sentence_a="один",
            sentence_b="два",
        )
        session.cmd_compare()
        output.truncate(0)
        output.seek(0)
        session.cmd_last()
        self.assertIn("один", output.getvalue())

    def test_last_empty(self):
        """last при пустой истории выводит сообщение."""
        session, output = self._make_session()
        session.cmd_last()
        self.assertIn("История пуста", output.getvalue())

    def test_clear(self):
        """Очистка истории."""
        session, output = self._make_session(
            sentence_a="один",
            sentence_b="два",
        )
        session.cmd_compare()
        self.assertEqual(len(session.history), 1)
        session.cmd_clear()
        self.assertEqual(len(session.history), 0)
        self.assertIn("очищена", output.getvalue())


class TestExport(unittest.TestCase):
    """Проверки экспорта истории в файлы."""

    def _make_session_with_history(self):
        """Создать сессию с одной записью в истории."""
        output = io.StringIO()
        session = SimilaritySession(
            sentence_a="запрос один",
            sentence_b="запрос два",
            output=output,
        )
        session.provider = _FakeEmbeddingProvider()
        session.cmd_compare()
        return session, output

    def test_export_json(self):
        """Экспорт в JSON создаёт валидный файл."""
        session, output = self._make_session_with_history()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            filepath = f.name
        try:
            session.cmd_export(["json", filepath])
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data["total_entries"], 1)
            self.assertEqual(len(data["history"]), 1)
            self.assertIn("settings", data)
        finally:
            os.unlink(filepath)

    def test_export_csv(self):
        """Экспорт в CSV создаёт файл с заголовками и данными."""
        session, output = self._make_session_with_history()
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            filepath = f.name
        try:
            session.cmd_export(["csv", filepath])
            with open(filepath, encoding="utf-8") as f:
                lines = f.readlines()
            self.assertGreaterEqual(len(lines), 2)  # header + 1 row
            self.assertIn("combined_similarity", lines[0])
        finally:
            os.unlink(filepath)

    def test_export_empty_history(self):
        """Экспорт пустой истории отклоняется."""
        output = io.StringIO()
        session = SimilaritySession(output=output)
        session.cmd_export(["json", "/tmp/test.json"])
        self.assertIn("нечего экспортировать", output.getvalue())

    def test_export_unknown_format(self):
        """Неизвестный формат экспорта отклоняется."""
        session, output = self._make_session_with_history()
        output.truncate(0)
        output.seek(0)
        session.cmd_export(["xml", "/tmp/test.xml"])
        self.assertIn("Неизвестный формат", output.getvalue())

    def test_export_insufficient_args(self):
        """Экспорт без аргументов показывает подсказку."""
        output = io.StringIO()
        session = SimilaritySession(output=output)
        session.cmd_export([])
        self.assertIn("Использование", output.getvalue())


class TestRecalculateCombined(unittest.TestCase):
    """Проверки пересчёта combined_similarity с разными метриками."""

    def test_all_metrics(self):
        """Combined со всеми метриками — среднее трёх."""
        output = io.StringIO()
        session = SimilaritySession(output=output)
        session.active_metrics = {"semantic", "lexical", "sequence"}
        result = {
            "semantic_similarity": 0.9,
            "lexical_similarity": 0.6,
            "sequence_similarity": 0.3,
        }
        combined = session._recalculate_combined(result)
        self.assertAlmostEqual(combined, 0.6, places=6)

    def test_single_metric(self):
        """Combined с одной метрикой возвращает её значение."""
        output = io.StringIO()
        session = SimilaritySession(output=output)
        session.active_metrics = {"lexical"}
        result = {
            "semantic_similarity": 0.9,
            "lexical_similarity": 0.6,
            "sequence_similarity": 0.3,
        }
        combined = session._recalculate_combined(result)
        self.assertAlmostEqual(combined, 0.6, places=6)

    def test_semantic_none_skipped(self):
        """Если semantic=None и она единственная активная, combined=0."""
        output = io.StringIO()
        session = SimilaritySession(output=output)
        session.active_metrics = {"semantic"}
        result = {
            "semantic_similarity": None,
            "lexical_similarity": 0.6,
            "sequence_similarity": 0.3,
        }
        combined = session._recalculate_combined(result)
        self.assertAlmostEqual(combined, 0.0, places=6)


class TestInteractiveREPL(unittest.TestCase):
    """Проверки основного цикла REPL через эмуляцию stdin."""

    def _run_commands(self, commands: list[str]) -> str:
        """Запустить REPL с заданными командами и вернуть вывод."""
        stdin_text = "\n".join(commands) + "\n"
        output = io.StringIO()
        with patch("builtins.input", side_effect=commands + [EOFError()]):
            run_interactive(output=output)
        return output.getvalue()

    def test_help_command(self):
        """Команда help выводит справку."""
        result = self._run_commands(["help"])
        self.assertIn("RAG Sentence Similarity REPL", result)

    def test_set_and_compare(self):
        """Установка предложений и сравнение."""
        output = io.StringIO()
        provider = _FakeEmbeddingProvider()
        commands = [
            "a Ошибка кассы",
            "b Касса не работает",
            "c",
            "quit",
        ]
        with patch("builtins.input", side_effect=commands):
            with patch(
                "src.sbs_helper_telegram_bot.ai_router.rag_similarity_interactive"
                ".SimilaritySession._ensure_provider",
                return_value=provider,
            ):
                run_interactive(output=output)
        text = output.getvalue()
        self.assertIn("A ←", text)
        self.assertIn("B ←", text)
        self.assertIn("Combined similarity", text)

    def test_swap(self):
        """Команда swap меняет предложения местами."""
        output = io.StringIO()
        commands = [
            "a первое",
            "b второе",
            "swap",
            "quit",
        ]
        with patch("builtins.input", side_effect=commands):
            run_interactive(output=output)
        text = output.getvalue()
        self.assertIn("A ↔ B", text)

    def test_threshold_setting(self):
        """Установка порога через REPL."""
        output = io.StringIO()
        commands = [
            "t 0.5",
            "settings",
            "quit",
        ]
        with patch("builtins.input", side_effect=commands):
            run_interactive(output=output)
        text = output.getvalue()
        self.assertIn("0.5000", text)

    def test_unknown_command(self):
        """Неизвестная команда выводит предупреждение."""
        output = io.StringIO()
        commands = ["foobar", "quit"]
        with patch("builtins.input", side_effect=commands):
            run_interactive(output=output)
        text = output.getvalue()
        self.assertIn("Неизвестная команда", text)

    def test_show_sentence_a_without_arg(self):
        """Команда 'a' без аргумента показывает текущее предложение."""
        output = io.StringIO()
        commands = ["a тест", "a", "quit"]
        with patch("builtins.input", side_effect=commands):
            run_interactive(output=output)
        text = output.getvalue()
        self.assertIn("A: тест", text)

    def test_show_sentence_a_empty(self):
        """Команда 'a' без предложения показывает предупреждение."""
        output = io.StringIO()
        commands = ["a", "quit"]
        with patch("builtins.input", side_effect=commands):
            run_interactive(output=output)
        text = output.getvalue()
        self.assertIn("не задано", text)

    def test_eof_exits_gracefully(self):
        """EOF (Ctrl+D) корректно завершает REPL."""
        output = io.StringIO()
        with patch("builtins.input", side_effect=EOFError()):
            exit_code = run_interactive(output=output)
        self.assertEqual(exit_code, 0)
        self.assertIn("До свидания", output.getvalue())

    def test_keyboard_interrupt_exits(self):
        """Ctrl+C корректно завершает REPL."""
        output = io.StringIO()
        with patch("builtins.input", side_effect=KeyboardInterrupt()):
            exit_code = run_interactive(output=output)
        self.assertEqual(exit_code, 0)

    def test_initial_sentences_shown(self):
        """При передаче начальных предложений показываются настройки."""
        output = io.StringIO()
        with patch("builtins.input", side_effect=["quit"]):
            run_interactive(
                sentence_a="начальное A",
                sentence_b="начальное B",
                output=output,
            )
        text = output.getvalue()
        self.assertIn("начальное A", text)
        self.assertIn("начальное B", text)


class TestStatus(unittest.TestCase):
    """Проверки команды status."""

    def test_status_ready(self):
        """Статус с рабочим провайдером показывает модель."""
        output = io.StringIO()
        session = SimilaritySession(output=output)
        provider = MagicMock()
        provider.is_ready.return_value = True
        provider._model_name = "test-model"
        provider._device = "cpu"
        provider._fp16_enabled = False
        session.provider = provider
        session.cmd_status()
        text = output.getvalue()
        self.assertIn("✅", text)
        self.assertIn("test-model", text)

    def test_status_not_ready(self):
        """Статус с нерабочим провайдером показывает ошибку."""
        output = io.StringIO()
        session = SimilaritySession(output=output)
        provider = MagicMock()
        provider.is_ready.return_value = False
        session.provider = provider
        session.cmd_status()
        text = output.getvalue()
        self.assertIn("❌", text)


if __name__ == "__main__":
    unittest.main()
