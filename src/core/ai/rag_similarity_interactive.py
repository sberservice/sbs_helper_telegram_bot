"""Интерактивный CLI для сравнения похожести предложений в RAG-сценариях.

Предоставляет полнофункциональный REPL с историей сравнений, возможностью
изменять одно предложение за раз, настраивать параметры (порог, метрики,
JSON-вывод) без повторного ввода предложений, экспортировать результаты.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import readline
import shlex
import sys
import time
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional, TextIO

from src.core.ai.rag_similarity import (
    calculate_sentence_similarity,
)
from src.core.ai.vector_search import LocalEmbeddingProvider

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
#  Константы
# --------------------------------------------------------------------------- #

_METRICS_ALL = ("semantic", "lexical", "sequence", "combined")

_HELP_TEXT = r"""
╔══════════════════════════════════════════════════════════════════════════╗
║                     RAG Sentence Similarity REPL                       ║
╠══════════════════════════════════════════════════════════════════════════╣
║  Команды для сравнения:                                                ║
║    compare / c          — сравнить текущие предложения                  ║
║    a <текст>            — задать / изменить предложение A               ║
║    b <текст>            — задать / изменить предложение B               ║
║    swap                 — поменять A и B местами                        ║
║                                                                        ║
║  Настройки:                                                            ║
║    threshold / t <0‥1>  — установить порог combined_similarity          ║
║    metrics [список]     — выбрать метрики для combined                  ║
║                          (semantic lexical sequence | all)              ║
║    json [on|off]        — переключить JSON-вывод                       ║
║    settings / s         — показать текущие настройки                    ║
║                                                                        ║
║  История:                                                              ║
║    history / h          — показать историю сравнений                    ║
║    history N            — показать запись #N подробно                   ║
║    diff N M             — сравнить записи #N и #M                      ║
║    last / l             — показать последний результат                  ║
║    clear                — очистить историю                              ║
║                                                                        ║
║  Экспорт:                                                              ║
║    export json <файл>   — экспортировать историю в JSON                 ║
║    export csv <файл>    — экспортировать историю в CSV                  ║
║                                                                        ║
║  Прочее:                                                               ║
║    status               — показать статус embedding-модели              ║
║    help / ?              — показать эту справку                         ║
║    quit / q / exit       — выйти                                       ║
╚══════════════════════════════════════════════════════════════════════════╝
""".strip()


# --------------------------------------------------------------------------- #
#  Вспомогательные функции форматирования
# --------------------------------------------------------------------------- #


def _fmt_score(value: Optional[float], width: int = 8) -> str:
    """Отформатировать значение метрики для табличного вывода."""
    if value is None:
        return "н/д".center(width)
    return f"{value:.4f}".center(width)


def _bar(value: Optional[float], length: int = 30) -> str:
    """Визуальный прогресс-бар для значения 0..1."""
    if value is None:
        return "░" * length
    clamped = max(0.0, min(1.0, value))
    filled = int(round(clamped * length))
    return "█" * filled + "░" * (length - filled)


def _verdict_str(combined: float, threshold: float) -> str:
    """Вердикт похожести с цветовой подсказкой."""
    if combined >= threshold:
        return f"✅ похожи (≥ {threshold:.2f})"
    return f"❌ не похожи (< {threshold:.2f})"


def _truncate(text: str, max_len: int = 60) -> str:
    """Обрезать текст для компактного отображения."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


# --------------------------------------------------------------------------- #
#  Класс сессии
# --------------------------------------------------------------------------- #


class SimilaritySession:
    """Состояние интерактивной REPL-сессии."""

    def __init__(
        self,
        sentence_a: str = "",
        sentence_b: str = "",
        threshold: float = 0.7,
        output: TextIO | None = None,
    ) -> None:
        self.sentence_a = sentence_a
        self.sentence_b = sentence_b
        self.threshold = threshold
        self.json_output = False
        self.active_metrics: set[str] = {"semantic", "lexical", "sequence"}
        self.history: List[Dict[str, Any]] = []
        self.provider: Optional[LocalEmbeddingProvider] = None
        self._output: TextIO = output or sys.stdout
        self._provider_ready: Optional[bool] = None

    # ---- Вывод ----------------------------------------------------------- #

    def _print(self, *args: Any, **kwargs: Any) -> None:
        """Печать в настроенный поток вывода."""
        kwargs.setdefault("file", self._output)
        print(*args, **kwargs)

    # ---- Провайдер эмбеддингов ------------------------------------------- #

    def _ensure_provider(self) -> LocalEmbeddingProvider:
        """Получить или создать провайдер эмбеддингов (ленивая инициализация)."""
        if self.provider is None:
            self.provider = LocalEmbeddingProvider()
        return self.provider

    def _check_provider_status(self) -> bool:
        """Проверить готовность embedding-модели."""
        try:
            provider = self._ensure_provider()
            ready = provider.is_ready()
            self._provider_ready = ready
            return ready
        except Exception:
            self._provider_ready = False
            return False

    # ---- Основные команды ------------------------------------------------ #

    def cmd_compare(self) -> Optional[Dict[str, Any]]:
        """Выполнить сравнение текущих предложений."""
        if not self.sentence_a.strip():
            self._print("⚠ Предложение A не задано. Используйте: a <текст>")
            return None
        if not self.sentence_b.strip():
            self._print("⚠ Предложение B не задано. Используйте: b <текст>")
            return None

        start = time.monotonic()
        try:
            result = calculate_sentence_similarity(
                self.sentence_a,
                self.sentence_b,
                embedding_provider=self._ensure_provider(),
            )
        except ValueError as exc:
            self._print(f"⚠ Ошибка: {exc}")
            return None
        except Exception as exc:
            logger.error("Ошибка при расчёте similarity: %s", exc, exc_info=True)
            self._print(f"⚠ Непредвиденная ошибка: {exc}")
            return None
        elapsed = time.monotonic() - start

        combined = self._recalculate_combined(result)
        result["combined_similarity"] = combined
        result["threshold"] = self.threshold
        result["verdict"] = (
            "похожи" if combined >= self.threshold else "не похожи"
        )
        result["active_metrics"] = sorted(self.active_metrics)
        result["elapsed_sec"] = round(elapsed, 4)
        result["timestamp"] = datetime.now().isoformat(timespec="seconds")

        entry_index = len(self.history) + 1
        result["index"] = entry_index
        self.history.append(result)

        if self.json_output:
            self._print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            self._print_result(result)

        return result

    def _recalculate_combined(self, result: Dict[str, Any]) -> float:
        """Пересчитать combined_similarity на основе активных метрик."""
        scores: List[float] = []
        mapping = {
            "semantic": result.get("semantic_similarity"),
            "lexical": result.get("lexical_similarity"),
            "sequence": result.get("sequence_similarity"),
        }
        for metric_name in self.active_metrics:
            value = mapping.get(metric_name)
            if value is not None:
                scores.append(value)
        if not scores:
            return 0.0
        return sum(scores) / len(scores)

    def _print_result(self, result: Dict[str, Any]) -> None:
        """Красиво напечатать результат сравнения."""
        self._print("")
        self._print(f"  #{result.get('index', '?')}  RAG Similarity Result")
        self._print("  " + "─" * 62)
        self._print(f"  A: {result['sentence_a']}")
        self._print(f"  B: {result['sentence_b']}")
        self._print("  " + "─" * 62)

        sem = result.get("semantic_similarity")
        lex = result.get("lexical_similarity", 0.0)
        seq = result.get("sequence_similarity", 0.0)
        comb = result.get("combined_similarity", 0.0)

        active = self.active_metrics

        def _metric_line(label: str, value: Optional[float], key: str) -> str:
            marker = "●" if key in active else "○"
            return f"  {marker} {label:<22} {_fmt_score(value)}  {_bar(value)}"

        self._print(_metric_line("Semantic similarity", sem, "semantic"))
        self._print(_metric_line("Lexical similarity", lex, "lexical"))
        self._print(_metric_line("Sequence similarity", seq, "sequence"))
        self._print("  " + "─" * 62)
        self._print(f"  ★ Combined similarity  {_fmt_score(comb)}  {_bar(comb)}")
        self._print(f"  Вердикт: {_verdict_str(comb, self.threshold)}")
        elapsed = result.get("elapsed_sec")
        if elapsed is not None:
            self._print(f"  Время: {elapsed:.3f}с")
        self._print("")

    # ---- Настройки ------------------------------------------------------- #

    def cmd_threshold(self, value_str: str) -> None:
        """Установить пороговое значение."""
        try:
            value = float(value_str)
        except ValueError:
            self._print("⚠ Порог должен быть числом от 0 до 1")
            return
        if value < -1.0 or value > 1.0:
            self._print("⚠ Порог должен быть в диапазоне от -1 до 1")
            return
        self.threshold = value
        self._print(f"  Порог установлен: {self.threshold:.4f}")

    def cmd_metrics(self, args: List[str]) -> None:
        """Установить активные метрики для combined score."""
        if not args:
            self._print(f"  Активные метрики: {', '.join(sorted(self.active_metrics))}")
            self._print(f"  Доступные: {', '.join(_METRICS_ALL[:3])}")
            return

        if args == ["all"]:
            self.active_metrics = {"semantic", "lexical", "sequence"}
            self._print("  Активные метрики: все (semantic, lexical, sequence)")
            return

        valid: set[str] = set()
        for name in args:
            clean = name.strip().lower().rstrip(",")
            if clean in _METRICS_ALL[:3]:
                valid.add(clean)
            else:
                self._print(f"  ⚠ Неизвестная метрика: {clean}")
        if valid:
            self.active_metrics = valid
            self._print(f"  Активные метрики: {', '.join(sorted(self.active_metrics))}")
        else:
            self._print("  ⚠ Ни одна из указанных метрик не распознана")

    def cmd_json_toggle(self, arg: str) -> None:
        """Переключить JSON-вывод."""
        if arg == "on":
            self.json_output = True
        elif arg == "off":
            self.json_output = False
        else:
            self.json_output = not self.json_output
        status = "включён" if self.json_output else "выключен"
        self._print(f"  JSON-вывод: {status}")

    def cmd_settings(self) -> None:
        """Показать текущие настройки сессии."""
        self._print("")
        self._print("  ⚙ Настройки сессии")
        self._print("  " + "─" * 40)
        self._print(f"  Предложение A: {self.sentence_a or '(не задано)'}")
        self._print(f"  Предложение B: {self.sentence_b or '(не задано)'}")
        self._print(f"  Порог:         {self.threshold:.4f}")
        self._print(f"  Метрики:       {', '.join(sorted(self.active_metrics))}")
        self._print(f"  JSON-вывод:    {'да' if self.json_output else 'нет'}")
        self._print(f"  История:       {len(self.history)} записей")
        model_status = "не проверялось"
        if self._provider_ready is True:
            model_status = "готова"
        elif self._provider_ready is False:
            model_status = "недоступна"
        self._print(f"  Модель:        {model_status}")
        self._print("")

    # ---- История --------------------------------------------------------- #

    def cmd_history(self, arg: str = "") -> None:
        """Показать историю сравнений или запись с указанным номером."""
        if not self.history:
            self._print("  История пуста")
            return

        if arg:
            try:
                idx = int(arg)
            except ValueError:
                self._print("  ⚠ Укажите номер записи (число)")
                return
            entry = self._get_history_entry(idx)
            if entry is None:
                return
            if self.json_output:
                self._print(json.dumps(entry, ensure_ascii=False, indent=2))
            else:
                self._print_result(entry)
            return

        self._print("")
        self._print(f"  История сравнений ({len(self.history)} записей)")
        self._print("  " + "─" * 78)
        self._print(
            f"  {'#':<4} {'Combined':>9} {'Verdict':<14} {'A':<25} {'B':<25}"
        )
        self._print("  " + "─" * 78)
        for entry in self.history:
            idx = entry.get("index", "?")
            comb = entry.get("combined_similarity", 0.0)
            verdict = entry.get("verdict", "?")
            sa = _truncate(entry.get("sentence_a", ""), 24)
            sb = _truncate(entry.get("sentence_b", ""), 24)
            self._print(f"  {idx:<4} {comb:>9.4f} {verdict:<14} {sa:<25} {sb:<25}")
        self._print("")

    def cmd_diff(self, args: List[str]) -> None:
        """Сравнить два результата из истории."""
        if len(args) < 2:
            self._print("  Использование: diff N M")
            return
        try:
            idx_n = int(args[0])
            idx_m = int(args[1])
        except ValueError:
            self._print("  ⚠ Укажите два номера записей")
            return

        entry_n = self._get_history_entry(idx_n)
        entry_m = self._get_history_entry(idx_m)
        if entry_n is None or entry_m is None:
            return

        self._print("")
        self._print(f"  Сравнение #{idx_n} и #{idx_m}")
        self._print("  " + "─" * 70)

        # Предложения
        if entry_n.get("sentence_a") != entry_m.get("sentence_a"):
            self._print(f"  A (#{idx_n}): {entry_n.get('sentence_a', '')}")
            self._print(f"  A (#{idx_m}): {entry_m.get('sentence_a', '')}")
        else:
            self._print(f"  A (общее): {entry_n.get('sentence_a', '')}")

        if entry_n.get("sentence_b") != entry_m.get("sentence_b"):
            self._print(f"  B (#{idx_n}): {entry_n.get('sentence_b', '')}")
            self._print(f"  B (#{idx_m}): {entry_m.get('sentence_b', '')}")
        else:
            self._print(f"  B (общее): {entry_n.get('sentence_b', '')}")

        self._print("  " + "─" * 70)
        self._print(f"  {'Метрика':<24} {'#' + str(idx_n):>10} {'#' + str(idx_m):>10} {'Δ':>10}")
        self._print("  " + "─" * 70)

        for label, key in [
            ("Semantic", "semantic_similarity"),
            ("Lexical", "lexical_similarity"),
            ("Sequence", "sequence_similarity"),
            ("Combined", "combined_similarity"),
        ]:
            val_n = entry_n.get(key)
            val_m = entry_m.get(key)
            delta: Optional[float] = None
            if val_n is not None and val_m is not None:
                delta = val_m - val_n
            delta_str = f"{delta:+.4f}" if delta is not None else "н/д"
            self._print(
                f"  {label:<24} {_fmt_score(val_n):>10} {_fmt_score(val_m):>10} {delta_str:>10}"
            )

        # Вердикты
        v_n = entry_n.get("verdict", "?")
        v_m = entry_m.get("verdict", "?")
        change_marker = " ←" if v_n != v_m else ""
        self._print("  " + "─" * 70)
        self._print(f"  Вердикт: #{idx_n} = {v_n},  #{idx_m} = {v_m}{change_marker}")
        self._print("")

    def cmd_last(self) -> None:
        """Показать последний результат."""
        if not self.history:
            self._print("  История пуста")
            return
        entry = self.history[-1]
        if self.json_output:
            self._print(json.dumps(entry, ensure_ascii=False, indent=2))
        else:
            self._print_result(entry)

    def cmd_clear(self) -> None:
        """Очистить историю."""
        count = len(self.history)
        self.history.clear()
        self._print(f"  История очищена ({count} записей удалено)")

    # ---- Экспорт --------------------------------------------------------- #

    def cmd_export(self, args: List[str]) -> None:
        """Экспортировать историю в файл."""
        if len(args) < 2:
            self._print("  Использование: export json <файл>  или  export csv <файл>")
            return

        fmt = args[0].lower()
        filepath = args[1]
        if not self.history:
            self._print("  ⚠ История пуста, нечего экспортировать")
            return

        try:
            if fmt == "json":
                self._export_json(filepath)
            elif fmt == "csv":
                self._export_csv(filepath)
            else:
                self._print(f"  ⚠ Неизвестный формат: {fmt}. Используйте json или csv")
        except OSError as exc:
            self._print(f"  ⚠ Ошибка записи файла: {exc}")

    def _export_json(self, filepath: str) -> None:
        """Экспортировать историю в JSON-файл."""
        output_path = Path(filepath).resolve()
        export_data = {
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "total_entries": len(self.history),
            "settings": {
                "threshold": self.threshold,
                "active_metrics": sorted(self.active_metrics),
                "json_output": self.json_output,
            },
            "history": self.history,
        }
        output_path.write_text(
            json.dumps(export_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._print(f"  ✅ Экспортировано {len(self.history)} записей → {output_path}")

    def _export_csv(self, filepath: str) -> None:
        """Экспортировать историю в CSV-файл."""
        output_path = Path(filepath).resolve()
        fieldnames = [
            "index",
            "timestamp",
            "sentence_a",
            "sentence_b",
            "semantic_similarity",
            "lexical_similarity",
            "sequence_similarity",
            "combined_similarity",
            "threshold",
            "verdict",
            "elapsed_sec",
        ]
        buffer = StringIO()
        writer = csv.DictWriter(
            buffer,
            fieldnames=fieldnames,
            extrasaction="ignore",
        )
        writer.writeheader()
        for entry in self.history:
            writer.writerow(entry)
        output_path.write_text(buffer.getvalue(), encoding="utf-8")
        self._print(f"  ✅ Экспортировано {len(self.history)} записей → {output_path}")

    # ---- Статус ---------------------------------------------------------- #

    def cmd_status(self) -> None:
        """Показать статус embedding-модели."""
        self._print("  Проверяю embedding-модель…")
        ready = self._check_provider_status()
        if ready:
            provider = self._ensure_provider()
            model_name = getattr(provider, "_model_name", "неизвестно")
            device = getattr(provider, "_device", "неизвестно")
            fp16 = getattr(provider, "_fp16_enabled", False)
            self._print(f"  ✅ Модель:    {model_name}")
            self._print(f"     Устройство: {device}")
            self._print(f"     FP16:       {'да' if fp16 else 'нет'}")
        else:
            self._print("  ❌ Embedding-модель недоступна (будут использоваться"
                         " только лексические метрики)")

    # ---- Вспомогательные ------------------------------------------------- #

    def _get_history_entry(self, index: int) -> Optional[Dict[str, Any]]:
        """Получить запись из истории по номеру."""
        for entry in self.history:
            if entry.get("index") == index:
                return entry
        self._print(f"  ⚠ Запись #{index} не найдена (доступно: 1‥{len(self.history)})")
        return None


# --------------------------------------------------------------------------- #
#  Настройка readline (автодополнение команд)
# --------------------------------------------------------------------------- #

_COMMANDS = [
    "compare",
    "c",
    "a",
    "b",
    "swap",
    "threshold",
    "t",
    "metrics",
    "json",
    "settings",
    "s",
    "history",
    "h",
    "diff",
    "last",
    "l",
    "clear",
    "export",
    "status",
    "help",
    "?",
    "quit",
    "q",
    "exit",
]

_METRICS_COMPLETIONS = ["semantic", "lexical", "sequence", "all"]
_EXPORT_FORMATS = ["json", "csv"]
_JSON_ARGS = ["on", "off"]


def _setup_readline() -> None:
    """Настроить readline с автодополнением команд и историей."""

    history_file = Path.home() / ".rag_similarity_history"

    try:
        readline.read_history_file(str(history_file))
    except (FileNotFoundError, OSError):
        pass

    readline.set_history_length(500)

    import atexit
    atexit.register(_save_readline_history, str(history_file))

    def completer(text: str, state: int) -> Optional[str]:
        """Автодополнение команд и аргументов."""
        buffer = readline.get_line_buffer().lstrip()
        parts = buffer.split()

        if len(parts) <= 1:
            matches = [cmd + " " for cmd in _COMMANDS if cmd.startswith(text.lower())]
        else:
            first = parts[0].lower()
            if first == "metrics":
                matches = [m + " " for m in _METRICS_COMPLETIONS if m.startswith(text.lower())]
            elif first == "export":
                if len(parts) == 2:
                    matches = [f + " " for f in _EXPORT_FORMATS if f.startswith(text.lower())]
                else:
                    matches = []
            elif first == "json":
                matches = [a + " " for a in _JSON_ARGS if a.startswith(text.lower())]
            else:
                matches = []

        if state < len(matches):
            return matches[state]
        return None

    readline.set_completer(completer)
    readline.parse_and_bind("tab: complete")
    readline.set_completer_delims(" \t\n")


def _save_readline_history(path: str) -> None:
    """Атемпт сохранить историю readline при выходе."""
    try:
        readline.write_history_file(path)
    except OSError:
        pass


# --------------------------------------------------------------------------- #
#  REPL (Read-Eval-Print Loop)
# --------------------------------------------------------------------------- #


def _parse_input(raw: str) -> tuple[str, str]:
    """Разобрать ввод на команду и аргументы."""
    stripped = raw.strip()
    if not stripped:
        return "", ""
    parts = stripped.split(maxsplit=1)
    cmd = parts[0].lower()
    rest = parts[1] if len(parts) > 1 else ""
    return cmd, rest


def run_interactive(
    sentence_a: str = "",
    sentence_b: str = "",
    threshold: float = 0.7,
    output: TextIO | None = None,
) -> int:
    """Запустить интерактивный REPL для сравнения предложений.

    Args:
        sentence_a: Начальное предложение A.
        sentence_b: Начальное предложение B.
        threshold: Начальное пороговое значение.
        output: Поток вывода (по умолчанию sys.stdout).

    Returns:
        Код выхода (0 — нормальный выход).
    """
    out = output or sys.stdout
    session = SimilaritySession(
        sentence_a=sentence_a,
        sentence_b=sentence_b,
        threshold=threshold,
        output=out,
    )

    use_readline = out is sys.stdout and sys.stdin.isatty()
    if use_readline:
        _setup_readline()

    print(_HELP_TEXT, file=out)
    print("", file=out)

    if session.sentence_a or session.sentence_b:
        session.cmd_settings()

    while True:
        try:
            prompt = "sim> "
            raw = input(prompt)
        except (EOFError, KeyboardInterrupt):
            print("", file=out)
            break

        cmd, rest = _parse_input(raw)
        if not cmd:
            continue

        # ---- Выход -------
        if cmd in ("quit", "q", "exit"):
            break

        # ---- Справка -----
        elif cmd in ("help", "?"):
            print(_HELP_TEXT, file=out)

        # ---- Предложения -
        elif cmd == "a":
            if not rest:
                if session.sentence_a:
                    print(f"  A: {session.sentence_a}", file=out)
                else:
                    print("  ⚠ Предложение A не задано", file=out)
            else:
                session.sentence_a = rest
                print(f"  A ← {rest}", file=out)

        elif cmd == "b":
            if not rest:
                if session.sentence_b:
                    print(f"  B: {session.sentence_b}", file=out)
                else:
                    print("  ⚠ Предложение B не задано", file=out)
            else:
                session.sentence_b = rest
                print(f"  B ← {rest}", file=out)

        elif cmd == "swap":
            session.sentence_a, session.sentence_b = (
                session.sentence_b,
                session.sentence_a,
            )
            print(f"  A ↔ B", file=out)
            print(f"  A: {session.sentence_a or '(не задано)'}", file=out)
            print(f"  B: {session.sentence_b or '(не задано)'}", file=out)

        # ---- Сравнение ---
        elif cmd in ("compare", "c"):
            session.cmd_compare()

        # ---- Настройки ---
        elif cmd in ("threshold", "t"):
            if not rest:
                print(f"  Порог: {session.threshold:.4f}", file=out)
            else:
                session.cmd_threshold(rest.strip())

        elif cmd == "metrics":
            parts = rest.split() if rest else []
            session.cmd_metrics(parts)

        elif cmd == "json":
            session.cmd_json_toggle(rest.strip().lower())

        elif cmd in ("settings", "s"):
            session.cmd_settings()

        # ---- История -----
        elif cmd in ("history", "h"):
            session.cmd_history(rest.strip())

        elif cmd == "diff":
            diff_args = rest.split() if rest else []
            session.cmd_diff(diff_args)

        elif cmd in ("last", "l"):
            session.cmd_last()

        elif cmd == "clear":
            session.cmd_clear()

        # ---- Экспорт -----
        elif cmd == "export":
            export_args = rest.split() if rest else []
            session.cmd_export(export_args)

        # ---- Статус ------
        elif cmd == "status":
            session.cmd_status()

        # ---- Неизвестная команда -
        else:
            print(f"  ⚠ Неизвестная команда: {cmd}. Введите help для справки", file=out)

    print("До свидания!", file=out)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Точка входа для интерактивного режима.

    Поддерживает аргументы для предварительной инициализации сессии.
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Интерактивный REPL для сравнения предложений в RAG",
    )
    parser.add_argument(
        "--sentence-a",
        default="",
        help="Начальное предложение A",
    )
    parser.add_argument(
        "--sentence-b",
        default="",
        help="Начальное предложение B",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.7,
        help="Начальный порог combined_similarity (по умолчанию: 0.7)",
    )
    args = parser.parse_args(argv)

    if args.threshold < -1.0 or args.threshold > 1.0:
        parser.error("--threshold должен быть в диапазоне от -1 до 1")

    return run_interactive(
        sentence_a=args.sentence_a,
        sentence_b=args.sentence_b,
        threshold=args.threshold,
    )


if __name__ == "__main__":
    raise SystemExit(main())
