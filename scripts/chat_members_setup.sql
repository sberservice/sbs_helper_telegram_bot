-- ============================================================================
-- Pre-Invited Users (Chat Members) Setup Script
-- ============================================================================
-- This script creates the chat_members table for managing pre-invited users.
-- Pre-invited users can access the bot without entering an invite code.
-- ============================================================================

-- Create chat_members table
CREATE TABLE IF NOT EXISTS `chat_members` (
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

-- ============================================================================
-- Example: Add a pre-invited user manually
-- ============================================================================
-- INSERT INTO chat_members (telegram_id, added_by_userid, notes, created_timestamp)
-- VALUES (123456789, NULL, 'Test user', UNIX_TIMESTAMP());

-- ============================================================================
-- Example: View all pre-invited users
-- ============================================================================
-- SELECT 
--     telegram_id,
--     notes,
--     FROM_UNIXTIME(created_timestamp) as created,
--     CASE WHEN activated_timestamp IS NULL THEN 'Pending' 
--          ELSE FROM_UNIXTIME(activated_timestamp) END as activated_status
-- FROM chat_members
-- ORDER BY created_timestamp DESC;

-- ============================================================================
-- Example: Remove a user from pre-invites
-- ============================================================================
-- DELETE FROM chat_members WHERE telegram_id = 123456789;
