CREATE TABLE IF NOT EXISTS notice_media (
    id TEXT PRIMARY KEY,
    notice_id TEXT NOT NULL REFERENCES notices(id) ON DELETE CASCADE,
    media_type TEXT NOT NULL DEFAULT 'image'
        CHECK (media_type IN ('image')),
    file_name TEXT NOT NULL,
    original_url TEXT,
    file_type TEXT,
    alt_text TEXT,
    caption TEXT,
    local_path TEXT,
    thumbnail_path TEXT,
    ocr_text TEXT,
    summary_text TEXT,
    download_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (download_status IN ('pending', 'downloaded', 'skipped', 'failed')),
    parse_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (parse_status IN ('pending', 'parsed', 'unsupported', 'empty', 'failed')),
    summary_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (summary_status IN ('pending', 'parsed', 'unsupported', 'empty', 'failed')),
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_notice_media_notice_id
    ON notice_media(notice_id);

CREATE INDEX IF NOT EXISTS idx_notice_media_parse_status
    ON notice_media(parse_status);

CREATE INDEX IF NOT EXISTS idx_notice_media_file_type
    ON notice_media(file_type);

ALTER TABLE notice_chunks
    ADD COLUMN chunk_type TEXT NOT NULL DEFAULT 'body'
        CHECK (chunk_type IN ('body', 'pdf_text', 'image_ocr', 'image_summary'));

ALTER TABLE notice_chunks
    ADD COLUMN media_id TEXT;

CREATE INDEX IF NOT EXISTS idx_notice_chunks_chunk_type
    ON notice_chunks(chunk_type);

CREATE INDEX IF NOT EXISTS idx_notice_chunks_media_id
    ON notice_chunks(media_id);

DROP INDEX IF EXISTS idx_notice_chunks_unique_body;

CREATE UNIQUE INDEX IF NOT EXISTS idx_notice_chunks_unique_body
    ON notice_chunks(notice_id, chunk_index)
    WHERE attachment_id IS NULL AND media_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_notice_chunks_unique_media
    ON notice_chunks(notice_id, media_id, chunk_type, chunk_index)
    WHERE media_id IS NOT NULL;
