-- Добавление статуса draft в ENUM статусов финальных сессий prompt tester.

SET @sql_add_draft_status = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'gk_final_prompt_tester_sessions'
              AND COLUMN_NAME = 'status'
              AND COLUMN_TYPE NOT LIKE "%'draft'%"
        ),
        "ALTER TABLE gk_final_prompt_tester_sessions MODIFY COLUMN status ENUM('draft','generating','judging','completed','abandoned') NOT NULL DEFAULT 'generating' COMMENT 'Статус: draft → generating → judging → completed/abandoned'",
        'SELECT 1'
    )
);

PREPARE stmt_add_draft_status FROM @sql_add_draft_status;
EXECUTE stmt_add_draft_status;
DEALLOCATE PREPARE stmt_add_draft_status;
