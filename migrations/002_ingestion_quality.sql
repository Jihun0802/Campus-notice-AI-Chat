ALTER TABLE notice_attachments
    ADD COLUMN download_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (download_status IN ('pending', 'downloaded', 'skipped', 'failed'));

ALTER TABLE notice_attachments
    ADD COLUMN parse_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (parse_status IN ('pending', 'parsed', 'unsupported', 'empty', 'failed'));

ALTER TABLE notice_attachments
    ADD COLUMN error_message TEXT;

ALTER TABLE notice_attachments
    ADD COLUMN updated_at TEXT;

CREATE INDEX IF NOT EXISTS idx_notice_attachments_download_status
    ON notice_attachments(download_status);

CREATE INDEX IF NOT EXISTS idx_notice_attachments_parse_status
    ON notice_attachments(parse_status);

CREATE TABLE IF NOT EXISTS crawl_runs (
    id TEXT PRIMARY KEY,
    source_key TEXT NOT NULL,
    source_name TEXT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('success', 'partial', 'failed')),
    imported_count INTEGER NOT NULL DEFAULT 0,
    attachment_count INTEGER NOT NULL DEFAULT 0,
    parsed_attachment_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_crawl_runs_source_key
    ON crawl_runs(source_key);

CREATE INDEX IF NOT EXISTS idx_crawl_runs_finished_at
    ON crawl_runs(finished_at);
