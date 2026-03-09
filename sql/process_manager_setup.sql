-- ==========================================================================
-- Process Manager: история запусков и желаемое состояние процессов
-- ==========================================================================

-- История запусков процессов (аудит-лог)
CREATE TABLE IF NOT EXISTS process_runs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    process_key VARCHAR(64) NOT NULL COMMENT 'Ключ процесса из реестра (registry)',
    pid INT DEFAULT NULL COMMENT 'PID операционной системы',
    flags_json TEXT DEFAULT NULL COMMENT 'JSON-массив флагов, с которыми запущен процесс',
    preset_name VARCHAR(128) DEFAULT NULL COMMENT 'Название пресета (NULL если кастомные флаги)',
    started_by BIGINT DEFAULT NULL COMMENT 'Telegram ID администратора, запустившего процесс',
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'Время запуска',
    stopped_at TIMESTAMP NULL DEFAULT NULL COMMENT 'Время остановки',
    exit_code INT DEFAULT NULL COMMENT 'Код завершения процесса',
    status ENUM('running', 'stopped', 'crashed', 'killed') NOT NULL DEFAULT 'running' COMMENT 'Итоговый статус',
    stop_reason VARCHAR(255) DEFAULT NULL COMMENT 'Причина: manual, auto_restart, crash, shutdown',
    INDEX idx_pr_process_key (process_key),
    INDEX idx_pr_started_at (started_at),
    INDEX idx_pr_process_started (process_key, started_at),
    INDEX idx_pr_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Желаемое состояние процессов: сохраняется при запуске/остановке,
-- используется для автоматического перезапуска после рестарта системы.
-- Если запись есть и should_run=TRUE — Process Manager при старте
-- автоматически поднимает процесс с указанными флагами.
CREATE TABLE IF NOT EXISTS process_desired_state (
    process_key VARCHAR(64) PRIMARY KEY COMMENT 'Ключ процесса из реестра',
    should_run BOOLEAN NOT NULL DEFAULT FALSE COMMENT 'Должен ли процесс быть запущен',
    flags_json TEXT DEFAULT NULL COMMENT 'JSON-массив флагов для запуска',
    preset_name VARCHAR(128) DEFAULT NULL COMMENT 'Название пресета',
    started_by BIGINT DEFAULT NULL COMMENT 'Telegram ID администратора',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Время обновления'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Права доступа для модуля process_manager
INSERT IGNORE INTO web_role_permissions (role, module_key, can_view, can_edit) VALUES
    ('admin', 'process_manager', TRUE, TRUE),
    ('expert', 'process_manager', TRUE, FALSE),
    ('viewer', 'process_manager', TRUE, FALSE);
