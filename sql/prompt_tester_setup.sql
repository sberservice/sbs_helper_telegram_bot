-- Таблицы для инструмента слепого тестирования промптов (Prompt A/B Tester)
-- Позволяет сравнивать качество summary, сгенерированных разными парами
-- system_prompt + user_message через попарное слепое голосование.

CREATE TABLE IF NOT EXISTS prompt_test_prompts (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    label           VARCHAR(255)    NOT NULL COMMENT 'Человекочитаемое название пары промптов',
    system_prompt_template TEXT     NOT NULL COMMENT 'Шаблон system prompt с плейсхолдерами {document_name}, {document_excerpt}, {max_summary_chars}',
    user_message    TEXT            NOT NULL COMMENT 'Содержимое user message для LLM',
    model_name      VARCHAR(128)    NULL     COMMENT 'Override модели (NULL = модель из .env)',
    temperature     FLOAT           NULL     COMMENT 'Override температуры (NULL = дефолт из settings)',
    is_active       BOOLEAN         NOT NULL DEFAULT TRUE COMMENT 'Активна ли пара (FALSE = архивирована)',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Пары промптов (system_prompt + user_message) для A/B тестирования summary';


CREATE TABLE IF NOT EXISTS prompt_test_sessions (
    id                      INT AUTO_INCREMENT PRIMARY KEY,
    name                    VARCHAR(255)    NOT NULL COMMENT 'Название сессии тестирования',
    prompt_ids_snapshot     JSON            NOT NULL COMMENT 'Массив ID промптов на момент создания',
    prompts_config_snapshot JSON            NOT NULL COMMENT 'Полный snapshot конфигурации промптов',
    document_ids            JSON            NOT NULL COMMENT 'Массив ID выбранных документов',
    status                  ENUM('generating', 'judging', 'in_progress', 'completed', 'abandoned')
                            NOT NULL DEFAULT 'generating'
                            COMMENT 'Статус сессии: generating→judging→in_progress→completed',

    total_comparisons       INT             NOT NULL DEFAULT 0 COMMENT 'Общее число попарных сравнений',
    completed_comparisons   INT             NOT NULL DEFAULT 0 COMMENT 'Завершённые сравнения',
    judge_mode              ENUM('human', 'llm', 'both')
                            NOT NULL DEFAULT 'human'
                            COMMENT 'Режим оценки: ручная, LLM или обе',
    created_at              DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at              DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Сессии тестирования промптов';


CREATE TABLE IF NOT EXISTS prompt_test_generations (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    session_id          INT             NOT NULL,
    document_id         INT             NOT NULL COMMENT 'FK на rag_documents.id',
    prompt_id           INT             NOT NULL COMMENT 'FK на prompt_test_prompts.id',
    prompt_label        VARCHAR(255)    NOT NULL COMMENT 'Label промпта из snapshot',
    system_prompt_used  TEXT            NOT NULL COMMENT 'Фактический system prompt после подстановки переменных',
    user_message_used   TEXT            NOT NULL COMMENT 'Фактический user message',
    model_name          VARCHAR(128)    NULL     COMMENT 'Использованная модель',
    temperature_used    FLOAT           NULL     COMMENT 'Использованная температура',
    summary_text        TEXT            NULL     COMMENT 'Сгенерированный summary (NULL если ещё генерируется)',
    generation_time_ms  INT             NULL     COMMENT 'Время генерации в миллисекундах',
    error_message       TEXT            NULL     COMMENT 'Сообщение об ошибке, если генерация не удалась',
    created_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_ptg_session  (session_id),
    INDEX idx_ptg_document (document_id),
    INDEX idx_ptg_prompt   (prompt_id),

    CONSTRAINT fk_ptg_session
        FOREIGN KEY (session_id) REFERENCES prompt_test_sessions(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Сгенерированные summary для тестирования';


CREATE TABLE IF NOT EXISTS prompt_test_votes (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    session_id          INT             NOT NULL,
    document_id         INT             NOT NULL COMMENT 'FK на rag_documents.id',
    generation_a_id     INT             NOT NULL COMMENT 'FK на prompt_test_generations.id',
    generation_b_id     INT             NOT NULL COMMENT 'FK на prompt_test_generations.id',
    winner              ENUM('a', 'b', 'tie', 'skip')
                        NOT NULL COMMENT 'Результат: a/b победило, tie или skip',
    judge_type          ENUM('human', 'llm')
                        NOT NULL DEFAULT 'human'
                        COMMENT 'Тип оценщика',
    llm_judge_reasoning TEXT            NULL     COMMENT 'Объяснение LLM-судьи (если judge_type=llm)',
    created_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_ptv_session    (session_id),
    INDEX idx_ptv_document   (document_id),
    INDEX idx_ptv_gen_a      (generation_a_id),
    INDEX idx_ptv_gen_b      (generation_b_id),

    CONSTRAINT fk_ptv_session
        FOREIGN KEY (session_id) REFERENCES prompt_test_sessions(id) ON DELETE CASCADE,
    CONSTRAINT fk_ptv_gen_a
        FOREIGN KEY (generation_a_id) REFERENCES prompt_test_generations(id) ON DELETE CASCADE,
    CONSTRAINT fk_ptv_gen_b
        FOREIGN KEY (generation_b_id) REFERENCES prompt_test_generations(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Голоса (человеческие и LLM-judge) для попарных сравнений summary';
