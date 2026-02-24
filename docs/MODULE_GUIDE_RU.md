# Руководство по разработке модулей

Это руководство объясняет, как создавать пользовательские модули для SBS Helper AI Telegram Bot.

## Обзор архитектуры

Бот использует модульную архитектуру, где каждая функция (валидация заявок, обработка изображений и т.д.) реализована как независимый модуль. Каждый модуль имеет свои:

- **messages.py** - Сообщения и тексты для пользователей
- **settings.py** - Конфигурация модуля и константы
- **keyboards.py** - Построители клавиатур Telegram
- **\*_bot_part.py** - Основные обработчики бота и логика

## Структура модуля

```
src/sbs_helper_telegram_bot/
├── base_module.py          # Базовый класс для всех модулей
├── telegram_bot/           # Основная оркестрация бота
│   └── telegram_bot.py     # Точка входа, регистрирует все модули
├── ticket_validator/       # Пример модуля
│   ├── __init__.py
│   ├── messages.py         # Сообщения модуля
│   ├── settings.py         # Настройки модуля
│   ├── keyboards.py        # Построители клавиатур
│   ├── ticket_validator_bot_part.py  # Обработчики бота
│   └── ...                 # Другие файлы модуля
└── your_module/            # Ваш пользовательский модуль
    ├── __init__.py
    ├── messages.py
    ├── settings.py
    ├── keyboards.py
    └── your_module_bot_part.py
```

## Создание нового модуля

### Шаг 1: Создание директории модуля

Создайте новую директорию в `src/sbs_helper_telegram_bot/`:

```bash
mkdir src/sbs_helper_telegram_bot/my_module
touch src/sbs_helper_telegram_bot/my_module/__init__.py
```

### Шаг 2: Создание messages.py

Определите все пользовательские сообщения для вашего модуля:

```python
"""
Сообщения модуля

Все пользовательские сообщения для моего модуля.
Сообщения используют формат Telegram MarkdownV2 при необходимости.
"""

# Основные сообщения
MESSAGE_SUBMENU = "🔧 *Мой модуль*\n\nВыберите действие из меню:"

MESSAGE_HELP = """*Справка по модулю*

Этот модуль делает что\\-то полезное\\.

*Команды:*
• `/mycommand` \\- сделать что\\-то"""

MESSAGE_SUCCESS = "✅ Операция успешно завершена\\!"

MESSAGE_ERROR = "❌ Произошла ошибка\\. Пожалуйста\\, попробуйте снова\\."
```

### Шаг 3: Создание settings.py

Определите конфигурацию модуля:

```python
"""
Настройки модуля

Настройки конфигурации модуля.
"""

from typing import Final, List

# Метаданные модуля
MODULE_NAME: Final[str] = "Мой модуль"
MODULE_DESCRIPTION: Final[str] = "Делает что-то полезное"
MODULE_VERSION: Final[str] = "1.0.0"
MODULE_AUTHOR: Final[str] = "Ваше имя"

# Кнопка главного меню для этого модуля
MENU_BUTTON_TEXT: Final[str] = "🔧 Мой модуль"

# Конфигурация кнопок подменю
SUBMENU_BUTTONS: Final[List[List[str]]] = [
    ["📋 Действие 1", "📜 Действие 2"],
    ["ℹ️ Справка"],
    ["🏠 Главное меню"]
]

# Специфичные настройки модуля
MY_SETTING: Final[int] = 100
ANOTHER_SETTING: Final[str] = "значение"
```

### Шаг 4: Создание keyboards.py

Определите построители клавиатур:

```python
"""
Клавиатуры модуля

Построители клавиатур Telegram для модуля.
"""

from telegram import ReplyKeyboardMarkup
from . import settings


def get_submenu_keyboard() -> ReplyKeyboardMarkup:
    """
    Построить клавиатуру подменю модуля.
    
    Returns:
        ReplyKeyboardMarkup для подменю модуля
    """
    return ReplyKeyboardMarkup(
        settings.SUBMENU_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False
    )
```

### Шаг 5: Создание основной части бота

Создайте файл основных обработчиков:

```python
"""
Обработчики бота модуля

Обработчики Telegram бота для модуля.
"""

from telegram import Update, constants
from telegram.ext import ContextTypes, ConversationHandler
import logging

from src.common.telegram_user import check_if_user_legit, update_user_info_from_telegram
from src.common.messages import MESSAGE_PLEASE_ENTER_INVITE

# Импорт компонентов модуля
from . import messages
from . import settings
from .keyboards import get_submenu_keyboard

logger = logging.getLogger(__name__)

# Состояния диалога (если требуется)
WAITING_FOR_INPUT = 1


async def my_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработка команды /mycommand.
    """
    # Проверка авторизации
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(MESSAGE_PLEASE_ENTER_INVITE)
        return
    
    update_user_info_from_telegram(update.effective_user)
    
    # Ваша логика здесь
    await update.message.reply_text(
        messages.MESSAGE_SUBMENU,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=get_submenu_keyboard()
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать справку по модулю."""
    await update.message.reply_text(
        messages.MESSAGE_HELP,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
```

### Шаг 6: Регистрация модуля в главном боте

Отредактируйте `src/sbs_helper_telegram_bot/telegram_bot/telegram_bot.py`:

```python
# Добавьте импорты
from src.sbs_helper_telegram_bot.my_module import messages as my_messages
from src.sbs_helper_telegram_bot.my_module import keyboards as my_keyboards
from src.sbs_helper_telegram_bot.my_module.my_module_bot_part import (
    my_command,
    help_command as my_help_command,
)

# Добавьте регистрацию обработчика в main()
application.add_handler(CommandHandler("mycommand", my_command))

# Добавьте обработку кнопки меню в text_entered()
elif text == "🔧 Мой модуль":
    await update.message.reply_text(
        my_messages.MESSAGE_SUBMENU,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=my_keyboards.get_submenu_keyboard()
    )
```


## Лучшие практики

### 1. Держите модули независимыми

- Импортируйте только из `src.common.*` для общих утилит
- Храните данные, специфичные для модуля, в файлах модуля
- Не импортируйте из других модулей, если это не абсолютно необходимо

### 2. Форматирование сообщений

- Используйте экранирование MarkdownV2 для специальных символов: `_*[]()~\`>#+-=|{}.!`
- Храните экранированные сообщения в `messages.py`
- Вспомогательная функция для экранирования:

```python
def escape_md(text: str) -> str:
    """Экранировать специальные символы для MarkdownV2."""
    special = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special:
        text = str(text).replace(char, f'\\{char}')
    return text
```

### 3. Авторизация

Всегда проверяйте авторизацию пользователя:

```python
if not check_if_user_legit(update.effective_user.id):
    await update.message.reply_text(MESSAGE_PLEASE_ENTER_INVITE)
    return
```

### 4. Обработка ошибок

Оборачивайте операции с базой данных и внешние вызовы:

```python
try:
    result = do_something()
except Exception as e:
    logger.error(f"Ошибка: {e}", exc_info=True)
    await update.message.reply_text(
        messages.MESSAGE_ERROR,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
```

### 5. Логирование

Используйте логгер, специфичный для модуля:

```python
import logging
logger = logging.getLogger(__name__)

logger.info("Операция завершена")
logger.error("Произошла ошибка", exc_info=True)
```

### 6. Сценарии с состоянием

- Перед обращением к данным в `context.user_data` проверяйте наличие ключа, так как команда `/menu` может сбросить состояние диалога
- При отсутствии данных уведомляйте пользователя и перезапускайте сценарий с первого шага

## Использование базового класса модуля

Для более продвинутых модулей наследуйтесь от `BotModule`:

```python
from src.sbs_helper_telegram_bot.base_module import BotModule
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import BaseHandler, CommandHandler, ContextTypes
from typing import List, Optional, Dict

from . import messages
from . import settings
from .keyboards import get_submenu_keyboard


class MyModule(BotModule):
    
    @property
    def name(self) -> str:
        return settings.MODULE_NAME
    
    @property
    def description(self) -> str:
        return settings.MODULE_DESCRIPTION
    
    @property
    def version(self) -> str:
        return settings.MODULE_VERSION
    
    def get_handlers(self) -> List[BaseHandler]:
        return [
            CommandHandler("mycommand", self.handle_command),
        ]
    
    def get_menu_button(self) -> Optional[str]:
        return settings.MENU_BUTTON_TEXT
    
    async def handle_menu_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        if update.message.text == settings.MENU_BUTTON_TEXT:
            await update.message.reply_text(
                messages.MESSAGE_SUBMENU,
                reply_markup=get_submenu_keyboard()
            )
            return True
        return False
    
    def get_commands(self) -> Dict[str, str]:
        return {
            "mycommand": "Команда моего модуля"
        }
    
    def get_submenu_keyboard(self, user_id: int) -> Optional[ReplyKeyboardMarkup]:
        return get_submenu_keyboard()
    
    async def handle_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Реализация обработчика
        pass
```

## Доступ к базе данных

Если вашему модулю нужен доступ к базе данных:

```python
from src.common.database import get_db_connection, get_cursor

def get_my_data(user_id: int) -> dict:
    with get_db_connection() as conn:
        with get_cursor(conn) as cursor:
            cursor.execute(
                "SELECT * FROM my_table WHERE user_id = %s",
                (user_id,)
            )
            return cursor.fetchone()
```

## Пример ConversationHandler

Для многошаговых взаимодействий:

```python
from telegram.ext import ConversationHandler, CommandHandler, MessageHandler, filters

STEP_ONE, STEP_TWO = range(2)

async def start_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Введите что-нибудь:")
    return STEP_ONE

async def handle_step_one(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['step_one'] = update.message.text
    await update.message.reply_text("Введите что-нибудь еще:")
    return STEP_TWO

async def handle_step_two(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Обработка данных
    await update.message.reply_text("Готово!")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Отменено.")
    return ConversationHandler.END

def get_conversation_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("myconvo", start_conversation)],
        states={
            STEP_ONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_step_one)],
            STEP_TWO: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_step_two)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
```

## Тестирование вашего модуля

Создайте тесты в директории `tests/`:

```python
# tests/test_my_module.py
import pytest
from src.sbs_helper_telegram_bot.my_module import messages, settings

def test_messages_defined():
    assert hasattr(messages, 'MESSAGE_SUBMENU')
    assert hasattr(messages, 'MESSAGE_HELP')

def test_settings_defined():
    assert settings.MODULE_NAME
    assert settings.MODULE_VERSION
```

## Чек-лист модуля

Перед выпуском вашего модуля:

- [ ] Все сообщения определены в `messages.py`
- [ ] Все настройки в `settings.py`
- [ ] Клавиатуры в `keyboards.py`
- [ ] Проверки авторизации во всех обработчиках
- [ ] Обработка ошибок для всех операций
- [ ] Правильное логирование
- [ ] Написаны тесты
- [ ] README или документация в директории модуля
- [ ] Модуль зарегистрирован в главном боте
