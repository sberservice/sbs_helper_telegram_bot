-- ============================================================
-- Group Knowledge — дедупликация Q&A по question_message_id
-- ============================================================
-- Назначение:
-- 1) удалить уже существующие дубли question_message_id (оставить самую новую запись),
-- 2) добавить UNIQUE-ограничение, чтобы новые дубли не появлялись.
--
-- Запуск: mysql -u root -p byl2 < sql/group_knowledge_qa_question_unique.sql

-- Удалить старые дубли по question_message_id, оставляя запись с максимальным id
DELETE t_old
FROM gk_qa_pairs t_old
JOIN gk_qa_pairs t_newer
  ON t_old.question_message_id = t_newer.question_message_id
 AND t_old.question_message_id IS NOT NULL
 AND t_old.id < t_newer.id;

-- Добавить уникальный индекс (NULL допускается многократно)
ALTER TABLE gk_qa_pairs
  ADD UNIQUE KEY uk_question_message_id (question_message_id);
