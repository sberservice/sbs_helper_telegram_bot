-- Feedback Module Database Setup
-- Creates tables for user feedback system with anonymous admin replies

-- Table: feedback_categories
-- Optional categorization of feedback (bug, suggestion, question, other)
CREATE TABLE IF NOT EXISTS `feedback_categories` (
    `id` int(11) NOT NULL AUTO_INCREMENT,
    `name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
    `description` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
    `emoji` varchar(10) COLLATE utf8mb4_unicode_ci DEFAULT '📝',
    `display_order` int(11) NOT NULL DEFAULT 0,
    `active` tinyint(1) NOT NULL DEFAULT 1,
    `created_timestamp` bigint(20) NOT NULL,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_feedback_categories_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: feedback_entries
-- Main table storing user feedback submissions
CREATE TABLE IF NOT EXISTS `feedback_entries` (
    `id` int(11) NOT NULL AUTO_INCREMENT,
    `user_id` bigint(20) NOT NULL,
    `category_id` int(11) DEFAULT NULL,
    `message` text COLLATE utf8mb4_unicode_ci NOT NULL,
    `status` enum('new','in_progress','resolved','closed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'new',
    `created_timestamp` bigint(20) NOT NULL,
    `updated_timestamp` bigint(20) DEFAULT NULL,
    PRIMARY KEY (`id`),
    KEY `idx_feedback_entries_user_id` (`user_id`),
    KEY `idx_feedback_entries_status` (`status`),
    KEY `idx_feedback_entries_category_id` (`category_id`),
    KEY `idx_feedback_entries_created` (`created_timestamp`),
    CONSTRAINT `fk_feedback_entries_category` FOREIGN KEY (`category_id`) 
        REFERENCES `feedback_categories` (`id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: feedback_responses
-- Admin responses to feedback (admin_id is NEVER exposed to users)
CREATE TABLE IF NOT EXISTS `feedback_responses` (
    `id` int(11) NOT NULL AUTO_INCREMENT,
    `entry_id` int(11) NOT NULL,
    `admin_id` bigint(20) NOT NULL COMMENT 'Internal use only - NEVER expose to users',
    `response_text` text COLLATE utf8mb4_unicode_ci NOT NULL,
    `created_timestamp` bigint(20) NOT NULL,
    PRIMARY KEY (`id`),
    KEY `idx_feedback_responses_entry_id` (`entry_id`),
    KEY `idx_feedback_responses_admin_id` (`admin_id`),
    CONSTRAINT `fk_feedback_responses_entry` FOREIGN KEY (`entry_id`) 
        REFERENCES `feedback_entries` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Insert default categories
INSERT INTO `feedback_categories` (`name`, `description`, `emoji`, `display_order`, `active`, `created_timestamp`) VALUES
('Ошибка', 'Сообщение об ошибке или проблеме', '🐛', 1, 1, UNIX_TIMESTAMP()),
('Предложение', 'Предложение по улучшению', '💡', 2, 1, UNIX_TIMESTAMP()),
('Вопрос', 'Вопрос по работе бота', '❓', 3, 1, UNIX_TIMESTAMP()),
('Другое', 'Другой тип обращения', '📝', 4, 1, UNIX_TIMESTAMP())
ON DUPLICATE KEY UPDATE `name` = VALUES(`name`);
