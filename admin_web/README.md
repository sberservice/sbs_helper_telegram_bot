# SBS Archie Admin Web

Единая веб-платформа администрирования SBS Archie с Telegram-аутентификацией и RBAC.

## Возможности

- **Telegram Login Widget** — аутентификация через Telegram-аккаунт
- **Password Login** — альтернативный вход по логину и паролю
- **RBAC** — ролевая модель доступа (super_admin, admin, expert, viewer)
- **Модульная архитектура** — расширяемая система модулей на базе `WebModule` ABC
- **Group Knowledge** — единый модуль аналитики, валидации и тестирования Q&A из Telegram-групп:
  - *Статистика* — обзорные метрики, тайм-лайн, распределение уверенности
    - *Q&A-пары* — полный каталог с фильтрацией, пагинацией и просмотром сохранённого LLM-запроса для отладки генерации
    - *Экспертная валидация* — проверка Q&A-пар с горячими клавишами (`Y,Y` / `N,N` / `S`), цепочками сообщений и просмотром сохранённого LLM-запроса
        - Тестовые генерации сохраняются изолированно в `gk_prompt_tester_*` и не попадают в основной корпус `gk_qa_pairs`
  - *Группы* — мониторируемые Telegram-группы
    - *Автоответчик* — лог live/dry-run ответов и отдельный subpage «Обзор» со статистикой по диапазону дат
      - *Изображения* — очередь обработки скриншотов GigaChat Vision, ручная загрузка изображений и превью файлов
    - *Image Prompt Tester* — отдельный blind A/B тестер промптов описания изображений (Elo, модель, сессии, кастомные промпты, глобальная статистика, предварительный расчёт числа сравнений, случайная выборка изображений)
    - *Final Prompt Tester* — отдельный blind A/B тестер финального промпта ответа пользователю (`_ANSWER_PROMPT_BASE`) с ручным вводом тестовых вопросов, Elo-рейтингов, клонами промптов и сессий; клонированные сессии создаются как редактируемый `draft` и запускаются вручную
    - *Message Browser* — просмотр сырых сообщений `gk_messages` с фильтрами по группе/пользователю/дате/статусам, индикаторами chain/analyzer/question, сплит-экраном для просмотра цепочки и полем результата обработки автоответчиком (`LIVE`/`DRY` + confidence)
    - *Песочница поиска* — гибридный BM25 + Vector + RRF поиск по реальному `QASearchService` с выбором модели, температурой генерации, загрузкой изображения (vision-описание + добавление gist в запрос), предпросмотром итогового ответа автоответчика и отображением этапов выполнения запроса
    - *Термины* — LLM-сканирование аббревиатур по диапазону дат, ручной запуск пересчёта `message_count`, автоматический пересчёт `message_count` после успешного сканирования, сортировка по частоте использования и просмотр примеров сообщений с выбранным термином (по `message_text`) для проверки релевантности
    - *Настройки* — runtime-управление LLM-провайдерами/моделями и ключевыми параметрами Group Knowledge (пороги уверенности, top-k контекста, включение llm_inferred, фильтр `tier=низкая` для финального LLM-контекста, лимит числа аббревиатур в LLM-промпте)

    ### Совместимость данных GK API

    - Backend вкладок Group Knowledge возвращает frontend-совместимые поля даже при изменениях SQL-агрегатов во внутренних слоях (`db_stats`, `db_groups`, `db_responder`).
    - Для «Статистики» нормализуются метрики overview/timeline/distribution, для «Групп» — плоские поля карточек и detail-метрики, для «Автоответчика» — алиас `total_entries`.
- **Prompt Tester** — запуск A/B тестера промптов из дашборда админ-панели в текущей вкладке
- **RAG** — отдельный раздел верхнего меню с подпунктами:
    - *Документы* — список документов корпуса из БД с фильтрами/поиском/сортировкой/пагинацией и агрегированными метриками
    - *Prompt Tester* — слепое A/B сравнение промптов
    - *Статистика* — агрегированные метрики RAG-корпуса (документы, чанки, сводки, эмбеддинги, запросы)
- **Dev-режим** — работа без Telegram-верификации для локальной разработки
- **Менеджер процессов** — компактный обзор карточек процессов для экранов с большим числом демонов, включая быстрые кнопки `Play`/`Stop` с подтверждением
- **The Helper** — отдельная страница в верхнем меню с подменю «Настройки групп» (управление `config/helper_groups.json`)

## Архитектура

```
admin_web/
├── __init__.py
├── __main__.py              ← Точка входа: python -m admin_web
├── core/
│   ├── app.py               ← FastAPI-приложение
│   ├── auth.py              ← Telegram HMAC-верификация + cookie-сессии
│   ├── rbac.py              ← RBAC-зависимости для FastAPI
│   ├── db.py                ← Сессии, роли, права в MySQL
│   └── models.py            ← Pydantic-модели (WebUser, WebRole, и т.д.)
├── modules/
│   ├── base.py              ← Абстрактный WebModule (ABC)
│   ├── expert_validation/   ← Legacy-модуль экспертной валидации (обратная совместимость)
│   │   ├── db.py
│   │   └── router.py
│   └── gk_knowledge/        ← Модуль Group Knowledge (13 вкладок)
│       ├── module.py         ← GKKnowledgeModule
│       ├── router.py         ← Главный роутер + подроутеры
│       ├── db_stats.py       ← Агрегированная статистика
│       ├── db_qa_pairs.py    ← Каталог Q&A-пар
│       ├── db_expert_validation.py ← SQL для экспертной валидации
│       ├── db_prompt_tester.py  ← CRUD + Elo для тестера промптов
│       ├── db_image_prompt_tester.py ← CRUD + Elo для тестера image-промптов
│       ├── db_final_prompt_tester.py ← CRUD + Elo для тестера финального промпта ответа
│       ├── db_groups.py      ← Список групп и детальная статистика
│       ├── db_responder.py   ← Лог автоответчика
│       ├── db_images.py      ← Очередь изображений
│       └── search_service.py ← Обёртка гибридного поиска
└── frontend/                ← React SPA (TypeScript + Vite)
    ├── src/
    │   ├── App.tsx           ← Маршрутизация + навигация
    │   ├── api.ts            ← API-клиент
    │   ├── auth.tsx          ← AuthContext + AuthProvider
    │   ├── pages/
    │   │   ├── LoginPage.tsx
    │   │   ├── DashboardPage.tsx
    │   │   ├── GKKnowledgePage.tsx  ← Главная страница с Tab Bar
    │   │   ├── HelperPage.tsx       ← Отдельная страница настроек The Helper
    │   │   ├── RagPage.tsx          ← Отдельная страница RAG с подменю
    │   │   └── gk_tabs/             ← Компоненты вкладок
    │   │       ├── StatsTab.tsx
    │   │       ├── QAPairsTab.tsx
    │   │       ├── ExpertValidationTab.tsx
    │   │       ├── PromptTesterTab.tsx
    │   │       ├── GroupsTab.tsx
    │   │       ├── ResponderTab.tsx
    │   │       ├── ImagesTab.tsx
    │   │       ├── ImagePromptTesterTab.tsx
    │   │       ├── FinalPromptTesterTab.tsx
    │   │       ├── SearchTab.tsx
    │   │       ├── TermsTab.tsx
    │   │       ├── SettingsTab.tsx
    │   │       └── QAAnalyzerSandboxTab.tsx
    │   │   └── rag_tabs/            ← Компоненты вкладок RAG
    │   │       ├── RagDocumentsTab.tsx
    │   │       ├── PromptTesterTab.tsx
    │   │       └── RagStatsTab.tsx
    │   └── components/
    │       └── ProtectedRoute.tsx
    └── package.json
```

## Запуск

### Подготовка базы данных

```bash
mysql -u root -p < sql/admin_web_setup.sql
mysql -u root -p < sql/gk_expert_validations_setup.sql
mysql -u root -p < sql/gk_image_prompt_tester_setup.sql
mysql -u root -p < sql/gk_final_prompt_tester_setup.sql
mysql -u root -p < sql/gk_final_prompt_tester_confidence_reason_text.sql
mysql -u root -p < sql/gk_final_prompt_tester_sessions_add_draft_status.sql
mysql -u root -p < sql/app_settings_setup.sql
```

### Backend

```bash
python -m admin_web
```

Переменные окружения:
- `ADMIN_WEB_PORT` — порт сервера (по умолчанию `8090`)
- `ADMIN_WEB_HOST` — хост (по умолчанию `127.0.0.1`)
- `ADMIN_WEB_DEV_MODE` — `true` для отключения Telegram-верификации
- `ADMIN_WEB_SESSION_TTL_HOURS` — время жизни сессии (по умолчанию `72`)
- `ADMIN_WEB_TELEGRAM_BOT_USERNAME` — username Telegram-бота для Login Widget (без `@`)
- `ADMIN_WEB_PASSWORD_AUTH_ENABLED` — включить password-вход (`true`/`false`, по умолчанию `true`)
- `ADMIN_WEB_PASSWORD_MIN_LENGTH` — минимальная длина пароля (по умолчанию `10`)
- `ADMIN_WEB_PASSWORD_RATE_LIMIT_WINDOW_SECONDS` — окно rate-limit для входа по паролю (по умолчанию `300`)
- `ADMIN_WEB_PASSWORD_RATE_LIMIT_MAX_ATTEMPTS` — максимум неуспешных попыток в окне (по умолчанию `10`)
- `ADMIN_WEB_PASSWORD_LOCKOUT_THRESHOLD` — порог подряд неуспешных попыток до блокировки (по умолчанию `5`)
- `ADMIN_WEB_PASSWORD_LOCKOUT_MINUTES` — длительность временной блокировки (по умолчанию `15`)

### Frontend (разработка)

```bash
cd admin_web/frontend
npm install
npm run dev
```

Dev-сервер на `http://localhost:5174` проксирует API-запросы к backend на порт 8090.

### Frontend (production)

```bash
cd admin_web/frontend
npm run build
```

Backend автоматически раздаёт statику из `frontend/dist/`.

## Роли и права

| Роль | Описание |
|------|----------|
| `super_admin` | Полный доступ ко всем модулям и управлению ролями |
| `admin` | Доступ к назначенным модулям с правом редактирования |
| `expert` | Валидация Q&A-пар (view + edit в expert_validation) |
| `viewer` | Только просмотр назначенных модулей |

Бот-администраторы (users.is_admin=1) автоматически получают `super_admin` при первом входе.

Права по ролям настраиваются в таблице `web_role_permissions`.

### Первый `super_admin` без Telegram

Если Telegram-вход недоступен, первый `super_admin` можно создать напрямую в БД через локальный password-аккаунт.

1. Убедитесь, что включён password-вход:

```bash
export ADMIN_WEB_PASSWORD_AUTH_ENABLED=true
```

2. Сгенерируйте PBKDF2-хеш пароля (тот же формат, что использует backend):

```bash
python - <<'PY'
from admin_web.core import db as web_db
print(web_db.hash_password('ChangeMe_123!'))
PY
```

3. Создайте standalone-аккаунт и назначьте роль `super_admin` (замените значения):

```sql
-- Пример значений
SET @login = 'root_admin';
SET @password_hash = 'PASTE_HASH_HERE';
SET @principal_id = 9000000000000001;

INSERT INTO web_local_accounts (
    login,
    password_hash,
    principal_telegram_id,
    linked_telegram_id,
    display_name,
    is_active,
    created_by,
    updated_by
) VALUES (
    @login,
    @password_hash,
    @principal_id,
    NULL,
    'Initial super admin',
    TRUE,
    NULL,
    NULL
);

INSERT INTO web_user_roles (telegram_id, role, created_by)
VALUES (@principal_id, 'super_admin', NULL)
ON DUPLICATE KEY UPDATE
    role = VALUES(role),
    created_by = VALUES(created_by);
```

4. Перезапустите backend (`python -m admin_web`) и войдите через форму Password Login.

Примечания:
- `@principal_id` должен быть уникальным в `web_local_accounts.principal_telegram_id`.
- После первого входа рекомендуется сразу сменить временный пароль.

## Password-аутентификация

Password-вход работает параллельно с Telegram-входом и использует локальные web-аккаунты.

- Аккаунты создаются и управляются только `super_admin` через API.
- Поддерживаются два типа аккаунтов:
    - связанный с `linked_telegram_id`;
    - standalone (без Telegram-привязки).
- Защита входа включает:
    - policy сложности пароля;
    - rate-limit неуспешных попыток;
    - временный lockout после порога ошибок.

SQL-таблицы для password auth создаются в `sql/admin_web_setup.sql`:
- `web_local_accounts`
- `web_auth_attempts`

## Экспертная валидация

Модуль для проверки Q&A-пар, извлечённых Group Knowledge из чатов поддержки.

### Workflow

1. Открыть раздел «Валидация» или нажать «Начать проверку»
2. Просмотреть вопрос и ответ пары
3. Развернуть цепочку сообщений клавишей `C` для контекста
4. Одобрить (`Y,Y`) или отклонить (`N,N`) с двойным подтверждением в течение 2 секунд, либо пропустить (`S`)
5. Добавить комментарий при необходимости

Кнопка «Начать проверку» автоматически запускает режим ревью с приоритетом пар с низкой уверенностью, чтобы спорные Q&A разбирались в первую очередь.

### Hotkeys

| Клавиша | Действие |
|---------|----------|
| `Y`, затем `Y` (≤2 сек) | Одобрить пару |
| `N`, затем `N` (≤2 сек) | Отклонить пару |
| `S` | Пропустить |
| `C` | Показать/скрыть цепочку |
| `←` / `→` | Навигация между парами |
| `Esc` | Вернуться к списку |

Примечание: первый клик по кнопкам «Одобрить/Отклонить» (или первое нажатие `Y`/`N`) только подготавливает действие. Для отправки вердикта требуется повторить то же действие в течение 2 секунд.

### Цепочка сообщений

Для каждой Q&A-пары реконструируется цепочка сообщений из `gk_messages`:
1. По `question_message_id` находится исходное сообщение
2. По `reply_to_message_id` восстанавливается корень reply-цепочки
3. BFS-обходом собираются все ответы в дереве
4. Добавляются соседние сообщения (±5 мин) от участников цепочки

**Важно:** невалидированные пары по-прежнему используются автоответчиком. Экспертная валидация — дополнительный слой качества.

## Добавление нового модуля

1. Создать директорию `admin_web/modules/<module_name>/`
2. Наследовать `WebModule` из `admin_web.modules.base`
3. Реализовать `key`, `name`, `get_router()` 
4. Зарегистрировать в `admin_web/core/app.py`: `register_module(MyModule())`
5. Добавить права в `sql/admin_web_setup.sql`
6. Создать фронтенд-страницу и маршрут в `App.tsx`

Пример:

```python
from admin_web.modules.base import WebModule
from fastapi import APIRouter

class MyModule(WebModule):
    @property
    def key(self) -> str:
        return "my_module"

    @property
    def name(self) -> str:
        return "Мой модуль"

    def get_router(self) -> APIRouter:
        router = APIRouter(tags=["my-module"])
        # ... маршруты ...
        return router
```
