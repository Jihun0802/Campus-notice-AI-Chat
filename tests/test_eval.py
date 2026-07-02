import tempfile
import unittest
from pathlib import Path

from campus_notice_ai.db import connect, init_db
from campus_notice_ai.eval import load_eval_questions, run_rag_eval
from campus_notice_ai.notice_repository import reindex_all_notices, seed_notices


class EvalTests(unittest.TestCase):
    def test_load_eval_questions_reads_project_file(self):
        questions = load_eval_questions()

        self.assertGreaterEqual(len(questions), 30)
        self.assertIn("id", questions[0])
        self.assertIn("query", questions[0])

    def test_run_rag_eval_executes_minimal_questions(self):
        with tempfile.TemporaryDirectory() as tmp:
            with connect(Path(tmp) / "test.sqlite3") as conn:
                init_db(conn)
                seed_notices(conn)
                reindex_all_notices(conn)
                result = run_rag_eval(
                    conn,
                    [
                        {
                            "id": "grad_exam",
                            "query": "졸업시험 신청",
                            "user_context": {
                                "department": "모바일시스템공학과",
                                "grade": "4",
                                "course_id": "",
                            },
                            "expected": {
                                "must_include_keywords": ["졸업시험"],
                                "preferred_chunk_types": ["body"],
                            },
                        }
                    ],
                )

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["passed"], 1)


if __name__ == "__main__":
    unittest.main()
