-- ============================================================================
-- rag_document_summaries_fulltext_index.sql — добавление FULLTEXT-индекса summary
-- ============================================================================
-- Запустить: mysql -u <user> -p <database> < scripts/rag_document_summaries_fulltext_index.sql
-- ============================================================================

SET @idx_exists := (
    SELECT COUNT(1)
    FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = 'rag_document_summaries'
      AND index_name = 'ft_rag_doc_summary_text'
);

SET @sql := IF(
    @idx_exists = 0,
    'ALTER TABLE rag_document_summaries ADD FULLTEXT KEY ft_rag_doc_summary_text (summary_text)',
    'SELECT ''FULLTEXT index ft_rag_doc_summary_text already exists'''
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
