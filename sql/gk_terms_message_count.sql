-- Миграция: добавление счётчика использования термина в сообщениях.
--
-- message_count — количество сообщений группы, в которых встречается термин.
-- message_count_updated_at — дата последнего пересчёта для отслеживания актуальности.
--
-- Счётчик используется для ранжирования аббревиатур при формировании
-- промпта: в инъекцию попадают только top-N наиболее часто используемых
-- терминов (настраивается через GK_ACRONYMS_MAX_PROMPT_TERMS).
--
-- Примечание по совместимости:
-- В некоторых версиях MySQL/MariaDB синтаксис ADD COLUMN IF NOT EXISTS
-- и CREATE INDEX IF NOT EXISTS не поддерживается.
-- Поэтому ниже используется проверка через INFORMATION_SCHEMA.

SET @current_db = DATABASE();

-- Добавить колонку message_count, если отсутствует.
SET @has_message_count = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = @current_db
      AND TABLE_NAME = 'gk_terms'
      AND COLUMN_NAME = 'message_count'
);

SET @sql_add_message_count = IF(
    @has_message_count = 0,
    'ALTER TABLE gk_terms ADD COLUMN message_count INT NOT NULL DEFAULT 0 COMMENT ''Число сообщений группы, в которых встречается термин''',
    'SELECT ''Column message_count already exists'''
);

PREPARE stmt FROM @sql_add_message_count;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Добавить колонку message_count_updated_at, если отсутствует.
SET @has_message_count_updated_at = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = @current_db
      AND TABLE_NAME = 'gk_terms'
      AND COLUMN_NAME = 'message_count_updated_at'
);

SET @sql_add_message_count_updated_at = IF(
    @has_message_count_updated_at = 0,
    'ALTER TABLE gk_terms ADD COLUMN message_count_updated_at DATETIME DEFAULT NULL COMMENT ''Дата последнего пересчёта message_count''',
    'SELECT ''Column message_count_updated_at already exists'''
);

PREPARE stmt FROM @sql_add_message_count_updated_at;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Индекс для сортировки по популярности при построении промпта.
SET @has_idx_message_count = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = @current_db
      AND TABLE_NAME = 'gk_terms'
      AND INDEX_NAME = 'idx_message_count'
);

SET @sql_add_idx_message_count = IF(
    @has_idx_message_count = 0,
    'CREATE INDEX idx_message_count ON gk_terms (message_count DESC)',
    'SELECT ''Index idx_message_count already exists'''
);

PREPARE stmt FROM @sql_add_idx_message_count;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
