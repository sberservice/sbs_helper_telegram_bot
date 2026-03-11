-- =====================================================================
-- Group Knowledge: поля качества Q&A-пар
-- =====================================================================

SET @db_name = DATABASE();

SET @sql_add_confidence_reason = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = @db_name
              AND TABLE_NAME = 'gk_qa_pairs'
              AND COLUMN_NAME = 'confidence_reason'
        ),
        'SELECT 1',
        "ALTER TABLE gk_qa_pairs
            ADD COLUMN confidence_reason VARCHAR(1024)
            CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
            NULL
            COMMENT 'Причина выставленного confidence'
            AFTER confidence"
    )
);

PREPARE stmt_add_confidence_reason FROM @sql_add_confidence_reason;
EXECUTE stmt_add_confidence_reason;
DEALLOCATE PREPARE stmt_add_confidence_reason;

SET @sql_add_fullness = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = @db_name
              AND TABLE_NAME = 'gk_qa_pairs'
              AND COLUMN_NAME = 'fullness'
        ),
        'SELECT 1',
        "ALTER TABLE gk_qa_pairs
            ADD COLUMN fullness FLOAT
            NULL
            COMMENT 'Полнота/подробность ответа (0.0–1.0)'
            AFTER confidence_reason"
    )
);

PREPARE stmt_add_fullness FROM @sql_add_fullness;
EXECUTE stmt_add_fullness;
DEALLOCATE PREPARE stmt_add_fullness;
