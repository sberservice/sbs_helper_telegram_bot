# Менеджер процессов

**Версия:** 0.9.1  
**Автор:** SBS Archie Team

## Описание

Модуль администрирования для централизованного управления всеми скриптами и демонами SBS Archie из единого веб-интерфейса. Позволяет запускать, останавливать и перезапускать процессы, выбирать режимы работы (пресеты или произвольные CLI-флаги), просматривать логи в реальном времени и отслеживать историю запусков.

## Возможности

- **18 процессов** по 5 категориям (Core, Group Knowledge, The Helper, RAG, Утилиты)
- **Запуск/остановка/перезапуск** из веб-интерфейса с RBAC-защитой
- **Пресеты** — именованные конфигурации запуска (например, «Live сбор», «Dry-run», «Backfill»)
- **Ручной ввод флагов** — возможность указать произвольные CLI-аргументы
- **Формы запуска** — интерактивные веб-формы для скриптов, требующих выбора параметров (например, выбор группы для тестового режима)
- **Управление группами** — CRUD-интерфейс для конфигурации групп The Helper + просмотр «собранных» групп (вкладка «Группы»)
- **Мониторинг статуса** — PID, uptime, текущий пресет/флаги, автообновление каждые 3–5 секунд
- **WebSocket-логи** — вывод процесса в реальном времени (live mode)
- **История запусков** — полная история с пагинацией и фильтрацией
- **Персистентное состояние** — после перезагрузки системы демоны автоматически восстанавливаются с теми же флагами/пресетами (таблица `process_desired_state`)
- **Авто-рестарт** — мониторинг демонов с автоматическим перезапуском при падении (до 3 попыток)
- **Корректное завершение one-shot** — одноразовые скрипты с `exit_code=0` помечаются как штатно завершённые, а не как `crashed`

## Архитектура

### Backend

| Файл | Назначение |
|------|------------|
| `models.py` | Pydantic-модели: перечисления, определения флагов/пресетов/процессов, API-запросы/ответы |
| `registry.py` | Декларативный реестр всех 18 процессов с командами, флагами и пресетами |
| `db.py` | Слой БД: `process_runs` (история), `process_desired_state` (персистентное состояние) |
| `supervisor.py` | Синглтон-супервизор: управление жизненным циклом, PID-файлы, мониторинг, WebSocket |
| `router.py` | FastAPI-маршрутизатор: REST API + WebSocket для live-логов |
| `groups_api.py` | Sub-router: CRUD-эндпоинты для управления конфигурацией групп GK и The Helper |
| `module.py` | Регистрация модуля в системе `WebModule` |

### Frontend

| Файл | Назначение |
|------|------------|
| `ProcessManagerPage.tsx` | React-компонент с 4 вкладками: Обзор, Процесс, История, Группы |

### База данных

Настройка: `mysql -u root -p < sql/process_manager_setup.sql`

Таблицы:
- `process_runs` — история всех запусков (PID, флаги, пресет, время, код выхода)
- `process_desired_state` — желаемое состояние для демонов (для восстановления после рестарта)

## Категории процессов

| Категория | Процессы |
|-----------|----------|
| **Core** | Telegram Bot, Image Queue, SOOS Queue, Health Check Daemon |
| **Group Knowledge** | GK Collector, GK Analyzer, GK Responder, GK Delete Group Data |
| **The Helper** | The Helper |
| **RAG** | RAG Ops, RAG Directory Ingest, RAG Certification Sync, RAG Vector Backfill, RAG Qdrant Sync |
| **Утилиты** | Sync Chat Members, Add Daily Scores, Release |

## API

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/process-manager/processes` | Все процессы по категориям |
| GET | `/api/process-manager/processes/{key}` | Статус одного процесса |
| GET | `/api/process-manager/processes/{key}/registry` | Флаги и пресеты процесса |
| POST | `/api/process-manager/processes/{key}/start` | Запустить процесс |
| POST | `/api/process-manager/processes/{key}/stop` | Остановить процесс |
| POST | `/api/process-manager/processes/{key}/restart` | Перезапустить процесс |
| GET | `/api/process-manager/processes/{key}/history` | История запусков процесса |
| GET | `/api/process-manager/history` | Общая история запусков |
| GET | `/api/process-manager/processes/{key}/output` | Буфер вывода процесса |
| WS | `/api/process-manager/processes/{key}/logs` | WebSocket для live-логов |

### Groups API

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/process-manager/groups/gk` | Конфигурация GK-групп |
| PUT | `/api/process-manager/groups/gk` | Полная замена конфигурации GK-групп |
| POST | `/api/process-manager/groups/gk/add` | Добавить GK-группу |
| DELETE | `/api/process-manager/groups/gk/{group_id}` | Удалить GK-группу |
| PATCH | `/api/process-manager/groups/gk/{group_id}/toggle` | Включить/отключить GK-группу |
| POST | `/api/process-manager/groups/gk/test-targets` | Добавить группу в список test-target |
| DELETE | `/api/process-manager/groups/gk/test-targets/{group_id}` | Удалить группу из списка test-target |
| PUT | `/api/process-manager/groups/gk/test-target` | Задать тестовую целевую группу |
| DELETE | `/api/process-manager/groups/gk/test-target` | Убрать тестовую целевую группу |
| GET | `/api/process-manager/groups/helper` | Конфигурация Helper-групп |
| PUT | `/api/process-manager/groups/helper` | Полная замена конфигурации Helper-групп |
| POST | `/api/process-manager/groups/helper/add` | Добавить Helper-группу |
| DELETE | `/api/process-manager/groups/helper/{group_id}` | Удалить Helper-группу |
| PATCH | `/api/process-manager/groups/helper/{group_id}/toggle` | Включить/отключить Helper-группу |
| GET | `/api/process-manager/groups/collected` | Группы из БД (gk_messages) |

## Формы запуска

Некоторые скрипты требуют интерактивного ввода данных (выбор группы, указание ID и т.д.), что несовместимо с subprocess-запуском. Для таких случаев реализован механизм **launch forms** — веб-форм, которые собирают данные перед запуском и преобразуют их в CLI-флаги.

### Как это работает

1. Пресет в реестре помечается: `requires_form=True, form_type="gk_test_mode"`
2. При клике на такой пресет в UI открывается модальная форма
3. Пользователь заполняет поля (выбор группы, ввод ID)
4. `form_data` отправляется в API-запрос `POST /start`
5. Router конвертирует `form_data` в CLI-флаги (например, `{"test-real-group-id": 123}` → `--test-real-group-id 123`)

### Доступные формы

| `form_type` | Скрипт | Назначение |
|-------------|--------|------------|
| `gk_test_mode` | GK Collector / GK Responder | Выбор реальной группы и тестового ID для тестового режима |
| `gk_redirect_test` | GK Collector | Выбор группы для перенаправления в redirect-тестовом режиме |
| `gk_delete_group` | GK Delete Group Data | Выбор группы для удаления данных |

### Скрытые пресеты

Пресеты с `hidden=True` скрыты из веб-интерфейса (например, `--manage-groups` — управление группами заменено вкладкой «Группы»).

### Примечание по GK Analyzer

Для запуска анализа всех необработанных данных без текущего дня добавлен пресет **«Необработанные (без сегодня)»** (`--all-unprocessed-except-today`). Это помогает не обрабатывать «живой» день, который ещё наполняется сообщениями.

## Управление группами

Вкладка **«Группы»** в Process Manager управляет конфигурацией The Helper и показывает собранные из БД группы.

CRUD для **GK Groups** и настройка **test-target** перенесены в модуль **Group Knowledge → вкладка «Группы»**.

### Секции

| Секция | Конфиг-файл | Описание |
|--------|-------------|----------|
| Helper Groups | `config/helper_groups.json` | Группы для The Helper |
| Собранные из БД | — | Группы из таблицы `gk_messages` (только чтение) |

### Формат конфигурации

**Helper Groups** (`config/helper_groups.json`):
```json
{
  "groups": [
    {"id": -1001234567890, "title": "Название группы"},
    {"id": -1009876543210, "title": "Отключённая группа", "disabled": true}
  ]
}
```

### Временное отключение групп

Каждая группа может быть временно отключена через кнопку «Активна / Отключена» в таблице.
При отключении группы:

- GK Collector **не собирает** новые сообщения из этой группы
- Автоответчик **не отвечает** на вопросы в этой группе
- The Helper **не слушает** `/helpme` в этой группе
- `gk_analyze.py` **продолжает работать** с уже собранными данными
- Во вкладке GK Knowledge → Группы у отключённых групп отображается метка «Отключена»

Отключение **не удаляет** группу из конфига — она остаётся в JSON-файле с полем `"disabled": true`.
Для применения изменений **необходимо перезапустить** GK Collector / The Helper через менеджер процессов.

## RBAC

| Уровень | Разрешение |
|---------|-----------|
| `view` | Просмотр статусов, логов, истории |
| `edit` | Запуск, остановка, перезапуск процессов |

Роли:
- `super_admin` — полный доступ
- `admin` — view + edit
- `expert` — только view
- `viewer` — только view

## Добавление нового процесса

Добавьте `ProcessDefinition` в список `PROCESS_DEFINITIONS` в `registry.py`:

```python
ProcessDefinition(
    key="my_new_script",
    name="My New Script",
    description="Описание скрипта",
    icon="🔧",
    category=CATEGORY_UTILS,
    process_type=ProcessType.ONE_SHOT,
    command=[sys.executable, "scripts/my_new_script.py"],
    singleton=True,
    flags=[
        FlagDefinition(name="--verbose", flag_type=FlagType.BOOL, description="Подробный вывод"),
    ],
    presets=[
        PresetDefinition(name="По умолчанию", flags=[], icon="▶️"),
    ],
),
```

Процесс автоматически появится в UI без перезапуска (при следующей загрузке страницы).

### Добавление пресета с формой

Если скрипт требует интерактивного ввода, добавьте CLI-флаги для неинтерактивного режима, затем:

1. Добавьте `FlagDefinition` для каждого нового флага в `registry.py`
2. Создайте пресет с `requires_form=True` и уникальным `form_type`
3. Добавьте рендеринг формы в `LaunchFormDialog` (`ProcessManagerPage.tsx`)
4. Router автоматически конвертирует `form_data` → CLI-флаги

```python
PresetDefinition(
    name="Тестовый режим",
    flags=["--test-mode"],
    icon="🧪",
    requires_form=True,
    form_type="my_test_mode",
),
```
