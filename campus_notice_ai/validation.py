from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from campus_notice_ai.db import connect, init_db
from campus_notice_ai.notice_repository import record_ingestion_log
from campus_notice_ai.rag import FallbackLLMProvider, answer_question
from campus_notice_ai.server import crawl_and_store


def _count(conn: sqlite3.Connection, query: str, params: tuple[Any, ...]) -> int:
    return int(conn.execute(query, params).fetchone()[0] or 0)


def _source_notice_ids(result: dict[str, Any]) -> list[str]:
    return [str(value) for value in result.get("notice_ids", []) if value]


def validate_real_data(
    db_path: str | Path | None = None,
    *,
    limit: int = 10,
    source_keys: list[str] | None = None,
    embed_after: bool = True,
) -> dict[str, Any]:
    crawl_result = crawl_and_store(
        Path(db_path) if db_path else None,
        limit=limit,
        source_keys=source_keys,
        embed_after=embed_after,
    )

    source_summaries: list[dict[str, Any]] = []
    with connect(db_path) as conn:
        init_db(conn)
        for source_result in crawl_result["sources"]:
            notice_ids = _source_notice_ids(source_result)
            if notice_ids:
                placeholders = ",".join("?" for _ in notice_ids)
                params: tuple[Any, ...] = tuple(notice_ids)
                body_extracted = _count(
                    conn,
                    f"SELECT COUNT(*) FROM notices WHERE id IN ({placeholders}) AND length(trim(body_text)) > 0",
                    params,
                )
                title_extracted = _count(
                    conn,
                    f"SELECT COUNT(*) FROM notices WHERE id IN ({placeholders}) AND length(trim(title)) > 0",
                    params,
                )
                original_url_present = _count(
                    conn,
                    f"SELECT COUNT(*) FROM notices WHERE id IN ({placeholders}) AND length(trim(COALESCE(original_url, ''))) > 0",
                    params,
                )
                attachment_count = _count(
                    conn,
                    f"SELECT COUNT(*) FROM notice_attachments WHERE notice_id IN ({placeholders})",
                    params,
                )
                pdf_total = _count(
                    conn,
                    f"SELECT COUNT(*) FROM notice_attachments WHERE notice_id IN ({placeholders}) AND file_type = 'pdf'",
                    params,
                )
                pdf_parsed = _count(
                    conn,
                    f"SELECT COUNT(*) FROM notice_attachments WHERE notice_id IN ({placeholders}) AND file_type = 'pdf' AND parse_status = 'parsed'",
                    params,
                )
                pdf_failed = _count(
                    conn,
                    f"SELECT COUNT(*) FROM notice_attachments WHERE notice_id IN ({placeholders}) AND file_type = 'pdf' AND parse_status = 'failed'",
                    params,
                )
                media_total = _count(
                    conn,
                    f"SELECT COUNT(*) FROM notice_media WHERE notice_id IN ({placeholders})",
                    params,
                )
                media_cached = _count(
                    conn,
                    f"SELECT COUNT(*) FROM notice_media WHERE notice_id IN ({placeholders}) AND local_path IS NOT NULL",
                    params,
                )
                ocr_available = _count(
                    conn,
                    f"SELECT COUNT(*) FROM notice_media WHERE notice_id IN ({placeholders}) AND parse_status = 'parsed'",
                    params,
                )
                chunks_created = _count(
                    conn,
                    f"SELECT COUNT(*) FROM notice_chunks WHERE notice_id IN ({placeholders})",
                    params,
                )
                embeddings_created = _count(
                    conn,
                    f"SELECT COUNT(*) FROM notice_chunks WHERE notice_id IN ({placeholders}) AND embedding IS NOT NULL",
                    params,
                )
                failures = _count(
                    conn,
                    f"SELECT COUNT(*) FROM ingestion_logs WHERE status = 'failed' AND notice_id IN ({placeholders})",
                    params,
                )
                evidence_ready = 0
                for notice_id in notice_ids[: min(3, len(notice_ids))]:
                    notice = conn.execute(
                        "SELECT title FROM notices WHERE id = ?",
                        (notice_id,),
                    ).fetchone()
                    if not notice:
                        continue
                    response = answer_question(
                        conn,
                        str(notice["title"]),
                        limit=1,
                        provider=FallbackLLMProvider(),
                    )
                    if response["sources"]:
                        evidence_ready += 1
            else:
                body_extracted = 0
                title_extracted = 0
                original_url_present = 0
                attachment_count = int(source_result.get("attachments") or 0)
                pdf_total = 0
                pdf_parsed = 0
                pdf_failed = 0
                media_total = int(source_result.get("media") or 0)
                media_cached = 0
                ocr_available = 0
                chunks_created = 0
                embeddings_created = 0
                failures = 1 if source_result.get("error") else 0
                evidence_ready = 0

            summary = {
                "source": source_result["source"],
                "crawled_notices": int(source_result.get("imported") or 0),
                "title_extracted": title_extracted,
                "body_extracted": body_extracted,
                "original_url_present": original_url_present,
                "attachments_found": attachment_count,
                "pdf_total": pdf_total,
                "pdf_parsed": pdf_parsed,
                "pdf_failed": pdf_failed,
                "images_found": media_total,
                "image_cached": media_cached,
                "ocr_available": ocr_available,
                "chunks_created": chunks_created,
                "embeddings_created": embeddings_created,
                "evidence_ready": evidence_ready,
                "failures": failures,
                "error": source_result.get("error"),
            }
            source_summaries.append(summary)
            status = "failed" if summary["error"] else "warning" if failures else "success"
            record_ingestion_log(
                conn,
                source_id=summary["source"],
                target_type="source",
                target_id=summary["source"],
                step="crawl",
                status=status,
                message=(
                    f"Real data validation: {summary['crawled_notices']} notices, "
                    f"{summary['chunks_created']} chunks, {summary['embeddings_created']} embeddings."
                ),
                error_message=summary["error"],
                retryable=bool(summary["error"]),
            )
        conn.commit()

    return {
        "limit": limit,
        "embed_after": embed_after,
        "imported": crawl_result["imported"],
        "embedding": crawl_result.get("embedding"),
        "sources": source_summaries,
    }
