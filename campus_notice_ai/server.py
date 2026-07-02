from __future__ import annotations

import base64
import json
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from campus_notice_ai.attachments import (
    ParsedAttachment,
    clean_file_name,
    download_attachment_bytes,
    guess_file_type,
    parse_attachment_text,
)
from campus_notice_ai.config import PROJECT_ROOT
from campus_notice_ai.crawler import crawl_dku_source, iter_sources
from campus_notice_ai.db import connect, init_db
from campus_notice_ai.embeddings import create_query_embedding_for_search, embed_notice_chunks
from campus_notice_ai.media import (
    ProcessedMedia,
    clean_media_file_name,
    decode_base64_media,
    guess_image_file_type,
    is_image_file_type,
    process_image_media,
)
from campus_notice_ai.notice_repository import (
    count_rows,
    get_ingestion_status,
    get_notice_detail,
    list_notices,
    make_notice_media_id,
    record_crawl_run,
    record_ingestion_log,
    reindex_all_notices,
    reindex_notice,
    seed_notices,
    upsert_notice,
    upsert_notice_attachment,
    upsert_notice_media,
    upsert_notice_source,
)
from campus_notice_ai.rag import answer_question
from campus_notice_ai.search import build_extract_answer, search_chunks


STATIC_DIR = PROJECT_ROOT / "static"
MAX_API_LIMIT = 100


def parse_positive_int(value: Any, *, default: int, field: str, max_value: int = MAX_API_LIMIT) -> int:
    if value in (None, ""):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc
    if parsed < 1:
        raise ValueError(f"{field} must be greater than 0")
    return min(parsed, max_value)


class CampusNoticeHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, db_path: Path | None = None, **kwargs: Any) -> None:
        self.db_path = db_path
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        try:
            self.handle_get()
        except ValueError as exc:
            self.send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self.send_json(
                {"error": "internal_server_error", "detail": str(exc)},
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def handle_get(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self.handle_health()
            return
        if parsed.path == "/api/ingestion/status":
            with connect(self.db_path) as conn:
                init_db(conn)
                self.send_json(get_ingestion_status(conn))
            return
        if parsed.path == "/api/notice" or parsed.path.startswith("/api/notices/"):
            query = parse_qs(parsed.query)
            notice_id = query.get("id", [""])[0]
            if parsed.path.startswith("/api/notices/"):
                notice_id = unquote(parsed.path.removeprefix("/api/notices/"))
            if not notice_id:
                raise ValueError("id is required")
            with connect(self.db_path) as conn:
                init_db(conn)
                detail = get_notice_detail(conn, notice_id)
            if detail is None:
                self.send_json({"error": "notice not found"}, status=HTTPStatus.NOT_FOUND)
                return
            self.send_json({"notice": detail})
            return
        if parsed.path == "/api/notices":
            query = parse_qs(parsed.query)
            limit = parse_positive_int(query.get("limit", ["50"])[0], default=50, field="limit")
            with connect(self.db_path) as conn:
                init_db(conn)
                self.send_json({"notices": list_notices(conn, limit=limit)})
            return
        if parsed.path == "/api/search":
            query = parse_qs(parsed.query)
            keyword = query.get("q", [""])[0]
            department = query.get("department", [None])[0] or None
            grade = query.get("grade", [None])[0] or None
            course_id = query.get("course_id", [None])[0] or None
            limit = parse_positive_int(query.get("limit", ["8"])[0], default=8, field="limit")
            with connect(self.db_path) as conn:
                init_db(conn)
                query_embedding = create_query_embedding_for_search(conn, keyword)
                results = search_chunks(
                    conn,
                    keyword,
                    department=department,
                    grade=grade,
                    course_id=course_id,
                    limit=limit,
                    query_embedding=query_embedding,
                )
            self.send_json({"answer": build_extract_answer(keyword, results), "results": results})
            return
        super().do_GET()

    def do_POST(self) -> None:
        try:
            self.handle_post()
        except (ValueError, json.JSONDecodeError, KeyError) as exc:
            self.send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self.send_json(
                {"error": "internal_server_error", "detail": str(exc)},
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def handle_post(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/admin/seed":
            payload = self.read_json()
            embed_after = bool(payload.get("embed_after") or False)
            embedding_batch_size = parse_positive_int(
                payload.get("embedding_batch_size"),
                default=32,
                field="embedding_batch_size",
                max_value=500,
            )
            with connect(self.db_path) as conn:
                init_db(conn)
                count = seed_notices(conn)
                reindexed = reindex_all_notices(conn)
                embedding = embed_missing_chunks_if_requested(
                    conn,
                    embed_after=embed_after,
                    batch_size=embedding_batch_size,
                )
            response = {"seeded": count, "reindexed": len(reindexed)}
            if embedding is not None:
                response["embedding"] = embedding
            self.send_json(response)
            return
        if parsed.path == "/api/admin/reindex":
            payload = self.read_json()
            embed_after = bool(payload.get("embed_after") or False)
            embedding_batch_size = parse_positive_int(
                payload.get("embedding_batch_size"),
                default=32,
                field="embedding_batch_size",
                max_value=500,
            )
            with connect(self.db_path) as conn:
                init_db(conn)
                result = reindex_all_notices(conn)
                embedding = embed_missing_chunks_if_requested(
                    conn,
                    embed_after=embed_after,
                    batch_size=embedding_batch_size,
                )
            response = {"reindexed": len(result), "chunks": sum(result.values())}
            if embedding is not None:
                response["embedding"] = embedding
            self.send_json(response)
            return
        if parsed.path == "/api/admin/embed":
            payload = self.read_json()
            batch_size = parse_positive_int(payload.get("batch_size"), default=32, field="batch_size")
            limit_value = payload.get("limit")
            limit = (
                parse_positive_int(limit_value, default=100, field="limit", max_value=5000)
                if limit_value not in (None, "")
                else None
            )
            force = bool(payload.get("force") or False)
            with connect(self.db_path) as conn:
                init_db(conn)
                result = embed_notice_chunks(
                    conn,
                    batch_size=batch_size,
                    limit=limit,
                    force=force,
                )
            self.send_json(result)
            return
        if parsed.path == "/api/admin/crawl":
            payload = self.read_json()
            limit = parse_positive_int(payload.get("limit"), default=3, field="limit")
            keys = payload.get("sources") or None
            if keys is not None and not isinstance(keys, list):
                raise ValueError("sources must be a list")
            embedding_batch_size = parse_positive_int(
                payload.get("embedding_batch_size"),
                default=32,
                field="embedding_batch_size",
                max_value=500,
            )
            imported = crawl_and_store(
                self.db_path,
                limit=limit,
                source_keys=keys,
                embed_after=bool(payload.get("embed_after") or False),
                embedding_batch_size=embedding_batch_size,
            )
            self.send_json(imported)
            return
        if parsed.path == "/api/chat":
            payload = self.read_json()
            query = str(payload.get("query") or "").strip()
            if not query:
                raise ValueError("query is required")
            limit = parse_positive_int(payload.get("limit"), default=3, field="limit")
            with connect(self.db_path) as conn:
                init_db(conn)
                response = answer_question(
                    conn,
                    query,
                    department=payload.get("department") or None,
                    grade=payload.get("grade") or None,
                    course_id=payload.get("course_id") or None,
                    limit=limit,
                )
            self.send_json(response)
            return
        if parsed.path == "/api/notices":
            payload = self.read_json()
            title = payload.get("title")
            body_text = payload.get("body_text")
            if not title or not body_text:
                raise ValueError("title and body_text are required")
            with connect(self.db_path) as conn:
                init_db(conn)
                source_id = upsert_notice_source(
                    conn,
                    name=payload.get("source_name") or "수동 등록",
                    source_type=payload.get("source_type") or "manual",
                    base_url=payload.get("source_base_url") or "manual://local",
                    department=payload.get("department") or None,
                )
                notice_id = upsert_notice(
                    conn,
                    source_id=source_id,
                    title=title,
                    body_text=body_text,
                    original_url=payload.get("original_url") or f"manual://{title}",
                    publisher=payload.get("publisher"),
                    category=payload.get("category"),
                    department=payload.get("department"),
                    grade=payload.get("grade"),
                    course_id=payload.get("course_id"),
                    visibility=payload.get("visibility") or "public",
                    published_at=payload.get("published_at"),
                    deadline_at=payload.get("deadline_at"),
                )
                attachment_payloads, media_payloads = split_attachment_and_media_payloads(
                    [item for item in payload.get("attachments", []) if isinstance(item, dict)],
                    [item for item in payload.get("media", []) if isinstance(item, dict)],
                )
                attachment_result = store_notice_attachments(
                    conn,
                    notice_id,
                    attachment_payloads,
                )
                media_result = store_notice_media(
                    conn,
                    notice_id,
                    media_payloads,
                )
                conn.commit()
                reindex_notice(conn, notice_id)
                embedding = embed_missing_chunks_if_requested(
                    conn,
                    embed_after=bool(payload.get("embed_after") or False),
                    batch_size=parse_positive_int(
                        payload.get("embedding_batch_size"),
                        default=32,
                        field="embedding_batch_size",
                        max_value=500,
                    ),
                )
            response = {
                "notice_id": notice_id,
                "attachments": attachment_result["stored"],
                "parsed_attachments": attachment_result["parsed"],
                "media": media_result["stored"],
                "parsed_media": media_result["parsed"],
            }
            if embedding is not None:
                response["embedding"] = embedding
            self.send_json(response, status=HTTPStatus.CREATED)
            return
        self.send_error(HTTPStatus.NOT_FOUND, "API route not found")

    def handle_health(self) -> None:
        with connect(self.db_path) as conn:
            init_db(conn)
            self.send_json({"status": "ok", "counts": count_rows(conn)})

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("content-length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw)

    def send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def process_attachment_payload(raw_attachment: dict[str, Any]) -> tuple[str, str | None, ParsedAttachment]:
    file_url = raw_attachment.get("file_url") or None
    file_name = clean_file_name(raw_attachment.get("file_name"), file_url)
    file_type = raw_attachment.get("file_type") or guess_file_type(file_name, file_url)
    extracted_text = str(raw_attachment.get("extracted_text") or "").strip()
    if extracted_text:
        return (
            file_name,
            file_url,
            ParsedAttachment(
                file_type=file_type,
                download_status="downloaded",
                parse_status="parsed",
                extracted_text=extracted_text,
            ),
        )

    if file_type != "pdf":
        return (
            file_name,
            file_url,
            ParsedAttachment(
                file_type=file_type,
                download_status="skipped",
                parse_status="unsupported",
            ),
        )
    if not file_url:
        encoded_content = raw_attachment.get("file_content_base64")
        if encoded_content:
            try:
                data = base64.b64decode(str(encoded_content), validate=True)
                parsed = parse_attachment_text(file_name, file_url, data)
            except Exception as exc:
                parsed = ParsedAttachment(
                    file_type=file_type,
                    download_status="failed",
                    parse_status="failed",
                    error_message=str(exc)[:500],
                )
            return file_name, file_url, parsed
        return (
            file_name,
            file_url,
            ParsedAttachment(
                file_type=file_type,
                download_status="failed",
                parse_status="failed",
                error_message="PDF attachment has no URL",
            ),
        )

    try:
        data = download_attachment_bytes(file_url)
        parsed = parse_attachment_text(file_name, file_url, data)
    except Exception as exc:
        parsed = ParsedAttachment(
            file_type=file_type,
            download_status="failed",
            parse_status="failed",
            error_message=str(exc)[:500],
        )
    return file_name, file_url, parsed


def is_image_payload(payload: dict[str, Any]) -> bool:
    file_url = payload.get("original_url") or payload.get("file_url")
    file_name = payload.get("file_name")
    file_type = payload.get("file_type") or guess_image_file_type(file_name, file_url)
    return is_image_file_type(file_type)


def split_attachment_and_media_payloads(
    attachments: list[dict[str, Any]],
    media: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    attachment_payloads: list[dict[str, Any]] = []
    media_payloads = list(media)
    for attachment in attachments:
        if is_image_payload(attachment):
            media_payloads.append(
                {
                    **attachment,
                    "original_url": attachment.get("original_url") or attachment.get("file_url"),
                }
            )
        else:
            attachment_payloads.append(attachment)
    return attachment_payloads, media_payloads


def process_media_payload(notice_id: str, raw_media: dict[str, Any]) -> ProcessedMedia:
    original_url = raw_media.get("original_url") or raw_media.get("file_url") or None
    file_name = clean_media_file_name(raw_media.get("file_name"), original_url)
    file_type = raw_media.get("file_type") or guess_image_file_type(file_name, original_url)
    media_id = make_notice_media_id(notice_id, file_name, original_url)
    data = None

    try:
        data = decode_base64_media(raw_media.get("file_content_base64"))
    except Exception as exc:
        return ProcessedMedia(
            file_name=file_name,
            original_url=original_url,
            file_type=file_type,
            alt_text=raw_media.get("alt_text"),
            caption=raw_media.get("caption"),
            download_status="failed",
            parse_status="failed",
            error_message=str(exc)[:500],
        )

    if data is None and original_url:
        try:
            data = download_attachment_bytes(original_url)
        except Exception as exc:
            return ProcessedMedia(
                file_name=file_name,
                original_url=original_url,
                file_type=file_type,
                alt_text=raw_media.get("alt_text"),
                caption=raw_media.get("caption"),
                download_status="failed",
                parse_status="failed",
                error_message=str(exc)[:500],
            )

    return process_image_media(
        media_id=media_id,
        file_name=file_name,
        original_url=original_url,
        file_type=file_type,
        alt_text=raw_media.get("alt_text"),
        caption=raw_media.get("caption"),
        data=data,
        ocr_text=raw_media.get("ocr_text"),
        summary_text=raw_media.get("summary_text"),
    )


def store_notice_attachments(
    conn,
    notice_id: str,
    attachments: list[dict[str, Any]],
) -> dict[str, Any]:
    stored = 0
    parsed_count = 0
    failed_count = 0
    failures: list[dict[str, Any]] = []
    for raw_attachment in attachments:
        file_name, file_url, parsed = process_attachment_payload(raw_attachment)
        attachment_id = upsert_notice_attachment(
            conn,
            notice_id=notice_id,
            file_name=file_name,
            file_url=file_url,
            file_type=parsed.file_type,
            extracted_text=parsed.extracted_text,
            download_status=parsed.download_status,
            parse_status=parsed.parse_status,
            error_message=parsed.error_message,
        )
        stored += 1
        if parsed.parse_status == "parsed":
            parsed_count += 1
        if parsed.parse_status == "failed" or parsed.download_status == "failed":
            failed_count += 1
            failures.append(
                {
                    "target_id": attachment_id,
                    "file_name": file_name,
                    "file_url": file_url,
                    "file_type": parsed.file_type,
                    "step": "pdf_extract" if parsed.file_type == "pdf" else "parse",
                    "error_message": parsed.error_message or "attachment processing failed",
                    "retryable": parsed.download_status == "failed",
                }
            )
    return {
        "stored": stored,
        "parsed": parsed_count,
        "failed": failed_count,
        "failures": failures,
    }


def store_notice_media(
    conn,
    notice_id: str,
    media_items: list[dict[str, Any]],
) -> dict[str, Any]:
    stored = 0
    parsed_count = 0
    failed_count = 0
    failures: list[dict[str, Any]] = []
    for raw_media in media_items:
        media = process_media_payload(notice_id, raw_media)
        media_id = upsert_notice_media(
            conn,
            notice_id=notice_id,
            file_name=media.file_name,
            original_url=media.original_url,
            file_type=media.file_type,
            alt_text=media.alt_text,
            caption=media.caption,
            local_path=media.local_path,
            thumbnail_path=media.thumbnail_path,
            ocr_text=media.ocr_text,
            summary_text=media.summary_text,
            download_status=media.download_status,
            parse_status=media.parse_status,
            summary_status=media.summary_status,
            error_message=media.error_message,
        )
        stored += 1
        if media.parse_status == "parsed":
            parsed_count += 1
        if media.parse_status == "failed" or media.download_status == "failed":
            failed_count += 1
            failures.append(
                {
                    "target_id": media_id,
                    "file_name": media.file_name,
                    "original_url": media.original_url,
                    "file_type": media.file_type,
                    "step": "image_cache" if media.download_status == "failed" else "ocr",
                    "error_message": media.error_message or "image media processing failed",
                    "retryable": media.download_status == "failed",
                }
            )
    return {
        "stored": stored,
        "parsed": parsed_count,
        "failed": failed_count,
        "failures": failures,
    }


def crawl_and_store(
    db_path: Path | None = None,
    *,
    limit: int = 3,
    source_keys: list[str] | None = None,
    embed_after: bool = False,
    embedding_batch_size: int = 32,
) -> dict[str, Any]:
    imported = 0
    source_results: list[dict[str, Any]] = []
    embedding: dict[str, Any] | None = None
    with connect(db_path) as conn:
        init_db(conn)
        for source in iter_sources(source_keys):
            source_attachment_count = 0
            source_parsed_attachment_count = 0
            source_failed_attachment_count = 0
            source_media_count = 0
            source_parsed_media_count = 0
            source_failed_media_count = 0
            try:
                effective_limit = min(limit, source.crawl_limit) if source.crawl_limit else limit
                notices = crawl_dku_source(source, limit=effective_limit)
            except Exception as exc:
                record_crawl_run(
                    conn,
                    source_key=source.key,
                    source_name=source.name,
                    status="failed",
                    error_message=str(exc)[:500],
                )
                record_ingestion_log(
                    conn,
                    source_id=source.key,
                    target_type="source",
                    target_id=source.list_url,
                    step="crawl",
                    status="failed",
                    message=f"Failed to crawl source {source.name}",
                    error_message=str(exc)[:500],
                    retryable=True,
                )
                conn.commit()
                source_results.append(
                    {"source": source.key, "imported": 0, "error": str(exc)}
                )
                continue
            source_id = upsert_notice_source(
                conn,
                name=source.name,
                source_type=source.source_type,
                base_url=source.list_url,
                department=source.department,
            )
            notice_ids: list[str] = []
            for notice in notices:
                notice_id = upsert_notice(
                    conn,
                    source_id=source_id,
                    title=str(notice["title"]),
                    body_text=str(notice["body_text"]),
                    original_url=str(notice["original_url"]),
                    publisher=notice.get("publisher"),
                    category=notice.get("category"),
                    department=notice.get("department"),
                    grade=notice.get("grade"),
                    course_id=notice.get("course_id"),
                    visibility=str(notice["visibility"]),
                    published_at=notice.get("published_at"),
                    deadline_at=notice.get("deadline_at"),
                )
                attachment_payloads, media_payloads = split_attachment_and_media_payloads(
                    [item for item in notice.get("attachments", []) if isinstance(item, dict)],
                    [item for item in notice.get("media", []) if isinstance(item, dict)],
                )
                attachment_result = store_notice_attachments(
                    conn,
                    notice_id,
                    attachment_payloads,
                )
                media_result = store_notice_media(
                    conn,
                    notice_id,
                    media_payloads,
                )
                if not str(notice.get("title") or "").strip():
                    record_ingestion_log(
                        conn,
                        source_id=source.key,
                        notice_id=notice_id,
                        target_type="notice",
                        target_id=notice_id,
                        step="parse",
                        status="failed",
                        message="Notice title was not extracted.",
                        error_message="empty title",
                        retryable=True,
                    )
                if not str(notice.get("body_text") or "").strip():
                    record_ingestion_log(
                        conn,
                        source_id=source.key,
                        notice_id=notice_id,
                        target_type="notice",
                        target_id=notice_id,
                        step="parse",
                        status="failed",
                        message="Notice body was not extracted.",
                        error_message="empty body_text",
                        retryable=True,
                    )
                if not str(notice.get("original_url") or "").strip():
                    record_ingestion_log(
                        conn,
                        source_id=source.key,
                        notice_id=notice_id,
                        target_type="notice",
                        target_id=notice_id,
                        step="parse",
                        status="failed",
                        message="Notice original URL was not extracted.",
                        error_message="empty original_url",
                        retryable=True,
                    )
                for failure in attachment_result["failures"]:
                    record_ingestion_log(
                        conn,
                        source_id=source.key,
                        notice_id=notice_id,
                        target_type="attachment",
                        target_id=failure["target_id"],
                        step=failure["step"],
                        status="failed",
                        message=f"Attachment failed: {failure['file_name']} ({failure.get('file_url') or '-'})",
                        error_message=failure["error_message"],
                        retryable=bool(failure["retryable"]),
                    )
                for failure in media_result["failures"]:
                    record_ingestion_log(
                        conn,
                        source_id=source.key,
                        notice_id=notice_id,
                        target_type="media",
                        target_id=failure["target_id"],
                        step=failure["step"],
                        status="failed",
                        message=f"Image media failed: {failure['file_name']} ({failure.get('original_url') or '-'})",
                        error_message=failure["error_message"],
                        retryable=bool(failure["retryable"]),
                    )
                source_attachment_count += attachment_result["stored"]
                source_parsed_attachment_count += attachment_result["parsed"]
                source_failed_attachment_count += attachment_result["failed"]
                source_media_count += media_result["stored"]
                source_parsed_media_count += media_result["parsed"]
                source_failed_media_count += media_result["failed"]
                notice_ids.append(notice_id)
            conn.commit()
            source_failed_reindex_count = 0
            for notice_id in notice_ids:
                try:
                    reindex_notice(conn, notice_id)
                except Exception as exc:
                    source_failed_reindex_count += 1
                    record_ingestion_log(
                        conn,
                        source_id=source.key,
                        notice_id=notice_id,
                        target_type="chunk",
                        target_id=notice_id,
                        step="reindex",
                        status="failed",
                        message="Notice reindex failed.",
                        error_message=str(exc)[:500],
                        retryable=True,
                    )
            imported += len(notice_ids)
            status = (
                "partial"
                if source_failed_attachment_count or source_failed_media_count or source_failed_reindex_count
                else "success"
            )
            record_crawl_run(
                conn,
                source_key=source.key,
                source_name=source.name,
                status=status,
                imported_count=len(notice_ids),
                attachment_count=source_attachment_count,
                parsed_attachment_count=source_parsed_attachment_count,
                error_message=(
                    f"{source_failed_attachment_count} attachment(s), "
                    f"{source_failed_media_count} media item(s), "
                    f"{source_failed_reindex_count} reindex job(s) failed"
                    if source_failed_attachment_count or source_failed_media_count or source_failed_reindex_count
                    else None
                ),
            )
            conn.commit()
            source_results.append(
                {
                    "source": source.key,
                    "imported": len(notice_ids),
                    "attachments": source_attachment_count,
                    "parsed_attachments": source_parsed_attachment_count,
                    "failed_attachments": source_failed_attachment_count,
                    "media": source_media_count,
                    "parsed_media": source_parsed_media_count,
                    "failed_media": source_failed_media_count,
                    "failed_reindex": source_failed_reindex_count,
                    "notice_ids": notice_ids,
                }
            )
        embedding = embed_missing_chunks_if_requested(
            conn,
            embed_after=embed_after,
            batch_size=embedding_batch_size,
        )
    result: dict[str, Any] = {"imported": imported, "sources": source_results}
    if embedding is not None:
        result["embedding"] = embedding
    return result


def embed_missing_chunks_if_requested(
    conn,
    *,
    embed_after: bool,
    batch_size: int,
) -> dict[str, Any] | None:
    if not embed_after:
        return None
    try:
        return dict(embed_notice_chunks(conn, batch_size=batch_size))
    except Exception as exc:
        record_ingestion_log(
            conn,
            target_type="embedding",
            step="embed",
            status="failed",
            message="Embedding generation failed.",
            error_message=str(exc)[:500],
            retryable=True,
        )
        conn.commit()
        return {
            "embedded": 0,
            "total_selected": 0,
            "error": str(exc)[:500],
        }


def run_server(host: str, port: int, db_path: Path | None = None) -> None:
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    handler = partial(CampusNoticeHandler, db_path=db_path)
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Campus Notice AI running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
