-- ============================================================
-- Group Knowledge — таблицы для майнинга знаний из Telegram-групп
-- ============================================================
-- Запуск: mysql -u root -p byl2 < sql/group_knowledge_setup.sql

-- -----------------------------------------------------------
-- 1. Сообщения из групп
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS `gk_messages` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `telegram_message_id` bigint(20) NOT NULL COMMENT 'ID сообщения в Telegram',
  `group_id` bigint(20) NOT NULL COMMENT 'ID группы/супергруппы',
  `group_title` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT 'Название группы',
  `sender_id` bigint(20) NOT NULL DEFAULT 0 COMMENT 'Telegram ID отправителя',
  `sender_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT 'Имя отправителя',
  `message_text` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT 'Текст сообщения',
  `caption` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT 'Подпись к медиа',
  `has_image` tinyint(1) NOT NULL DEFAULT 0 COMMENT 'Сообщение содержит изображение',
  `image_path` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Путь к сохранённому изображению',
  `image_description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT 'Описание изображения от GigaChat',
  `reply_to_message_id` bigint(20) DEFAULT NULL COMMENT 'ID сообщения, на которое ответ (Telegram reply-to)',
  `message_date` bigint(20) NOT NULL COMMENT 'Дата сообщения (UNIX timestamp)',
  `collected_at` bigint(20) NOT NULL COMMENT 'Время сбора (UNIX timestamp)',
  `processed` tinyint(1) NOT NULL DEFAULT 0 COMMENT '0=не обработано, 1=обработано',
  `is_question` tinyint(1) DEFAULT NULL COMMENT 'Результат классификации сообщения как вопроса',
  `question_confidence` float DEFAULT NULL COMMENT 'Уверенность классификатора вопроса',
  `question_reason` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Краткая причина классификации вопроса',
  `question_model_used` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Модель классификации вопроса',
  `question_detected_at` bigint(20) DEFAULT NULL COMMENT 'Время классификации вопроса (UNIX timestamp)',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_group_message` (`group_id`, `telegram_message_id`),
  KEY `idx_group_date` (`group_id`, `message_date`),
  KEY `idx_processed` (`processed`),
  KEY `idx_question_detection` (`group_id`, `is_question`, `message_date`),
  KEY `idx_reply_to` (`group_id`, `reply_to_message_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------
-- 2. Извлечённые Q&A-пары
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS `gk_qa_pairs` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `question_text` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Текст вопроса',
  `answer_text` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Текст ответа',
  `question_message_id` bigint(20) DEFAULT NULL COMMENT 'FK → gk_messages.id (вопрос)',
  `answer_message_id` bigint(20) DEFAULT NULL COMMENT 'FK → gk_messages.id (ответ)',
  `group_id` bigint(20) NOT NULL COMMENT 'ID группы',
  `extraction_type` enum('thread_reply','llm_inferred') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'thread_reply' COMMENT 'Метод извлечения',
  `confidence` float DEFAULT NULL COMMENT 'Уверенность LLM (0.0–1.0)',
  `confidence_reason` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Причина выставленного confidence',
  `fullness` float DEFAULT NULL COMMENT 'Полнота/подробность ответа (0.0–1.0)',
  `llm_model_used` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT 'Модель LLM',
  `llm_request_payload` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT 'JSON запроса, отправленного в LLM для отладки',
  `created_at` bigint(20) NOT NULL COMMENT 'Время создания (UNIX timestamp)',
  `approved` tinyint(1) NOT NULL DEFAULT 1 COMMENT '1=одобрено, 0=отклонено',
  `vector_indexed` tinyint(1) NOT NULL DEFAULT 0 COMMENT '1=проиндексировано в Qdrant',
  PRIMARY KEY (`id`),
  KEY `idx_group` (`group_id`),
  KEY `idx_extraction_type` (`extraction_type`),
  KEY `idx_vector_indexed` (`vector_indexed`, `approved`),
  KEY `idx_question_msg` (`question_message_id`),
  KEY `idx_answer_msg` (`answer_message_id`),
  FULLTEXT KEY `ft_qa_text` (`question_text`, `answer_text`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------
-- 3. Очередь обработки изображений
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS `gk_image_queue` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `message_id` bigint(20) NOT NULL COMMENT 'FK → gk_messages.id',
  `image_path` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Путь к изображению',
  `status` int(11) NOT NULL DEFAULT 0 COMMENT '0=pending, 1=processing, 2=done, 3=error',
  `error_message` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT 'Текст ошибки',
  `created_at` bigint(20) NOT NULL COMMENT 'Время создания (UNIX timestamp)',
  `updated_at` bigint(20) NOT NULL COMMENT 'Время обновления (UNIX timestamp)',
  PRIMARY KEY (`id`),
  KEY `idx_status` (`status`),
  KEY `idx_message` (`message_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------
-- 4. Лог автоответчика
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS `gk_responder_log` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `group_id` bigint(20) NOT NULL COMMENT 'ID группы',
  `question_message_id` bigint(20) NOT NULL COMMENT 'Telegram message ID вопроса',
  `question_message_date` bigint(20) DEFAULT NULL COMMENT 'Время сообщения-вопроса (UNIX timestamp)',
  `question_text` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT 'Текст вопроса',
  `answer_text` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT 'Сгенерированный ответ',
  `llm_request_payload` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT 'Полный JSON запроса, отправленного в LLM',
  `qa_pair_id` bigint(20) DEFAULT NULL COMMENT 'FK → gk_qa_pairs.id',
  `confidence` float NOT NULL DEFAULT 0 COMMENT 'Уверенность в ответе',
  `dry_run` tinyint(1) NOT NULL DEFAULT 1 COMMENT '1=dry-run, 0=ответ отправлен',
  `responded_at` bigint(20) NOT NULL COMMENT 'Время ответа (UNIX timestamp)',
  PRIMARY KEY (`id`),
  KEY `idx_group` (`group_id`),
  KEY `idx_responded_at` (`responded_at`),
  KEY `idx_dry_run` (`dry_run`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
