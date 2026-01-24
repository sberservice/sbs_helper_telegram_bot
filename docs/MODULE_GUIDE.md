# Module Development Guide

This guide explains how to create custom modules for the SBS Helper Telegram Bot.

## Architecture Overview

The bot uses a modular architecture where each feature (ticket validation, image processing, etc.) is implemented as an independent module. Each module has its own:

- **messages.py** - User-facing messages and texts
- **settings.py** - Module configuration and constants
- **keyboards.py** - Telegram keyboard builders
- **\*_bot_part.py** - Main bot handlers and logic

## Module Structure

```
src/sbs_helper_telegram_bot/
├── base_module.py          # Base class for all modules
├── telegram_bot/           # Main bot orchestration
│   └── telegram_bot.py     # Entry point, registers all modules
├── ticket_validator/       # Example module
│   ├── __init__.py
│   ├── messages.py         # Module messages
│   ├── settings.py         # Module settings
│   ├── keyboards.py        # Keyboard builders
│   ├── ticket_validator_bot_part.py  # Bot handlers
│   └── ...                 # Other module files
└── your_module/            # Your custom module
    ├── __init__.py
    ├── messages.py
    ├── settings.py
    ├── keyboards.py
    └── your_module_bot_part.py
```

## Creating a New Module

### Step 1: Create Module Directory

Create a new directory under `src/sbs_helper_telegram_bot/`:

```bash
mkdir src/sbs_helper_telegram_bot/my_module
touch src/sbs_helper_telegram_bot/my_module/__init__.py
```

### Step 2: Create messages.py

Define all user-facing messages for your module:

```python
"""
My Module Messages

All user-facing messages for my module.
Messages use Telegram MarkdownV2 format where needed.
"""

# Main messages
MESSAGE_SUBMENU = "🔧 *My Module*\n\nSelect an action:"

MESSAGE_HELP = """*My Module Help*

This module does something useful\\.

*Commands:*
• `/mycommand` \\- do something"""

MESSAGE_SUCCESS = "✅ Operation completed successfully\\!"

MESSAGE_ERROR = "❌ An error occurred\\. Please try again\\."
```

### Step 3: Create settings.py

Define module configuration:

```python
"""
My Module Settings

Module-specific configuration settings.
"""

from typing import Final, List

# Module metadata
MODULE_NAME: Final[str] = "My Module"
MODULE_DESCRIPTION: Final[str] = "Does something useful"
MODULE_VERSION: Final[str] = "1.0.0"
MODULE_AUTHOR: Final[str] = "Your Name"

# Main menu button for this module
MENU_BUTTON_TEXT: Final[str] = "🔧 My Module"

# Submenu button configuration
SUBMENU_BUTTONS: Final[List[List[str]]] = [
    ["📋 Action 1", "📜 Action 2"],
    ["ℹ️ Help"],
    ["🏠 Main Menu"]
]

# Module-specific settings
MY_SETTING: Final[int] = 100
ANOTHER_SETTING: Final[str] = "value"
```

### Step 4: Create keyboards.py

Define keyboard builders:

```python
"""
My Module Keyboards

Telegram keyboard builders for my module.
"""

from telegram import ReplyKeyboardMarkup
from . import settings


def get_submenu_keyboard() -> ReplyKeyboardMarkup:
    """
    Build module submenu keyboard.
    
    Returns:
        ReplyKeyboardMarkup for module submenu
    """
    return ReplyKeyboardMarkup(
        settings.SUBMENU_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False
    )
```

### Step 5: Create Main Bot Part

Create the main handlers file:

```python
"""
My Module Bot Handlers

Telegram bot handlers for my module.
"""

from telegram import Update, constants
from telegram.ext import ContextTypes, ConversationHandler
import logging

from src.common.telegram_user import check_if_user_legit, update_user_info_from_telegram
from src.common.messages import MESSAGE_PLEASE_ENTER_INVITE

# Import module-specific components
from . import messages
from . import settings
from .keyboards import get_submenu_keyboard

logger = logging.getLogger(__name__)

# Conversation states (if needed)
WAITING_FOR_INPUT = 1


async def my_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /mycommand command.
    """
    # Check authorization
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(MESSAGE_PLEASE_ENTER_INVITE)
        return
    
    update_user_info_from_telegram(update.effective_user)
    
    # Your logic here
    await update.message.reply_text(
        messages.MESSAGE_SUBMENU,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=get_submenu_keyboard()
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show module help."""
    await update.message.reply_text(
        messages.MESSAGE_HELP,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
```

### Step 6: Register Module in Main Bot

Edit `src/sbs_helper_telegram_bot/telegram_bot/telegram_bot.py`:

```python
# Add imports
from src.sbs_helper_telegram_bot.my_module import messages as my_messages
from src.sbs_helper_telegram_bot.my_module import keyboards as my_keyboards
from src.sbs_helper_telegram_bot.my_module.my_module_bot_part import (
    my_command,
    help_command as my_help_command,
)

# Add handler registration in main()
application.add_handler(CommandHandler("mycommand", my_command))

# Add menu button handling in text_entered()
elif text == "🔧 My Module":
    await update.message.reply_text(
        my_messages.MESSAGE_SUBMENU,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=my_keyboards.get_submenu_keyboard()
    )
```

### Step 7: Add Main Menu Button (Optional)

To add your module to the main menu, edit `config/settings.py`:

```python
MAIN_MENU_BUTTONS: Final[List[List[str]]] = [
    ["✅ Валидация заявок", "📸 Обработать скриншот"],
    ["🔧 My Module"],  # Add your button
    ["🎫 Мои инвайты", "❓ Помощь"]
]
```

## Best Practices

### 1. Keep Modules Independent

- Import only from `src.common.*` for shared utilities
- Keep module-specific data in module files
- Don't import from other modules unless absolutely necessary

### 2. Message Formatting

- Use MarkdownV2 escaping for special characters: `_*[]()~\`>#+-=|{}.!`
- Store escaped messages in `messages.py`
- Helper function for escaping:

```python
def escape_md(text: str) -> str:
    """Escape special characters for MarkdownV2."""
    special = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special:
        text = str(text).replace(char, f'\\{char}')
    return text
```

### 3. Authorization

Always check user authorization:

```python
if not check_if_user_legit(update.effective_user.id):
    await update.message.reply_text(MESSAGE_PLEASE_ENTER_INVITE)
    return
```

### 4. Error Handling

Wrap database operations and external calls:

```python
try:
    result = do_something()
except Exception as e:
    logger.error(f"Error: {e}", exc_info=True)
    await update.message.reply_text(
        messages.MESSAGE_ERROR,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
```

### 5. Logging

Use module-specific logger:

```python
import logging
logger = logging.getLogger(__name__)

logger.info("Operation completed")
logger.error("Error occurred", exc_info=True)
```

## Using the Base Module Class

For more advanced modules, inherit from `BotModule`:

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
            "mycommand": "My module command"
        }
    
    def get_submenu_keyboard(self, user_id: int) -> Optional[ReplyKeyboardMarkup]:
        return get_submenu_keyboard()
    
    async def handle_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Handler implementation
        pass
```

## Database Access

If your module needs database access:

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

## ConversationHandler Example

For multi-step interactions:

```python
from telegram.ext import ConversationHandler, CommandHandler, MessageHandler, filters

STEP_ONE, STEP_TWO = range(2)

async def start_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Enter something:")
    return STEP_ONE

async def handle_step_one(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['step_one'] = update.message.text
    await update.message.reply_text("Enter something else:")
    return STEP_TWO

async def handle_step_two(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Process data
    await update.message.reply_text("Done!")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Cancelled.")
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

## Testing Your Module

Create tests in the `tests/` directory:

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

## Module Checklist

Before releasing your module:

- [ ] All messages defined in `messages.py`
- [ ] All settings in `settings.py`
- [ ] Keyboards in `keyboards.py`
- [ ] Authorization checks in all handlers
- [ ] Error handling for all operations
- [ ] Proper logging
- [ ] Tests written
- [ ] README or documentation in module directory
- [ ] Module registered in main bot
