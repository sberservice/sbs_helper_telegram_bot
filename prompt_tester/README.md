# Prompt Tester — слепое A/B тестирование промптов

Инструмент для попарного (pairwise) слепого сравнения комбинаций `(system_prompt + user_message + model + temperature)` при генерации summary документов RAG-базы.

## Возможности

- **CRUD промптов**: создание, редактирование, клонирование, архивирование пар (system\_prompt + user\_message)
- **Слепое сравнение**: оценщик видит только Summary A / Summary B без привязки к промптам
- **LLM\-as\-Judge**: автоматическая оценка через LLM с защитой от позиционного bias
- **Стратифицированная выборка**: документы делятся на малые, средние и крупные
- **Elo \+ Win Rate**: рейтинговая система для ранжирования промптов
- **Split\-view**: документ слева, два summary справа
- **Клавиатурные хоткеи**: `1` — A лучше, `2` — ничья, `3` — B лучше, `S` — пропуск
- **Возобновляемые сессии**: можно продолжить тест позже
- **Прозрачные статусы выполнения**: `generating -> judging -> in_progress/completed` для корректного отображения этапа LLM-as-Judge

## Установка

### 1\. База данных

```bash
mysql -u root -p sbs_helper < sql/prompt_tester_setup.sql
```

Для уже существующей БД (обновление до релиза 0.3.0 Prompt Tester):

```bash
mysql -u root -p sbs_helper < sql/prompt_tester_add_judging_status.sql
```

### 2\. Зависимости бэкенда

```bash
pip install -r prompt_tester/requirements.txt
```

### 3\. Зависимости фронтенда

```bash
cd prompt_tester/frontend
npm install
npm run build
```

## Запуск

### Production (собранный фронтенд)

```bash
python -m prompt_tester
```

Откройте http://localhost:8080

Если Prompt Tester смонтирован внутри Admin Web как sub-application, используйте путь `/prompt-tester/` (например, `http://localhost:8090/prompt-tester/`).
В этом режиме в верхней панели доступна кнопка «← Админ-панель» для возврата на главную страницу админки.

### Разработка (с hot\-reload)

Терминал 1 — бэкенд:
```bash
python -m prompt_tester
```

Терминал 2 — фронтенд:
```bash
cd prompt_tester/frontend
npm run dev
```

Откройте http://localhost:5173 (проксирует API на :8080)

## Структура

```
prompt_tester/
├── __init__.py
├── __main__.py              # Точка входа
├── requirements.txt
├── backend/
│   ├── __init__.py
│   ├── app.py               # FastAPI приложение
│   ├── db.py                # SQL-запросы
│   ├── models.py            # Pydantic-модели
│   ├── document_sampler.py  # Стратифицированная выборка
│   ├── summary_generator.py # Генерация summary через LLM
│   ├── llm_judge.py         # LLM-as-Judge
│   └── scoring.py           # Elo + Win Rate
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── api.ts
│       ├── index.css
│       ├── pages/
│       │   ├── PromptsPage.tsx
│       │   ├── SetupPage.tsx
│       │   ├── TestPage.tsx
│       │   ├── ResultsPage.tsx
│       │   └── SessionsPage.tsx
│       └── components/
│           ├── PromptEditor.tsx
│           ├── DocumentPanel.tsx
│           ├── SummaryCard.tsx
│           └── ProgressBar.tsx
```

## Рабочий процесс

1. **Промпты** — создайте минимум 2 пары `(system_prompt + user_message)`
2. **Настройка теста** — выберите промпты, количество документов и режим оценки
3. **Слепая оценка** — сравнивайте summary попарно, не зная какой промпт их сгенерировал
4. **Результаты** — посмотрите рейтинг Elo и Win Rate для каждого промпта

## Шаблон System Prompt

В system prompt доступны переменные:

| Переменная | Описание |
|---|---|
| `{document_name}` | Название документа |
| `{document_excerpt}` | Текст документа (до 12000 символов) |
| `{max_summary_chars}` | Лимит символов для summary (1200) |

## Режимы оценки

| Режим | Описание |
|---|---|
| `human` | Только ручная оценка через интерфейс |
| `llm` | Только автоматическая оценка через LLM-as-Judge |
| `both` | Оба: сначала LLM-Judge, потом ручная оценка |

## Статусы сессии

| Статус | Описание |
|---|---|
| `generating` | Генерируются summary для документов и выбранных промптов |
| `judging` | LLM-as-Judge выполняет автоматическую попарную оценку |
| `in_progress` | Доступно ручное голосование (режимы `human` и `both`) |
| `completed` | Все сравнения в рамках выбранного режима завершены |
| `abandoned` | Сессия остановлена вручную |
