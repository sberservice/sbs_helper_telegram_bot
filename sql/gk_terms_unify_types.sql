-- ---------------------------------------------------------------------------
-- Миграция: объединение term_type (fixed_term / acronym) в единую сущность.
--
-- До миграции:
--   - gk_terms.term_type ENUM('fixed_term', 'acronym')
--   - Один и тот же термин мог существовать как обе записи
--   - UNIQUE KEY (group_id, term, term_type)
--
-- После миграции:
--   - column term_type удалён
--   - UNIQUE KEY (group_id, term)
--   - definition IS NOT NULL → термин участвует в LLM-промпте
--   - definition IS NULL → только BM25-защита
--
-- Стратегия слияния дубликатов:
--   Для каждой пары (group_id, term), где существует и fixed_term, и acronym:
--   - оставляем строку с непустым definition (т.е. acronym-запись)
--   - удаляем строку fixed_term (дубликат без definition)
--   - Если у обеих нет definition — оставляем ту, что имеет id поменьше
-- ---------------------------------------------------------------------------

-- Шаг 1: Слияние дубликатов.
-- Обновить definition у fixed_term из acronym (если fixed_term не имеет definition).
UPDATE gk_terms ft
JOIN gk_terms ac
  ON ft.group_id = ac.group_id
  AND ft.term = ac.term
  AND ft.term_type = 'fixed_term'
  AND ac.term_type = 'acronym'
SET ft.definition = COALESCE(ft.definition, ac.definition),
    ft.confidence = GREATEST(COALESCE(ft.confidence, 0), COALESCE(ac.confidence, 0)),
    ft.updated_at = NOW()
WHERE ac.definition IS NOT NULL
  AND ft.definition IS NULL;

-- Шаг 2: Удалить строки acronym, которые дублируются с fixed_term.
-- (После шага 1 fixed_term уже содержит definition.)
DELETE ac FROM gk_terms ac
JOIN gk_terms ft
  ON ac.group_id = ft.group_id
  AND ac.term = ft.term
  AND ac.term_type = 'acronym'
  AND ft.term_type = 'fixed_term';

-- Шаг 3: Удалить дубликаты с одинаковым term_type (если вдруг).
-- Оставить строку с минимальным id.
DELETE t1 FROM gk_terms t1
JOIN gk_terms t2
  ON t1.group_id = t2.group_id
  AND t1.term = t2.term
  AND t1.id > t2.id;

-- Шаг 4: Удалить старые индексы и constraints.
ALTER TABLE gk_terms
  DROP INDEX uq_group_term_type,
  DROP INDEX idx_term_type;

-- Шаг 5: Удалить колонку term_type.
ALTER TABLE gk_terms
  DROP COLUMN term_type;

-- Шаг 6: Создать новый уникальный ключ.
ALTER TABLE gk_terms
  ADD UNIQUE KEY uq_group_term (group_id, term);

-- Шаг 7: Обновить COMMENT на definition.
ALTER TABLE gk_terms
  MODIFY COLUMN definition TEXT DEFAULT NULL COMMENT 'Расшифровка / определение (NULL = только BM25-защита)';

-- Шаг 8: Добавить индекс по наличию definition для быстрой фильтрации.
ALTER TABLE gk_terms
  ADD KEY idx_has_definition ((definition IS NOT NULL));
