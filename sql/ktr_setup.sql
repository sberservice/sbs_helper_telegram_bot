-- KTR (Коэффициент Трудозатрат) Module Database Setup
-- Run this script to create the required tables for the KTR module

-- Categories table
CREATE TABLE IF NOT EXISTS `ktr_categories` (
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

-- KTR codes table
CREATE TABLE IF NOT EXISTS `ktr_codes` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `code` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `category_id` bigint(20) DEFAULT NULL,
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `minutes` int(11) NOT NULL DEFAULT '0',
  `date_updated` varchar(10) DEFAULT NULL COMMENT 'Date when minutes value was updated (dd.mm.yyyy format)',
  `active` tinyint(1) NOT NULL DEFAULT '1',
  `created_timestamp` bigint(20) NOT NULL,
  `updated_timestamp` bigint(20) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `code` (`code`),
  KEY `category_id` (`category_id`),
  KEY `active` (`active`),
  CONSTRAINT `fk_ktr_category` FOREIGN KEY (`category_id`) REFERENCES `ktr_categories` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Unknown codes tracking table
CREATE TABLE IF NOT EXISTS `ktr_unknown_codes` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `code` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `times_requested` int(11) NOT NULL DEFAULT '1',
  `first_requested_timestamp` bigint(20) NOT NULL,
  `last_requested_timestamp` bigint(20) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `code` (`code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Request log table (for statistics)
CREATE TABLE IF NOT EXISTS `ktr_request_log` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `user_id` bigint(20) NOT NULL,
  `code` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `found` tinyint(1) NOT NULL,
  `request_timestamp` bigint(20) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `user_id` (`user_id`),
  KEY `code` (`code`),
  KEY `request_timestamp` (`request_timestamp`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Sample categories
INSERT INTO `ktr_categories` (`name`, `description`, `display_order`, `created_timestamp`) VALUES
('POS-терминалы', 'Работы с POS-терминалами', 1, UNIX_TIMESTAMP()),
('Кассы', 'Работы с кассовым оборудованием', 2, UNIX_TIMESTAMP()),
('Сетевое оборудование', 'Работы с сетевым оборудованием', 3, UNIX_TIMESTAMP()),
('Программное обеспечение', 'Работы с ПО', 4, UNIX_TIMESTAMP()),
('Прочее', 'Прочие работы', 99, UNIX_TIMESTAMP())
ON DUPLICATE KEY UPDATE `name` = VALUES(`name`);

-- Sample KTR codes
INSERT INTO `ktr_codes` (`code`, `category_id`, `description`, `minutes`, `created_timestamp`) VALUES
('POS2421', (SELECT id FROM ktr_categories WHERE name = 'POS-терминалы'), 'Установка POS-терминала', 90, UNIX_TIMESTAMP()),
('POS2422', (SELECT id FROM ktr_categories WHERE name = 'POS-терминалы'), 'Замена POS-терминала', 60, UNIX_TIMESTAMP()),
('POS2423', (SELECT id FROM ktr_categories WHERE name = 'POS-терминалы'), 'Настройка POS-терминала', 45, UNIX_TIMESTAMP()),
('KASS001', (SELECT id FROM ktr_categories WHERE name = 'Кассы'), 'Установка кассы', 120, UNIX_TIMESTAMP()),
('KASS002', (SELECT id FROM ktr_categories WHERE name = 'Кассы'), 'Замена кассы', 90, UNIX_TIMESTAMP()),
('NET001', (SELECT id FROM ktr_categories WHERE name = 'Сетевое оборудование'), 'Настройка роутера', 30, UNIX_TIMESTAMP())
ON DUPLICATE KEY UPDATE `code` = VALUES(`code`);
