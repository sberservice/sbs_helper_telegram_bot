-- Добавить поля LLM-классификации вопроса в gk_messages
ALTER TABLE `gk_messages`
  ADD COLUMN `is_question` tinyint(1) DEFAULT NULL COMMENT 'Результат классификации сообщения как вопроса',
  ADD COLUMN `question_confidence` float DEFAULT NULL COMMENT 'Уверенность классификатора вопроса',
  ADD COLUMN `question_reason` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Краткая причина классификации вопроса',
  ADD COLUMN `question_model_used` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Модель классификации вопроса',
  ADD COLUMN `question_detected_at` bigint(20) DEFAULT NULL COMMENT 'Время классификации вопроса (UNIX timestamp)';

CREATE INDEX `idx_gk_messages_is_question` ON `gk_messages` (`group_id`, `is_question`, `message_date`);
