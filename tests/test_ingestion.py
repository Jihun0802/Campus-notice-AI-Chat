import tempfile
import unittest
from pathlib import Path

from campus_notice_ai.db import connect, init_db
from campus_notice_ai.notice_repository import (
    get_notice_detail,
    get_ingestion_status,
    list_notices,
    record_ingestion_log,
    reindex_notice,
    upsert_notice,
    upsert_notice_attachment,
    upsert_notice_media,
    upsert_notice_source,
)
from campus_notice_ai.search import search_chunks


class IngestionTests(unittest.TestCase):
    def test_reindex_includes_attachment_text_chunks(self):
        with tempfile.TemporaryDirectory() as tmp:
            with connect(Path(tmp) / "test.sqlite3") as conn:
                init_db(conn)
                source_id = upsert_notice_source(
                    conn,
                    name="Manual source",
                    source_type="manual",
                    base_url="manual://source",
                )
                notice_id = upsert_notice(
                    conn,
                    source_id=source_id,
                    title="Test notice",
                    body_text="Body only.",
                    original_url="manual://notice",
                )
                attachment_id = upsert_notice_attachment(
                    conn,
                    notice_id=notice_id,
                    file_name="guide.pdf",
                    file_url="https://example.test/guide.pdf",
                    file_type="pdf",
                    extracted_text="Final deadline is 2026-07-03.",
                    download_status="downloaded",
                    parse_status="parsed",
                )
                conn.commit()

                chunk_count = reindex_notice(conn, notice_id)
                results = search_chunks(conn, "deadline", limit=3)

                self.assertEqual(chunk_count, 2)
                self.assertEqual(results[0]["metadata"]["attachment_id"], attachment_id)
                self.assertEqual(results[0]["metadata"]["attachment_file_name"], "guide.pdf")

    def test_ingestion_status_counts_attachments(self):
        with tempfile.TemporaryDirectory() as tmp:
            with connect(Path(tmp) / "test.sqlite3") as conn:
                init_db(conn)
                source_id = upsert_notice_source(
                    conn,
                    name="Manual source",
                    source_type="manual",
                    base_url="manual://source",
                )
                notice_id = upsert_notice(
                    conn,
                    source_id=source_id,
                    title="Test notice",
                    body_text="Body only.",
                    original_url="manual://notice",
                )
                upsert_notice_attachment(
                    conn,
                    notice_id=notice_id,
                    file_name="guide.pdf",
                    file_url="https://example.test/guide.pdf",
                    file_type="pdf",
                    extracted_text="Final deadline is 2026-07-03.",
                    download_status="downloaded",
                    parse_status="parsed",
                )
                conn.commit()

                status = get_ingestion_status(conn)

                self.assertEqual(status["counts"]["notice_attachments"], 1)
                self.assertEqual(status["attachments"]["parsed"], 1)
                self.assertEqual(status["attachments"]["pdf_total"], 1)

    def test_reindex_includes_image_ocr_chunks(self):
        with tempfile.TemporaryDirectory() as tmp:
            with connect(Path(tmp) / "test.sqlite3") as conn:
                init_db(conn)
                source_id = upsert_notice_source(
                    conn,
                    name="Manual source",
                    source_type="manual",
                    base_url="manual://source",
                )
                notice_id = upsert_notice(
                    conn,
                    source_id=source_id,
                    title="Image notice",
                    body_text="See poster image.",
                    original_url="manual://image-notice",
                )
                media_id = upsert_notice_media(
                    conn,
                    notice_id=notice_id,
                    file_name="poster.png",
                    original_url="https://example.test/poster.png",
                    file_type="png",
                    local_path="/media_cache/poster.png",
                    thumbnail_path="/media_cache/poster.thumb.png",
                    ocr_text="Booth application deadline is 2026-07-22.",
                    download_status="downloaded",
                    parse_status="parsed",
                )
                conn.commit()

                chunk_count = reindex_notice(conn, notice_id)
                results = search_chunks(conn, "Booth deadline", limit=3)

                self.assertEqual(chunk_count, 2)
                self.assertEqual(results[0]["metadata"]["chunk_type"], "image_ocr")
                self.assertEqual(results[0]["metadata"]["media_id"], media_id)
                self.assertEqual(results[0]["metadata"]["media_thumbnail_path"], "/media_cache/poster.thumb.png")

    def test_ingestion_status_counts_media(self):
        with tempfile.TemporaryDirectory() as tmp:
            with connect(Path(tmp) / "test.sqlite3") as conn:
                init_db(conn)
                source_id = upsert_notice_source(
                    conn,
                    name="Manual source",
                    source_type="manual",
                    base_url="manual://source",
                )
                notice_id = upsert_notice(
                    conn,
                    source_id=source_id,
                    title="Image notice",
                    body_text="See poster image.",
                    original_url="manual://image-notice",
                )
                upsert_notice_media(
                    conn,
                    notice_id=notice_id,
                    file_name="poster.png",
                    original_url="https://example.test/poster.png",
                    file_type="png",
                    parse_status="failed",
                    download_status="downloaded",
                    error_message="OCR failed",
                )
                conn.commit()

                status = get_ingestion_status(conn)

                self.assertEqual(status["counts"]["notice_media"], 1)
                self.assertEqual(status["media"]["image_total"], 1)
                self.assertEqual(status["media"]["failed"], 1)

    def test_list_notices_includes_media_preview_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            with connect(Path(tmp) / "test.sqlite3") as conn:
                init_db(conn)
                source_id = upsert_notice_source(
                    conn,
                    name="Manual source",
                    source_type="manual",
                    base_url="manual://source",
                )
                notice_id = upsert_notice(
                    conn,
                    source_id=source_id,
                    title="Image notice",
                    body_text="See poster image.",
                    original_url="manual://image-notice",
                )
                upsert_notice_media(
                    conn,
                    notice_id=notice_id,
                    file_name="poster.png",
                    original_url="https://example.test/poster.png",
                    file_type="png",
                    thumbnail_path="/media_cache/poster.thumb.png",
                    parse_status="parsed",
                    download_status="downloaded",
                )
                conn.commit()

                notices = list_notices(conn)

        self.assertEqual(notices[0]["media_count"], 1)
        self.assertEqual(notices[0]["media"][0]["thumbnail_path"], "/media_cache/poster.thumb.png")

    def test_notice_detail_includes_attachments_media_and_chunk_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            with connect(Path(tmp) / "test.sqlite3") as conn:
                init_db(conn)
                source_id = upsert_notice_source(
                    conn,
                    name="Manual source",
                    source_type="manual",
                    base_url="manual://source",
                )
                notice_id = upsert_notice(
                    conn,
                    source_id=source_id,
                    title="Detail notice",
                    body_text="Body text for detail.",
                    original_url="manual://detail-notice",
                )
                upsert_notice_attachment(
                    conn,
                    notice_id=notice_id,
                    file_name="guide.pdf",
                    file_url="https://example.test/guide.pdf",
                    file_type="pdf",
                    extracted_text="PDF extracted text for detail preview.",
                    download_status="downloaded",
                    parse_status="parsed",
                )
                upsert_notice_media(
                    conn,
                    notice_id=notice_id,
                    file_name="poster.png",
                    original_url="https://example.test/poster.png",
                    file_type="png",
                    thumbnail_path="/media_cache/poster.thumb.png",
                    ocr_text="Poster OCR text for detail preview.",
                    parse_status="parsed",
                    download_status="downloaded",
                )
                conn.commit()
                reindex_notice(conn, notice_id)

                detail = get_notice_detail(conn, notice_id)

        self.assertIsNotNone(detail)
        self.assertEqual(detail["id"], notice_id)
        self.assertEqual(len(detail["attachments"]), 1)
        self.assertIn("PDF extracted", detail["attachments"][0]["extracted_text_preview"])
        self.assertEqual(len(detail["media"]), 1)
        self.assertIn("Poster OCR", detail["media"][0]["ocr_text_preview"])
        self.assertEqual(detail["chunks"]["total_chunks"], 3)
        self.assertTrue(detail["related_actions"]["can_reindex"])

    def test_ingestion_status_includes_summary_ocr_health_and_failure_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            with connect(Path(tmp) / "test.sqlite3") as conn:
                init_db(conn)
                source_id = upsert_notice_source(
                    conn,
                    name="Manual source",
                    source_type="manual",
                    base_url="manual://source",
                )
                notice_id = upsert_notice(
                    conn,
                    source_id=source_id,
                    title="Failed media notice",
                    body_text="Body only.",
                    original_url="manual://failed-media",
                )
                record_ingestion_log(
                    conn,
                    source_id="manual-source",
                    notice_id=notice_id,
                    target_type="media",
                    target_id="media-1",
                    step="ocr",
                    status="failed",
                    error_message="OCR failed",
                    retryable=True,
                )
                conn.commit()

                status = get_ingestion_status(conn)

        self.assertIn("summary", status)
        self.assertIn("ocr_health", status)
        self.assertEqual(status["summary"]["total_notices"], 1)
        self.assertEqual(status["summary"]["failure_logs"], 1)
        self.assertEqual(status["failure_logs"][0]["error_message"], "OCR failed")


if __name__ == "__main__":
    unittest.main()
