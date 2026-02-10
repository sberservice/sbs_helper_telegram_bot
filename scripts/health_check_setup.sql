-- Tax service health check status table
-- Stores latest health status and timestamps

CREATE TABLE IF NOT EXISTS `tax_service_health` (
  `id` tinyint(1) NOT NULL,
  `last_status` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `last_checked_at` bigint(20) DEFAULT NULL,
  `last_healthy_at` bigint(20) DEFAULT NULL,
  `last_broken_at` bigint(20) DEFAULT NULL,
  `last_broken_started_at` bigint(20) DEFAULT NULL,
  `updated_timestamp` bigint(20) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
