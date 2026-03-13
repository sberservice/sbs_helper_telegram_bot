-- =====================================================================
-- Group Knowledge: отладочный payload запроса LLM для лога автоответчика
-- =====================================================================

SET @db_name = DATABASE();

SET @sql_add_llm_request_payload = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = @db_name
              AND TABLE_NAME = 'gk_responder_log'
              AND COLUMN_NAME = 'llm_request_payload'
        ),
        'SELECT 1',
        "ALTER TABLE gk_responder_log
            ADD COLUMN llm_request_payload LONGTEXT
            CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
            NULL
            COMMENT 'Полный JSON запроса, отправленного в LLM'
            AFTER answer_text"
    )
);

PREPARE stmt_add_llm_request_payload FROM @sql_add_llm_request_payload;
EXECUTE stmt_add_llm_request_payload;
DEALLOCATE PREPARE stmt_add_llm_request_payload;
