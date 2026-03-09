-- ==========================================================================
-- Экспертная валидация Q&A-пар Group Knowledge
-- ==========================================================================

-- Записи валидации: каждый эксперт может оценить каждую пару один раз.
-- Последняя запись (по updated_at) считается актуальной, если эксперт пересмотрел.
CREATE TABLE IF NOT EXISTS gk_expert_validations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    qa_pair_id INT NOT NULL COMMENT 'FK → gk_qa_pairs.id',
    expert_telegram_id BIGINT NOT NULL COMMENT 'Telegram ID эксперта',
    verdict ENUM('approved', 'rejected', 'skipped') NOT NULL COMMENT 'Вердикт эксперта',
    comment TEXT DEFAULT NULL COMMENT 'Необязательный комментарий эксперта',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_gev_qa_pair (qa_pair_id),
    INDEX idx_gev_expert (expert_telegram_id),
    INDEX idx_gev_verdict (verdict),
    UNIQUE KEY uk_gev_pair_expert (qa_pair_id, expert_telegram_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Добавляем поле expert_status в gk_qa_pairs если его ещё нет.
-- NULL = не валидирована, 'approved' = эксперт одобрил, 'rejected' = эксперт отклонил.
-- Автоматически обновляется триггером или кодом приложения.
SET @db_name = DATABASE();

-- expert_status
SET @sql_add_expert_status = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = @db_name
              AND TABLE_NAME = 'gk_qa_pairs'
              AND COLUMN_NAME = 'expert_status'
        ),
        'SELECT 1',
        "ALTER TABLE gk_qa_pairs
            ADD COLUMN expert_status ENUM('approved', 'rejected') DEFAULT NULL
            COMMENT 'Сводный статус экспертной валидации'
            AFTER vector_indexed"
    )
);
PREPARE stmt_add_expert_status FROM @sql_add_expert_status;
EXECUTE stmt_add_expert_status;
DEALLOCATE PREPARE stmt_add_expert_status;

-- expert_validated_at
SET @sql_add_expert_validated_at = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = @db_name
              AND TABLE_NAME = 'gk_qa_pairs'
              AND COLUMN_NAME = 'expert_validated_at'
        ),
        'SELECT 1',
        "ALTER TABLE gk_qa_pairs
            ADD COLUMN expert_validated_at TIMESTAMP NULL DEFAULT NULL
            COMMENT 'Когда пара была валидирована экспертом'
            AFTER expert_status"
    )
);
PREPARE stmt_add_expert_validated_at FROM @sql_add_expert_validated_at;
EXECUTE stmt_add_expert_validated_at;
DEALLOCATE PREPARE stmt_add_expert_validated_at;

-- idx_gqp_expert_status
SET @sql_add_expert_status_index = (
    SELECT IF(
        EXISTS (
            SELECT 1
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = @db_name
              AND TABLE_NAME = 'gk_qa_pairs'
              AND INDEX_NAME = 'idx_gqp_expert_status'
        ),
        'SELECT 1',
        'ALTER TABLE gk_qa_pairs ADD INDEX idx_gqp_expert_status (expert_status)'
    )
);
PREPARE stmt_add_expert_status_index FROM @sql_add_expert_status_index;
EXECUTE stmt_add_expert_status_index;
DEALLOCATE PREPARE stmt_add_expert_status_index;