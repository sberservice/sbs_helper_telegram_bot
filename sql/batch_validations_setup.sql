-- Migration: Add batch validations tracking
-- Date: 2026-02-05
-- Description: Adds table for tracking batch file validations

-- Create batch validations table
CREATE TABLE IF NOT EXISTS `ticket_validator_batch_validations` (
    `id` int NOT NULL AUTO_INCREMENT,
    `user_id` bigint NOT NULL COMMENT 'Telegram user ID who initiated the validation',
    `source` varchar(50) NOT NULL DEFAULT 'bot' COMMENT 'Source of validation: bot, cli, web, api',
    `input_filename` varchar(255) DEFAULT NULL COMMENT 'Original filename uploaded',
    `ticket_column` varchar(255) DEFAULT NULL COMMENT 'Column name/index used for tickets',
    `total_tickets` int NOT NULL DEFAULT 0 COMMENT 'Total number of tickets processed',
    `valid_tickets` int NOT NULL DEFAULT 0 COMMENT 'Number of valid tickets',
    `invalid_tickets` int NOT NULL DEFAULT 0 COMMENT 'Number of invalid tickets',
    `skipped_tickets` int NOT NULL DEFAULT 0 COMMENT 'Number of skipped (empty) tickets',
    `created_timestamp` int NOT NULL COMMENT 'Unix timestamp when validation started',
    `completed_timestamp` int DEFAULT NULL COMMENT 'Unix timestamp when validation completed',
    `status` varchar(20) NOT NULL DEFAULT 'processing' COMMENT 'Status: processing, completed, failed, cancelled',
    `error_message` text DEFAULT NULL COMMENT 'Error message if status is failed',
    PRIMARY KEY (`id`),
    KEY `idx_user_id` (`user_id`),
    KEY `idx_created` (`created_timestamp`),
    KEY `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Tracks batch file validations';

-- Add batch_id to validation history for linking individual validations to batches
-- Check if column exists before adding
SET @dbname = DATABASE();
SET @tablename = 'ticket_validator_validation_history';
SET @columnname = 'batch_id';
SET @preparedStatement = (SELECT IF(
  (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = @dbname
    AND TABLE_NAME = @tablename
    AND COLUMN_NAME = @columnname
  ) > 0,
  'SELECT 1',
  CONCAT('ALTER TABLE `', @tablename, '` ADD COLUMN `', @columnname, '` int DEFAULT NULL COMMENT "Reference to batch validation"')
));
PREPARE alterIfNotExists FROM @preparedStatement;
EXECUTE alterIfNotExists;
DEALLOCATE PREPARE alterIfNotExists;

-- Add row_number column
SET @columnname = 'row_number';
SET @preparedStatement = (SELECT IF(
  (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = @dbname
    AND TABLE_NAME = @tablename
    AND COLUMN_NAME = @columnname
  ) > 0,
  'SELECT 1',
  CONCAT('ALTER TABLE `', @tablename, '` ADD COLUMN `', @columnname, '` int DEFAULT NULL COMMENT "Row number in source file"')
));
PREPARE alterIfNotExists FROM @preparedStatement;
EXECUTE alterIfNotExists;
DEALLOCATE PREPARE alterIfNotExists;

-- Add index for batch_id if table exists and has the column
-- This will fail silently if index already exists
-- ALTER TABLE `ticket_validator_validation_history` ADD INDEX `idx_batch_id` (`batch_id`);
