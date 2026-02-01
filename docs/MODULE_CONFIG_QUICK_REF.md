# Quick Reference: Module Configuration

## File Location
`src/common/bot_settings.py` → `MODULE_CONFIG` list

## Add New Module
```python
# In MODULE_CONFIG list, add:
{
    'key': 'your_module',
    'setting_key': 'module_your_module_enabled',
    'button_label': '🔹 Your Module',
    'order': 7,  # Next available number
    'columns': 2  # 1 or 2
}
```

## Reorder Modules
Change the `order` value:
```python
'order': 3,  # Will appear 3rd in the menu
```

## Change Button Layout
```python
'columns': 1,  # Full width button
'columns': 2,  # Half width (default)
```

## Change Button Text
```python
'button_label': '🆕 New Text',
```

## Functions

### Get Modules (Enabled Only)
```python
from src.common import bot_settings
modules = bot_settings.get_modules_config(enabled_only=True)
```

### Get All Modules
```python
modules = bot_settings.get_modules_config(enabled_only=False)
```

### Build Keyboard
```python
from src.common.messages import get_modules_menu_keyboard
keyboard = get_modules_menu_keyboard()
```

## Module Object Structure
```python
{
    'key': str,           # Unique identifier
    'setting_key': str,   # Database key
    'button_label': str,  # Display text
    'order': int,         # Position (1, 2, 3...)
    'columns': int        # Layout (1 or 2)
}
```

## Current Modules (in order)
1. Валидация заявок (ticket_validator)
2. Обработать скриншот (screenshot)  
3. UPOS Ошибки (upos_errors)
4. Аттестация (certification)
5. КТР (ktr)
6. Обратная связь (feedback)

## See Also
- Full guide: `docs/MODULE_CONFIG_GUIDE.md`
- Summary: `REFACTORING_SUMMARY.md`
