"""Реестр всех управляемых процессов SBS Archie.

Декларативное описание каждого скрипта и демона: команда запуска,
доступные CLI-флаги, пресеты режимов работы, тип (daemon/one_shot),
категория для группировки в UI.

Новые процессы добавляются путём расширения PROCESS_REGISTRY.
"""

from __future__ import annotations

import sys
from typing import Dict, List

from admin_web.modules.process_manager.models import (
    FlagDefinition,
    FlagType,
    PresetDefinition,
    ProcessDefinition,
    ProcessType,
)

# ---------------------------------------------------------------------------
# Категории процессов
# ---------------------------------------------------------------------------

CATEGORY_CORE = "Core"
CATEGORY_GK = "Group Knowledge"
CATEGORY_HELPER = "The Helper"
CATEGORY_RAG = "RAG"
CATEGORY_UTILS = "Утилиты"

CATEGORY_ORDER = [
    CATEGORY_CORE,
    CATEGORY_GK,
    CATEGORY_HELPER,
    CATEGORY_RAG,
    CATEGORY_UTILS,
]

# ---------------------------------------------------------------------------
# Реестр процессов
# ---------------------------------------------------------------------------

PROCESS_DEFINITIONS: List[ProcessDefinition] = [
    # ===== CORE (4 процесса из run_bot.py) =====
    ProcessDefinition(
        key="telegram_bot",
        name="Telegram Bot",
        description="Основной Telegram-бот — все взаимодействия с пользователями",
        icon="🤖",
        category=CATEGORY_CORE,
        process_type=ProcessType.DAEMON,
        command=[sys.executable, "-m", "src.sbs_helper_telegram_bot.telegram_bot.telegram_bot"],
        singleton=True,
        auto_restart=True,
        flags=[],
        presets=[
            PresetDefinition(
                name="Стандартный запуск",
                description="Запуск бота в штатном режиме",
                flags=[],
                icon="▶️",
            ),
        ],
    ),
    ProcessDefinition(
        key="image_queue",
        name="Image Queue",
        description="Фоновая обработка скриншотов (выезд-был)",
        icon="🖼️",
        category=CATEGORY_CORE,
        process_type=ProcessType.DAEMON,
        command=[sys.executable, "-m", "src.sbs_helper_telegram_bot.vyezd_byl.processimagequeue"],
        singleton=True,
        auto_restart=True,
        flags=[],
        presets=[
            PresetDefinition(
                name="Стандартный запуск",
                description="Обработка очереди скриншотов",
                flags=[],
                icon="▶️",
            ),
        ],
    ),
    ProcessDefinition(
        key="soos_queue",
        name="SOOS Queue",
        description="Фоновый рендеринг SOOS-документов",
        icon="📄",
        category=CATEGORY_CORE,
        process_type=ProcessType.DAEMON,
        command=[sys.executable, "-m", "src.sbs_helper_telegram_bot.soos.processimagequeue"],
        singleton=True,
        auto_restart=True,
        flags=[],
        presets=[
            PresetDefinition(
                name="Стандартный запуск",
                description="Обработка очереди SOOS-документов",
                flags=[],
                icon="▶️",
            ),
        ],
    ),
    ProcessDefinition(
        key="health_check_daemon",
        name="Health Check",
        description="Периодическая проверка доступности налоговой службы",
        icon="💓",
        category=CATEGORY_CORE,
        process_type=ProcessType.DAEMON,
        command=[
            sys.executable, "-m",
            "src.sbs_helper_telegram_bot.health_check.health_check_daemon",
        ],
        singleton=True,
        auto_restart=True,
        flags=[],
        presets=[
            PresetDefinition(
                name="Стандартный запуск",
                description="Мониторинг доступности налоговых сервисов",
                flags=[],
                icon="▶️",
            ),
        ],
    ),

    # ===== GROUP KNOWLEDGE =====
    ProcessDefinition(
        key="gk_collector",
        name="GK Collector",
        description="Сбор сообщений из Telegram-групп + обработка изображений + автоответчик",
        icon="📡",
        category=CATEGORY_GK,
        process_type=ProcessType.DAEMON,
        command=[sys.executable, "scripts/gk_collector.py"],
        singleton=True,
        auto_restart=True,
        flags=[
            FlagDefinition(
                name="--live",
                flag_type=FlagType.BOOL,
                description="Отправлять реальные ответы в группы (без этого — dry-run)",
            ),
            FlagDefinition(
                name="--test-mode",
                flag_type=FlagType.BOOL,
                description="Интерактивный выбор тестовой группы",
            ),
            FlagDefinition(
                name="--redirect-test-mode",
                flag_type=FlagType.BOOL,
                description="Слушать prod-группы, отправлять в тестовую",
            ),
            FlagDefinition(
                name="--collect-only",
                flag_type=FlagType.BOOL,
                description="Только сбор сообщений без автоответчика",
            ),
            FlagDefinition(
                name="--test-real-group-id",
                flag_type=FlagType.INT,
                description="ID реальной группы для test-mode (неинтерактивный)",
            ),
            FlagDefinition(
                name="--test-group-id",
                flag_type=FlagType.INT,
                description="ID тестовой группы для test-mode (неинтерактивный)",
            ),
            FlagDefinition(
                name="--redirect-group-id",
                flag_type=FlagType.INT,
                description="ID тестовой группы для redirect-test-mode (неинтерактивный)",
            ),
            FlagDefinition(
                name="--group-id",
                flag_type=FlagType.INT,
                description="ID конкретной группы для сбора",
            ),
            FlagDefinition(
                name="--manage-groups",
                flag_type=FlagType.BOOL,
                description="Интерактивное управление группами (одноразовый режим)",
                mutually_exclusive_group="mode",
            ),
            FlagDefinition(
                name="--backfill",
                flag_type=FlagType.BOOL,
                description="Загрузить историю сообщений",
                mutually_exclusive_group="mode",
            ),
            FlagDefinition(
                name="--days",
                flag_type=FlagType.INT,
                description="Количество дней для backfill",
                default=7,
            ),
            FlagDefinition(
                name="--force",
                flag_type=FlagType.BOOL,
                description="Принудительная повторная загрузка (для backfill)",
            ),
            FlagDefinition(
                name="--fill-missing-is-question",
                flag_type=FlagType.BOOL,
                description="Заполнить NULL значения is_question",
                mutually_exclusive_group="mode",
            ),
            FlagDefinition(
                name="--fill-days",
                flag_type=FlagType.INT,
                description="Ограничить заполнение N днями",
            ),
            FlagDefinition(
                name="--fill-limit",
                flag_type=FlagType.INT,
                description="Лимит сообщений для fill-missing",
            ),
        ],
        presets=[
            PresetDefinition(
                name="Live",
                description="Сбор + автоответчик с реальной отправкой",
                flags=["--live"],
                icon="🟢",
            ),
            PresetDefinition(
                name="Dry-run",
                description="Сбор + автоответчик без отправки (по умолчанию)",
                flags=[],
                icon="🔇",
            ),
            PresetDefinition(
                name="Collect only",
                description="Только сбор сообщений, без автоответчика",
                flags=["--collect-only"],
                icon="📥",
            ),
            PresetDefinition(
                name="Test mode",
                description="Работа с тестовой группой (выберите группы в форме)",
                flags=["--test-mode"],
                icon="🧪",
                requires_form=True,
                form_type="gk_test_mode",
            ),
            PresetDefinition(
                name="Redirect test",
                description="Слушать prod, отправлять в тестовую группу (выберите группу в форме)",
                flags=["--redirect-test-mode", "--live"],
                icon="↪️",
                requires_form=True,
                form_type="gk_redirect_test",
            ),
            PresetDefinition(
                name="Backfill 7 дней",
                description="Загрузить историю за последние 7 дней",
                flags=["--backfill", "--days", "7"],
                icon="📚",
            ),
            PresetDefinition(
                name="Backfill 30 дней",
                description="Загрузить историю за последние 30 дней",
                flags=["--backfill", "--days", "30"],
                icon="📚",
            ),
        ],
    ),
    ProcessDefinition(
        key="gk_analyzer",
        name="GK Analyzer",
        description="Извлечение Q&A-пар из собранных сообщений и индексация в Qdrant",
        icon="🔬",
        category=CATEGORY_GK,
        process_type=ProcessType.ONE_SHOT,
        command=[sys.executable, "scripts/gk_analyze.py"],
        singleton=True,
        auto_restart=False,
        flags=[
            FlagDefinition(
                name="--date",
                flag_type=FlagType.STRING,
                description="Дата для анализа (YYYY-MM-DD)",
                mutually_exclusive_group="date_selector",
            ),
            FlagDefinition(
                name="--all-unprocessed",
                flag_type=FlagType.BOOL,
                description="Все необработанные даты",
                mutually_exclusive_group="date_selector",
            ),
            FlagDefinition(
                name="--all-unprocessed-except-today",
                flag_type=FlagType.BOOL,
                description="Все необработанные даты, кроме сегодняшней",
                mutually_exclusive_group="date_selector",
            ),
            FlagDefinition(
                name="--all-dates",
                flag_type=FlagType.BOOL,
                description="Все даты",
                mutually_exclusive_group="date_selector",
            ),
            FlagDefinition(
                name="--group-id",
                flag_type=FlagType.INT,
                description="ID конкретной группы",
            ),
            FlagDefinition(
                name="--index",
                flag_type=FlagType.BOOL,
                description="Только индексация в Qdrant (без анализа)",
            ),
            FlagDefinition(
                name="--rebuild-vector-index",
                flag_type=FlagType.BOOL,
                description="Полностью пересобрать QA-векторный индекс (удалить QA-векторы и переиндексировать approved-пары)",
            ),
            FlagDefinition(
                name="--no-index",
                flag_type=FlagType.BOOL,
                description="Не индексировать после анализа",
            ),
            FlagDefinition(
                name="--skip-thread",
                flag_type=FlagType.BOOL,
                description="Пропустить thread-based извлечение",
            ),
            FlagDefinition(
                name="--skip-llm",
                flag_type=FlagType.BOOL,
                description="Пропустить LLM-inferred извлечение",
            ),
            FlagDefinition(
                name="--force-reanalyze",
                flag_type=FlagType.BOOL,
                description="Принудительный переанализ обработанных сообщений",
            ),
            FlagDefinition(
                name="--rebuild-pairs",
                flag_type=FlagType.BOOL,
                description="Удалить и пересоздать все пары (требует --all-dates)",
            ),
        ],
        presets=[
            PresetDefinition(
                name="Необработанные",
                description="Запустить анализ всех необработанных дат",
                flags=["--all-unprocessed"],
                icon="📋",
            ),
            PresetDefinition(
                name="Необработанные (без сегодня)",
                description="Запустить анализ всех необработанных дат, кроме текущего дня",
                flags=["--all-unprocessed-except-today"],
                icon="🗓️",
            ),
            PresetDefinition(
                name="Все даты",
                description="Полный анализ всех дат",
                flags=["--all-dates"],
                icon="📅",
            ),
            PresetDefinition(
                name="Только индексация",
                description="Индексировать существующие пары в Qdrant",
                flags=["--index"],
                icon="🗂️",
            ),
            PresetDefinition(
                name="Rebuild vector index",
                description="Удалить QA-векторы и полностью переиндексировать approved-пары",
                flags=["--rebuild-vector-index"],
                icon="♻️",
            ),
            PresetDefinition(
                name="Переанализ всех",
                description="Принудительный переанализ всех дат",
                flags=["--all-dates", "--force-reanalyze"],
                icon="🔄",
            ),
            PresetDefinition(
                name="Rebuild (без сегодня)",
                description="Полностью пересобрать Q&A-пары по всем датам, кроме текущей",
                flags=["--all-dates", "--rebuild-pairs"],
                icon="🧱",
            ),
        ],
    ),
    ProcessDefinition(
        key="gk_responder",
        name="GK Responder",
        description="Автономный автоответчик в Telegram-группах (legacy, заменён daemon в gk_collector)",
        icon="💬",
        category=CATEGORY_GK,
        process_type=ProcessType.DAEMON,
        command=[sys.executable, "scripts/gk_responder.py"],
        singleton=True,
        auto_restart=False,
        flags=[
            FlagDefinition(
                name="--live",
                flag_type=FlagType.BOOL,
                description="Отправлять реальные ответы",
            ),
            FlagDefinition(
                name="--test-mode",
                flag_type=FlagType.BOOL,
                description="Интерактивный выбор тестовой группы",
            ),
            FlagDefinition(
                name="--test-real-group-id",
                flag_type=FlagType.INT,
                description="ID реальной группы для test-mode (неинтерактивный)",
            ),
            FlagDefinition(
                name="--test-group-id",
                flag_type=FlagType.INT,
                description="ID тестовой группы для test-mode (неинтерактивный)",
            ),
            FlagDefinition(
                name="--manage-groups",
                flag_type=FlagType.BOOL,
                description="Интерактивное управление группами",
            ),
        ],
        presets=[
            PresetDefinition(
                name="Live",
                description="Автоответчик с реальной отправкой",
                flags=["--live"],
                icon="🟢",
            ),
            PresetDefinition(
                name="Dry-run",
                description="Автоответчик без отправки",
                flags=[],
                icon="🔇",
            ),
            PresetDefinition(
                name="Test mode",
                description="Работа с тестовой группой (выберите группы в форме)",
                flags=["--test-mode"],
                icon="🧪",
                requires_form=True,
                form_type="gk_test_mode",
            ),
        ],
    ),
    ProcessDefinition(
        key="gk_delete_group_data",
        name="GK Delete Group Data",
        description="Безопасное удаление данных конкретной группы (с Qdrant cleanup)",
        icon="🗑️",
        category=CATEGORY_GK,
        process_type=ProcessType.ONE_SHOT,
        command=[sys.executable, "scripts/gk_delete_group_data.py"],
        singleton=True,
        auto_restart=False,
        flags=[
            FlagDefinition(
                name="--group-id",
                flag_type=FlagType.INT,
                description="ID группы для удаления",
                required=True,
            ),
            FlagDefinition(
                name="--yes",
                flag_type=FlagType.BOOL,
                description="Подтвердить удаление без запросов",
            ),
            FlagDefinition(
                name="--no-vector-cleanup",
                flag_type=FlagType.BOOL,
                description="Не очищать векторы в Qdrant",
            ),
        ],
        presets=[
            PresetDefinition(
                name="Удалить данные группы",
                description="Укажите группу для удаления данных (выберите в форме)",
                flags=["--yes"],
                icon="🗑️",
                requires_form=True,
                form_type="gk_delete_group",
            ),
        ],
    ),

    # ===== THE HELPER =====
    ProcessDefinition(
        key="the_helper",
        name="The Helper",
        description="Обработчик /helpme запросов в Telegram-группах (Telethon)",
        icon="🆘",
        category=CATEGORY_HELPER,
        process_type=ProcessType.DAEMON,
        command=[sys.executable, "scripts/the_helper.py"],
        singleton=True,
        auto_restart=True,
        flags=[
            FlagDefinition(
                name="--manage-groups",
                flag_type=FlagType.BOOL,
                description="Интерактивное управление группами",
            ),
        ],
        presets=[
            PresetDefinition(
                name="Стандартный запуск",
                description="Слушать /helpme во всех настроенных группах",
                flags=[],
                icon="▶️",
            ),
        ],
    ),

    # ===== RAG =====
    ProcessDefinition(
        key="rag_ops",
        name="RAG Ops",
        description="Управление RAG-системой: health, status, setup, update, sync",
        icon="📚",
        category=CATEGORY_RAG,
        process_type=ProcessType.ONE_SHOT,
        command=[sys.executable, "scripts/rag_ops.py"],
        singleton=False,
        auto_restart=False,
        flags=[
            FlagDefinition(
                name="subcommand",
                flag_type=FlagType.CHOICE,
                description="Подкоманда RAG Ops",
                choices=["health", "status", "setup", "update", "sync-remote"],
                required=True,
            ),
            FlagDefinition(
                name="--apply-sql",
                flag_type=FlagType.BOOL,
                description="Применить SQL-миграции",
            ),
            FlagDefinition(
                name="--yes",
                flag_type=FlagType.BOOL,
                description="Подтвердить действия без запросов",
            ),
            FlagDefinition(
                name="--force",
                flag_type=FlagType.BOOL,
                description="Принудительное обновление",
            ),
            FlagDefinition(
                name="--dry-run",
                flag_type=FlagType.BOOL,
                description="Без изменений в БД",
            ),
            FlagDefinition(
                name="--batch-size",
                flag_type=FlagType.INT,
                description="Размер батча обработки",
            ),
            FlagDefinition(
                name="--target",
                flag_type=FlagType.CHOICE,
                description="Цель обновления векторов",
                choices=["chunks", "summaries", "both"],
            ),
        ],
        presets=[
            PresetDefinition(
                name="Health",
                description="Проверить подключение к MySQL и Qdrant",
                flags=["health"],
                icon="💓",
            ),
            PresetDefinition(
                name="Status",
                description="Статистика RAG-корпуса",
                flags=["status"],
                icon="📊",
            ),
            PresetDefinition(
                name="Setup",
                description="Начальная настройка с SQL-миграциями",
                flags=["setup", "--apply-sql", "--yes"],
                icon="⚙️",
            ),
        ],
    ),
    ProcessDefinition(
        key="rag_directory_ingest",
        name="RAG Directory Ingest",
        description="Синхронизация директории документов с RAG-базой знаний",
        icon="📁",
        category=CATEGORY_RAG,
        process_type=ProcessType.ONE_SHOT,
        command=[sys.executable, "scripts/rag_directory_ingest.py"],
        singleton=True,
        auto_restart=False,
        flags=[
            FlagDefinition(
                name="--directory",
                flag_type=FlagType.STRING,
                description="Путь к директории документов",
                required=True,
            ),
            FlagDefinition(
                name="--daemon",
                flag_type=FlagType.BOOL,
                description="Непрерывный режим (повторять каждые N секунд)",
            ),
            FlagDefinition(
                name="--interval-seconds",
                flag_type=FlagType.INT,
                description="Интервал цикла в daemon-режиме",
                default=900,
            ),
            FlagDefinition(
                name="--dry-run",
                flag_type=FlagType.BOOL,
                description="Без записи в БД",
            ),
            FlagDefinition(
                name="--force-update",
                flag_type=FlagType.BOOL,
                description="Перезагрузить даже без изменения хеша",
            ),
            FlagDefinition(
                name="--uploaded-by",
                flag_type=FlagType.INT,
                description="ID пользователя-загрузчика",
                default=0,
            ),
            FlagDefinition(
                name="--no-recursive",
                flag_type=FlagType.BOOL,
                description="Только файлы верхнего уровня",
            ),
            FlagDefinition(
                name="--regenerate-summaries",
                flag_type=FlagType.BOOL,
                description="Перегенерировать summaries",
            ),
            FlagDefinition(
                name="--verbose",
                flag_type=FlagType.BOOL,
                description="Подробное логирование (DEBUG)",
            ),
        ],
        presets=[
            PresetDefinition(
                name="Dry-run",
                description="Показать изменения без записи в БД",
                flags=["--directory", "classified_docs", "--dry-run"],
                icon="🔇",
            ),
            PresetDefinition(
                name="Синхронизация classified_docs",
                description="Синхронизировать classified_docs с RAG",
                flags=["--directory", "classified_docs"],
                icon="📂",
            ),
            PresetDefinition(
                name="Daemon-режим",
                description="Непрерывная синхронизация classified_docs",
                flags=["--directory", "classified_docs", "--daemon"],
                icon="🔄",
            ),
        ],
    ),
    ProcessDefinition(
        key="rag_certification_sync",
        name="RAG Certification Sync",
        description="Синхронизация сертификационных сигналов",
        icon="🎓",
        category=CATEGORY_RAG,
        process_type=ProcessType.ONE_SHOT,
        command=[sys.executable, "scripts/rag_certification_sync.py"],
        singleton=True,
        auto_restart=False,
        flags=[
            FlagDefinition(
                name="--uploaded-by",
                flag_type=FlagType.INT,
                description="ID пользователя-загрузчика",
            ),
            FlagDefinition(
                name="--upsert-vectors",
                flag_type=FlagType.BOOL,
                description="Обновить векторы в Qdrant",
            ),
            FlagDefinition(
                name="--force-update",
                flag_type=FlagType.BOOL,
                description="Принудительное обновление",
            ),
        ],
        presets=[
            PresetDefinition(
                name="Полная синхронизация",
                description="Синхронизировать сертификационные сигналы + векторы",
                flags=["--upsert-vectors"],
                icon="🔄",
            ),
        ],
    ),
    ProcessDefinition(
        key="rag_vector_backfill",
        name="RAG Vector Backfill",
        description="Заполнение недостающих векторов в Qdrant",
        icon="🔢",
        category=CATEGORY_RAG,
        process_type=ProcessType.ONE_SHOT,
        command=[sys.executable, "scripts/rag_vector_backfill.py"],
        singleton=True,
        auto_restart=False,
        flags=[
            FlagDefinition(
                name="--batch-size",
                flag_type=FlagType.INT,
                description="Размер батча",
            ),
            FlagDefinition(
                name="--source-type",
                flag_type=FlagType.STRING,
                description="Тип источника",
            ),
            FlagDefinition(
                name="--max-documents",
                flag_type=FlagType.INT,
                description="Максимум документов",
            ),
            FlagDefinition(
                name="--dry-run",
                flag_type=FlagType.BOOL,
                description="Без записи в Qdrant",
            ),
            FlagDefinition(
                name="--target",
                flag_type=FlagType.CHOICE,
                description="Цель: chunks, summaries или both",
                choices=["chunks", "summaries", "both"],
            ),
        ],
        presets=[
            PresetDefinition(
                name="Полный backfill",
                description="Заполнить все недостающие векторы",
                flags=[],
                icon="▶️",
            ),
            PresetDefinition(
                name="Dry-run",
                description="Показать без записи",
                flags=["--dry-run"],
                icon="🔇",
            ),
        ],
    ),
    ProcessDefinition(
        key="rag_qdrant_sync",
        name="RAG Qdrant Sync",
        description="Синхронизация Qdrant: remote → local",
        icon="🔄",
        category=CATEGORY_RAG,
        process_type=ProcessType.ONE_SHOT,
        command=[sys.executable, "scripts/rag_qdrant_sync_remote_to_local.py"],
        singleton=True,
        auto_restart=False,
        flags=[
            FlagDefinition(
                name="--collection",
                flag_type=FlagType.STRING,
                description="Название коллекции",
            ),
            FlagDefinition(
                name="--batch-size",
                flag_type=FlagType.INT,
                description="Размер батча",
            ),
            FlagDefinition(
                name="--max-points",
                flag_type=FlagType.INT,
                description="Максимум точек для синхронизации",
            ),
            FlagDefinition(
                name="--delete-missing",
                flag_type=FlagType.BOOL,
                description="Удалить точки, отсутствующие в remote",
            ),
        ],
        presets=[
            PresetDefinition(
                name="Стандартная синхронизация",
                description="Синхронизация всех коллекций",
                flags=[],
                icon="🔄",
            ),
        ],
    ),

    # ===== УТИЛИТЫ =====
    ProcessDefinition(
        key="sync_chat_members",
        name="Sync Chat Members",
        description="Синхронизация участников Telegram-группы в БД",
        icon="👥",
        category=CATEGORY_UTILS,
        process_type=ProcessType.ONE_SHOT,
        command=[sys.executable, "scripts/sync_chat_members.py"],
        singleton=True,
        auto_restart=False,
        flags=[
            FlagDefinition(
                name="--daemon",
                flag_type=FlagType.BOOL,
                description="Непрерывный режим (повторять каждые N часов)",
            ),
            FlagDefinition(
                name="--dry-run",
                flag_type=FlagType.BOOL,
                description="Показать изменения без записи",
            ),
            FlagDefinition(
                name="--verbose",
                flag_type=FlagType.BOOL,
                description="Подробное логирование",
            ),
        ],
        presets=[
            PresetDefinition(
                name="Одноразовая синхронизация",
                description="Синхронизировать участников один раз",
                flags=[],
                icon="👥",
            ),
            PresetDefinition(
                name="Daemon",
                description="Непрерывная синхронизация",
                flags=["--daemon"],
                icon="🔄",
            ),
            PresetDefinition(
                name="Dry-run",
                description="Показать без записи",
                flags=["--dry-run"],
                icon="🔇",
            ),
        ],
    ),
    ProcessDefinition(
        key="add_daily_scores",
        name="Add Daily Scores",
        description="Начисление ежедневных баллов геймификации",
        icon="🏆",
        category=CATEGORY_UTILS,
        process_type=ProcessType.ONE_SHOT,
        command=[sys.executable, "scripts/add_daily_scores.py"],
        singleton=False,
        auto_restart=False,
        flags=[
            FlagDefinition(
                name="--all-active",
                flag_type=FlagType.BOOL,
                description="Начислить всем активным пользователям",
                mutually_exclusive_group="target",
            ),
            FlagDefinition(
                name="--userid",
                flag_type=FlagType.INT,
                description="ID конкретного пользователя",
                mutually_exclusive_group="target",
            ),
            FlagDefinition(
                name="--file",
                flag_type=FlagType.STRING,
                description="Файл со списком пользователей",
                mutually_exclusive_group="target",
            ),
            FlagDefinition(
                name="--points",
                flag_type=FlagType.INT,
                description="Количество баллов",
                required=True,
            ),
            FlagDefinition(
                name="--reason",
                flag_type=FlagType.STRING,
                description="Причина начисления",
            ),
            FlagDefinition(
                name="--source",
                flag_type=FlagType.STRING,
                description="Источник начисления",
            ),
            FlagDefinition(
                name="--dry-run",
                flag_type=FlagType.BOOL,
                description="Без записи в БД",
            ),
        ],
        presets=[],
    ),
    ProcessDefinition(
        key="release",
        name="Release",
        description="Сборка релиза: bump VERSION, обновление CHANGELOG, git tag",
        icon="🚀",
        category=CATEGORY_UTILS,
        process_type=ProcessType.ONE_SHOT,
        command=[sys.executable, "scripts/release.py"],
        singleton=True,
        auto_restart=False,
        flags=[
            FlagDefinition(
                name="bump_type",
                flag_type=FlagType.CHOICE,
                description="Тип версии",
                choices=["major", "minor", "patch"],
                required=True,
            ),
        ],
        presets=[
            PresetDefinition(
                name="Patch",
                description="Патч-релиз (0.0.x)",
                flags=["patch"],
                icon="🔧",
            ),
            PresetDefinition(
                name="Minor",
                description="Минорный релиз (0.x.0)",
                flags=["minor"],
                icon="📦",
            ),
            PresetDefinition(
                name="Major",
                description="Мажорный релиз (x.0.0)",
                flags=["major"],
                icon="🚀",
            ),
        ],
    ),
]


def get_process_registry() -> Dict[str, ProcessDefinition]:
    """Получить реестр процессов как словарь key → ProcessDefinition."""
    return {p.key: p for p in PROCESS_DEFINITIONS}


def get_process_definition(key: str) -> ProcessDefinition | None:
    """Получить определение процесса по ключу."""
    registry = get_process_registry()
    return registry.get(key)


def get_processes_by_category() -> Dict[str, List[ProcessDefinition]]:
    """Получить процессы, сгруппированные по категориям в порядке CATEGORY_ORDER."""
    result: Dict[str, List[ProcessDefinition]] = {}
    for cat in CATEGORY_ORDER:
        result[cat] = []

    for proc in PROCESS_DEFINITIONS:
        category = proc.category
        if category not in result:
            result[category] = []
        result[category].append(proc)

    return {k: v for k, v in result.items() if v}
