-- ============================================================================
-- ai_rag_setup.sql — таблицы базы знаний (RAG)
-- ============================================================================
-- Запустить: mysql -u <user> -p <database> < scripts/ai_rag_setup.sql
-- ============================================================================

CREATE TABLE IF NOT EXISTS rag_documents (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    source_type VARCHAR(32) NOT NULL DEFAULT 'telegram',
    source_url TEXT NULL,
    uploaded_by BIGINT NOT NULL,
    status ENUM('active', 'archived', 'deleted') NOT NULL DEFAULT 'active',
    content_hash CHAR(64) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uq_rag_documents_hash (content_hash),
    INDEX idx_rag_documents_status (status),
    INDEX idx_rag_documents_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Документы базы знаний для RAG';

CREATE TABLE IF NOT EXISTS rag_chunks (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    document_id BIGINT NOT NULL,
    chunk_index INT NOT NULL,
    chunk_text MEDIUMTEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uq_rag_chunks_doc_idx (document_id, chunk_index),
    INDEX idx_rag_chunks_document_id (document_id),
    FULLTEXT KEY ft_rag_chunk_text (chunk_text),
    CONSTRAINT fk_rag_chunks_document
        FOREIGN KEY (document_id) REFERENCES rag_documents(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Чанки документов базы знаний для retrieval';

CREATE TABLE IF NOT EXISTS rag_corpus_version (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    reason VARCHAR(255) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_rag_corpus_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Версии корпуса RAG для инвалидации кэша';

CREATE TABLE IF NOT EXISTS rag_query_log (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    query_text TEXT NOT NULL,
    cache_hit TINYINT(1) NOT NULL DEFAULT 0,
    chunks_count INT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_rag_query_user (user_id),
    INDEX idx_rag_query_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Логи запросов к RAG';
