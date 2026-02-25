-- ============================================================================
-- ai_router_setup.sql — Таблица логирования AI-маршрутизации
-- ============================================================================
-- Запустить: mysql -u <user> -p <database> < sql/ai_router_setup.sql
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

CREATE TABLE IF NOT EXISTS ai_model_io_log (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NULL COMMENT 'Telegram user ID (может быть NULL для системных вызовов)',
    provider VARCHAR(32) NOT NULL COMMENT 'Имя LLM-провайдера',
    model_name VARCHAR(64) NOT NULL COMMENT 'Модель LLM',
    purpose VARCHAR(64) NOT NULL COMMENT 'Назначение вызова: classification/chat/rag_answer/rag_summary',
    request_text_full LONGTEXT NOT NULL COMMENT 'Полный текст запроса к модели (с маскировкой PII)',
    response_text_full LONGTEXT NULL COMMENT 'Полный текст ответа модели (с маскировкой PII)',
    error_text TEXT NULL COMMENT 'Текст ошибки при неуспешном вызове',
    status VARCHAR(32) NOT NULL DEFAULT 'ok' COMMENT 'Статус вызова: ok/http_error/parse_error',
    response_time_ms INT NULL COMMENT 'Время ответа модели в миллисекундах',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Время записи',

    INDEX idx_ai_model_io_user_id (user_id),
    INDEX idx_ai_model_io_created_at (created_at),
    INDEX idx_ai_model_io_purpose (purpose),
    INDEX idx_ai_model_io_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Полные логи prompt/response модели для RAG/AI маршрутизатора';

-- Добавляем настройку AI-модуля в bot_settings (если ещё нет)
-- Добавляем настройку AI-модуля в bot_settings (если ещё нет)
INSERT IGNORE INTO bot_settings (setting_key, setting_value, updated_timestamp, updated_by_userid)
VALUES ('module_ai_router_enabled', '1', UNIX_TIMESTAMP(), NULL);

INSERT IGNORE INTO bot_settings (setting_key, setting_value, updated_timestamp, updated_by_userid)
VALUES ('ai_deepseek_model', 'deepseek-chat', UNIX_TIMESTAMP(), NULL);

INSERT IGNORE INTO bot_settings (setting_key, setting_value, updated_timestamp, updated_by_userid)
VALUES ('ai_deepseek_model_classification', 'deepseek-chat', UNIX_TIMESTAMP(), NULL);

INSERT IGNORE INTO bot_settings (setting_key, setting_value, updated_timestamp, updated_by_userid)
VALUES ('ai_deepseek_model_response', 'deepseek-chat', UNIX_TIMESTAMP(), NULL);

INSERT IGNORE INTO bot_settings (setting_key, setting_value, updated_timestamp, updated_by_userid)
VALUES ('ai_rag_html_splitter_enabled', '1', UNIX_TIMESTAMP(), NULL);
