-- Перевод confidence_reason в TEXT для хранения длинных объяснений
-- в финальном GK prompt tester без обрезки.

SET @sql_modify_confidence_reason = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'gk_final_prompt_tester_generations'
              AND COLUMN_NAME = 'confidence_reason'
              AND DATA_TYPE <> 'text'
        ),
        'ALTER TABLE gk_final_prompt_tester_generations MODIFY COLUMN confidence_reason TEXT DEFAULT NULL COMMENT ''Краткая причина confidence''',
        'SELECT 1'
    )
);

PREPARE stmt_modify_confidence_reason FROM @sql_modify_confidence_reason;
EXECUTE stmt_modify_confidence_reason;
DEALLOCATE PREPARE stmt_modify_confidence_reason;
