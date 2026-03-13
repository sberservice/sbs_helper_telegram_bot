-- =====================================================================
-- Group Knowledge: timestamp исходного вопроса в логе автоответчика
-- =====================================================================

SET @db_name = DATABASE();

SET @sql_add_question_message_date = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = @db_name
              AND TABLE_NAME = 'gk_responder_log'
              AND COLUMN_NAME = 'question_message_date'
        ),
        'SELECT 1',
        "ALTER TABLE gk_responder_log
            ADD COLUMN question_message_date BIGINT
            NULL
            COMMENT 'Время сообщения-вопроса (UNIX timestamp)'
            AFTER question_message_id"
    )
);

PREPARE stmt_add_question_message_date FROM @sql_add_question_message_date;
EXECUTE stmt_add_question_message_date;
DEALLOCATE PREPARE stmt_add_question_message_date;
