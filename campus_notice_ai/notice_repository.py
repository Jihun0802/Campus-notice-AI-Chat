from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from hashlib import sha1
from typing import Any
from uuid import uuid4

from campus_notice_ai.chunking import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    build_notice_document,
    chunk_text,
    stable_chunk_id,
)
from campus_notice_ai.media import get_ocr_health
from campus_notice_ai.seed_data import MOBILE_SYSTEMS_SOURCE, SEED_NOTICES


def stable_id(prefix: str, value: str) -> str:
    digest = sha1(value.encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:24]}"


def current_timestamp() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def upsert_notice_source(
    conn: sqlite3.Connection,
    *,
    name: str,
    source_type: str,
    base_url: str | None,
    department: str | None = None,
    is_active: bool = True,
) -> str:
    source_key = base_url or f"{source_type}:{name}:{department or ''}"
    source_id = stable_id("src", source_key)
    conn.execute(
        """
        INSERT INTO notice_sources (
            id, name, source_type, base_url, department, is_active
        )
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            source_type = excluded.source_type,
            base_url = excluded.base_url,
            department = excluded.department,
            is_active = excluded.is_active
        """,
        (
            source_id,
            name,
            source_type,
            base_url,
            department,
            1 if is_active else 0,
        ),
    )
    return source_id


def upsert_notice(
    conn: sqlite3.Connection,
    *,
    source_id: str | None,
    title: str,
    body_text: str,
    original_url: str,
    publisher: str | None = None,
    category: str | None = None,
    department: str | None = None,
    grade: str | None = None,
    course_id: str | None = None,
    visibility: str = "public",
    published_at: str | None = None,
    deadline_at: str | None = None,
    valid_until: str | None = None,
) -> str:
    notice_id = stable_id("notice", original_url or title)
    conn.execute(
        """
        INSERT INTO notices (
            id,
            source_id,
            title,
            body_text,
            original_url,
            publisher,
            category,
            department,
            grade,
            course_id,
            visibility,
            published_at,
            deadline_at,
            valid_until,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(original_url) DO UPDATE SET
            source_id = excluded.source_id,
            title = excluded.title,
            body_text = excluded.body_text,
            publisher = excluded.publisher,
            category = excluded.category,
            department = excluded.department,
            grade = excluded.grade,
            course_id = excluded.course_id,
            visibility = excluded.visibility,
            published_at = excluded.published_at,
            deadline_at = excluded.deadline_at,
            valid_until = excluded.valid_until,
            updated_at = datetime('now')
        """,
        (
            notice_id,
            source_id,
            title,
            body_text,
            original_url,
            publisher,
            category,
            department,
            grade,
            course_id,
            visibility,
            published_at,
            deadline_at,
            valid_until,
        ),
    )
    row = conn.execute(
        "SELECT id FROM notices WHERE original_url = ?",
        (original_url,),
    ).fetchone()
    return row["id"] if row else notice_id


def seed_notices(conn: sqlite3.Connection) -> int:
    source_id = upsert_notice_source(
        conn,
        name=MOBILE_SYSTEMS_SOURCE["name"],
        source_type=MOBILE_SYSTEMS_SOURCE["source_type"],
        base_url=MOBILE_SYSTEMS_SOURCE["base_url"],
        department=MOBILE_SYSTEMS_SOURCE["department"],
    )

    for notice in SEED_NOTICES:
        upsert_notice(
            conn,
            source_id=source_id,
            title=notice["title"],
            body_text=notice["body_text"],
            original_url=notice["original_url"],
            publisher=notice["publisher"],
            category=notice["category"],
            department=notice["department"],
            grade=notice["grade"],
            course_id=notice["course_id"],
            visibility=notice["visibility"],
            published_at=notice["published_at"],
            deadline_at=notice["deadline_at"],
        )

    conn.commit()
    return len(SEED_NOTICES)


def get_notice(conn: sqlite3.Connection, notice_id: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT notices.*, notice_sources.name AS source_name, notice_sources.source_type
        FROM notices
        LEFT JOIN notice_sources ON notice_sources.id = notices.source_id
        WHERE notices.id = ?
        """,
        (notice_id,),
    ).fetchone()


def find_notice(conn: sqlite3.Connection, id_or_url: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT notices.*, notice_sources.name AS source_name, notice_sources.source_type
        FROM notices
        LEFT JOIN notice_sources ON notice_sources.id = notices.source_id
        WHERE notices.id = ? OR notices.original_url = ?
        """,
        (id_or_url, id_or_url),
    ).fetchone()


def list_notice_ids(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT id FROM notices ORDER BY published_at, id").fetchall()
    return [row["id"] for row in rows]


def count_rows(conn: sqlite3.Connection) -> dict[str, int]:
    tables = ["notice_sources", "notices", "notice_attachments", "notice_media", "notice_chunks"]
    return {
        table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in tables
    }


def upsert_notice_attachment(
    conn: sqlite3.Connection,
    *,
    notice_id: str,
    file_name: str,
    file_url: str | None,
    file_type: str | None = None,
    extracted_text: str | None = None,
    download_status: str = "pending",
    parse_status: str = "pending",
    error_message: str | None = None,
) -> str:
    attachment_key = file_url or f"{notice_id}:{file_name}"
    attachment_id = stable_id("att", f"{notice_id}:{attachment_key}")
    updated_at = current_timestamp()
    conn.execute(
        """
        INSERT INTO notice_attachments (
            id,
            notice_id,
            file_name,
            file_url,
            file_type,
            extracted_text,
            download_status,
            parse_status,
            error_message,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            file_name = excluded.file_name,
            file_url = excluded.file_url,
            file_type = excluded.file_type,
            extracted_text = excluded.extracted_text,
            download_status = excluded.download_status,
            parse_status = excluded.parse_status,
            error_message = excluded.error_message,
            updated_at = excluded.updated_at
        """,
        (
            attachment_id,
            notice_id,
            file_name,
            file_url,
            file_type,
            extracted_text,
            download_status,
            parse_status,
            error_message,
            updated_at,
        ),
    )
    return attachment_id


def upsert_notice_media(
    conn: sqlite3.Connection,
    *,
    notice_id: str,
    file_name: str,
    original_url: str | None,
    file_type: str | None = None,
    alt_text: str | None = None,
    caption: str | None = None,
    local_path: str | None = None,
    thumbnail_path: str | None = None,
    ocr_text: str | None = None,
    summary_text: str | None = None,
    download_status: str = "pending",
    parse_status: str = "pending",
    summary_status: str = "pending",
    error_message: str | None = None,
) -> str:
    media_id = make_notice_media_id(notice_id, file_name, original_url)
    updated_at = current_timestamp()
    conn.execute(
        """
        INSERT INTO notice_media (
            id,
            notice_id,
            media_type,
            file_name,
            original_url,
            file_type,
            alt_text,
            caption,
            local_path,
            thumbnail_path,
            ocr_text,
            summary_text,
            download_status,
            parse_status,
            summary_status,
            error_message,
            updated_at
        )
        VALUES (?, ?, 'image', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            file_name = excluded.file_name,
            original_url = excluded.original_url,
            file_type = excluded.file_type,
            alt_text = excluded.alt_text,
            caption = excluded.caption,
            local_path = excluded.local_path,
            thumbnail_path = excluded.thumbnail_path,
            ocr_text = excluded.ocr_text,
            summary_text = excluded.summary_text,
            download_status = excluded.download_status,
            parse_status = excluded.parse_status,
            summary_status = excluded.summary_status,
            error_message = excluded.error_message,
            updated_at = excluded.updated_at
        """,
        (
            media_id,
            notice_id,
            file_name,
            original_url,
            file_type,
            alt_text,
            caption,
            local_path,
            thumbnail_path,
            ocr_text,
            summary_text,
            download_status,
            parse_status,
            summary_status,
            error_message,
            updated_at,
        ),
    )
    return media_id


def make_notice_media_id(notice_id: str, file_name: str, original_url: str | None) -> str:
    media_key = original_url or f"{notice_id}:{file_name}"
    return stable_id("media", f"{notice_id}:{media_key}")


def list_notice_attachments(
    conn: sqlite3.Connection,
    notice_id: str,
    *,
    only_searchable: bool = False,
) -> list[sqlite3.Row]:
    where = ["notice_id = ?"]
    params: list[Any] = [notice_id]
    if only_searchable:
        where.append("extracted_text IS NOT NULL")
        where.append("length(trim(extracted_text)) > 0")
    return conn.execute(
        f"""
        SELECT *
        FROM notice_attachments
        WHERE {' AND '.join(where)}
        ORDER BY file_name, id
        """,
        params,
    ).fetchall()


def list_notice_media(
    conn: sqlite3.Connection,
    notice_id: str,
    *,
    only_searchable: bool = False,
) -> list[sqlite3.Row]:
    where = ["notice_id = ?"]
    params: list[Any] = [notice_id]
    if only_searchable:
        where.append(
            """
            (
                (ocr_text IS NOT NULL AND length(trim(ocr_text)) > 0)
                OR (summary_text IS NOT NULL AND length(trim(summary_text)) > 0)
            )
            """
        )
    return conn.execute(
        f"""
        SELECT *
        FROM notice_media
        WHERE {' AND '.join(where)}
        ORDER BY file_name, id
        """,
        params,
    ).fetchall()


def list_notices(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            notices.*,
            notice_sources.name AS source_name,
            notice_sources.source_type AS source_type,
            COUNT(DISTINCT notice_chunks.id) AS chunk_count,
            COUNT(DISTINCT notice_attachments.id) AS attachment_count,
            COUNT(DISTINCT notice_media.id) AS media_count
        FROM notices
        LEFT JOIN notice_sources ON notice_sources.id = notices.source_id
        LEFT JOIN notice_chunks ON notice_chunks.notice_id = notices.id
        LEFT JOIN notice_attachments ON notice_attachments.notice_id = notices.id
        LEFT JOIN notice_media ON notice_media.notice_id = notices.id
        GROUP BY notices.id
        ORDER BY
            COALESCE(notices.published_at, '') DESC,
            notices.updated_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    notices: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        media_rows = conn.execute(
            """
            SELECT
                id,
                file_name,
                original_url,
                file_type,
                alt_text,
                caption,
                local_path,
                thumbnail_path,
                parse_status
            FROM notice_media
            WHERE notice_id = ?
            ORDER BY file_name, id
            LIMIT 3
            """,
            (row["id"],),
        ).fetchall()
        item["media"] = [dict(media_row) for media_row in media_rows]
        notices.append(item)
    return notices


def record_crawl_run(
    conn: sqlite3.Connection,
    *,
    source_key: str,
    source_name: str,
    status: str,
    imported_count: int = 0,
    attachment_count: int = 0,
    parsed_attachment_count: int = 0,
    error_message: str | None = None,
) -> str:
    run_id = f"crawl_{uuid4().hex[:24]}"
    timestamp = current_timestamp()
    conn.execute(
        """
        INSERT INTO crawl_runs (
            id,
            source_key,
            source_name,
            status,
            imported_count,
            attachment_count,
            parsed_attachment_count,
            error_message,
            started_at,
            finished_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            source_key,
            source_name,
            status,
            imported_count,
            attachment_count,
            parsed_attachment_count,
            error_message,
            timestamp,
            timestamp,
        ),
    )
    return run_id


def text_preview(value: str | None, limit: int = 500) -> str | None:
    if not value:
        return None
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return compact[:limit].rstrip() + "..."


def record_ingestion_log(
    conn: sqlite3.Connection,
    *,
    source_id: str | None = None,
    notice_id: str | None = None,
    target_type: str,
    target_id: str | None = None,
    step: str,
    status: str,
    message: str | None = None,
    error_message: str | None = None,
    retryable: bool = False,
) -> str:
    log_id = f"log_{uuid4().hex[:24]}"
    conn.execute(
        """
        INSERT INTO ingestion_logs (
            id,
            source_id,
            notice_id,
            target_type,
            target_id,
            step,
            status,
            message,
            error_message,
            retryable
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            log_id,
            source_id,
            notice_id,
            target_type,
            target_id,
            step,
            status,
            message,
            error_message,
            1 if retryable else 0,
        ),
    )
    return log_id


def list_ingestion_failure_logs(conn: sqlite3.Connection, limit: int = 20) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            id,
            source_id,
            notice_id,
            target_type,
            target_id,
            step,
            status,
            message,
            error_message,
            retryable,
            created_at
        FROM ingestion_logs
        WHERE status = 'failed'
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_notice_detail(conn: sqlite3.Connection, id_or_url: str) -> dict[str, Any] | None:
    notice = find_notice(conn, id_or_url)
    if notice is None:
        return None

    attachments = []
    for row in list_notice_attachments(conn, notice["id"]):
        item = dict(row)
        item["extracted_text_preview"] = text_preview(item.get("extracted_text"))
        attachments.append(item)

    media = []
    for row in list_notice_media(conn, notice["id"]):
        item = dict(row)
        item["ocr_text_preview"] = text_preview(item.get("ocr_text"))
        item["summary_text_preview"] = text_preview(item.get("summary_text"))
        media.append(item)

    chunk_rows = conn.execute(
        """
        SELECT
            chunk_type,
            COUNT(*) AS count,
            SUM(CASE WHEN embedding IS NOT NULL THEN 1 ELSE 0 END) AS embedded_count,
            SUM(CASE WHEN embedding IS NULL THEN 1 ELSE 0 END) AS missing_embedding_count
        FROM notice_chunks
        WHERE notice_id = ?
        GROUP BY chunk_type
        ORDER BY chunk_type
        """,
        (notice["id"],),
    ).fetchall()
    chunk_types = [dict(row) for row in chunk_rows]
    total_chunks = sum(int(row["count"] or 0) for row in chunk_types)
    embedded_chunks = sum(int(row["embedded_count"] or 0) for row in chunk_types)
    missing_embeddings = sum(int(row["missing_embedding_count"] or 0) for row in chunk_types)

    detail = dict(notice)
    detail["attachments"] = attachments
    detail["media"] = media
    detail["chunks"] = {
        "total_chunks": total_chunks,
        "embedded_chunks": embedded_chunks,
        "missing_embeddings": missing_embeddings,
        "by_type": chunk_types,
    }
    detail["related_actions"] = {
        "can_reindex": True,
        "can_embed": missing_embeddings > 0,
    }
    return detail


def get_ingestion_status(conn: sqlite3.Connection) -> dict[str, Any]:
    counts = count_rows(conn)
    embedding_row = conn.execute(
        """
        SELECT
            COUNT(*) AS total_chunks,
            SUM(CASE WHEN embedding IS NOT NULL THEN 1 ELSE 0 END) AS embedded_chunks,
            SUM(CASE WHEN embedding IS NULL THEN 1 ELSE 0 END) AS missing_embeddings
        FROM notice_chunks
        """
    ).fetchone()
    embeddings = {key: int(embedding_row[key] or 0) for key in embedding_row.keys()}
    attachment_row = conn.execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN file_type = 'pdf' THEN 1 ELSE 0 END) AS pdf_total,
            SUM(CASE WHEN parse_status = 'parsed' THEN 1 ELSE 0 END) AS parsed,
            SUM(CASE WHEN parse_status = 'failed' THEN 1 ELSE 0 END) AS failed,
            SUM(CASE WHEN parse_status = 'unsupported' THEN 1 ELSE 0 END) AS unsupported,
            SUM(CASE WHEN parse_status = 'empty' THEN 1 ELSE 0 END) AS empty,
            SUM(CASE WHEN parse_status = 'pending' THEN 1 ELSE 0 END) AS pending,
            SUM(CASE WHEN download_status = 'downloaded' THEN 1 ELSE 0 END) AS downloaded,
            SUM(CASE WHEN download_status = 'skipped' THEN 1 ELSE 0 END) AS skipped,
            SUM(CASE WHEN download_status = 'failed' THEN 1 ELSE 0 END) AS download_failed
        FROM notice_attachments
        """
    ).fetchone()
    attachments = {key: int(attachment_row[key] or 0) for key in attachment_row.keys()}
    media_row = conn.execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN media_type = 'image' THEN 1 ELSE 0 END) AS image_total,
            SUM(CASE WHEN parse_status = 'parsed' THEN 1 ELSE 0 END) AS parsed,
            SUM(CASE WHEN parse_status = 'failed' THEN 1 ELSE 0 END) AS failed,
            SUM(CASE WHEN parse_status = 'unsupported' THEN 1 ELSE 0 END) AS unsupported,
            SUM(CASE WHEN parse_status = 'empty' THEN 1 ELSE 0 END) AS empty,
            SUM(CASE WHEN parse_status = 'pending' THEN 1 ELSE 0 END) AS pending,
            SUM(CASE WHEN download_status = 'downloaded' THEN 1 ELSE 0 END) AS downloaded,
            SUM(CASE WHEN download_status = 'skipped' THEN 1 ELSE 0 END) AS skipped,
            SUM(CASE WHEN download_status = 'failed' THEN 1 ELSE 0 END) AS download_failed
        FROM notice_media
        """
    ).fetchone()
    media = {key: int(media_row[key] or 0) for key in media_row.keys()}

    source_rows = [
        dict(row)
        for row in conn.execute(
            """
            SELECT
                notice_sources.id,
                notice_sources.name,
                notice_sources.source_type,
                notice_sources.department,
                notice_sources.is_active,
                COUNT(DISTINCT notices.id) AS notice_count,
                COUNT(DISTINCT notice_attachments.id) AS attachment_count,
                COUNT(DISTINCT notice_media.id) AS media_count,
                COUNT(DISTINCT notice_chunks.id) AS chunk_count
            FROM notice_sources
            LEFT JOIN notices ON notices.source_id = notice_sources.id
            LEFT JOIN notice_attachments ON notice_attachments.notice_id = notices.id
            LEFT JOIN notice_media ON notice_media.notice_id = notices.id
            LEFT JOIN notice_chunks ON notice_chunks.notice_id = notices.id
            GROUP BY notice_sources.id
            ORDER BY notice_sources.name
            """
        ).fetchall()
    ]
    for source in source_rows:
        crawl_row = conn.execute(
            """
            SELECT source_key, finished_at
            FROM crawl_runs
            WHERE source_name = ?
            ORDER BY COALESCE(finished_at, started_at) DESC, id DESC
            LIMIT 1
            """,
            (source["name"],),
        ).fetchone()
        success_row = conn.execute(
            """
            SELECT finished_at
            FROM crawl_runs
            WHERE source_name = ? AND status IN ('success', 'partial')
            ORDER BY COALESCE(finished_at, started_at) DESC, id DESC
            LIMIT 1
            """,
            (source["name"],),
        ).fetchone()
        failure_row = conn.execute(
            """
            SELECT finished_at, error_message
            FROM crawl_runs
            WHERE source_name = ? AND status = 'failed'
            ORDER BY COALESCE(finished_at, started_at) DESC, id DESC
            LIMIT 1
            """,
            (source["name"],),
        ).fetchone()
        source_key = crawl_row["source_key"] if crawl_row else None
        failure_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM ingestion_logs
            WHERE status = 'failed' AND (source_id = ? OR source_id = ?)
            """,
            (source["id"], source_key),
        ).fetchone()[0]
        latest_log_error = conn.execute(
            """
            SELECT error_message
            FROM ingestion_logs
            WHERE status = 'failed' AND (source_id = ? OR source_id = ?)
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (source["id"], source_key),
        ).fetchone()
        source["source_id"] = source["id"]
        source["source_key"] = source_key
        source["enabled"] = bool(source["is_active"])
        source["last_crawl_at"] = crawl_row["finished_at"] if crawl_row else None
        source["last_success_at"] = success_row["finished_at"] if success_row else None
        source["last_failure_at"] = failure_row["finished_at"] if failure_row else None
        source["failure_count"] = int(failure_count or 0)
        source["latest_error_message"] = (
            latest_log_error["error_message"]
            if latest_log_error and latest_log_error["error_message"]
            else failure_row["error_message"]
            if failure_row
            else None
        )

    recent_runs = [
        dict(row)
        for row in conn.execute(
            """
            SELECT
                id,
                source_key,
                source_name,
                status,
                imported_count,
                attachment_count,
                parsed_attachment_count,
                error_message,
                started_at,
                finished_at
            FROM crawl_runs
            ORDER BY COALESCE(finished_at, started_at) DESC, id DESC
            LIMIT 8
            """
        ).fetchall()
    ]

    last_reindex_row = conn.execute(
        "SELECT MAX(created_at) AS last_reindex_at FROM notice_chunks"
    ).fetchone()
    failure_logs = list_ingestion_failure_logs(conn, limit=20)
    summary = {
        "total_notices": counts.get("notices", 0),
        "total_chunks": embeddings["total_chunks"],
        "total_embeddings": embeddings["embedded_chunks"],
        "missing_embeddings": embeddings["missing_embeddings"],
        "total_attachments": attachments["total"],
        "pdf_attachments": attachments["pdf_total"],
        "pdf_parse_success": attachments["parsed"],
        "pdf_parse_failed": attachments["failed"],
        "hwp_attachments": int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM notice_attachments
                WHERE lower(COALESCE(file_type, '')) IN ('hwp', 'hwpx')
                """
            ).fetchone()[0]
            or 0
        ),
        "total_media": media["total"],
        "image_media": media["image_total"],
        "image_ocr_success": media["parsed"],
        "image_ocr_failed": media["failed"],
        "image_ocr_unsupported": media["unsupported"],
        "last_crawl_at": recent_runs[0]["finished_at"] if recent_runs else None,
        "last_reindex_at": last_reindex_row["last_reindex_at"] if last_reindex_row else None,
        "last_embed_at": None,
        "failure_logs": len(failure_logs),
    }

    return {
        "counts": counts,
        "summary": summary,
        "embeddings": embeddings,
        "attachments": attachments,
        "media": media,
        "ocr_health": get_ocr_health(),
        "sources": source_rows,
        "failure_logs": failure_logs,
        "recent_runs": recent_runs,
        "last_crawl_at": summary["last_crawl_at"],
    }


def build_chunk_metadata(
    notice: sqlite3.Row,
    *,
    chunk_type: str,
    attachment_id: str | None = None,
    attachment: sqlite3.Row | None = None,
    media_id: str | None = None,
    media: sqlite3.Row | None = None,
) -> dict[str, Any]:
    return {
        "notice_id": notice["id"],
        "chunk_type": chunk_type,
        "attachment_id": attachment_id,
        "attachment_file_name": attachment["file_name"] if attachment else None,
        "attachment_file_url": attachment["file_url"] if attachment else None,
        "attachment_file_type": attachment["file_type"] if attachment else None,
        "media_id": media_id,
        "media_file_name": media["file_name"] if media else None,
        "media_original_url": media["original_url"] if media else None,
        "media_file_type": media["file_type"] if media else None,
        "media_alt_text": media["alt_text"] if media else None,
        "media_caption": media["caption"] if media else None,
        "media_local_path": media["local_path"] if media else None,
        "media_thumbnail_path": media["thumbnail_path"] if media else None,
        "title": notice["title"],
        "department": notice["department"],
        "grade": notice["grade"],
        "course_id": notice["course_id"],
        "visibility": notice["visibility"],
        "publisher": notice["publisher"],
        "category": notice["category"],
        "published_at": notice["published_at"],
        "deadline_at": notice["deadline_at"],
        "valid_until": notice["valid_until"],
        "original_url": notice["original_url"],
        "source_type": notice["source_type"],
    }


def reindex_notice(
    conn: sqlite3.Connection,
    notice_id: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> int:
    notice = get_notice(conn, notice_id)
    if notice is None:
        raise ValueError(f"notice not found: {notice_id}")

    conn.execute("DELETE FROM notice_chunks WHERE notice_id = ?", (notice_id,))
    total_chunks = 0

    document = build_notice_document(notice["title"], notice["body_text"])
    body_chunks = chunk_text(document, chunk_size=chunk_size, overlap=overlap)
    body_metadata = build_chunk_metadata(notice, chunk_type="body")

    for chunk in body_chunks:
        conn.execute(
            """
            INSERT INTO notice_chunks (
                id,
                notice_id,
                attachment_id,
                media_id,
                chunk_type,
                chunk_text,
                chunk_index,
                metadata,
                embedding
            )
            VALUES (?, ?, NULL, NULL, 'body', ?, ?, ?, NULL)
            """,
            (
                stable_chunk_id(notice_id, None, chunk),
                notice_id,
                chunk.text,
                chunk.index,
                json.dumps(body_metadata, ensure_ascii=False, sort_keys=True),
            ),
        )
        total_chunks += 1

    for attachment in list_notice_attachments(conn, notice_id, only_searchable=True):
        attachment_chunk_type = "pdf_text" if attachment["file_type"] == "pdf" else "body"
        attachment_document = build_notice_document(
            f"{notice['title']} / {attachment['file_name']}",
            attachment["extracted_text"],
        )
        attachment_chunks = chunk_text(attachment_document, chunk_size=chunk_size, overlap=overlap)
        attachment_metadata = build_chunk_metadata(
            notice,
            chunk_type=attachment_chunk_type,
            attachment_id=attachment["id"],
            attachment=attachment,
        )
        for chunk in attachment_chunks:
            conn.execute(
                """
                INSERT INTO notice_chunks (
                    id,
                    notice_id,
                    attachment_id,
                    media_id,
                    chunk_type,
                    chunk_text,
                    chunk_index,
                    metadata,
                    embedding
                )
                VALUES (?, ?, ?, NULL, ?, ?, ?, ?, NULL)
                """,
                (
                    stable_chunk_id(notice_id, attachment["id"], chunk),
                    notice_id,
                    attachment["id"],
                    attachment_chunk_type,
                    chunk.text,
                    chunk.index,
                    json.dumps(attachment_metadata, ensure_ascii=False, sort_keys=True),
                ),
            )
            total_chunks += 1

    for media in list_notice_media(conn, notice_id, only_searchable=True):
        media_sources = [
            ("image_ocr", media["ocr_text"]),
            ("image_summary", media["summary_text"]),
        ]
        for chunk_type, source_text in media_sources:
            if not source_text or not source_text.strip():
                continue
            media_document = build_notice_document(
                f"{notice['title']} / {media['file_name']}",
                source_text,
            )
            media_chunks = chunk_text(media_document, chunk_size=chunk_size, overlap=overlap)
            media_metadata = build_chunk_metadata(
                notice,
                chunk_type=chunk_type,
                media_id=media["id"],
                media=media,
            )
            for chunk in media_chunks:
                conn.execute(
                    """
                    INSERT INTO notice_chunks (
                        id,
                        notice_id,
                        attachment_id,
                        media_id,
                        chunk_type,
                        chunk_text,
                        chunk_index,
                        metadata,
                        embedding
                    )
                    VALUES (?, ?, NULL, ?, ?, ?, ?, ?, NULL)
                    """,
                    (
                        stable_chunk_id(notice_id, f"{media['id']}:{chunk_type}", chunk),
                        notice_id,
                        media["id"],
                        chunk_type,
                        chunk.text,
                        chunk.index,
                        json.dumps(media_metadata, ensure_ascii=False, sort_keys=True),
                    ),
                )
                total_chunks += 1
    conn.commit()
    return total_chunks


def reindex_notice_by_id_or_url(
    conn: sqlite3.Connection,
    id_or_url: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> tuple[str, int]:
    notice = find_notice(conn, id_or_url)
    if notice is None:
        raise ValueError(f"notice not found: {id_or_url}")
    return notice["id"], reindex_notice(conn, notice["id"], chunk_size, overlap)


def reindex_all_notices(
    conn: sqlite3.Connection,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> dict[str, int]:
    result: dict[str, int] = {}
    for notice_id in list_notice_ids(conn):
        result[notice_id] = reindex_notice(conn, notice_id, chunk_size, overlap)
    return result
