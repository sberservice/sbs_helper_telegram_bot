#!/usr/bin/env python3
"""
Утилита релиза проекта с семантической версией.

Что делает скрипт:
1) Проверяет, что git-репозиторий чистый и (по умолчанию) текущая ветка main.
2) Увеличивает версию в файле VERSION (major/minor/patch).
3) Переносит изменения из секции Unreleased в секцию новой версии в CHANGELOG.md.
4) Создаёт commit и аннотированный tag вида vX.Y.Z.

Пример:
    python scripts/release.py patch
"""

from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import re
import subprocess
import sys

ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT_DIR / "VERSION"
CHANGELOG_FILE = ROOT_DIR / "CHANGELOG.md"
SEMVER_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")

UNRELEASED_TEMPLATE = [
    "",
    "### Added",
    "- Нет изменений.",
    "",
    "### Changed",
    "- Нет изменений.",
    "",
    "### Fixed",
    "- Нет изменений.",
]


class ReleaseError(Exception):
    """Ошибка выполнения релизного сценария."""


def run_git(args: list[str]) -> str:
    """Выполняет git-команду и возвращает stdout."""
    process = subprocess.run(
        ["git", *args],
        cwd=ROOT_DIR,
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        raise ReleaseError(process.stderr.strip() or f"Команда git {' '.join(args)} завершилась с ошибкой")
    return process.stdout.strip()


def ensure_git_ready(expected_branch: str | None) -> None:
    """Проверяет, что репозиторий готов к релизу."""
    status = run_git(["status", "--porcelain"])
    if status:
        raise ReleaseError("Рабочее дерево не чистое. Закоммитьте или stash изменения перед релизом.")

    if expected_branch:
        current_branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"])
        if current_branch != expected_branch:
            raise ReleaseError(
                f"Релиз разрешён только из ветки {expected_branch}. Текущая ветка: {current_branch}."
            )


def read_version() -> tuple[int, int, int]:
    """Читает текущую версию из VERSION."""
    if not VERSION_FILE.exists():
        raise ReleaseError("Файл VERSION не найден.")

    raw_version = VERSION_FILE.read_text(encoding="utf-8").strip()
    if not SEMVER_PATTERN.match(raw_version):
        raise ReleaseError(f"Неверный формат VERSION: {raw_version}. Ожидается MAJOR.MINOR.PATCH")

    major, minor, patch = raw_version.split(".")
    return int(major), int(minor), int(patch)


def bump_version(current: tuple[int, int, int], part: str) -> tuple[int, int, int]:
    """Увеличивает часть семантической версии."""
    major, minor, patch = current

    if part == "major":
        return major + 1, 0, 0
    if part == "minor":
        return major, minor + 1, 0
    if part == "patch":
        return major, minor, patch + 1

    raise ReleaseError(f"Неизвестный тип инкремента: {part}")


def version_to_string(version: tuple[int, int, int]) -> str:
    """Преобразует версию в строку MAJOR.MINOR.PATCH."""
    return f"{version[0]}.{version[1]}.{version[2]}"


def write_version(new_version: str) -> None:
    """Сохраняет новую версию в VERSION."""
    VERSION_FILE.write_text(f"{new_version}\n", encoding="utf-8")


def normalize_unreleased_content(content_lines: list[str]) -> list[str]:
    """Подготавливает контент секции Unreleased для переноса в релиз."""
    normalized = [line.rstrip() for line in content_lines]

    while normalized and normalized[0] == "":
        normalized.pop(0)
    while normalized and normalized[-1] == "":
        normalized.pop()

    if not normalized:
        return ["- Нет изменений."]

    text = "\n".join(normalized)
    template_text = "\n".join(line for line in UNRELEASED_TEMPLATE if line)
    if text == template_text:
        return ["- Нет изменений."]

    return normalized


def update_changelog(new_version: str) -> None:
    """Переносит Unreleased в новую секцию версии и сбрасывает Unreleased к шаблону."""
    if not CHANGELOG_FILE.exists():
        raise ReleaseError("Файл CHANGELOG.md не найден.")

    original_lines = CHANGELOG_FILE.read_text(encoding="utf-8").splitlines()

    try:
        unreleased_index = original_lines.index("## [Unreleased]")
    except ValueError as exc:
        raise ReleaseError("В CHANGELOG.md нет секции '## [Unreleased]'.") from exc

    next_section_index = len(original_lines)
    for idx in range(unreleased_index + 1, len(original_lines)):
        if original_lines[idx].startswith("## ["):
            next_section_index = idx
            break

    unreleased_body = original_lines[unreleased_index + 1 : next_section_index]
    release_body = normalize_unreleased_content(unreleased_body)

    release_header = f"## [{new_version}] - {dt.date.today().isoformat()}"

    rebuilt: list[str] = []
    rebuilt.extend(original_lines[: unreleased_index + 1])
    rebuilt.extend(UNRELEASED_TEMPLATE)
    rebuilt.append("")
    rebuilt.append(release_header)
    rebuilt.extend(release_body)

    if next_section_index < len(original_lines):
        rebuilt.append("")
        rebuilt.extend(original_lines[next_section_index:])

    CHANGELOG_FILE.write_text("\n".join(rebuilt).rstrip() + "\n", encoding="utf-8")


def ensure_tag_does_not_exist(tag: str) -> None:
    """Проверяет, что git-тег ещё не создан."""
    existing = run_git(["tag", "--list", tag])
    if existing:
        raise ReleaseError(f"Тег {tag} уже существует.")


def create_release_commit_and_tag(new_version: str, skip_tag: bool) -> None:
    """Создаёт commit релиза и тег версии."""
    commit_message = f"release: v{new_version}"
    run_git(["add", "VERSION", "CHANGELOG.md"])
    run_git(["commit", "-m", commit_message])

    if not skip_tag:
        run_git(["tag", "-a", f"v{new_version}", "-m", f"Release v{new_version}"])


def parse_args() -> argparse.Namespace:
    """Парсит аргументы CLI."""
    parser = argparse.ArgumentParser(description="Релиз проекта с обновлением VERSION и CHANGELOG")
    parser.add_argument("part", choices=["major", "minor", "patch"], help="Какая часть версии увеличивается")
    parser.add_argument(
        "--branch",
        default="main",
        help="Ветка, из которой разрешён релиз (по умолчанию: main). Для отключения укажите пустую строку.",
    )
    parser.add_argument(
        "--skip-tag",
        action="store_true",
        help="Не создавать git-tag (полезно для dry-run процесса вручную).",
    )
    return parser.parse_args()


def main() -> int:
    """Точка входа CLI скрипта релиза."""
    args = parse_args()
    expected_branch = args.branch or None

    try:
        ensure_git_ready(expected_branch)
        current_version = read_version()
        new_version = version_to_string(bump_version(current_version, args.part))

        ensure_tag_does_not_exist(f"v{new_version}")
        write_version(new_version)
        update_changelog(new_version)
        create_release_commit_and_tag(new_version, skip_tag=args.skip_tag)

        print(f"Релиз подготовлен: v{new_version}")
        if args.skip_tag:
            print("Тег не создан (включён --skip-tag).")
        else:
            print(f"Создан тег: v{new_version}")
        print("Следующий шаг: git push && git push --tags")
        return 0
    except ReleaseError as exc:
        print(f"Ошибка релиза: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
