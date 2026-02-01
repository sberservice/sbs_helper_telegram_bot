-- News Module Database Setup
-- Creates tables for news publishing, broadcasting, categories, reactions, and read tracking

-- Table: news_categories
-- Categories for news articles (e.g., Bot news, Company news)
CREATE TABLE IF NOT EXISTS `news_categories` (
    `id` int(11) NOT NULL AUTO_INCREMENT,
    `name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
    `emoji` varchar(10) COLLATE utf8mb4_unicode_ci DEFAULT '📰',
    `description` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
    `display_order` int(11) NOT NULL DEFAULT 0,
    `active` tinyint(1) NOT NULL DEFAULT 1,
    `created_timestamp` bigint(20) NOT NULL,
    `updated_timestamp` bigint(20) DEFAULT NULL,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_news_categories_name` (`name`),
    KEY `idx_news_categories_active` (`active`),
    KEY `idx_news_categories_order` (`display_order`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: news_articles
-- Main table for news content
CREATE TABLE IF NOT EXISTS `news_articles` (
    `id` int(11) NOT NULL AUTO_INCREMENT,
    `category_id` int(11) NOT NULL,
    `title` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
    `content` text COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'MarkdownV2 formatted content',
    `image_file_id` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Telegram file_id for attached image',
    `attachment_file_id` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Telegram file_id for attached document',
    `attachment_filename` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Original filename of attachment',
    `status` enum('draft','published','archived') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'draft',
    `is_silent` tinyint(1) NOT NULL DEFAULT 0 COMMENT '1 = do not broadcast on publish',
    `is_mandatory` tinyint(1) NOT NULL DEFAULT 0 COMMENT '1 = force users to acknowledge before using bot',
    `created_by_userid` bigint(20) NOT NULL,
    `created_timestamp` bigint(20) NOT NULL,
    `updated_timestamp` bigint(20) DEFAULT NULL,
    `published_timestamp` bigint(20) DEFAULT NULL,
    PRIMARY KEY (`id`),
    KEY `idx_news_articles_category` (`category_id`),
    KEY `idx_news_articles_status` (`status`),
    KEY `idx_news_articles_published` (`published_timestamp`),
    KEY `idx_news_articles_mandatory` (`is_mandatory`),
    CONSTRAINT `fk_news_articles_category` FOREIGN KEY (`category_id`) 
        REFERENCES `news_categories` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: news_read_log
-- Tracks when a user last viewed the news section (marks all news as read up to that timestamp)
CREATE TABLE IF NOT EXISTS `news_read_log` (
    `user_id` bigint(20) NOT NULL,
    `last_read_timestamp` bigint(20) NOT NULL COMMENT 'Timestamp when user entered news module',
    PRIMARY KEY (`user_id`),
    KEY `idx_news_read_log_timestamp` (`last_read_timestamp`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: news_mandatory_ack
-- Explicit acknowledgment for mandatory news (users must click "Принято" button)
CREATE TABLE IF NOT EXISTS `news_mandatory_ack` (
    `id` bigint(20) NOT NULL AUTO_INCREMENT,
    `news_id` int(11) NOT NULL,
    `user_id` bigint(20) NOT NULL,
    `ack_timestamp` bigint(20) NOT NULL,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_news_mandatory_ack` (`news_id`, `user_id`),
    KEY `idx_news_mandatory_ack_user` (`user_id`),
    CONSTRAINT `fk_news_mandatory_ack_news` FOREIGN KEY (`news_id`) 
        REFERENCES `news_articles` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: news_reactions
-- User reactions to news articles (like, love, dislike)
CREATE TABLE IF NOT EXISTS `news_reactions` (
    `id` bigint(20) NOT NULL AUTO_INCREMENT,
    `news_id` int(11) NOT NULL,
    `user_id` bigint(20) NOT NULL,
    `reaction_type` enum('like','love','dislike') COLLATE utf8mb4_unicode_ci NOT NULL,
    `created_timestamp` bigint(20) NOT NULL,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_news_reactions` (`news_id`, `user_id`),
    KEY `idx_news_reactions_user` (`user_id`),
    KEY `idx_news_reactions_type` (`reaction_type`),
    CONSTRAINT `fk_news_reactions_news` FOREIGN KEY (`news_id`) 
        REFERENCES `news_articles` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: news_delivery_log
-- Tracks broadcast delivery status per user
CREATE TABLE IF NOT EXISTS `news_delivery_log` (
    `id` bigint(20) NOT NULL AUTO_INCREMENT,
    `news_id` int(11) NOT NULL,
    `user_id` bigint(20) NOT NULL,
    `status` enum('sent','failed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'sent',
    `error_message` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
    `delivered_timestamp` bigint(20) NOT NULL,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_news_delivery` (`news_id`, `user_id`),
    KEY `idx_news_delivery_user` (`user_id`),
    KEY `idx_news_delivery_status` (`status`),
    CONSTRAINT `fk_news_delivery_news` FOREIGN KEY (`news_id`) 
        REFERENCES `news_articles` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Insert default categories
INSERT INTO `news_categories` (`name`, `emoji`, `description`, `display_order`, `active`, `created_timestamp`) VALUES
('Новости бота', '🤖', 'Обновления и новые функции бота-помощника', 1, 1, UNIX_TIMESTAMP()),
('СберСервис', '🏢', 'Корпоративные новости и объявления СберСервис', 2, 1, UNIX_TIMESTAMP())
ON DUPLICATE KEY UPDATE `name` = VALUES(`name`);

-- Add default settings for news module
INSERT INTO `bot_settings` (`setting_key`, `setting_value`, `updated_timestamp`) VALUES
('news_expiry_days', '30', UNIX_TIMESTAMP()),
('module_news_enabled', '1', UNIX_TIMESTAMP())
ON DUPLICATE KEY UPDATE `setting_key` = VALUES(`setting_key`);
