-- MySQL dump 10.13  Distrib 8.0.23, for Win64 (x86_64)
--
-- Host: localhost    Database: byl2
-- ------------------------------------------------------
-- Server version	8.0.16

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES UTF8 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `imagequeue`
--

DROP TABLE IF EXISTS `imagequeue`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `imagequeue` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `timestamp` bigint(20) NOT NULL,
  `userid` bigint(20) NOT NULL,
  `file_name` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` int(11) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `status` (`status`),
  KEY `userid` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=193 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `invites`
--

DROP TABLE IF EXISTS `invites`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `invites` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `userid` bigint(20) NOT NULL,
  `invite` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `issued_timestamp` bigint(20) NOT NULL,
  `consumed_userid` bigint(20) DEFAULT NULL,
  `consumed_timestamp` bigint(20) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `userid` (`userid`) USING BTREE,
  KEY `invite` (`invite`) USING BTREE,
  KEY `consumed_userid` (`consumed_userid`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=40 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `queue`
--

DROP TABLE IF EXISTS `queue`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `queue` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `timestamp` bigint(20) NOT NULL,
  `userid` bigint(20) NOT NULL,
  `coordinatex` float NOT NULL,
  `coordinatey` float NOT NULL,
  `status` int(11) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `users`
--

DROP TABLE IF EXISTS `users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `users` (
  `userid` bigint(20) NOT NULL,
  `first_name` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `last_name` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `username` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `timestamp` bigint(20) NOT NULL,
  `is_admin` tinyint(1) NOT NULL DEFAULT '0',
  PRIMARY KEY (`userid`),
  KEY `first_name` (`first_name`),
  KEY `last_name` (`last_name`),
  KEY `username` (`username`),
  KEY `is_admin` (`is_admin`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

--
-- Table structure for table `validation_rules`
--

DROP TABLE IF EXISTS `ticket_validator_validation_rules`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ticket_validator_validation_rules` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `rule_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `pattern` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `rule_type` enum('regex','regex_not_match','regex_fullmatch','regex_not_fullmatch','fias_check','custom') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `error_message` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `active` tinyint(1) NOT NULL DEFAULT '1',
  `priority` int(11) NOT NULL DEFAULT '0',
  `created_timestamp` bigint(20) NOT NULL,
  `updated_timestamp` bigint(20) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `active` (`active`),
  KEY `priority` (`priority`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `validation_history`
--

DROP TABLE IF EXISTS `ticket_validator_validation_history`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ticket_validator_validation_history` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `userid` bigint(20) NOT NULL,
  `ticket_type_id` bigint(20) DEFAULT NULL,
  `ticket_text` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `validation_result` enum('valid','invalid') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `failed_rules` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `timestamp` bigint(20) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `userid` (`userid`),
  KEY `validation_result` (`validation_result`),
  KEY `timestamp` (`timestamp`),
  KEY `ticket_type_id` (`ticket_type_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ticket_templates`
--

DROP TABLE IF EXISTS `ticket_validator_ticket_templates`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ticket_validator_ticket_templates` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `template_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `template_text` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `expected_result` enum('pass','fail') DEFAULT 'pass',
  `ticket_type_id` bigint(20) DEFAULT NULL,
  `active` tinyint(1) NOT NULL DEFAULT '1',
  `created_timestamp` bigint(20) NOT NULL,
  `updated_timestamp` bigint(20) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `active` (`active`),
  KEY `template_name` (`template_name`),
  KEY `ticket_type_id` (`ticket_type_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `template_rule_tests`
--

DROP TABLE IF EXISTS `ticket_validator_template_rule_tests`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ticket_validator_template_rule_tests` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `template_id` bigint(20) NOT NULL,
  `validation_rule_id` bigint(20) NOT NULL,
  `expected_pass` tinyint(1) NOT NULL DEFAULT '1' COMMENT '1 = rule should pass, 0 = rule should fail',
  `notes` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Admin notes about why this expectation exists',
  `created_timestamp` bigint(20) NOT NULL,
  `updated_timestamp` bigint(20) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `template_rule_unique` (`template_id`, `validation_rule_id`),
  KEY `template_id` (`template_id`),
  KEY `validation_rule_id` (`validation_rule_id`),
  CONSTRAINT `fk_template_rule_template` FOREIGN KEY (`template_id`) REFERENCES `ticket_validator_ticket_templates` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_template_rule_rule` FOREIGN KEY (`validation_rule_id`) REFERENCES `ticket_validator_validation_rules` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `template_test_results`
--

DROP TABLE IF EXISTS `ticket_validator_template_test_results`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ticket_validator_template_test_results` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `template_id` bigint(20) NOT NULL,
  `admin_userid` bigint(20) NOT NULL COMMENT 'Admin who ran the test',
  `overall_pass` tinyint(1) NOT NULL COMMENT '1 = all expectations met, 0 = some failed',
  `total_rules_tested` int NOT NULL DEFAULT 0,
  `rules_passed_as_expected` int NOT NULL DEFAULT 0,
  `rules_failed_unexpectedly` int NOT NULL DEFAULT 0,
  `details_json` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT 'JSON with detailed per-rule results',
  `run_timestamp` bigint(20) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `template_id` (`template_id`),
  KEY `admin_userid` (`admin_userid`),
  KEY `run_timestamp` (`run_timestamp`),
  CONSTRAINT `fk_test_result_template` FOREIGN KEY (`template_id`) REFERENCES `ticket_validator_ticket_templates` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ticket_types`
--

DROP TABLE IF EXISTS `ticket_validator_ticket_types`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ticket_validator_ticket_types` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `type_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `detection_keywords` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `keyword_weights` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT 'JSON object mapping keywords to their weights (default weight is 1.0)',
  `active` tinyint(1) NOT NULL DEFAULT '1',
  `created_timestamp` bigint(20) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `type_name` (`type_name`),
  KEY `active` (`active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `ticket_type_rules`
--

DROP TABLE IF EXISTS `ticket_validator_ticket_type_rules`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ticket_validator_ticket_type_rules` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `ticket_type_id` bigint(20) NOT NULL,
  `validation_rule_id` bigint(20) NOT NULL,
  `created_timestamp` bigint(20) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `type_rule_unique` (`ticket_type_id`,`validation_rule_id`),
  KEY `ticket_type_id` (`ticket_type_id`),
  KEY `validation_rule_id` (`validation_rule_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `upos_error_categories`
--

DROP TABLE IF EXISTS `upos_error_categories`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `upos_error_categories` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `display_order` int(11) NOT NULL DEFAULT '0',
  `active` tinyint(1) NOT NULL DEFAULT '1',
  `created_timestamp` bigint(20) NOT NULL,
  `updated_timestamp` bigint(20) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`),
  KEY `active` (`active`),
  KEY `display_order` (`display_order`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `upos_error_codes`
--

DROP TABLE IF EXISTS `upos_error_codes`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `upos_error_codes` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `error_code` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `category_id` bigint(20) DEFAULT NULL,
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `suggested_actions` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `active` tinyint(1) NOT NULL DEFAULT '1',
  `created_timestamp` bigint(20) NOT NULL,
  `updated_timestamp` bigint(20) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `error_code` (`error_code`),
  KEY `category_id` (`category_id`),
  KEY `active` (`active`),
  CONSTRAINT `fk_upos_error_category` FOREIGN KEY (`category_id`) REFERENCES `upos_error_categories` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `upos_error_unknown_codes`
--

DROP TABLE IF EXISTS `upos_error_unknown_codes`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `upos_error_unknown_codes` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `error_code` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `times_requested` int(11) NOT NULL DEFAULT '1',
  `first_requested_timestamp` bigint(20) NOT NULL,
  `last_requested_timestamp` bigint(20) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `error_code` (`error_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `upos_error_request_log`
--

DROP TABLE IF EXISTS `upos_error_request_log`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `upos_error_request_log` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `user_id` bigint(20) NOT NULL,
  `error_code` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `found` tinyint(1) NOT NULL,
  `request_timestamp` bigint(20) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `user_id` (`user_id`),
  KEY `error_code` (`error_code`),
  KEY `request_timestamp` (`request_timestamp`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

-- --------------------------------------------------------
--
-- Employee Certification Module Tables
--
-- --------------------------------------------------------

--
-- Table structure for table `certification_categories`
--

DROP TABLE IF EXISTS `certification_categories`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `certification_categories` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `display_order` int(11) NOT NULL DEFAULT '0',
  `active` tinyint(1) NOT NULL DEFAULT '1',
  `created_timestamp` bigint(20) NOT NULL,
  `updated_timestamp` bigint(20) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`),
  KEY `active` (`active`),
  KEY `display_order` (`display_order`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `certification_questions`
--

DROP TABLE IF EXISTS `certification_questions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `certification_questions` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `question_text` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `option_a` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `option_b` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `option_c` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `option_d` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `correct_option` enum('A','B','C','D') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `explanation` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT 'Optional explanation shown after answering',
  `difficulty` enum('easy','medium','hard') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'medium',
  `relevance_date` date NOT NULL COMMENT 'Date until which the question is considered relevant',
  `active` tinyint(1) NOT NULL DEFAULT '1',
  `created_timestamp` bigint(20) NOT NULL,
  `updated_timestamp` bigint(20) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `active` (`active`),
  KEY `difficulty` (`difficulty`),
  KEY `relevance_date` (`relevance_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `certification_question_categories`
-- Junction table for many-to-many relationship between questions and categories
--

DROP TABLE IF EXISTS `certification_question_categories`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `certification_question_categories` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `question_id` bigint(20) NOT NULL,
  `category_id` bigint(20) NOT NULL,
  `created_timestamp` bigint(20) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `question_category_unique` (`question_id`, `category_id`),
  KEY `question_id` (`question_id`),
  KEY `category_id` (`category_id`),
  CONSTRAINT `fk_qc_question` FOREIGN KEY (`question_id`) REFERENCES `certification_questions` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_qc_category` FOREIGN KEY (`category_id`) REFERENCES `certification_categories` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `certification_attempts`
-- Stores each test attempt by a user
--

DROP TABLE IF EXISTS `certification_attempts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `certification_attempts` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `userid` bigint(20) NOT NULL,
  `category_id` bigint(20) DEFAULT NULL COMMENT 'NULL means all categories (full certification)',
  `total_questions` int(11) NOT NULL,
  `correct_answers` int(11) NOT NULL DEFAULT '0',
  `score_percent` decimal(5,2) NOT NULL DEFAULT '0.00',
  `passed` tinyint(1) NOT NULL DEFAULT '0',
  `time_limit_seconds` int(11) NOT NULL COMMENT 'Time limit for the test in seconds',
  `time_spent_seconds` int(11) DEFAULT NULL COMMENT 'Actual time spent (NULL if not completed)',
  `started_timestamp` bigint(20) NOT NULL,
  `completed_timestamp` bigint(20) DEFAULT NULL,
  `status` enum('in_progress','completed','expired','cancelled') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'in_progress',
  PRIMARY KEY (`id`),
  KEY `userid` (`userid`),
  KEY `category_id` (`category_id`),
  KEY `started_timestamp` (`started_timestamp`),
  KEY `completed_timestamp` (`completed_timestamp`),
  KEY `status` (`status`),
  KEY `passed` (`passed`),
  KEY `score_percent` (`score_percent`),
  CONSTRAINT `fk_attempt_category` FOREIGN KEY (`category_id`) REFERENCES `certification_categories` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `certification_answers`
-- Stores individual answers for each attempt
--

DROP TABLE IF EXISTS `certification_answers`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `certification_answers` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `attempt_id` bigint(20) NOT NULL,
  `question_id` bigint(20) NOT NULL,
  `question_order` int(11) NOT NULL COMMENT 'Order in which question was shown (1-based)',
  `user_answer` enum('A','B','C','D') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'NULL if not answered (timed out)',
  `is_correct` tinyint(1) DEFAULT NULL COMMENT 'NULL if not answered',
  `answered_timestamp` bigint(20) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `attempt_question_unique` (`attempt_id`, `question_id`),
  KEY `attempt_id` (`attempt_id`),
  KEY `question_id` (`question_id`),
  KEY `is_correct` (`is_correct`),
  CONSTRAINT `fk_answer_attempt` FOREIGN KEY (`attempt_id`) REFERENCES `certification_attempts` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_answer_question` FOREIGN KEY (`question_id`) REFERENCES `certification_questions` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `certification_settings`
-- Configurable settings for certification module
--

DROP TABLE IF EXISTS `certification_settings`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `certification_settings` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `setting_key` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `setting_value` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `updated_timestamp` bigint(20) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `setting_key` (`setting_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `chat_members`
-- Pre-invited users who can access the bot without an invite code
--

DROP TABLE IF EXISTS `chat_members`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `chat_members` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `telegram_id` bigint(20) NOT NULL COMMENT 'Pre-authorized Telegram user ID',
  `added_by_userid` bigint(20) DEFAULT NULL COMMENT 'Admin who added this user',
  `notes` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT 'Optional admin notes about the user',
  `created_timestamp` bigint(20) NOT NULL,
  `activated_timestamp` bigint(20) DEFAULT NULL COMMENT 'When user first used the bot (NULL = not yet activated)',
  PRIMARY KEY (`id`),
  UNIQUE KEY `telegram_id` (`telegram_id`),
  KEY `added_by_userid` (`added_by_userid`),
  KEY `activated_timestamp` (`activated_timestamp`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

-- Dump completed on 2025-12-04 18:58:13
