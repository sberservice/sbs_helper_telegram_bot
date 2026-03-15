-- =============================================================================
-- GK Final Answer Prompt Tester: A/B тестирование финального ответа пользователю
-- =============================================================================

CREATE TABLE IF NOT EXISTS gk_final_prompt_tester_prompts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    label VARCHAR(255) NOT NULL COMMENT 'Название промпта',
    prompt_template TEXT NOT NULL COMMENT 'Шаблон финального промпта (форматируется с qa_context/relevance_rule/acronyms_section)',
    model_name VARCHAR(128) DEFAULT NULL COMMENT 'Название модели LLM (NULL = по умолчанию)',
    temperature FLOAT DEFAULT 0.3 COMMENT 'Температура генерации',
    created_by_telegram_id BIGINT DEFAULT NULL COMMENT 'Кто создал промпт',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    is_active BOOLEAN NOT NULL DEFAULT TRUE COMMENT 'Активен ли промпт',
    INDEX idx_gkfpt_prompts_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS gk_final_prompt_tester_sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL COMMENT 'Название сессии',
    status ENUM('draft', 'generating', 'judging', 'completed', 'abandoned') NOT NULL DEFAULT 'generating'
        COMMENT 'Статус: draft → generating → judging → completed/abandoned',
    prompt_ids JSON NOT NULL COMMENT 'Массив ID промптов для сравнения',
    prompts_config_snapshot JSON DEFAULT NULL COMMENT 'Снимок конфигурации промптов на момент создания',
    judge_mode ENUM('human', 'llm', 'both') NOT NULL DEFAULT 'human'
        COMMENT 'Режим оценки: human (ручная), llm (автоматическая), both',
    source_group_id BIGINT DEFAULT NULL COMMENT 'ID группы для retrieval-фильтра (опционально)',
    question_count INT NOT NULL DEFAULT 0 COMMENT 'Количество вопросов в сессии',
    questions_snapshot JSON DEFAULT NULL COMMENT 'Снимок вопросов, введённых пользователем',
    created_by_telegram_id BIGINT DEFAULT NULL COMMENT 'Кто создал сессию',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_gkfpt_sessions_status (status),
    INDEX idx_gkfpt_sessions_created (created_by_telegram_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS gk_final_prompt_tester_generations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id INT NOT NULL COMMENT 'FK → gk_final_prompt_tester_sessions.id',
    prompt_id INT NOT NULL COMMENT 'FK → gk_final_prompt_tester_prompts.id',
    question_index INT NOT NULL COMMENT 'Индекс вопроса в сессии (0-based)',
    user_question TEXT NOT NULL COMMENT 'Текст пользовательского вопроса',
    retrieved_pair_ids JSON DEFAULT NULL COMMENT 'ID пар, полученных retrieval-этапом',
    answer_text TEXT DEFAULT NULL COMMENT 'Сгенерированный финальный ответ',
    is_relevant BOOLEAN NOT NULL DEFAULT FALSE COMMENT 'is_relevant из JSON LLM',
    confidence FLOAT DEFAULT NULL COMMENT 'Confidence финального ответа (0.0–1.0)',
    confidence_reason TEXT DEFAULT NULL COMMENT 'Краткая причина confidence',
    used_pair_ids JSON DEFAULT NULL COMMENT 'Индексы/ID пар, использованных LLM',
    model_used VARCHAR(128) DEFAULT NULL COMMENT 'Модель, использованная для генерации',
    temperature_used FLOAT DEFAULT NULL COMMENT 'Температура, использованная для генерации',
    llm_request_payload LONGTEXT DEFAULT NULL COMMENT 'JSON payload запроса в LLM для отладки',
    raw_llm_response LONGTEXT DEFAULT NULL COMMENT 'Сырое поле (зарезервировано; пока не заполняется)',
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_gkfpt_gen_session (session_id),
    INDEX idx_gkfpt_gen_prompt (prompt_id),
    INDEX idx_gkfpt_gen_session_question (session_id, question_index),
    INDEX idx_gkfpt_gen_session_prompt (session_id, prompt_id),
    CONSTRAINT fk_gkfpt_gen_session FOREIGN KEY (session_id)
        REFERENCES gk_final_prompt_tester_sessions(id) ON DELETE CASCADE,
    CONSTRAINT fk_gkfpt_gen_prompt FOREIGN KEY (prompt_id)
        REFERENCES gk_final_prompt_tester_prompts(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS gk_final_prompt_tester_comparisons (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id INT NOT NULL COMMENT 'FK → gk_final_prompt_tester_sessions.id',
    question_index INT NOT NULL COMMENT 'Индекс вопроса, для которого сравниваются ответы',
    generation_a_id INT NOT NULL COMMENT 'FK → gk_final_prompt_tester_generations.id (вариант A)',
    generation_b_id INT NOT NULL COMMENT 'FK → gk_final_prompt_tester_generations.id (вариант B)',
    voter_telegram_id BIGINT DEFAULT NULL COMMENT 'Telegram ID голосующего (NULL для LLM)',
    voter_type ENUM('human', 'llm') NOT NULL DEFAULT 'human' COMMENT 'Тип голосующего',
    winner ENUM('a', 'b', 'tie', 'skip') DEFAULT NULL COMMENT 'Результат: a, b, tie, skip',
    voted_at TIMESTAMP NULL DEFAULT NULL COMMENT 'Время голосования',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_gkfpt_cmp_session (session_id),
    INDEX idx_gkfpt_cmp_question (session_id, question_index),
    INDEX idx_gkfpt_cmp_voter (voter_telegram_id),
    INDEX idx_gkfpt_cmp_unvoted (session_id, winner),
    CONSTRAINT fk_gkfpt_cmp_session FOREIGN KEY (session_id)
        REFERENCES gk_final_prompt_tester_sessions(id) ON DELETE CASCADE,
    CONSTRAINT fk_gkfpt_cmp_gen_a FOREIGN KEY (generation_a_id)
        REFERENCES gk_final_prompt_tester_generations(id) ON DELETE CASCADE,
    CONSTRAINT fk_gkfpt_cmp_gen_b FOREIGN KEY (generation_b_id)
        REFERENCES gk_final_prompt_tester_generations(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
