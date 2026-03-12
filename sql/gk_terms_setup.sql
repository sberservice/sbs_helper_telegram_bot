    -- Таблица для хранения защищённых терминов (per-group).
    --
    -- gk_terms — термины, найденные LLM-сканированием или добавленные вручную.
    --   - term с definition IS NOT NULL → участвует в LLM-промпте (аббревиатура).
    --   - term с definition IS NULL → только BM25-защита (protected token).
    -- gk_term_validations — экспертные вердикты по каждому термину.
    --
    -- group_id = 0 — зарезервировано для глобальных (мигрированных) терминов,
    -- применяемых ко всем группам.

    CREATE TABLE IF NOT EXISTS gk_terms (
        id              INT AUTO_INCREMENT PRIMARY KEY,
        group_id        BIGINT       NOT NULL DEFAULT 0   COMMENT 'ID группы Telegram (0 = глобальный)',
        term            VARCHAR(100) NOT NULL              COMMENT 'Сокращение / термин (в нижнем регистре)',
        definition      TEXT         DEFAULT NULL           COMMENT 'Расшифровка / определение (NULL = только BM25-защита)',
        source          ENUM('llm_discovered', 'migrated', 'manual') NOT NULL DEFAULT 'llm_discovered',
        status          ENUM('pending', 'approved', 'rejected') NOT NULL DEFAULT 'pending',
        confidence      FLOAT        DEFAULT NULL           COMMENT 'Уверенность LLM (0.0–1.0)',
        llm_model_used  VARCHAR(100) DEFAULT NULL,
        llm_request_payload TEXT     DEFAULT NULL           COMMENT 'Debug JSON запроса к LLM',
        scan_batch_id   VARCHAR(36)  DEFAULT NULL           COMMENT 'UUID батча сканирования',
        expert_status   ENUM('approved', 'rejected') DEFAULT NULL COMMENT 'Денормализованный статус экспертной валидации',
        expert_validated_at DATETIME DEFAULT NULL,
        created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
        updated_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

        UNIQUE KEY uq_group_term (group_id, term),
        KEY idx_group_status (group_id, status),
        KEY idx_scan_batch (scan_batch_id),
        KEY idx_expert_status (expert_status),
        KEY idx_status_created (status, created_at),
        KEY idx_has_definition ((definition IS NOT NULL))
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


    CREATE TABLE IF NOT EXISTS gk_term_validations (
        id                   INT AUTO_INCREMENT PRIMARY KEY,
        term_id              INT          NOT NULL,
        expert_telegram_id   BIGINT       NOT NULL,
        verdict              ENUM('approved', 'rejected', 'edited') NOT NULL,
        edited_term          VARCHAR(100) DEFAULT NULL  COMMENT 'Исправленный термин (при verdict=edited)',
        edited_definition    TEXT         DEFAULT NULL  COMMENT 'Исправленная расшифровка (при verdict=edited)',
        comment              TEXT         DEFAULT NULL,
        created_at           TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
        updated_at           TIMESTAMP    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

        UNIQUE KEY uq_term_expert (term_id, expert_telegram_id),
        KEY idx_term_id (term_id),

        CONSTRAINT fk_term_validation_term
            FOREIGN KEY (term_id) REFERENCES gk_terms (id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


    -- ---------------------------------------------------------------------------
    -- Миграция существующих хардкодных терминов из _GK_FIXED_TERMS (qa_search.py)
    -- и аббревиатур из THREAD_VALIDATION_PROMPT (qa_analyzer.py).
    -- group_id = 0 = глобальные (legacy), source = 'migrated', status = 'approved'.
    -- Термины с расшифровкой имеют definition, остальные — только BM25-защита.
    -- ---------------------------------------------------------------------------

    INSERT IGNORE INTO gk_terms (group_id, term, definition, source, status, expert_status) VALUES
    -- Protected search tokens (только BM25-защита, без расшифровки)
    (0, 'осно',      NULL,                                                  'migrated', 'approved', 'approved'),
    (0, 'усн',       NULL,                                                  'migrated', 'approved', 'approved'),
    (0, 'псн',       NULL,                                                  'migrated', 'approved', 'approved'),
    (0, 'енвд',      NULL,                                                  'migrated', 'approved', 'approved'),
    (0, 'нпд',       NULL,                                                  'migrated', 'approved', 'approved'),
    (0, 'сно',       NULL,                                                  'migrated', 'approved', 'approved'),
    (0, 'фн',        NULL,                                                  'migrated', 'approved', 'approved'),
    (0, 'ккт',       NULL,                                                  'migrated', 'approved', 'approved'),
    (0, 'офд',       NULL,                                                  'migrated', 'approved', 'approved'),
    (0, 'инн',       NULL,                                                  'migrated', 'approved', 'approved'),
    (0, 'кпп',       NULL,                                                  'migrated', 'approved', 'approved'),
    (0, 'аусн',      NULL,                                                  'migrated', 'approved', 'approved'),
    (0, 'ип',        NULL,                                                  'migrated', 'approved', 'approved'),
    (0, 'ндс',       NULL,                                                  'migrated', 'approved', 'approved'),
    (0, 'ндфл',      NULL,                                                  'migrated', 'approved', 'approved'),
    (0, 'ооо',       NULL,                                                  'migrated', 'approved', 'approved'),
    (0, 'кбк',       NULL,                                                  'migrated', 'approved', 'approved'),
    (0, 'ффд',       NULL,                                                  'migrated', 'approved', 'approved'),
    (0, 'фд',        NULL,                                                  'migrated', 'approved', 'approved'),
    (0, 'фп',        NULL,                                                  'migrated', 'approved', 'approved'),
    (0, 'фпд',       NULL,                                                  'migrated', 'approved', 'approved'),
    (0, 'рн',        NULL,                                                  'migrated', 'approved', 'approved'),
    (0, 'зн',        NULL,                                                  'migrated', 'approved', 'approved'),
    (0, 'ккм',       NULL,                                                  'migrated', 'approved', 'approved'),
    (0, 'pos',       NULL,                                                  'migrated', 'approved', 'approved'),
    (0, 'пин',       NULL,                                                  'migrated', 'approved', 'approved'),
    (0, 'арм',       NULL,                                                  'migrated', 'approved', 'approved'),
    (0, 'цто',       NULL,                                                  'migrated', 'approved', 'approved'),
    (0, 'то',        NULL,                                                  'migrated', 'approved', 'approved'),
    (0, 'усо',       NULL,                                                  'migrated', 'approved', 'approved'),
    (0, 'атм',       NULL,                                                  'migrated', 'approved', 'approved'),
    (0, 'nfc',       NULL,                                                  'migrated', 'approved', 'approved'),
    (0, 'sim',       NULL,                                                  'migrated', 'approved', 'approved'),
    (0, 'pin',       NULL,                                                  'migrated', 'approved', 'approved'),
    (0, 'tcp',       NULL,                                                  'migrated', 'approved', 'approved'),
    (0, 'usb',       NULL,                                                  'migrated', 'approved', 'approved'),
    (0, 'lan',       NULL,                                                  'migrated', 'approved', 'approved'),
    (0, 'gps',       NULL,                                                  'migrated', 'approved', 'approved'),
    (0, 'гпн',       NULL,                                                  'migrated', 'approved', 'approved'),
    (0, 'эвотор 6',  NULL,                                                  'migrated', 'approved', 'approved'),
    (0, 'эво6',      NULL,                                                  'migrated', 'approved', 'approved'),
    (0, 'эвотор6',   NULL,                                                  'migrated', 'approved', 'approved'),
    (0, 'утп',       NULL,                                                  'migrated', 'approved', 'approved'),
    (0, 'лкп',       NULL,                                                  'migrated', 'approved', 'approved'),
    (0, 'лкк',       NULL,                                                  'migrated', 'approved', 'approved'),
    (0, '1с',        NULL,                                                  'migrated', 'approved', 'approved'),
    -- Термины с расшифровкой (участвуют и в BM25, и в LLM-промпте)
    (0, 'гз',        'Горячая замена',                                      'migrated', 'approved', 'approved'),
    (0, 'чз',        'Честный Знак',                                        'migrated', 'approved', 'approved'),
    (0, 'уз',        'удаленная загрузка',                                  'migrated', 'approved', 'approved'),
    (0, 'ца',        'Центральный Аппарат',                                 'migrated', 'approved', 'approved'),
    (0, 'цк',        'Центр Компетенций',                                   'migrated', 'approved', 'approved'),
    (0, 'сбс',       'СберСервис',                                          'migrated', 'approved', 'approved'),
    (0, 'рм',        'Региональный Менеджер',                               'migrated', 'approved', 'approved'),
    (0, 'тст',       'торгово-сервисная точка',                             'migrated', 'approved', 'approved'),
    (0, 'фиас',      'Федеральная информационная адресная система',          'migrated', 'approved', 'approved'),
    (0, 'техобнул',  'технологическое обнуление',                           'migrated', 'approved', 'approved');
