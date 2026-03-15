# -*- coding: utf-8 -*-
"""
Фильтрация torch-пакетов из requirements.txt.

Создаёт копию requirements.txt без строк torch, torchvision, torchaudio,
чтобы update.bat мог установить их отдельно с нужным index-url (CPU/CUDA).

Использование:
    python deploy/filter_torch_requirements.py <input.txt> <output.txt>

Вынесено из update.bat в отдельный скрипт, чтобы избежать проблемы
парсинга cmd.exe спецсимволов (|, <, >, !) в inline python -c.
"""

import pathlib
import re
import sys


# Пакеты, которые нужно исключить (устанавливаются отдельно в update.bat)
_TORCH_PATTERN = re.compile(
    r"^\s*(torch|torchvision|torchaudio)(\s*$|[=<>!~\s])",
    re.IGNORECASE,
)


def filter_requirements(src: pathlib.Path, dst: pathlib.Path) -> int:
    """Копирует requirements без torch-пакетов. Возвращает число исключённых строк."""
    lines = src.read_text(encoding="utf-8").splitlines(True)
    filtered = [line for line in lines if not _TORCH_PATTERN.match(line)]
    dst.write_text("".join(filtered), encoding="utf-8")
    return len(lines) - len(filtered)


def main() -> None:
    if len(sys.argv) != 3:
        print(f"Использование: python {sys.argv[0]} <input.txt> <output.txt>", file=sys.stderr)
        sys.exit(2)

    src = pathlib.Path(sys.argv[1])
    dst = pathlib.Path(sys.argv[2])

    if not src.exists():
        print(f"ОШИБКА: файл не найден: {src}", file=sys.stderr)
        sys.exit(1)

    excluded = filter_requirements(src, dst)
    if excluded:
        print(f"Исключено {excluded} torch-пакет(ов) из {src.name}")


if __name__ == "__main__":
    main()
