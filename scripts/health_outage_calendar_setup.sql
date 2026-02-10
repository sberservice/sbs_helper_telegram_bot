-- Planned outage calendar for tax service
-- Stores outage dates and computed time windows

CREATE TABLE IF NOT EXISTS `tax_service_planned_outages` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `outage_date` date NOT NULL,
  `outage_type` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `start_timestamp` bigint(20) NOT NULL,
  `end_timestamp` bigint(20) NOT NULL,
  `created_by_userid` bigint(20) DEFAULT NULL,
  `updated_by_userid` bigint(20) DEFAULT NULL,
  `created_timestamp` bigint(20) NOT NULL,
  `updated_timestamp` bigint(20) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uniq_outage_date_type` (`outage_date`, `outage_type`),
  KEY `idx_outage_start` (`start_timestamp`),
  KEY `idx_outage_end` (`end_timestamp`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
