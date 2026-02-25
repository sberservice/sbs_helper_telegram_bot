-- Bot Settings Table Setup
-- This script creates the bot_settings table for storing bot-wide settings
-- such as the invite system toggle.

-- Create bot_settings table
CREATE TABLE IF NOT EXISTS `bot_settings` (
  `setting_key` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `setting_value` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `updated_timestamp` bigint(20) NOT NULL,
  `updated_by_userid` bigint(20) DEFAULT NULL,
  PRIMARY KEY (`setting_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Insert default setting for invite system (enabled by default)
INSERT INTO `bot_settings` (`setting_key`, `setting_value`, `updated_timestamp`, `updated_by_userid`)
VALUES ('invite_system_enabled', '1', UNIX_TIMESTAMP(), NULL)
ON DUPLICATE KEY UPDATE `setting_key` = `setting_key`;
