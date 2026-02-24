-- ============================================================================
-- ai_rag_document_summaries_setup.sql — миграция таблицы AI-summary для RAG
-- ============================================================================
-- Запустить: mysql -u <user> -p <database> < scripts/ai_rag_document_summaries_setup.sql
-- ============================================================================

CREATE TABLE IF NOT EXISTS rag_document_summaries (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    document_id BIGINT NOT NULL,
    summary_text TEXT NOT NULL,
    model_name VARCHAR(64) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uq_rag_doc_summary_document (document_id),
    INDEX idx_rag_doc_summary_updated_at (updated_at),
    FULLTEXT KEY ft_rag_doc_summary_text (summary_text),
    CONSTRAINT fk_rag_doc_summary_document
        FOREIGN KEY (document_id) REFERENCES rag_documents(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='AI-summary документов базы знаний для prefilter и prompt enrichment';
