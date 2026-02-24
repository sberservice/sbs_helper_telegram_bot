# Модуль геймификации

Система достижений, рейтингов и цифровых профилей пользователей SBS Helper AI.

## Описание

Модуль геймификации мотивирует пользователей активнее использовать бота, начисляя очки за действия и выдавая достижения. Интегрируется с другими модулями через систему событий.

## Возможности

### Для пользователей

- **Профиль** — просмотр своего ранга, очков и достижений
- **Достижения** — список всех полученных достижений с уровнями
- **Рейтинги** — таблицы лидеров по очкам и достижениям
- **Просмотр профилей** — возможность посмотреть профиль другого пользователя из рейтинга

### Для администраторов

- Просмотр профиля любого пользователя по ID или username
- Настройка очков за различные действия
- Просмотр списка всех достижений
- Статистика системы

## Установка

### 1. Создание таблиц базы данных

```bash
mysql -u <user> -p <database> < scripts/gamification_setup.sql
```

## Структура модуля

```
gamification/
├── __init__.py              # Экспорт публичных функций
├── settings.py              # Константы, состояния, кнопки
├── messages.py              # Тексты сообщений
├── keyboards.py             # Клавиатуры (reply и inline)
├── events.py                # Шина событий
├── gamification_logic.py    # Бизнес-логика
├── gamification_bot_part.py # Обработчики пользователей
├── admin_panel_bot_part.py  # Обработчики админов
└── README.md                # Документация
```

## База данных

### Таблицы

| Таблица | Описание |
|---------|----------|
| `gamification_achievements` | Определения достижений (пороги, описания) |
| `gamification_user_progress` | Прогресс пользователей к достижениям |
| `gamification_user_achievements` | Полученные достижения |
| `gamification_scores` | Лог начисления очков |
| `gamification_user_totals` | Кэш итогов (очки, достижения) |
| `gamification_events` | Лог событий |
| `gamification_settings` | Системные настройки |
| `gamification_score_config` | Настройка очков за действия |

### Уровни достижений

Каждое достижение имеет три уровня:

| Уровень | Описание |
|---------|----------|
| 🥉 Бронза | Начальный уровень |
| 🥈 Серебро | Средний уровень |
| 🥇 Золото | Максимальный уровень |

Пороги задаются индивидуально для каждого достижения в полях `threshold_bronze`, `threshold_silver`, `threshold_gold`.

### Ранги

По умолчанию настроено 5 рангов:

| Ранг | Очки от |
|------|---------|
| 🌱 Новичок | 0 |
| 📘 Специалист | 100 |
| ⭐ Эксперт | 500 |
| 🏅 Мастер | 2000 |
| 👑 Легенда | 5000 |

## Система событий

Модуль использует шину событий для слабой связанности. Другие модули вызывают `emit_event()`, а система геймификации обрабатывает события.

### Использование

```python
from src.sbs_helper_telegram_bot.gamification import emit_event

# В обработчике модуля:
await emit_event("ktr.lookup", user_id, {"code": code})
```

### Интеграция с другими модулями

1. Импортировать `emit_event()` в свой модуль
2. Зарегистрировать событие в `events.py`
3. Добавить данные в БД (достижение и очки за действие)

```python
# В events.py
register_event(
    event_type="module.action",
    achievement_code="module_action",
    score_action="module_action"
)
```

## Пользовательский интерфейс

### Главное меню

Кнопка **🏆 Достижения** в главном меню открывает подменю:

- **👤 Мой профиль** — ранг, очки, статистика
- **🎖️ Мои достижения** — список полученных достижений
- **📊 Рейтинги** — таблицы лидеров

### Рейтинги

Два типа рейтингов:
- **По очкам** — сортировка по сумме очков
- **По достижениям** — сортировка по количеству достижений

Три периода:
- За месяц
- За год
- За всё время

## Админ-панель

Вход через подменю достижений → **🔐 Админ профилей**

### Функции

| Кнопка | Описание |
|--------|----------|
| 🔍 Найти профиль | Поиск пользователя по ID или username |
| ⚙️ Настройки очков | Изменение очков за действия |
| 📋 Все достижения | Список всех достижений в системе |
| 📈 Статистика системы | Общая статистика |
| 🔒 Скрытие имён | Анонимизация имён в рейтингах |

## Внешние скрипты

### add_daily_scores.py

Скрипт для массового начисления очков:

```bash
# Одному пользователю
python scripts/add_daily_scores.py --userid 123456789 --points 10 --reason "Бонус"

# Списку из файла
python scripts/add_daily_scores.py --file users.txt --points 5 --reason "Ежедневный бонус"

# Всем активным пользователям
python scripts/add_daily_scores.py --all-active --points 1 --reason "Активность"

# Тестовый запуск (без изменений в БД)
python scripts/add_daily_scores.py --all-active --points 10 --dry-run
```

## Конфигурация

### Настройка очков за действия

```sql
-- Просмотр текущих настроек
SELECT * FROM gamification_score_config;

-- Изменение очков
UPDATE gamification_score_config SET points = 10 WHERE action_code = 'ktr_lookup';
```

### Настройка рангов

```sql
UPDATE gamification_settings 
SET setting_value = '{"name": "⭐ Специалист", "min_score": 200}' 
WHERE setting_key = 'rank_2';
```

### Настройка порогов достижений

```sql
UPDATE gamification_achievements 
SET threshold_bronze = 5, threshold_silver = 25, threshold_gold = 100 
WHERE code = 'ktr_lookup';
```

## Примеры SQL-запросов

### Топ-10 пользователей по очкам

```sql
SELECT u.userid, u.username, t.total_score, t.total_achievements
FROM gamification_user_totals t
JOIN telegram_users u ON t.userid = u.userid
ORDER BY t.total_score DESC
LIMIT 10;
```

### Пользователи с золотым достижением

```sql
SELECT u.userid, u.username, a.name
FROM gamification_user_achievements ua
JOIN telegram_users u ON ua.userid = u.userid
JOIN gamification_achievements a ON ua.achievement_id = a.id
WHERE ua.level = 3;
```

---

**Версия:** 1.0.0  
**Обновлено:** Февраль 2026
