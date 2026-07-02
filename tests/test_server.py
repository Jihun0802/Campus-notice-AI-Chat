import unittest
import json
import os
import tempfile
import threading
import zlib
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from campus_notice_ai.crawler import DEFAULT_DKU_SOURCES, DkuNoticeSource
from campus_notice_ai.db import connect, init_db
from campus_notice_ai.notice_repository import reindex_all_notices, seed_notices
from campus_notice_ai.server import CampusNoticeHandler, crawl_and_store, parse_positive_int
from campus_notice_ai.search import search_chunks


def raise_for_source(source, *, limit):
    if source.key == DEFAULT_DKU_SOURCES[0].key:
        raise RuntimeError("source failed")
    return []


def make_pdf_stream(text: str) -> bytes:
    stream = zlib.compress(f"BT ({text}) Tj ET".encode("utf-8"))
    return (
        b"%PDF-1.4\n"
        b"1 0 obj\n"
        b"<< /Filter /FlateDecode /Length "
        + str(len(stream)).encode("ascii")
        + b" >>\nstream\n"
        + stream
        + b"\nendstream\nendobj\n%%EOF"
    )


class TestServer:
    def __init__(self, db_path: Path) -> None:
        handler = partial(CampusNoticeHandler, db_path=db_path)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()

    def post_json(self, path: str, payload: dict) -> tuple[int, dict]:
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            try:
                return exc.code, json.loads(exc.read().decode("utf-8"))
            finally:
                exc.close()

    def post_raw(self, path: str, body: bytes) -> tuple[int, dict]:
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            try:
                return exc.code, json.loads(exc.read().decode("utf-8"))
            finally:
                exc.close()

    def get_json(self, path: str) -> tuple[int, dict]:
        request = Request(f"{self.base_url}{path}", method="GET")
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            try:
                return exc.code, json.loads(exc.read().decode("utf-8"))
            finally:
                exc.close()


def prepare_seed_db(db_path: Path) -> None:
    with connect(db_path) as conn:
        init_db(conn)
        seed_notices(conn)
        reindex_all_notices(conn)


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.env_patch = patch.dict(os.environ, {"OPENAI_API_KEY": ""})
        self.env_patch.start()
        self.dotenv_patch = patch("campus_notice_ai.rag.load_dotenv", return_value={})
        self.dotenv_patch.start()

    def tearDown(self):
        self.dotenv_patch.stop()
        self.env_patch.stop()

    def test_parse_positive_int_accepts_default_and_caps_large_values(self):
        self.assertEqual(parse_positive_int(None, default=3, field="limit"), 3)
        self.assertEqual(parse_positive_int("500", default=3, field="limit", max_value=100), 100)

    def test_parse_positive_int_rejects_bad_values(self):
        with self.assertRaises(ValueError):
            parse_positive_int("abc", default=3, field="limit")
        with self.assertRaises(ValueError):
            parse_positive_int("0", default=3, field="limit")

    def test_crawl_and_store_keeps_source_failures_isolated(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            with patch("campus_notice_ai.server.crawl_dku_source", side_effect=raise_for_source):
                result = crawl_and_store(db_path, limit=1)
            with connect(db_path) as conn:
                failed_logs = conn.execute(
                    "SELECT COUNT(*) FROM ingestion_logs WHERE status = 'failed' AND step = 'crawl'"
                ).fetchone()[0]

        failed = [source for source in result["sources"] if source.get("error")]
        self.assertEqual(result["imported"], 0)
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed_logs, 1)

    def test_crawl_and_store_parses_pdf_attachment_chunks_and_embedding_step(self):
        source = DkuNoticeSource(
            key="pdf-source",
            name="PDF source",
            source_type="school_notice",
            list_url="https://example.test/notices",
            detail_base_url="https://example.test/notices",
            crawl_limit=1,
        )
        crawled_notice = {
            "title": "PDF 첨부 공지",
            "body_text": "자세한 신청 요건은 첨부 PDF를 확인하세요.",
            "original_url": "https://example.test/notices/1",
            "publisher": "학사팀",
            "category": "학사",
            "department": None,
            "grade": None,
            "course_id": None,
            "visibility": "public",
            "published_at": "2026-07-02",
            "deadline_at": None,
            "attachments": [
                {
                    "file_name": "guide.pdf",
                    "file_url": "https://example.test/guide.pdf",
                    "file_type": "pdf",
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            with (
                patch("campus_notice_ai.server.iter_sources", return_value=[source]),
                patch("campus_notice_ai.server.crawl_dku_source", return_value=[crawled_notice]),
                patch(
                    "campus_notice_ai.server.download_attachment_bytes",
                    return_value=make_pdf_stream("Portfolio deadline is 2026-07-09."),
                ),
                patch(
                    "campus_notice_ai.server.embed_notice_chunks",
                    return_value={
                        "embedded": 2,
                        "total_selected": 2,
                        "model": "fake-embedding",
                        "dimensions": 2,
                    },
                ) as embed_mock,
            ):
                result = crawl_and_store(db_path, limit=1, embed_after=True)

            with connect(db_path) as conn:
                attachment = conn.execute("SELECT * FROM notice_attachments").fetchone()
                attachment_chunk = conn.execute(
                    "SELECT * FROM notice_chunks WHERE attachment_id IS NOT NULL"
                ).fetchone()
                results = search_chunks(conn, "Portfolio", limit=3)

        self.assertEqual(result["imported"], 1)
        self.assertEqual(result["embedding"]["embedded"], 2)
        embed_mock.assert_called_once()
        self.assertEqual(attachment["parse_status"], "parsed")
        self.assertIn("Portfolio deadline", attachment["extracted_text"])
        self.assertIsNotNone(attachment_chunk)
        self.assertEqual(results[0]["metadata"]["attachment_file_name"], "guide.pdf")

    def test_api_chat_missing_query_returns_400(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            prepare_seed_db(db_path)
            with TestServer(db_path) as server:
                status, body = server.post_json("/api/chat", {"department": "모바일시스템공학과"})

        self.assertEqual(status, 400)
        self.assertEqual(body["error"], "query is required")

    def test_api_chat_bad_json_returns_400(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            prepare_seed_db(db_path)
            with TestServer(db_path) as server:
                status, body = server.post_raw("/api/chat", b"{bad json")

        self.assertEqual(status, 400)
        self.assertIn("Expecting property name", body["error"])

    def test_api_chat_returns_answer_and_sources(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            db_path = Path(tmp) / "test.sqlite3"
            prepare_seed_db(db_path)
            with TestServer(db_path) as server:
                status, body = server.post_json(
                    "/api/chat",
                    {
                        "query": "졸업시험 신청 언제까지야?",
                        "department": "모바일시스템공학과",
                        "grade": "4",
                    },
                )

        self.assertEqual(status, 200)
        self.assertEqual(body["mode"], "fallback")
        self.assertGreaterEqual(len(body["sources"]), 1)
        self.assertIn("졸업시험", body["answer"])

    def test_api_chat_no_answer_returns_empty_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            prepare_seed_db(db_path)
            with TestServer(db_path) as server:
                status, body = server.post_json(
                    "/api/chat",
                    {"query": "존재하지않는특수공지키워드"},
                )

        self.assertEqual(status, 200)
        self.assertEqual(body["sources"], [])
        self.assertIn("관련 공지를 찾지 못했습니다", body["answer"])

    def test_api_chat_course_notice_requires_matching_course_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            prepare_seed_db(db_path)
            with TestServer(db_path) as server:
                status_without, body_without = server.post_json(
                    "/api/chat",
                    {
                        "query": "컴퓨터네트워크",
                        "department": "모바일시스템공학과",
                    },
                )
                status_with, body_with = server.post_json(
                    "/api/chat",
                    {
                        "query": "컴퓨터네트워크",
                        "department": "모바일시스템공학과",
                        "course_id": "computer-network",
                    },
                )

        self.assertEqual(status_without, 200)
        self.assertEqual(body_without["sources"], [])
        self.assertEqual(status_with, 200)
        self.assertEqual(body_with["sources"][0]["course_id"], "computer-network")

    def test_api_chat_source_card_fields_are_present(self):
        required = {
            "notice_id",
            "title",
            "publisher",
            "department",
            "category",
            "published_at",
            "deadline_at",
            "original_url",
            "matched_text",
        }
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            prepare_seed_db(db_path)
            with TestServer(db_path) as server:
                status, body = server.post_json(
                    "/api/chat",
                    {
                        "query": "장학금 신청 공지 있어?",
                        "department": "모바일시스템공학과",
                    },
                )

        self.assertEqual(status, 200)
        self.assertTrue(required.issubset(set(body["sources"][0].keys())))

    def test_api_ingestion_status_returns_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            prepare_seed_db(db_path)
            with TestServer(db_path) as server:
                status, body = server.get_json("/api/ingestion/status")

        self.assertEqual(status, 200)
        self.assertIn("counts", body)
        self.assertIn("embeddings", body)
        self.assertIn("attachments", body)
        self.assertIn("recent_runs", body)
        self.assertIn("summary", body)
        self.assertIn("ocr_health", body)

    def test_api_notice_detail_returns_notice_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            prepare_seed_db(db_path)
            with connect(db_path) as conn:
                notice_id = conn.execute("SELECT id FROM notices LIMIT 1").fetchone()["id"]
            with TestServer(db_path) as server:
                status, body = server.get_json(f"/api/notice?id={notice_id}")

        self.assertEqual(status, 200)
        self.assertEqual(body["notice"]["id"], notice_id)
        self.assertIn("attachments", body["notice"])
        self.assertIn("media", body["notice"])
        self.assertIn("chunks", body["notice"])
        self.assertIn("related_actions", body["notice"])

    def test_api_admin_embed_returns_embedding_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            prepare_seed_db(db_path)
            with patch(
                "campus_notice_ai.server.embed_notice_chunks",
                return_value={
                    "embedded": 2,
                    "total_selected": 2,
                    "model": "fake-embedding",
                    "dimensions": 2,
                },
            ):
                with TestServer(db_path) as server:
                    status, body = server.post_json("/api/admin/embed", {"batch_size": 2})

        self.assertEqual(status, 200)
        self.assertEqual(body["embedded"], 2)
        self.assertEqual(body["model"], "fake-embedding")

    def test_api_notice_image_attachment_is_stored_as_media_with_ocr_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            with (
                patch("campus_notice_ai.server.download_attachment_bytes", return_value=b"fake-image"),
                patch(
                    "campus_notice_ai.media.cache_image_file",
                    return_value=("/media_cache/poster.png", "/media_cache/poster.thumb.png"),
                ),
                patch(
                    "campus_notice_ai.media.extract_image_ocr_text",
                    return_value=(None, "failed", "OCR failed"),
                ),
            ):
                with TestServer(db_path) as server:
                    status, body = server.post_json(
                        "/api/notices",
                        {
                            "title": "Image attachment notice",
                            "body_text": "See image attachment.",
                            "original_url": "manual://image-attachment-notice",
                            "attachments": [
                                {
                                    "file_name": "poster.png",
                                    "file_url": "https://example.test/poster.png",
                                    "file_type": "png",
                                }
                            ],
                        },
                    )

            with connect(db_path) as conn:
                media = conn.execute("SELECT * FROM notice_media").fetchone()
                attachment_count = conn.execute("SELECT COUNT(*) FROM notice_attachments").fetchone()[0]

        self.assertEqual(status, 201)
        self.assertEqual(body["attachments"], 0)
        self.assertEqual(body["media"], 1)
        self.assertEqual(body["parsed_media"], 0)
        self.assertEqual(attachment_count, 0)
        self.assertEqual(media["file_name"], "poster.png")
        self.assertEqual(media["download_status"], "downloaded")
        self.assertEqual(media["parse_status"], "failed")
        self.assertEqual(media["thumbnail_path"], "/media_cache/poster.thumb.png")
        self.assertIn("OCR failed", media["error_message"])


if __name__ == "__main__":
    unittest.main()
