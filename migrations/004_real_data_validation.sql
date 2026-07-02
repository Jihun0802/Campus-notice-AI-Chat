CREATE TABLE IF NOT EXISTS ingestion_logs (
    id TEXT PRIMARY KEY,
    source_id TEXT,
    notice_id TEXT REFERENCES notices(id) ON DELETE SET NULL,
    target_type TEXT NOT NULL
        CHECK (target_type IN ('source', 'notice', 'attachment', 'media', 'chunk', 'embedding')),
    target_id TEXT,
    step TEXT NOT NULL
        CHECK (step IN ('crawl', 'parse', 'pdf_extract', 'image_cache', 'ocr', 'reindex', 'embed')),
    status TEXT NOT NULL
        CHECK (status IN ('success', 'warning', 'failed')),
    message TEXT,
    error_message TEXT,
    retryable INTEGER NOT NULL DEFAULT 0
        CHECK (retryable IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_ingestion_logs_source_id
    ON ingestion_logs(source_id);

CREATE INDEX IF NOT EXISTS idx_ingestion_logs_notice_id
    ON ingestion_logs(notice_id);

CREATE INDEX IF NOT EXISTS idx_ingestion_logs_status
    ON ingestion_logs(status);

CREATE INDEX IF NOT EXISTS idx_ingestion_logs_created_at
    ON ingestion_logs(created_at);
