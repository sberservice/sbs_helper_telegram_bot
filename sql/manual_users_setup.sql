-- ============================================================================
-- Manual Users Table Setup Script
-- ============================================================================
-- This script creates the manual_users table for managing users added manually
-- by admins. These users can access the bot even if they are not in chat_members
-- table and haven't consumed an invite.
-- ============================================================================

-- Create manual_users table
CREATE TABLE IF NOT EXISTS `manual_users` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `telegram_id` bigint(20) NOT NULL COMMENT 'Telegram user ID',
  `added_by_userid` bigint(20) NOT NULL COMMENT 'Admin who added this user',
  `notes` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT 'Optional admin notes about the user',
  `created_timestamp` bigint(20) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `telegram_id` (`telegram_id`),
  KEY `added_by_userid` (`added_by_userid`),
  KEY `created_timestamp` (`created_timestamp`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- Example: Add a manual user
-- ============================================================================
-- INSERT INTO manual_users (telegram_id, added_by_userid, notes, created_timestamp)
-- VALUES (123456789, 987654321, 'VIP user', UNIX_TIMESTAMP());

-- ============================================================================
-- Example: View all manual users
-- ============================================================================
-- SELECT 
--     mu.telegram_id,
--     mu.notes,
--     mu.added_by_userid,
--     FROM_UNIXTIME(mu.created_timestamp) as created,
--     u.first_name,
--     u.last_name,
--     u.username
-- FROM manual_users mu
-- LEFT JOIN users u ON mu.telegram_id = u.userid
-- ORDER BY mu.created_timestamp DESC;

-- ============================================================================
-- Example: Remove a manual user
-- ============================================================================
-- DELETE FROM manual_users WHERE telegram_id = 123456789;
