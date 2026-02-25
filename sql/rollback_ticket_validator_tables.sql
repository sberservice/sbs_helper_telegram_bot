-- Rollback Script: Revert Ticket Validator Table Names
-- This script reverts the ticket_validator_ prefix renaming back to original table names
-- Use this ONLY if you need to rollback the migration
-- 
-- IMPORTANT: 
-- 1. Backup your database before running this script
-- 2. Ensure the old version of the application is ready to deploy
-- 3. Run this during a maintenance window when the bot is offline
--
-- This is the rollback for: migrate_ticket_validator_tables.sql

-- Disable foreign key checks temporarily to allow renaming
SET FOREIGN_KEY_CHECKS = 0;

-- Revert validation_rules table
ALTER TABLE `ticket_validator_validation_rules` RENAME TO `validation_rules`;

-- Revert validation_history table
ALTER TABLE `ticket_validator_validation_history` RENAME TO `validation_history`;

-- Revert ticket_types table
ALTER TABLE `ticket_validator_ticket_types` RENAME TO `ticket_types`;

-- Revert ticket_type_rules table
ALTER TABLE `ticket_validator_ticket_type_rules` RENAME TO `ticket_type_rules`;

-- Revert ticket_templates table
ALTER TABLE `ticket_validator_ticket_templates` RENAME TO `ticket_templates`;

-- Revert template_rule_tests table
ALTER TABLE `ticket_validator_template_rule_tests` RENAME TO `template_rule_tests`;

-- Revert template_test_results table
ALTER TABLE `ticket_validator_template_test_results` RENAME TO `template_test_results`;

-- Re-enable foreign key checks
SET FOREIGN_KEY_CHECKS = 1;

-- Verify the rollback
SELECT 'Rollback completed. Verifying tables...' AS status;

-- Show the original table names
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = DATABASE() 
  AND table_name IN (
    'validation_rules',
    'validation_history',
    'ticket_types',
    'ticket_type_rules',
    'ticket_templates',
    'template_rule_tests',
    'template_test_results'
  );

-- Show count of records in each table to verify data integrity
SELECT 'validation_rules' AS table_name, COUNT(*) AS record_count 
FROM validation_rules
UNION ALL
SELECT 'validation_history', COUNT(*) 
FROM validation_history
UNION ALL
SELECT 'ticket_types', COUNT(*) 
FROM ticket_types
UNION ALL
SELECT 'ticket_type_rules', COUNT(*) 
FROM ticket_type_rules
UNION ALL
SELECT 'ticket_templates', COUNT(*) 
FROM ticket_templates
UNION ALL
SELECT 'template_rule_tests', COUNT(*) 
FROM template_rule_tests
UNION ALL
SELECT 'template_test_results', COUNT(*) 
FROM template_test_results;

SELECT 'Rollback verification complete!' AS status;
