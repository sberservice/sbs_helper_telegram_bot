-- Add is_admin field to existing users table
-- Run this script to update existing database with admin functionality

ALTER TABLE users 
ADD COLUMN is_admin tinyint(1) NOT NULL DEFAULT 0 AFTER timestamp,
ADD KEY is_admin (is_admin);

-- Example: Make a specific user an admin (replace with actual userid)
-- UPDATE users SET is_admin = 1 WHERE userid = YOUR_TELEGRAM_USER_ID;
