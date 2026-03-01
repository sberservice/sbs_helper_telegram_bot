-- ============================================================================
-- ai_rag_certification_signals_setup.sql — сигналы ранжирования RAG-документов
-- ============================================================================
-- Запустить: mysql -u <user> -p <database> < sql/ai_rag_certification_signals_setup.sql
-- ============================================================================

CREATE TABLE IF NOT EXISTS rag_document_signals (
    document_id BIGINT NOT NULL,
    domain_key VARCHAR(64) NOT NULL DEFAULT '',
    question_id BIGINT NULL,
    category_keys_json TEXT NULL,
    category_labels_json TEXT NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    is_outdated TINYINT(1) NOT NULL DEFAULT 0,
    relevance_date DATE NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (document_id),
    INDEX idx_rag_document_signals_domain (domain_key),
    INDEX idx_rag_document_signals_outdated (is_outdated),
    INDEX idx_rag_document_signals_question_id (question_id),
    CONSTRAINT fk_rag_document_signals_document
        FOREIGN KEY (document_id) REFERENCES rag_documents(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Дополнительные сигналы ранжирования RAG-документов (категории/актуальность)';
