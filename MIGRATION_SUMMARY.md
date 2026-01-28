# Ticket Validator Table Renaming - Migration Summary

## Overview
All database tables in the `ticket_validator` module have been renamed to include the `ticket_validator_` prefix to avoid naming conflicts with other modules and improve code organization.

## Changes Made

### 1. Database Schema (schema.sql)
Renamed all 7 tables:
- `validation_rules` → `ticket_validator_validation_rules`
- `validation_history` → `ticket_validator_validation_history`
- `ticket_types` → `ticket_validator_ticket_types`
- `ticket_type_rules` → `ticket_validator_ticket_type_rules`
- `ticket_templates` → `ticket_validator_ticket_templates`
- `template_rule_tests` → `ticket_validator_template_rule_tests`
- `template_test_results` → `ticket_validator_template_test_results`

Updated all foreign key constraints to reference the new table names.

### 2. SQL Setup Scripts (scripts/)
Updated table references in:
- `initial_validation_rules.sql` - All INSERT statements
- `initial_ticket_types.sql` - All INSERT statements
- `map_rules_to_ticket_types.sql` - All INSERT statements
- `sample_templates.sql` - All INSERT statements
- `sample_test_templates.sql` - All INSERT and DELETE statements
- `example_negative_keywords.sql` - All UPDATE and INSERT statements

### 3. Python Code (src/sbs_helper_telegram_bot/ticket_validator/)
Updated all SQL queries in:
- `validation_rules.py` - All SELECT, INSERT, UPDATE, DELETE, and JOIN statements
- `messages.py` - All SELECT statements
- `admin_panel_bot_part.py` - No direct SQL (uses functions from validation_rules.py)
- `ticket_validator_bot_part.py` - No direct SQL (uses functions from validation_rules.py)
- `validators.py` - No direct SQL (uses data classes)

### 4. Documentation
Updated table references in:
- `TEST_TEMPLATES.md` - All table name references
- `TICKET_TYPES.md` - All table name references
- `NEGATIVE_KEYWORDS.md` - All UPDATE statement examples

### 5. Migration Scripts
Created new scripts:
- `scripts/migrate_ticket_validator_tables.sql` - Renames existing tables in production
- `scripts/rollback_ticket_validator_tables.sql` - Reverts changes if needed

## Migration Instructions

### For New Installations
1. Use the updated `schema.sql` to create tables with new names
2. Run setup scripts in order:
   - `initial_validation_rules.sql`
   - `initial_ticket_types.sql`
   - `map_rules_to_ticket_types.sql`
   - `sample_templates.sql` (optional)
   - `sample_test_templates.sql` (optional)

### For Existing Databases
1. **IMPORTANT**: Backup your database before proceeding
2. Deploy the updated code to your server (DO NOT restart the bot yet)
3. Stop the Telegram bot
4. Run `scripts/migrate_ticket_validator_tables.sql` to rename tables
5. Verify migration completed successfully (script includes verification queries)
6. Start the bot with the new code

### Rollback Procedure (if needed)
1. Stop the bot
2. Run `scripts/rollback_ticket_validator_tables.sql`
3. Deploy the old code version
4. Start the bot

## Testing Recommendations
1. After migration, test the following:
   - Validate a ticket (user flow)
   - View validation rules in admin panel
   - Create/edit a validation rule
   - Create/edit a ticket type
   - Run template tests
   - Assign rules to ticket types

2. Verify data integrity:
   - Check that all validation rules are present
   - Check that all ticket types are present
   - Check that rule-to-type mappings are intact
   - Check that templates and test results are accessible

## Files Modified

### Schema & Scripts
- schema.sql
- scripts/initial_validation_rules.sql
- scripts/initial_ticket_types.sql
- scripts/map_rules_to_ticket_types.sql
- scripts/sample_templates.sql
- scripts/sample_test_templates.sql
- scripts/example_negative_keywords.sql

### Python Code
- src/sbs_helper_telegram_bot/ticket_validator/validation_rules.py
- src/sbs_helper_telegram_bot/ticket_validator/messages.py

### Documentation
- src/sbs_helper_telegram_bot/ticket_validator/TEST_TEMPLATES.md
- src/sbs_helper_telegram_bot/ticket_validator/TICKET_TYPES.md
- src/sbs_helper_telegram_bot/ticket_validator/NEGATIVE_KEYWORDS.md

### New Files
- scripts/migrate_ticket_validator_tables.sql
- scripts/rollback_ticket_validator_tables.sql
- MIGRATION_SUMMARY.md (this file)

## Notes
- All foreign key constraints remain intact and reference the new table names
- No data is lost during migration - ALTER TABLE RENAME preserves all data
- The rollback script is provided for emergency use only
- All indexes and constraints are automatically renamed by MySQL during table rename

## Verification Queries

After migration, you can verify the changes with:

```sql
-- Show all ticket_validator tables
SHOW TABLES LIKE 'ticket_validator_%';

-- Count records in each table
SELECT 'ticket_validator_validation_rules' AS table_name, COUNT(*) AS records FROM ticket_validator_validation_rules
UNION ALL
SELECT 'ticket_validator_ticket_types', COUNT(*) FROM ticket_validator_ticket_types
UNION ALL
SELECT 'ticket_validator_ticket_type_rules', COUNT(*) FROM ticket_validator_ticket_type_rules
UNION ALL
SELECT 'ticket_validator_ticket_templates', COUNT(*) FROM ticket_validator_ticket_templates
UNION ALL
SELECT 'ticket_validator_template_rule_tests', COUNT(*) FROM ticket_validator_template_rule_tests
UNION ALL
SELECT 'ticket_validator_template_test_results', COUNT(*) FROM ticket_validator_template_test_results
UNION ALL
SELECT 'ticket_validator_validation_history', COUNT(*) FROM ticket_validator_validation_history;
```

## Contact
For questions or issues, please refer to the project documentation or contact the development team.

---
**Migration Date**: January 29, 2026
**Branch**: certification_module
