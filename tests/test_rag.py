import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from campus_notice_ai.db import connect, init_db
from campus_notice_ai.embeddings import serialize_embedding
from campus_notice_ai.notice_repository import (
    reindex_all_notices,
    reindex_notice,
    seed_notices,
    upsert_notice,
    upsert_notice_attachment,
    upsert_notice_media,
    upsert_notice_source,
)
from campus_notice_ai.rag import FallbackLLMProvider, OpenAICompatibleProvider, answer_question, load_prompt


def prepare_conn(path: Path):
    conn = connect(path)
    init_db(conn)
    seed_notices(conn)
    reindex_all_notices(conn)
    return conn


class RagTests(unittest.TestCase):
    def test_fallback_provider_is_available_without_api_key(self):
        provider = FallbackLLMProvider()

        self.assertTrue(provider.is_available())

    def test_answer_question_uses_fallback_without_api_key(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.dict(os.environ, {"OPENAI_API_KEY": ""}),
            patch("campus_notice_ai.rag.load_dotenv", return_value={}),
        ):
            with prepare_conn(Path(tmp) / "test.sqlite3") as conn:
                response = answer_question(
                    conn,
                    "졸업시험 신청 언제까지야?",
                    department="모바일시스템공학과",
                    grade="4",
                )

        self.assertEqual(response["mode"], "fallback")
        self.assertGreaterEqual(len(response["sources"]), 1)
        self.assertEqual(response["confidence"], "high")

    def test_answer_question_no_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            with prepare_conn(Path(tmp) / "test.sqlite3") as conn:
                response = answer_question(conn, "존재하지않는특수공지키워드")

        self.assertEqual(response["sources"], [])
        self.assertEqual(response["confidence"], "low")
        self.assertIn("관련 공지를 찾지 못했습니다", response["answer"])

    def test_answer_question_can_ground_answer_in_pdf_attachment_chunk(self):
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
                    title="첨부파일 제출 안내",
                    body_text="상세 요건은 첨부파일을 확인하세요.",
                    original_url="manual://pdf-notice",
                    visibility="public",
                )
                attachment_id = upsert_notice_attachment(
                    conn,
                    notice_id=notice_id,
                    file_name="requirements.pdf",
                    file_url="https://example.test/requirements.pdf",
                    file_type="pdf",
                    extracted_text="Portfolio submission deadline is 2026-07-15.",
                    download_status="downloaded",
                    parse_status="parsed",
                )
                reindex_notice(conn, notice_id)
                for row in conn.execute(
                    "SELECT id, attachment_id FROM notice_chunks WHERE notice_id = ?",
                    (notice_id,),
                ).fetchall():
                    vector = [1.0, 0.0] if row["attachment_id"] == attachment_id else [0.0, 1.0]
                    conn.execute(
                        "UPDATE notice_chunks SET embedding = ? WHERE id = ?",
                        (serialize_embedding(vector), row["id"]),
                    )
                conn.commit()

                with patch("campus_notice_ai.rag.create_query_embedding_for_search", return_value=[1.0, 0.0]):
                    response = answer_question(
                        conn,
                        "portfolio requirements",
                        provider=FallbackLLMProvider(),
                    )

        self.assertEqual(response["sources"][0]["attachment_id"], attachment_id)
        self.assertEqual(response["sources"][0]["attachment_file_name"], "requirements.pdf")
        self.assertEqual(response["sources"][0]["retrieval_mode"], "hybrid")
        self.assertIn("Portfolio submission deadline", response["sources"][0]["matched_text"])

    def test_answer_question_exposes_image_source_card_fields(self):
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
                    title="이미지 포스터 안내",
                    body_text="포스터 이미지를 확인하세요.",
                    original_url="manual://image-rag-notice",
                    visibility="public",
                )
                media_id = upsert_notice_media(
                    conn,
                    notice_id=notice_id,
                    file_name="poster.png",
                    original_url="https://example.test/poster.png",
                    file_type="png",
                    alt_text="행사 포스터",
                    local_path="/media_cache/poster.png",
                    thumbnail_path="/media_cache/poster.thumb.png",
                    ocr_text="Poster booth deadline is 2026-07-22.",
                    download_status="downloaded",
                    parse_status="parsed",
                )
                reindex_notice(conn, notice_id)
                conn.execute(
                    "UPDATE notice_chunks SET embedding = ? WHERE media_id = ?",
                    (serialize_embedding([1.0, 0.0]), media_id),
                )
                conn.execute(
                    "UPDATE notice_chunks SET embedding = ? WHERE media_id IS NULL",
                    (serialize_embedding([0.0, 1.0]),),
                )
                conn.commit()

                with patch("campus_notice_ai.rag.create_query_embedding_for_search", return_value=[1.0, 0.0]):
                    response = answer_question(
                        conn,
                        "poster booth deadline",
                        provider=FallbackLLMProvider(),
                    )

        source = response["sources"][0]
        self.assertEqual(source["chunk_type"], "image_ocr")
        self.assertEqual(source["media_id"], media_id)
        self.assertEqual(source["media_thumbnail_path"], "/media_cache/poster.thumb.png")
        self.assertEqual(source["media_original_url"], "https://example.test/poster.png")
        self.assertIn("Poster booth deadline", source["matched_text"])


    def test_load_prompt_uses_file_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            prompt_path = Path(tmp) / "prompt.md"
            prompt_path.write_text("custom prompt", encoding="utf-8")

            self.assertEqual(load_prompt(prompt_path), "custom prompt")

    def test_load_prompt_uses_default_when_missing(self):
        self.assertEqual(load_prompt(Path("missing-prompt.md"), default="fallback"), "fallback")

    def test_openai_provider_uses_prompt_file_in_payload(self):
        captured = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return None

            def read(self):
                return json.dumps(
                    {"choices": [{"message": {"content": "ok"}}]}
                ).encode("utf-8")

        def fake_urlopen(request, timeout):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse()

        with tempfile.TemporaryDirectory() as tmp, patch("campus_notice_ai.rag.urlopen", side_effect=fake_urlopen):
            prompt_path = Path(tmp) / "prompt.md"
            prompt_path.write_text("custom system prompt", encoding="utf-8")
            provider = OpenAICompatibleProvider(
                api_key="sk-test",
                system_prompt_path=prompt_path,
            )

            answer = provider.generate_answer(
                "question",
                [{"title": "notice", "matched_text": "evidence"}],
                {"department": "test"},
            )

        self.assertEqual(answer, "ok")
        self.assertEqual(captured["payload"]["messages"][0]["content"], "custom system prompt")


if __name__ == "__main__":
    unittest.main()
