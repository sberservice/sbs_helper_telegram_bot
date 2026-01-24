-- Migration: Transform ticket_templates into validation rule test templates
-- This migration converts the template system from user-facing examples
-- to admin-only validation rule testing framework

-- Step 1: Add expected_result column to ticket_templates
-- This stores whether the template should PASS or FAIL validation
ALTER TABLE `ticket_templates` 
ADD COLUMN `expected_result` ENUM('pass', 'fail') DEFAULT 'pass' AFTER `description`,
ADD COLUMN `ticket_type_id` BIGINT(20) DEFAULT NULL AFTER `expected_result`,
ADD COLUMN `updated_timestamp` BIGINT(20) DEFAULT NULL AFTER `created_timestamp`,
ADD KEY `ticket_type_id` (`ticket_type_id`);

-- Step 2: Create junction table for template-to-rule expected results
-- This defines which rules a template is designed to test and expected outcomes
DROP TABLE IF EXISTS `template_rule_tests`;
CREATE TABLE `template_rule_tests` (
  `id` BIGINT(20) NOT NULL AUTO_INCREMENT,
  `template_id` BIGINT(20) NOT NULL,
  `validation_rule_id` BIGINT(20) NOT NULL,
  `expected_pass` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '1 = rule should pass, 0 = rule should fail',
  `notes` TEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Admin notes about why this expectation exists',
  `created_timestamp` BIGINT(20) NOT NULL,
  `updated_timestamp` BIGINT(20) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `template_rule_unique` (`template_id`, `validation_rule_id`),
  KEY `template_id` (`template_id`),
  KEY `validation_rule_id` (`validation_rule_id`),
  CONSTRAINT `fk_template_rule_template` FOREIGN KEY (`template_id`) REFERENCES `ticket_templates` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_template_rule_rule` FOREIGN KEY (`validation_rule_id`) REFERENCES `validation_rules` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Step 3: Create table to store test run results
DROP TABLE IF EXISTS `template_test_results`;
CREATE TABLE `template_test_results` (
  `id` BIGINT(20) NOT NULL AUTO_INCREMENT,
  `template_id` BIGINT(20) NOT NULL,
  `admin_userid` BIGINT(20) NOT NULL COMMENT 'Admin who ran the test',
  `overall_pass` TINYINT(1) NOT NULL COMMENT '1 = all expectations met, 0 = some failed',
  `total_rules_tested` INT NOT NULL DEFAULT 0,
  `rules_passed_as_expected` INT NOT NULL DEFAULT 0,
  `rules_failed_unexpectedly` INT NOT NULL DEFAULT 0,
  `details_json` TEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT 'JSON with detailed per-rule results',
  `run_timestamp` BIGINT(20) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `template_id` (`template_id`),
  KEY `admin_userid` (`admin_userid`),
  KEY `run_timestamp` (`run_timestamp`),
  CONSTRAINT `fk_test_result_template` FOREIGN KEY (`template_id`) REFERENCES `ticket_templates` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Step 4: Rename column for clarity (template is now a "test case")
-- Note: We keep the table name as ticket_templates for backward compatibility
-- but the semantics change to "validation test templates"
