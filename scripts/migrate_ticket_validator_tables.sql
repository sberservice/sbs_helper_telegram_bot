-- Migration Script: Rename Ticket Validator Tables
-- This script renames all ticket_validator module tables to include the ticket_validator_ prefix
-- Run this script on existing databases to migrate from old table names to new ones
-- 
-- IMPORTANT: 
-- 1. Backup your database before running this script
-- 2. This script will rename existing tables - existing data will be preserved
-- 3. The application must be updated to use new table names BEFORE running this
-- 4. Run this during a maintenance window when the bot is offline
--
-- To rollback, see the companion script: rollback_ticket_validator_tables.sql

-- Disable foreign key checks temporarily to allow renaming
SET FOREIGN_KEY_CHECKS = 0;

-- Rename validation_rules table
ALTER TABLE `validation_rules` RENAME TO `ticket_validator_validation_rules`;

-- Rename validation_history table
ALTER TABLE `validation_history` RENAME TO `ticket_validator_validation_history`;

-- Rename ticket_types table
ALTER TABLE `ticket_types` RENAME TO `ticket_validator_ticket_types`;

-- Rename ticket_type_rules table
ALTER TABLE `ticket_type_rules` RENAME TO `ticket_validator_ticket_type_rules`;

-- Rename ticket_templates table
ALTER TABLE `ticket_templates` RENAME TO `ticket_validator_ticket_templates`;

-- Rename template_rule_tests table
ALTER TABLE `template_rule_tests` RENAME TO `ticket_validator_template_rule_tests`;

-- Rename template_test_results table
ALTER TABLE `template_test_results` RENAME TO `ticket_validator_template_test_results`;

-- Re-enable foreign key checks
SET FOREIGN_KEY_CHECKS = 1;

-- Verify the migration
SELECT 'Migration completed. Verifying tables...' AS status;

-- Show the renamed tables
SHOW TABLES LIKE 'ticket_validator_%';

-- Show count of records in each table to verify data integrity
SELECT 'ticket_validator_validation_rules' AS table_name, COUNT(*) AS record_count 
FROM ticket_validator_validation_rules
UNION ALL
SELECT 'ticket_validator_validation_history', COUNT(*) 
FROM ticket_validator_validation_history
UNION ALL
SELECT 'ticket_validator_ticket_types', COUNT(*) 
FROM ticket_validator_ticket_types
UNION ALL
SELECT 'ticket_validator_ticket_type_rules', COUNT(*) 
FROM ticket_validator_ticket_type_rules
UNION ALL
SELECT 'ticket_validator_ticket_templates', COUNT(*) 
FROM ticket_validator_ticket_templates
UNION ALL
SELECT 'ticket_validator_template_rule_tests', COUNT(*) 
FROM ticket_validator_template_rule_tests
UNION ALL
SELECT 'ticket_validator_template_test_results', COUNT(*) 
FROM ticket_validator_template_test_results;

SELECT 'Migration verification complete!' AS status;
