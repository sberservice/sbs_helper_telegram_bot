# Admin Interface Documentation

## Overview

The bot now includes a full conversation-based admin interface for managing validation rules and ticket types without needing direct database access.

## Setup

### 1. Update Database Schema

For existing databases, run the migration script:
```bash
mysql -u root -p your_database < scripts/add_admin_field.sql
```

For new installations, the `schema.sql` already includes the `is_admin` field.

### 2. Grant Admin Access

To make a user an administrator, update their record in the database:

```sql
UPDATE users SET is_admin = 1 WHERE userid = YOUR_TELEGRAM_USER_ID;
```

Replace `YOUR_TELEGRAM_USER_ID` with the actual Telegram user ID (visible in bot logs or database).

## Admin Commands

### Main Commands

- `/admin` - Open admin panel menu
- `/add_rule` - Add new validation rule (conversation)
- `/edit_rule` - Edit existing rule (conversation)
- `/assign_rules` - Assign rules to ticket types (conversation)
- `/list_rules` - View all validation rules
- `/manage_types` - View and manage ticket types
- `/cancel` - Cancel any ongoing admin operation

## Features

### 1. Add Validation Rule

**Flow:**
1. Use `/add_rule` or click "➕ Добавить правило"
2. Enter rule name (e.g., "Проверка ИНН")
3. Select rule type from inline keyboard:
   - **Regex** - Regular expression pattern
   - **Required Field** - Mandatory field detection
   - **Format** - Format validation (INN, phone, email)
   - **Length** - Length constraints
   - **Custom** - Custom validation logic
4. Enter pattern/parameter based on type
5. Enter error message shown to users
6. Enter priority (higher = checked first)
7. Rule is created and ready to assign

**Example:**
```
Name: Проверка ИНН
Type: regex
Pattern: ИНН:\s*\d{10,12}
Error: ИНН должен содержать 10 или 12 цифр
Priority: 10
```

### 2. Edit Validation Rule

**Flow:**
1. Use `/edit_rule` or click "📝 Править правило"
2. Select rule from list (shows ID and status ✅/❌)
3. Choose field to edit:
   - Название (Name)
   - Паттерн (Pattern)
   - Сообщение об ошибке (Error message)
   - Приоритет (Priority)
   - Активность (Active/Inactive toggle)
4. Enter new value
5. Rule is updated

**Features:**
- View up to 20 rules at once
- Active/inactive status indicator
- Instant toggle for activation/deactivation

### 3. Assign Rules to Ticket Types

**Flow:**
1. Use `/assign_rules` or click "🔗 Назначить правила"
2. Select ticket type
3. View current assignments with indicators:
   - ✅ - Rule is assigned
   - ➕ - Rule is not assigned
4. Click to toggle assignment
5. Click "✔️ Готово" when finished

**Features:**
- Real-time assignment updates
- Visual feedback for current state
- Only shows active rules
- Shows assignment count

### 4. List All Rules

Use `/list_rules` or click "📋 Список правил" to view:
- Rule ID
- Rule name
- Type (regex, required_field, etc.)
- Priority
- Active status (✅/❌)

### 5. Manage Ticket Types

Use `/manage_types` or click "🎫 Управление типами заявок" to:
- View all existing ticket types
- See available commands for type management

**Future commands:**
- `/create_type` - Create new ticket type
- `/edit_type <id>` - Edit ticket type

## Menu Navigation

### Admin Panel Menu Buttons

When in admin panel (`/admin`):
- **➕ Добавить правило** - Start add rule conversation
- **📝 Править правило** - Start edit rule conversation
- **🔗 Назначить правила** - Start assign rules conversation
- **📋 Список правил** - View all rules
- **🎫 Управление типами заявок** - Manage ticket types
- **🏠 Главное меню** - Return to main menu

## Access Control

- All admin commands check `is_admin` flag
- Non-admin users receive: "❌ У вас нет прав администратора."
- Admin menu only accessible to admins
- Regular users don't see admin commands

## Database Functions

The following functions are available in `validation_rules.py`:

### Rule Management
- `create_validation_rule()` - Create new rule
- `update_validation_rule()` - Update existing rule
- `delete_validation_rule()` - Soft delete (deactivate)
- `get_all_rules()` - Get all rules including inactive
- `load_rule_by_id()` - Load specific rule

### Assignment Management
- `assign_rule_to_ticket_type()` - Assign rule to type
- `unassign_rule_from_ticket_type()` - Remove assignment
- `get_rules_for_ticket_type()` - Get all rules for type

### Ticket Type Management
- `create_ticket_type()` - Create new ticket type
- `update_ticket_type()` - Update ticket type
- `load_all_ticket_types()` - Load all active types
- `load_ticket_type_by_id()` - Load specific type

## Best Practices

### Rule Creation
1. **Use descriptive names** - Make rules easy to identify
2. **Set appropriate priorities** - Higher priority rules check first
3. **Write clear error messages** - Users see these when validation fails
4. **Test regex patterns** - Use online regex testers before adding
5. **Start with high priority** - Critical checks should be 15-20

### Rule Assignment
1. **Assign relevant rules only** - Don't over-validate
2. **Group related rules** - Assign logically related rules to types
3. **Review assignments** - Use `/list_rules` to audit
4. **Test after changes** - Validate actual tickets after modifications

### Maintenance
1. **Regular audits** - Review and clean up unused rules
2. **Document patterns** - Keep notes on complex regex patterns
3. **Monitor history** - Check validation history for issues
4. **Gradual rollout** - Test new rules on one type first

## Troubleshooting

### Rule Not Working
- Check if rule is active (✅ in list)
- Verify rule is assigned to ticket type
- Check rule priority (lower priority = checked later)
- Review pattern syntax for regex rules

### Assignment Issues
- Ensure ticket type exists and is active
- Verify rule exists and is active
- Check for database connection errors in logs

### Access Issues
- Verify `is_admin = 1` in database
- Check user is legitimate (has consumed invite)
- Restart bot after database changes

## Examples

### Example 1: Add INN Validation Rule

```
/add_rule
→ Name: Проверка формата ИНН
→ Type: regex
→ Pattern: ИНН:\s*\d{10,12}
→ Error: ИНН должен содержать 10 или 12 цифр
→ Priority: 15
```

### Example 2: Add Required Field

```
/add_rule
→ Name: Обязательное поле Адрес
→ Type: required_field
→ Pattern: Адрес
→ Error: Не указан адрес установки
→ Priority: 10
```

### Example 3: Assign Rules to Ticket Type

```
/assign_rules
→ Select: Выезд БУЛ
→ Toggle: ✅ Проверка ИНН
→ Toggle: ✅ Обязательное поле Адрес
→ Click: ✔️ Готово
```

## Future Enhancements

Planned features:
- Full ticket type creation via bot
- Rule testing interface
- Bulk rule operations
- Import/export rules
- Rule templates
- Analytics dashboard

## Security Notes

- Admin access is critical - grant carefully
- Monitor admin actions in logs
- Regular backup of validation rules
- Limit number of admins
- Use separate admin accounts if possible

## Support

For issues or questions:
1. Check bot logs for errors
2. Verify database schema is up to date
3. Review this documentation
4. Check IMPLEMENTATION_SUMMARY.md for technical details
