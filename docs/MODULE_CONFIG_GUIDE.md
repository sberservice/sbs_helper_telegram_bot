# Module Configuration Guide

## Overview

The bot's module menu keyboard is now dynamically generated based on configuration defined in `src/common/bot_settings.py`. This eliminates the need to modify code in multiple places when adding or reordering modules.

## How It Works

### Configuration Location

Module configuration is stored in the `MODULE_CONFIG` list in [src/common/bot_settings.py](src/common/bot_settings.py).

### Module Configuration Structure

Each module in `MODULE_CONFIG` is a dictionary with the following fields:

```python
{
    'key': 'module_identifier',           # Unique identifier for the module
    'setting_key': 'module_x_enabled',    # Database setting key for enable/disable
    'button_label': '🔹 Module Name',     # Text displayed on the button
    'order': 1,                            # Display order (lower numbers appear first)
    'columns': 2                           # Number of buttons per row (1 or 2)
}
```

### Example Configuration

```python
MODULE_CONFIG = [
    {
        'key': 'ticket_validator',
        'setting_key': 'module_ticket_validator_enabled',
        'button_label': '✅ Валидация заявок',
        'order': 1,
        'columns': 2
    },
    {
        'key': 'screenshot',
        'setting_key': 'module_screenshot_enabled',
        'button_label': '📸 Обработать скриншот',
        'order': 2,
        'columns': 2
    },
    # ... more modules
]
```

## Common Tasks

### Adding a New Module

1. Add a new entry to `MODULE_CONFIG` in `bot_settings.py`:

```python
{
    'key': 'new_module',
    'setting_key': 'module_new_module_enabled',
    'button_label': '🆕 New Module',
    'order': 7,  # Place it at the end or insert where you want
    'columns': 2
}
```

2. Add the corresponding database setting (if not using defaults):

```sql
INSERT INTO `bot_settings` (`setting_key`, `setting_value`, `updated_timestamp`, `updated_by_userid`)
VALUES ('module_new_module_enabled', '1', UNIX_TIMESTAMP(), NULL);
```

That's it! The module will automatically appear in the keyboard.

### Changing Module Order

Simply modify the `order` field in `MODULE_CONFIG`. Modules are sorted by this field when generating the keyboard.

Example - move feedback to position 3:

```python
{
    'key': 'feedback',
    'setting_key': 'module_feedback_enabled',
    'button_label': '📬 Обратная связь',
    'order': 3,  # Changed from 6 to 3
    'columns': 2
}
```

### Changing Button Layout

Modify the `columns` field:
- `columns: 1` - One button per row (full width)
- `columns: 2` - Two buttons per row (default)

Example - make a module take full width:

```python
{
    'key': 'certification',
    'setting_key': 'module_certification_enabled',
    'button_label': '📝 Аттестация',
    'order': 4,
    'columns': 1  # Full width button
}
```

### Renaming a Module Button

Just change the `button_label` field:

```python
{
    'key': 'feedback',
    'setting_key': 'module_feedback_enabled',
    'button_label': '💬 Обратная связь',  # Changed emoji
    'order': 6,
    'columns': 2
}
```

### Removing a Module

Remove the module's entry from `MODULE_CONFIG`. The keyboard will automatically update.

## API Reference

### Functions in `bot_settings.py`

#### `get_modules_config(enabled_only=True)`

Returns module configuration in display order.

**Parameters:**
- `enabled_only` (bool): If True, return only enabled modules. If False, return all modules.

**Returns:**
- List of module configuration dictionaries, sorted by `order` field.

**Example:**

```python
from src.common import bot_settings

# Get all enabled modules in order
enabled_modules = bot_settings.get_modules_config(enabled_only=True)
for module in enabled_modules:
    print(f"{module['button_label']} (order: {module['order']})")

# Get all modules (including disabled)
all_modules = bot_settings.get_modules_config(enabled_only=False)
```

### Functions in `messages.py`

#### `get_modules_menu_keyboard()`

Builds the modules menu keyboard dynamically based on module configuration.

**Returns:**
- `ReplyKeyboardMarkup` for the modules menu

**Example:**

```python
from src.common.messages import get_modules_menu_keyboard

# Get the keyboard
keyboard = get_modules_menu_keyboard()

# Use it in a message
await update.message.reply_text(
    MESSAGE_MODULES_MENU,
    reply_markup=keyboard,
    parse_mode='MarkdownV2'
)
```

## Backward Compatibility

The following constants are automatically derived from `MODULE_CONFIG` for backward compatibility:

- `MODULE_KEYS` - Dictionary mapping module keys to setting keys
- `MODULE_NAMES` - Dictionary mapping module keys to display names

Existing code using these constants will continue to work without modification.

## Migration Notes

### Before (Hardcoded)

Previously, adding a module required:
1. Editing `MODULE_KEYS` in `bot_settings.py`
2. Editing `MODULE_NAMES` in `bot_settings.py`
3. Editing `BUTTON_*` constants in `messages.py`
4. Editing `get_modules_menu_keyboard()` function to add button logic

### After (Dynamic)

Now, adding a module requires:
1. Adding one entry to `MODULE_CONFIG` in `bot_settings.py`

That's it!

## Best Practices

1. **Keep orders sequential**: Use 1, 2, 3, 4... for clarity
2. **Use consistent columns**: Stick to 2 columns unless a module needs emphasis
3. **Use emojis consistently**: Each module should have a distinctive emoji
4. **Test after changes**: Verify the keyboard displays correctly after modifications
5. **Update database settings**: Remember to add new module settings to the database

## Troubleshooting

### Module not appearing in keyboard

Check:
1. Module is in `MODULE_CONFIG`
2. Module is enabled in database (`bot_settings` table)
3. `order` field is set correctly
4. No duplicate `order` values

### Buttons in wrong order

- Verify `order` field values
- Check for duplicate orders
- Ensure `MODULE_CONFIG` is not being modified elsewhere

### Button layout issues

- Check `columns` field (should be 1 or 2)
- Ensure all modules have the `columns` field
