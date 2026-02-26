-- ============================================================================
-- ai_rag_summary_vector_setup.sql — метаданные векторной индексации summary-документов RAG
-- ============================================================================
-- Запустить: mysql -u <user> -p <database> < sql/ai_rag_summary_vector_setup.sql
-- ============================================================================

CREATE TABLE IF NOT EXISTS rag_summary_embeddings (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    document_id BIGINT NOT NULL,
    embedding_model VARCHAR(128) NOT NULL,
    embedding_dim INT NOT NULL,
    embedding_hash CHAR(64) NOT NULL,
    embedding_status ENUM('ready', 'failed', 'stale') NOT NULL DEFAULT 'ready',
    error_message VARCHAR(255) NULL,
    embedded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uq_rag_summary_embeddings_doc_model (document_id, embedding_model),
    INDEX idx_rag_summary_embeddings_document_id (document_id),
    INDEX idx_rag_summary_embeddings_status (embedding_status),
    INDEX idx_rag_summary_embeddings_updated_at (updated_at),
    CONSTRAINT fk_rag_summary_embeddings_document
        FOREIGN KEY (document_id) REFERENCES rag_documents(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Метаданные состояния векторной индексации summary документов RAG';
