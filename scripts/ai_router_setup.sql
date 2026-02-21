-- ============================================================================
-- ai_router_setup.sql — Таблица логирования AI-маршрутизации
-- ============================================================================
-- Запустить: mysql -u <user> -p <database> < scripts/ai_router_setup.sql
-- ============================================================================

CREATE TABLE IF NOT EXISTS ai_router_log (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id         BIGINT NOT NULL COMMENT 'Telegram user ID',
    input_text      TEXT NOT NULL COMMENT 'Текст входного сообщения (обрезан до 500 символов)',
    detected_intent VARCHAR(64) NOT NULL COMMENT 'Определённое намерение (intent)',
    confidence      DECIMAL(4,3) NOT NULL DEFAULT 0.000 COMMENT 'Уверенность классификации 0.000-1.000',
    explain_code    VARCHAR(64) DEFAULT 'UNKNOWN' COMMENT 'Мнемонический код причины маршрутизации',
    response_time_ms INT DEFAULT 0 COMMENT 'Общее время обработки в миллисекундах',
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Время записи',

    INDEX idx_user_id (user_id),
    INDEX idx_created_at (created_at),
    INDEX idx_intent (detected_intent),
    INDEX idx_confidence (confidence)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Лог AI-маршрутизации для аналитики и отладки';

-- Добавляем настройку AI-модуля в bot_settings (если ещё нет)
INSERT IGNORE INTO bot_settings (setting_key, setting_value, updated_by, updated_at)
VALUES ('module_ai_router_enabled', '1', 0, NOW());
