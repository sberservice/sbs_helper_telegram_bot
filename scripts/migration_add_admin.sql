-- Migration script: Add admin functionality to existing database
-- Run this script on existing databases to add the is_admin column

-- Add is_admin column to users table if it doesn't exist
ALTER TABLE `users` 
ADD COLUMN IF NOT EXISTS `is_admin` tinyint(1) NOT NULL DEFAULT '0' AFTER `timestamp`;

-- Add index on is_admin for better query performance
ALTER TABLE `users`
ADD INDEX IF NOT EXISTS `is_admin` (`is_admin`);

-- To make a user an admin, run:
-- UPDATE users SET is_admin = 1 WHERE userid = <telegram_user_id>;

-- Example: Make user with ID 123456789 an admin
-- UPDATE users SET is_admin = 1 WHERE userid = 123456789;
