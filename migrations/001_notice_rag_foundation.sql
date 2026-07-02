CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    department TEXT,
    grade TEXT,
    role TEXT NOT NULL DEFAULT 'student'
        CHECK (role IN ('student', 'admin', 'reviewer')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS notice_sources (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    source_type TEXT NOT NULL
        CHECK (
            source_type IN (
                'school_notice',
                'department_notice',
                'scholarship_notice',
                'academic_calendar',
                'email_notice',
                'lms_notice',
                'manual'
            )
        ),
    base_url TEXT,
    department TEXT,
    is_active INTEGER NOT NULL DEFAULT 1
        CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS notices (
    id TEXT PRIMARY KEY,
    source_id TEXT REFERENCES notice_sources(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    body_text TEXT NOT NULL,
    original_url TEXT UNIQUE,
    publisher TEXT,
    category TEXT,
    department TEXT,
    grade TEXT,
    course_id TEXT,
    visibility TEXT NOT NULL DEFAULT 'public'
        CHECK (visibility IN ('public', 'department', 'grade', 'course', 'private')),
    published_at TEXT,
    deadline_at TEXT,
    valid_until TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_notices_source_id ON notices(source_id);
CREATE INDEX IF NOT EXISTS idx_notices_department ON notices(department);
CREATE INDEX IF NOT EXISTS idx_notices_visibility ON notices(visibility);
CREATE INDEX IF NOT EXISTS idx_notices_published_at ON notices(published_at);
CREATE INDEX IF NOT EXISTS idx_notices_deadline_at ON notices(deadline_at);

CREATE TABLE IF NOT EXISTS notice_attachments (
    id TEXT PRIMARY KEY,
    notice_id TEXT NOT NULL REFERENCES notices(id) ON DELETE CASCADE,
    file_name TEXT NOT NULL,
    file_url TEXT,
    file_type TEXT,
    extracted_text TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_notice_attachments_notice_id
    ON notice_attachments(notice_id);

CREATE TABLE IF NOT EXISTS notice_chunks (
    id TEXT PRIMARY KEY,
    notice_id TEXT NOT NULL REFERENCES notices(id) ON DELETE CASCADE,
    attachment_id TEXT REFERENCES notice_attachments(id) ON DELETE CASCADE,
    chunk_text TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    metadata TEXT NOT NULL,
    embedding TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (notice_id, attachment_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_notice_chunks_notice_id ON notice_chunks(notice_id);
CREATE INDEX IF NOT EXISTS idx_notice_chunks_attachment_id ON notice_chunks(attachment_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_notice_chunks_unique_body
    ON notice_chunks(notice_id, chunk_index)
    WHERE attachment_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_notice_chunks_unique_attachment
    ON notice_chunks(notice_id, attachment_id, chunk_index)
    WHERE attachment_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS mail_notice_candidates (
    id TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    sender TEXT NOT NULL,
    body_text TEXT,
    attachment_text TEXT,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected')),
    reviewer_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    approved_notice_id TEXT REFERENCES notices(id) ON DELETE SET NULL,
    received_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_mail_notice_candidates_status
    ON mail_notice_candidates(status);
