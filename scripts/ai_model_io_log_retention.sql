-- ============================================================================
-- ai_model_io_log_retention.sql — очистка full-text логов model I/O
-- ============================================================================
-- Запустить: mysql -u <user> -p <database> < scripts/ai_model_io_log_retention.sql
-- По умолчанию оставляет записи только за последние 30 дней.
-- ============================================================================

DELETE FROM ai_model_io_log
WHERE created_at < DATE_SUB(NOW(), INTERVAL 30 DAY);

SELECT ROW_COUNT() AS deleted_rows;
