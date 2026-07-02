import tempfile
import unittest
from pathlib import Path

from campus_notice_ai.db import connect, init_db
from campus_notice_ai.embeddings import serialize_embedding
from campus_notice_ai.notice_repository import reindex_notice, upsert_notice, upsert_notice_source
from campus_notice_ai.search import score_chunk, search_chunks, tokenize, visible_for_context


class SearchTests(unittest.TestCase):
    def test_tokenize_keeps_korean_terms(self):
        self.assertEqual(tokenize("졸업시험 언제까지 신청해?"), ["졸업시험", "언제까지", "신청해"])

    def test_deadline_bonus_requires_query_match(self):
        score = score_chunk(
            "졸업시험",
            ["졸업시험"],
            "수강신청 안내",
            "수강신청 본문",
            {"deadline_at": "2026-07-03"},
        )

        self.assertEqual(score, 0)

    def test_department_notice_is_visible_to_matching_context(self):
        metadata = {"visibility": "department", "department": "모바일시스템공학과"}

        self.assertTrue(visible_for_context(metadata, department="모바일시스템공학과"))
        self.assertFalse(visible_for_context(metadata, department="소프트웨어학과"))

    def test_course_notice_requires_matching_course_context(self):
        metadata = {
            "visibility": "course",
            "department": "모바일시스템공학과",
            "course_id": "computer-network",
        }

        self.assertTrue(visible_for_context(metadata, course_id="computer-network"))
        self.assertFalse(visible_for_context(metadata, department="모바일시스템공학과"))
        self.assertFalse(visible_for_context(metadata, course_id="capstone-design"))

    def test_search_can_use_embedding_without_keyword_match(self):
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
                    title="Graduation notice",
                    body_text="Final deadline is 2026-07-03.",
                    original_url="manual://notice",
                )
                reindex_notice(conn, notice_id)
                conn.execute(
                    "UPDATE notice_chunks SET embedding = ? WHERE notice_id = ?",
                    (serialize_embedding([1.0, 0.0]), notice_id),
                )
                conn.commit()

                results = search_chunks(conn, "different words", query_embedding=[1.0, 0.0])

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["retrieval_mode"], "hybrid")
        self.assertEqual(results[0]["vector_score"], 1.0)


if __name__ == "__main__":
    unittest.main()
