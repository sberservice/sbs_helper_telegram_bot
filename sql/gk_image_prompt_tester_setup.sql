-- ======================================================================
-- GK Image Prompt Tester: отдельный blind A/B тестер промптов описаний
-- ======================================================================

CREATE TABLE IF NOT EXISTS gk_image_prompt_tester_prompts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    label VARCHAR(255) NOT NULL COMMENT 'Название промпта',
    prompt_text TEXT NOT NULL COMMENT 'Промпт описания изображения',
    model_name VARCHAR(128) DEFAULT NULL COMMENT 'Модель GigaChat (NULL = по умолчанию)',
    temperature FLOAT DEFAULT 0.3 COMMENT 'Температура (метаданные пресета)',
    created_by_telegram_id BIGINT DEFAULT NULL COMMENT 'Кто создал промпт',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    is_active BOOLEAN NOT NULL DEFAULT TRUE COMMENT 'Активен ли промпт',
    INDEX idx_gkipt_prompts_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS gk_image_prompt_tester_sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL COMMENT 'Название сессии',
    status ENUM('generating', 'judging', 'completed', 'abandoned') NOT NULL DEFAULT 'generating'
        COMMENT 'Статус сессии',
    prompt_ids JSON NOT NULL COMMENT 'ID промптов в сессии',
    prompts_config_snapshot JSON DEFAULT NULL COMMENT 'Снимок конфигурации промптов',
    source_group_id BIGINT DEFAULT NULL COMMENT 'Ограничение по группе',
    source_date_from VARCHAR(10) DEFAULT NULL COMMENT 'Дата начала (YYYY-MM-DD)',
    source_date_to VARCHAR(10) DEFAULT NULL COMMENT 'Дата конца (YYYY-MM-DD)',
    image_count INT DEFAULT 0 COMMENT 'Количество изображений в сессии',
    source_image_ids_snapshot JSON DEFAULT NULL COMMENT 'Снимок ID изображений gk_image_queue',
    created_by_telegram_id BIGINT DEFAULT NULL COMMENT 'Кто создал сессию',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_gkipt_sessions_status (status),
    INDEX idx_gkipt_sessions_created (created_by_telegram_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS gk_image_prompt_tester_generations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id INT NOT NULL COMMENT 'FK → gk_image_prompt_tester_sessions.id',
    prompt_id INT NOT NULL COMMENT 'FK → gk_image_prompt_tester_prompts.id',
    image_queue_id BIGINT NOT NULL COMMENT 'FK → gk_image_queue.id',
    image_path TEXT NOT NULL COMMENT 'Путь изображения на момент генерации',
    generated_text TEXT NOT NULL COMMENT 'Сгенерированное описание',
    model_used VARCHAR(128) DEFAULT NULL COMMENT 'Фактически использованная модель',
    raw_llm_response TEXT DEFAULT NULL COMMENT 'Сырой ответ модели (для отладки)',
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_gkipt_gen_session (session_id),
    INDEX idx_gkipt_gen_prompt (prompt_id),
    INDEX idx_gkipt_gen_image (image_queue_id),
    INDEX idx_gkipt_gen_session_image (session_id, image_queue_id),
    CONSTRAINT fk_gkipt_gen_session FOREIGN KEY (session_id)
        REFERENCES gk_image_prompt_tester_sessions(id) ON DELETE CASCADE,
    CONSTRAINT fk_gkipt_gen_prompt FOREIGN KEY (prompt_id)
        REFERENCES gk_image_prompt_tester_prompts(id) ON DELETE RESTRICT,
    CONSTRAINT fk_gkipt_gen_image FOREIGN KEY (image_queue_id)
        REFERENCES gk_image_queue(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS gk_image_prompt_tester_comparisons (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id INT NOT NULL COMMENT 'FK → gk_image_prompt_tester_sessions.id',
    image_queue_id BIGINT NOT NULL COMMENT 'FK → gk_image_queue.id',
    generation_a_id INT NOT NULL COMMENT 'FK → gk_image_prompt_tester_generations.id (вариант A)',
    generation_b_id INT NOT NULL COMMENT 'FK → gk_image_prompt_tester_generations.id (вариант B)',
    voter_telegram_id BIGINT DEFAULT NULL COMMENT 'ID голосующего',
    voter_type ENUM('human', 'llm') NOT NULL DEFAULT 'human' COMMENT 'Тип голосующего',
    winner ENUM('a', 'b', 'tie', 'skip') DEFAULT NULL COMMENT 'Результат сравнения',
    voted_at TIMESTAMP NULL DEFAULT NULL COMMENT 'Время голосования',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_gkipt_cmp_session (session_id),
    INDEX idx_gkipt_cmp_image (image_queue_id),
    INDEX idx_gkipt_cmp_unvoted (session_id, winner),
    CONSTRAINT fk_gkipt_cmp_session FOREIGN KEY (session_id)
        REFERENCES gk_image_prompt_tester_sessions(id) ON DELETE CASCADE,
    CONSTRAINT fk_gkipt_cmp_image FOREIGN KEY (image_queue_id)
        REFERENCES gk_image_queue(id) ON DELETE CASCADE,
    CONSTRAINT fk_gkipt_cmp_gen_a FOREIGN KEY (generation_a_id)
        REFERENCES gk_image_prompt_tester_generations(id) ON DELETE CASCADE,
    CONSTRAINT fk_gkipt_cmp_gen_b FOREIGN KEY (generation_b_id)
        REFERENCES gk_image_prompt_tester_generations(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
