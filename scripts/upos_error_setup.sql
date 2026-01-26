-- UPOS Error Module Database Setup
-- Run this script to create the required tables for the UPOS Error module

-- Categories table
CREATE TABLE IF NOT EXISTS `upos_error_categories` (
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

-- Error codes table
CREATE TABLE IF NOT EXISTS `upos_error_codes` (
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

-- Unknown codes tracking table
CREATE TABLE IF NOT EXISTS `upos_error_unknown_codes` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `error_code` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `times_requested` int(11) NOT NULL DEFAULT '1',
  `first_requested_timestamp` bigint(20) NOT NULL,
  `last_requested_timestamp` bigint(20) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `error_code` (`error_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Request log table (for statistics)
CREATE TABLE IF NOT EXISTS `upos_error_request_log` (
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

-- Sample categories
INSERT INTO `upos_error_categories` (`name`, `description`, `display_order`, `created_timestamp`) VALUES
('Принтер', 'Ошибки, связанные с работой принтера', 1, UNIX_TIMESTAMP()),
('Сеть', 'Сетевые ошибки и проблемы связи', 2, UNIX_TIMESTAMP()),
('Касса', 'Ошибки кассовой системы', 3, UNIX_TIMESTAMP()),
('Авторизация', 'Ошибки авторизации и доступа', 4, UNIX_TIMESTAMP()),
('Общие', 'Прочие ошибки системы', 99, UNIX_TIMESTAMP())
ON DUPLICATE KEY UPDATE `name` = VALUES(`name`);

-- Sample error codes
INSERT INTO `upos_error_codes` (`error_code`, `category_id`, `description`, `suggested_actions`, `created_timestamp`) VALUES
('101', (SELECT id FROM upos_error_categories WHERE name = 'Принтер'), 'Нет бумаги в принтере', '1. Откройте крышку принтера\n2. Установите новый рулон бумаги\n3. Закройте крышку и повторите операцию', UNIX_TIMESTAMP()),
('102', (SELECT id FROM upos_error_categories WHERE name = 'Принтер'), 'Замятие бумаги', '1. Выключите принтер\n2. Откройте крышку и аккуратно извлеките замятую бумагу\n3. Проверьте, не осталось ли обрывков\n4. Включите принтер и повторите операцию', UNIX_TIMESTAMP()),
('201', (SELECT id FROM upos_error_categories WHERE name = 'Сеть'), 'Нет связи с сервером', '1. Проверьте подключение к интернету\n2. Перезагрузите роутер\n3. Если проблема сохраняется, обратитесь в техподдержку', UNIX_TIMESTAMP()),
('301', (SELECT id FROM upos_error_categories WHERE name = 'Касса'), 'Смена не открыта', '1. Выполните открытие смены\n2. При необходимости обратитесь к администратору', UNIX_TIMESTAMP()),
('401', (SELECT id FROM upos_error_categories WHERE name = 'Авторизация'), 'Неверный пароль', '1. Проверьте правильность введённого пароля\n2. При многократных ошибках обратитесь к администратору для сброса пароля', UNIX_TIMESTAMP())
ON DUPLICATE KEY UPDATE `error_code` = VALUES(`error_code`);
