-- Gamification Module Database Setup
-- Run this script to create the required tables for the gamification system
-- Tables: achievements, user progress, scores, rankings, settings

-- =====================================================
-- ACHIEVEMENTS DEFINITIONS
-- Stores all possible achievements with their 3 levels
-- =====================================================
CREATE TABLE IF NOT EXISTS `gamification_achievements` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `code` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Unique achievement identifier',
  `module` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Source module name',
  `name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Display name',
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Achievement description',
  `icon` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT '🏆' COMMENT 'Emoji icon',
  `threshold_bronze` int(11) NOT NULL DEFAULT '1' COMMENT 'Actions required for bronze level',
  `threshold_silver` int(11) NOT NULL DEFAULT '10' COMMENT 'Actions required for silver level',
  `threshold_gold` int(11) NOT NULL DEFAULT '100' COMMENT 'Actions required for gold level',
  `image_bronze` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Image path for bronze badge',
  `image_silver` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Image path for silver badge',
  `image_gold` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Image path for gold badge',
  `display_order` int(11) NOT NULL DEFAULT '0',
  `active` tinyint(1) NOT NULL DEFAULT '1',
  `created_timestamp` bigint(20) NOT NULL,
  `updated_timestamp` bigint(20) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `code` (`code`),
  KEY `module` (`module`),
  KEY `active` (`active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================
-- USER ACHIEVEMENT PROGRESS
-- Tracks progress toward each achievement per user
-- =====================================================
CREATE TABLE IF NOT EXISTS `gamification_user_progress` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `userid` bigint(20) NOT NULL COMMENT 'Telegram user ID',
  `achievement_id` bigint(20) NOT NULL,
  `current_count` int(11) NOT NULL DEFAULT '0' COMMENT 'Current progress count',
  `last_increment_timestamp` bigint(20) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `user_achievement` (`userid`, `achievement_id`),
  KEY `userid` (`userid`),
  KEY `achievement_id` (`achievement_id`),
  CONSTRAINT `fk_progress_achievement` FOREIGN KEY (`achievement_id`) REFERENCES `gamification_achievements` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================
-- USER UNLOCKED ACHIEVEMENTS
-- Records when a user unlocks an achievement level
-- =====================================================
CREATE TABLE IF NOT EXISTS `gamification_user_achievements` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `userid` bigint(20) NOT NULL COMMENT 'Telegram user ID',
  `achievement_id` bigint(20) NOT NULL,
  `level` tinyint(1) NOT NULL COMMENT '1=Bronze, 2=Silver, 3=Gold',
  `unlocked_timestamp` bigint(20) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `user_achievement_level` (`userid`, `achievement_id`, `level`),
  KEY `userid` (`userid`),
  KEY `achievement_id` (`achievement_id`),
  KEY `level` (`level`),
  CONSTRAINT `fk_user_achievement` FOREIGN KEY (`achievement_id`) REFERENCES `gamification_achievements` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================
-- SCORE POINTS LOG
-- Tracks all score point additions with source info
-- =====================================================
CREATE TABLE IF NOT EXISTS `gamification_scores` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `userid` bigint(20) NOT NULL COMMENT 'Telegram user ID',
  `points` int(11) NOT NULL COMMENT 'Points added (can be negative)',
  `source` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Source module or script',
  `reason` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Reason for points',
  `timestamp` bigint(20) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `userid` (`userid`),
  KEY `source` (`source`),
  KEY `timestamp` (`timestamp`),
  KEY `userid_timestamp` (`userid`, `timestamp`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================
-- USER TOTALS CACHE
-- Cached total scores for fast ranking queries
-- Updated on score changes via trigger or application
-- =====================================================
CREATE TABLE IF NOT EXISTS `gamification_user_totals` (
  `userid` bigint(20) NOT NULL COMMENT 'Telegram user ID',
  `total_score` bigint(20) NOT NULL DEFAULT '0',
  `total_achievements` int(11) NOT NULL DEFAULT '0' COMMENT 'Total achievement levels unlocked',
  `current_rank` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Current rank name',
  `last_updated` bigint(20) NOT NULL,
  PRIMARY KEY (`userid`),
  KEY `total_score` (`total_score`),
  KEY `total_achievements` (`total_achievements`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================
-- EVENT LOG
-- Central event bus log for all trackable actions
-- =====================================================
CREATE TABLE IF NOT EXISTS `gamification_events` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `event_type` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'e.g., ktr.lookup, certification.test_passed',
  `userid` bigint(20) NOT NULL,
  `data_json` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT 'JSON payload with event details',
  `timestamp` bigint(20) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `event_type` (`event_type`),
  KEY `userid` (`userid`),
  KEY `timestamp` (`timestamp`),
  KEY `userid_event_type` (`userid`, `event_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================
-- MODULE SETTINGS
-- Runtime configuration for gamification system
-- =====================================================
CREATE TABLE IF NOT EXISTS `gamification_settings` (
  `key` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `value` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `updated_timestamp` bigint(20) DEFAULT NULL,
  PRIMARY KEY (`key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================
-- SCORE CONFIGURATION PER MODULE
-- Defines how many points each action gives
-- =====================================================
CREATE TABLE IF NOT EXISTS `gamification_score_config` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `module` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `action` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Action type within module',
  `points` int(11) NOT NULL DEFAULT '1' COMMENT 'Points per action',
  `description` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `active` tinyint(1) NOT NULL DEFAULT '1',
  `created_timestamp` bigint(20) NOT NULL,
  `updated_timestamp` bigint(20) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `module_action` (`module`, `action`),
  KEY `module` (`module`),
  KEY `active` (`active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================
-- DEFAULT SETTINGS
-- =====================================================
INSERT INTO `gamification_settings` (`key`, `value`, `description`, `updated_timestamp`) VALUES
('obfuscate_names', 'false', 'Hide full names in public rankings (show initials)', UNIX_TIMESTAMP()),
('rankings_per_page', '10', 'Number of users per page in rankings', UNIX_TIMESTAMP()),
('rank_1_name', 'Новичок', 'Rank 1 display name', UNIX_TIMESTAMP()),
('rank_1_threshold', '0', 'Minimum points for rank 1', UNIX_TIMESTAMP()),
('rank_1_icon', '🌱', 'Rank 1 icon', UNIX_TIMESTAMP()),
('rank_2_name', 'Специалист', 'Rank 2 display name', UNIX_TIMESTAMP()),
('rank_2_threshold', '100', 'Minimum points for rank 2', UNIX_TIMESTAMP()),
('rank_2_icon', '📘', 'Rank 2 icon', UNIX_TIMESTAMP()),
('rank_3_name', 'Эксперт', 'Rank 3 display name', UNIX_TIMESTAMP()),
('rank_3_threshold', '500', 'Minimum points for rank 3', UNIX_TIMESTAMP()),
('rank_3_icon', '⭐', 'Rank 3 icon', UNIX_TIMESTAMP()),
('rank_4_name', 'Мастер', 'Rank 4 display name', UNIX_TIMESTAMP()),
('rank_4_threshold', '2000', 'Minimum points for rank 4', UNIX_TIMESTAMP()),
('rank_4_icon', '🏅', 'Rank 4 icon', UNIX_TIMESTAMP()),
('rank_5_name', 'Легенда', 'Rank 5 display name', UNIX_TIMESTAMP()),
('rank_5_threshold', '5000', 'Minimum points for rank 5', UNIX_TIMESTAMP()),
('rank_5_icon', '👑', 'Rank 5 icon', UNIX_TIMESTAMP())
ON DUPLICATE KEY UPDATE `key` = VALUES(`key`);

-- =====================================================
-- SAMPLE KTR ACHIEVEMENTS
-- =====================================================
INSERT INTO `gamification_achievements` (`code`, `module`, `name`, `description`, `icon`, `threshold_bronze`, `threshold_silver`, `threshold_gold`, `display_order`, `created_timestamp`) VALUES
('ktr_lookup', 'ktr', 'Исследователь КТР', 'Поиск кодов КТР', '🔍', 1, 50, 500, 1, UNIX_TIMESTAMP()),
('ktr_lookup_found', 'ktr', 'Успешный поиск', 'Найти существующий код КТР', '✅', 1, 25, 250, 2, UNIX_TIMESTAMP()),
('ktr_daily_user', 'ktr', 'Ежедневный пользователь', 'Использовать КТР в разные дни', '📅', 1, 7, 30, 3, UNIX_TIMESTAMP())
ON DUPLICATE KEY UPDATE `code` = VALUES(`code`);

-- =====================================================
-- SAMPLE CERTIFICATION ACHIEVEMENTS
-- =====================================================
INSERT INTO `gamification_achievements` (`code`, `module`, `name`, `description`, `icon`, `threshold_bronze`, `threshold_silver`, `threshold_gold`, `display_order`, `created_timestamp`) VALUES
('cert_test_completed', 'certification', 'Экзаменатор', 'Пройти тест аттестации', '📝', 1, 5, 20, 1, UNIX_TIMESTAMP()),
('cert_test_passed', 'certification', 'Отличник', 'Успешно пройти тест аттестации', '✅', 1, 5, 15, 2, UNIX_TIMESTAMP()),
('cert_daily_user', 'certification', 'Регулярная аттестация', 'Проходить тесты в разные дни', '📅', 1, 7, 30, 3, UNIX_TIMESTAMP()),
('cert_learning_answered', 'certification', 'Учусь на практике', 'Ответить на вопросы в режиме обучения', '🎓', 5, 25, 100, 4, UNIX_TIMESTAMP()),
('cert_learning_completed', 'certification', 'Учебная сессия', 'Завершить обучение', '📚', 1, 5, 20, 5, UNIX_TIMESTAMP())
ON DUPLICATE KEY UPDATE `code` = VALUES(`code`);

-- =====================================================
-- SAMPLE KTR SCORE CONFIGURATION
-- =====================================================
INSERT INTO `gamification_score_config` (`module`, `action`, `points`, `description`, `created_timestamp`) VALUES
('ktr', 'lookup', 1, 'Поиск кода КТР', UNIX_TIMESTAMP()),
('ktr', 'lookup_found', 2, 'Успешный поиск кода КТР', UNIX_TIMESTAMP())
ON DUPLICATE KEY UPDATE `module` = VALUES(`module`);

-- =====================================================
-- SAMPLE CERTIFICATION SCORE CONFIGURATION
-- =====================================================
INSERT INTO `gamification_score_config` (`module`, `action`, `points`, `description`, `created_timestamp`) VALUES
('certification', 'test_completed', 3, 'Прохождение теста аттестации', UNIX_TIMESTAMP()),
('certification', 'test_passed', 5, 'Успешное прохождение теста аттестации', UNIX_TIMESTAMP())
ON DUPLICATE KEY UPDATE `module` = VALUES(`module`);
