-- App Settings Table Setup
-- Таблица для общепроектных runtime-настроек (не только Telegram-бот).

CREATE TABLE IF NOT EXISTS `app_settings` (
  `setting_key` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `setting_value` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `updated_timestamp` int NOT NULL DEFAULT '0',
  `updated_by_userid` bigint DEFAULT NULL,
  PRIMARY KEY (`setting_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
