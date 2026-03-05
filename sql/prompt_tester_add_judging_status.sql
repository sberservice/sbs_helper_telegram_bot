-- Добавление статуса 'judging' в enum prompt_test_sessions.status
-- Этот статус используется пока LLM-as-Judge оценивает сгенерированные summary.
ALTER TABLE prompt_test_sessions
    MODIFY COLUMN status ENUM('generating', 'judging', 'in_progress', 'completed', 'abandoned')
    NOT NULL DEFAULT 'generating'
    COMMENT 'Статус сессии: generating→judging→in_progress→completed';
