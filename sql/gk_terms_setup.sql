-- Таблицы для хранения защищённых терминов и аббревиатур (per-group).
--
-- gk_terms — термины/аббревиатуры, найденные LLM-сканированием или добавленные вручную.
-- gk_term_validations — экспертные вердикты по каждому термину.
--
-- group_id = 0 — зарезервировано для глобальных (мигрированных) терминов,
-- применяемых ко всем группам.

CREATE TABLE IF NOT EXISTS gk_terms (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    group_id        BIGINT       NOT NULL DEFAULT 0   COMMENT 'ID группы Telegram (0 = глобальный)',
    term            VARCHAR(100) NOT NULL              COMMENT 'Сокращение / термин (в нижнем регистре)',
    term_type       ENUM('fixed_term', 'acronym') NOT NULL  COMMENT 'Тип: protected-токен или аббревиатура с расшифровкой',
    definition      TEXT         DEFAULT NULL           COMMENT 'Расшифровка (только для acronym)',
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

    UNIQUE KEY uq_group_term_type (group_id, term, term_type),
    KEY idx_group_status (group_id, status),
    KEY idx_term_type (term_type),
    KEY idx_scan_batch (scan_batch_id),
    KEY idx_expert_status (expert_status),
    KEY idx_status_created (status, created_at)
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
-- ---------------------------------------------------------------------------

INSERT IGNORE INTO gk_terms (group_id, term, term_type, source, status, expert_status) VALUES
-- Из _GK_FIXED_TERMS (qa_search.py) — protected search tokens
(0, 'осно',      'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'усн',       'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'псн',       'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'енвд',      'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'нпд',       'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'сно',       'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'фн',        'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'ккт',       'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'офд',       'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'инн',       'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'кпп',       'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'аусн',      'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'ип',        'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'ндс',       'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'ндфл',      'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'ооо',       'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'кбк',       'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'ффд',       'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'фд',        'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'фп',        'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'фпд',       'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'рн',        'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'зн',        'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'ккм',       'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'pos',       'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'пин',       'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'арм',       'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'цто',       'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'то',        'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'усо',       'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'атм',       'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'nfc',       'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'sim',       'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'pin',       'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'tcp',       'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'usb',       'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'lan',       'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'gps',       'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'гз',        'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'гпн',       'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'эвотор 6',  'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'эво6',      'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'эвотор6',   'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'чз',        'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'уз',        'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'ца',        'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'цк',        'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'сбс',       'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'рм',        'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'тст',       'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'утп',       'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'лкп',       'fixed_term', 'migrated', 'approved', 'approved'),
(0, 'лкк',       'fixed_term', 'migrated', 'approved', 'approved'),
(0, '1с',        'fixed_term', 'migrated', 'approved', 'approved'),

-- Аббревиатуры из THREAD_VALIDATION_PROMPT (qa_analyzer.py)
-- Также зарегистрированы как fixed_term выше, здесь добавлены как acronym с расшифровкой.
(0, 'гз',        'acronym', 'migrated', 'approved', 'approved'),
(0, 'чз',        'acronym', 'migrated', 'approved', 'approved'),
(0, 'уз',        'acronym', 'migrated', 'approved', 'approved'),
(0, 'ца',        'acronym', 'migrated', 'approved', 'approved'),
(0, 'цк',        'acronym', 'migrated', 'approved', 'approved'),
(0, 'сбс',       'acronym', 'migrated', 'approved', 'approved'),
(0, 'рм',        'acronym', 'migrated', 'approved', 'approved'),
(0, 'тст',       'acronym', 'migrated', 'approved', 'approved'),
(0, 'фиас',      'acronym', 'migrated', 'approved', 'approved'),
(0, 'техобнул',  'acronym', 'migrated', 'approved', 'approved');

-- Теперь обновим расшифровки аббревиатур
UPDATE gk_terms SET definition = 'Горячая замена'                             WHERE group_id = 0 AND term = 'гз'       AND term_type = 'acronym';
UPDATE gk_terms SET definition = 'Честный Знак'                              WHERE group_id = 0 AND term = 'чз'       AND term_type = 'acronym';
UPDATE gk_terms SET definition = 'удаленная загрузка'                        WHERE group_id = 0 AND term = 'уз'       AND term_type = 'acronym';
UPDATE gk_terms SET definition = 'Центральный Аппарат'                       WHERE group_id = 0 AND term = 'ца'       AND term_type = 'acronym';
UPDATE gk_terms SET definition = 'Центр Компетенций'                         WHERE group_id = 0 AND term = 'цк'       AND term_type = 'acronym';
UPDATE gk_terms SET definition = 'СберСервис'                                WHERE group_id = 0 AND term = 'сбс'      AND term_type = 'acronym';
UPDATE gk_terms SET definition = 'Региональный Менеджер'                     WHERE group_id = 0 AND term = 'рм'       AND term_type = 'acronym';
UPDATE gk_terms SET definition = 'торгово-сервисная точка'                   WHERE group_id = 0 AND term = 'тст'      AND term_type = 'acronym';
UPDATE gk_terms SET definition = 'Федеральная информационная адресная система' WHERE group_id = 0 AND term = 'фиас'    AND term_type = 'acronym';
UPDATE gk_terms SET definition = 'технологическое обнуление'                 WHERE group_id = 0 AND term = 'техобнул' AND term_type = 'acronym';
