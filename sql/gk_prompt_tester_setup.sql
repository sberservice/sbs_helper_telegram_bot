-- ==========================================================================
-- GK Prompt Tester: таблицы для A/B тестирования промптов извлечения Q&A-пар
-- ==========================================================================

-- Шаблоны промптов для извлечения Q&A-пар
CREATE TABLE IF NOT EXISTS gk_prompt_tester_prompts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    label VARCHAR(255) NOT NULL COMMENT 'Название промпта',
    system_prompt TEXT NOT NULL COMMENT 'Пользовательский промпт извлечения (инструкция для LLM; system prompt фиксированный в QAAnalyzer)',
    extraction_type ENUM('thread_reply', 'llm_inferred') NOT NULL DEFAULT 'llm_inferred'
        COMMENT 'Тип извлечения: thread_reply или llm_inferred',
    model_name VARCHAR(128) DEFAULT NULL COMMENT 'Название модели LLM (NULL = по умолчанию)',
    temperature FLOAT DEFAULT 0.3 COMMENT 'Температура генерации',
    created_by_telegram_id BIGINT DEFAULT NULL COMMENT 'Кто создал промпт',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    is_active BOOLEAN NOT NULL DEFAULT TRUE COMMENT 'Активен ли промпт',
    INDEX idx_gkpt_prompts_active (is_active),
    INDEX idx_gkpt_prompts_type (extraction_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Сессии тестирования промптов
CREATE TABLE IF NOT EXISTS gk_prompt_tester_sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL COMMENT 'Название сессии',
    status ENUM('generating', 'judging', 'completed', 'abandoned') NOT NULL DEFAULT 'generating'
        COMMENT 'Статус: generating → judging → completed/abandoned',
    prompt_ids JSON NOT NULL COMMENT 'Массив ID промптов для сравнения',
    prompts_config_snapshot JSON DEFAULT NULL COMMENT 'Снимок конфигурации промптов на момент создания',
    judge_mode ENUM('human', 'llm', 'both') NOT NULL DEFAULT 'human'
        COMMENT 'Режим оценки: human (ручная), llm (автоматическая), both',
    source_group_id BIGINT DEFAULT NULL COMMENT 'ID группы-источника сообщений',
    source_date_from VARCHAR(10) DEFAULT NULL COMMENT 'Дата начала выборки (YYYY-MM-DD)',
    source_date_to VARCHAR(10) DEFAULT NULL COMMENT 'Дата конца выборки (YYYY-MM-DD)',
    message_count INT DEFAULT 0 COMMENT 'Количество цепочек/контекстов для применения промптов',
    source_messages_snapshot JSON DEFAULT NULL COMMENT 'Снимок ID исходных сообщений',
    created_by_telegram_id BIGINT DEFAULT NULL COMMENT 'Кто создал сессию',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_gkpt_sessions_status (status),
    INDEX idx_gkpt_sessions_created (created_by_telegram_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Сгенерированные Q&A-пары в рамках сессии
CREATE TABLE IF NOT EXISTS gk_prompt_tester_generations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id INT NOT NULL COMMENT 'FK → gk_prompt_tester_sessions.id',
    prompt_id INT NOT NULL COMMENT 'FK → gk_prompt_tester_prompts.id',
    question_text TEXT NOT NULL COMMENT 'Извлечённый вопрос',
    answer_text TEXT NOT NULL COMMENT 'Извлечённый ответ',
    confidence FLOAT DEFAULT NULL COMMENT 'Уверенность модели (0.0–1.0)',
    extraction_type VARCHAR(32) DEFAULT NULL COMMENT 'Фактический тип извлечения',
    raw_llm_response TEXT DEFAULT NULL COMMENT 'Полный ответ LLM (для отладки)',
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_gkpt_gen_session (session_id),
    INDEX idx_gkpt_gen_prompt (prompt_id),
    INDEX idx_gkpt_gen_session_prompt (session_id, prompt_id),
    CONSTRAINT fk_gkpt_gen_session FOREIGN KEY (session_id)
        REFERENCES gk_prompt_tester_sessions(id) ON DELETE CASCADE,
    CONSTRAINT fk_gkpt_gen_prompt FOREIGN KEY (prompt_id)
        REFERENCES gk_prompt_tester_prompts(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Слепые сравнения (A/B голосование)
CREATE TABLE IF NOT EXISTS gk_prompt_tester_comparisons (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id INT NOT NULL COMMENT 'FK → gk_prompt_tester_sessions.id',
    generation_a_id INT NOT NULL COMMENT 'FK → gk_prompt_tester_generations.id (вариант A)',
    generation_b_id INT NOT NULL COMMENT 'FK → gk_prompt_tester_generations.id (вариант B)',
    voter_telegram_id BIGINT DEFAULT NULL COMMENT 'Telegram ID голосующего (NULL для LLM)',
    voter_type ENUM('human', 'llm') NOT NULL DEFAULT 'human' COMMENT 'Тип голосующего',
    winner ENUM('a', 'b', 'tie', 'skip') DEFAULT NULL COMMENT 'Результат: a, b, tie, skip',
    voted_at TIMESTAMP NULL DEFAULT NULL COMMENT 'Время голосования',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_gkpt_cmp_session (session_id),
    INDEX idx_gkpt_cmp_voter (voter_telegram_id),
    INDEX idx_gkpt_cmp_unvoted (session_id, winner),
    CONSTRAINT fk_gkpt_cmp_session FOREIGN KEY (session_id)
        REFERENCES gk_prompt_tester_sessions(id) ON DELETE CASCADE,
    CONSTRAINT fk_gkpt_cmp_gen_a FOREIGN KEY (generation_a_id)
        REFERENCES gk_prompt_tester_generations(id) ON DELETE CASCADE,
    CONSTRAINT fk_gkpt_cmp_gen_b FOREIGN KEY (generation_b_id)
        REFERENCES gk_prompt_tester_generations(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
