-- ==========================================================================
-- Admin Web: сессии аутентификации, роли пользователей, права доступа
-- ==========================================================================

-- Сессии аутентификации через Telegram Login Widget
CREATE TABLE IF NOT EXISTS web_sessions (
    id VARCHAR(64) PRIMARY KEY COMMENT 'Случайный токен сессии (secrets.token_urlsafe)',
    telegram_id BIGINT NOT NULL COMMENT 'Telegram user ID',
    telegram_username VARCHAR(255) DEFAULT NULL COMMENT 'Telegram username',
    telegram_first_name VARCHAR(255) DEFAULT NULL COMMENT 'Имя пользователя',
    telegram_last_name VARCHAR(255) DEFAULT NULL COMMENT 'Фамилия пользователя',
    telegram_photo_url TEXT DEFAULT NULL COMMENT 'URL аватара из Telegram',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL COMMENT 'Время истечения сессии',
    is_active BOOLEAN DEFAULT TRUE COMMENT 'Активна ли сессия',
    user_agent TEXT DEFAULT NULL COMMENT 'User-Agent браузера',
    ip_address VARCHAR(45) DEFAULT NULL COMMENT 'IP-адрес клиента',
    auth_method ENUM('telegram', 'password', 'dev') NOT NULL DEFAULT 'telegram' COMMENT 'Метод аутентификации',
    local_account_id INT DEFAULT NULL COMMENT 'ID локального password-аккаунта (если auth_method=password)',
    INDEX idx_ws_telegram_id (telegram_id),
    INDEX idx_ws_expires (expires_at),
    INDEX idx_ws_active (is_active, expires_at),
    INDEX idx_ws_auth_method (auth_method),
    INDEX idx_ws_local_account (local_account_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Совместимость для существующих инсталляций: добавляем новые столбцы web_sessions при необходимости
SET @db_name = DATABASE();

SET @sql_add_ws_auth_method = (
    SELECT IF(
        EXISTS (
            SELECT 1 FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = @db_name AND TABLE_NAME = 'web_sessions' AND COLUMN_NAME = 'auth_method'
        ),
        'SELECT 1',
        "ALTER TABLE web_sessions
            ADD COLUMN auth_method ENUM('telegram', 'password', 'dev') NOT NULL DEFAULT 'telegram'
            COMMENT 'Метод аутентификации' AFTER ip_address"
    )
);
PREPARE stmt_add_ws_auth_method FROM @sql_add_ws_auth_method;
EXECUTE stmt_add_ws_auth_method;
DEALLOCATE PREPARE stmt_add_ws_auth_method;

SET @sql_add_ws_local_account = (
    SELECT IF(
        EXISTS (
            SELECT 1 FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = @db_name AND TABLE_NAME = 'web_sessions' AND COLUMN_NAME = 'local_account_id'
        ),
        'SELECT 1',
        "ALTER TABLE web_sessions
            ADD COLUMN local_account_id INT DEFAULT NULL
            COMMENT 'ID локального password-аккаунта (если auth_method=password)'
            AFTER auth_method"
    )
);
PREPARE stmt_add_ws_local_account FROM @sql_add_ws_local_account;
EXECUTE stmt_add_ws_local_account;
DEALLOCATE PREPARE stmt_add_ws_local_account;

SET @sql_add_idx_ws_auth_method = (
    SELECT IF(
        EXISTS (
            SELECT 1 FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = @db_name AND TABLE_NAME = 'web_sessions' AND INDEX_NAME = 'idx_ws_auth_method'
        ),
        'SELECT 1',
        'ALTER TABLE web_sessions ADD INDEX idx_ws_auth_method (auth_method)'
    )
);
PREPARE stmt_add_idx_ws_auth_method FROM @sql_add_idx_ws_auth_method;
EXECUTE stmt_add_idx_ws_auth_method;
DEALLOCATE PREPARE stmt_add_idx_ws_auth_method;

SET @sql_add_idx_ws_local_account = (
    SELECT IF(
        EXISTS (
            SELECT 1 FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = @db_name AND TABLE_NAME = 'web_sessions' AND INDEX_NAME = 'idx_ws_local_account'
        ),
        'SELECT 1',
        'ALTER TABLE web_sessions ADD INDEX idx_ws_local_account (local_account_id)'
    )
);
PREPARE stmt_add_idx_ws_local_account FROM @sql_add_idx_ws_local_account;
EXECUTE stmt_add_idx_ws_local_account;
DEALLOCATE PREPARE stmt_add_idx_ws_local_account;

-- Локальные password-аккаунты (могут быть как привязаны к Telegram, так и standalone)
CREATE TABLE IF NOT EXISTS web_local_accounts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    login VARCHAR(100) NOT NULL COMMENT 'Нормализованный логин (lowercase)',
    password_hash VARCHAR(255) NOT NULL COMMENT 'PBKDF2-хеш пароля',
    principal_telegram_id BIGINT NOT NULL COMMENT 'Principal ID для RBAC/web_user_roles',
    linked_telegram_id BIGINT DEFAULT NULL COMMENT 'Опциональная привязка к Telegram user ID',
    display_name VARCHAR(255) DEFAULT NULL COMMENT 'Имя для отображения в web UI',
    is_active BOOLEAN NOT NULL DEFAULT TRUE COMMENT 'Активен ли аккаунт',
    failed_attempts INT NOT NULL DEFAULT 0 COMMENT 'Счётчик подряд неуспешных входов',
    locked_until TIMESTAMP NULL DEFAULT NULL COMMENT 'Время окончания блокировки после brute-force',
    last_login_at TIMESTAMP NULL DEFAULT NULL COMMENT 'Время последнего успешного входа',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_by BIGINT DEFAULT NULL COMMENT 'Кто создал аккаунт (principal id)',
    updated_by BIGINT DEFAULT NULL COMMENT 'Кто последний обновил аккаунт (principal id)',
    UNIQUE KEY uk_wla_login (login),
    UNIQUE KEY uk_wla_principal (principal_telegram_id),
    INDEX idx_wla_linked_telegram (linked_telegram_id),
    INDEX idx_wla_active (is_active),
    INDEX idx_wla_locked_until (locked_until)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Журнал попыток аутентификации для rate-limit и аудита
CREATE TABLE IF NOT EXISTS web_auth_attempts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    login_identifier VARCHAR(100) DEFAULT NULL COMMENT 'Логин для password auth (если есть)',
    ip_address VARCHAR(45) DEFAULT NULL COMMENT 'IP клиента',
    auth_method ENUM('telegram', 'password', 'dev') NOT NULL,
    success BOOLEAN NOT NULL DEFAULT FALSE,
    reason VARCHAR(255) DEFAULT NULL COMMENT 'Причина отказа/статус',
    principal_telegram_id BIGINT DEFAULT NULL COMMENT 'Principal ID при успешном входе',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_waa_login_created (login_identifier, created_at),
    INDEX idx_waa_ip_created (ip_address, created_at),
    INDEX idx_waa_method_created (auth_method, created_at),
    INDEX idx_waa_principal_created (principal_telegram_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Роли пользователей в веб-интерфейсе
-- super_admin: полный доступ ко всем модулям
-- admin: доступ к назначенным модулям с правом редактирования
-- expert: доступ к назначенным модулям (обычно expert_validation)
-- viewer: только просмотр назначенных модулей
CREATE TABLE IF NOT EXISTS web_user_roles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    telegram_id BIGINT NOT NULL COMMENT 'Telegram user ID',
    role ENUM('super_admin', 'admin', 'expert', 'viewer') NOT NULL DEFAULT 'viewer',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_by BIGINT DEFAULT NULL COMMENT 'Telegram ID того, кто назначил роль',
    UNIQUE KEY uk_wur_telegram_id (telegram_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Права доступа по ролям к модулям веб-интерфейса
-- Если записи нет — доступ запрещён.
-- super_admin всегда имеет полный доступ (проверяется в коде).
CREATE TABLE IF NOT EXISTS web_role_permissions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    role ENUM('super_admin', 'admin', 'expert', 'viewer') NOT NULL,
    module_key VARCHAR(64) NOT NULL COMMENT 'Ключ модуля: expert_validation, prompt_tester, и т.д.',
    can_view BOOLEAN DEFAULT FALSE COMMENT 'Разрешён просмотр',
    can_edit BOOLEAN DEFAULT FALSE COMMENT 'Разрешено редактирование',
    UNIQUE KEY uk_wrp_role_module (role, module_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Умолчания для ролей
INSERT IGNORE INTO web_role_permissions (role, module_key, can_view, can_edit) VALUES
    -- admin: всё кроме управления ролями
    ('admin', 'expert_validation', TRUE, TRUE),
    ('admin', 'prompt_tester', TRUE, TRUE),
    ('admin', 'gk_knowledge', TRUE, TRUE),
    -- expert: валидация пар и GK Knowledge
    ('expert', 'expert_validation', TRUE, TRUE),
    ('expert', 'prompt_tester', FALSE, FALSE),
    ('expert', 'gk_knowledge', TRUE, TRUE),
    -- viewer: только просмотр
    ('viewer', 'expert_validation', TRUE, FALSE),
    ('viewer', 'prompt_tester', TRUE, FALSE),
    ('viewer', 'gk_knowledge', TRUE, FALSE);
