import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from campus_notice_ai.db import connect, init_db
from campus_notice_ai.embeddings import (
    OpenAIEmbeddingProvider,
    cosine_similarity,
    embed_notice_chunks,
    parse_embedding,
    parse_embedding_dimensions,
    serialize_embedding,
)
from campus_notice_ai.notice_repository import reindex_notice, upsert_notice, upsert_notice_source


class EmbeddingTests(unittest.TestCase):
    def test_parse_embedding_dimensions(self):
        self.assertEqual(parse_embedding_dimensions("1536"), 1536)
        self.assertIsNone(parse_embedding_dimensions(""))
        with self.assertRaises(ValueError):
            parse_embedding_dimensions("0")

    def test_embedding_serialization_roundtrip(self):
        self.assertEqual(parse_embedding(serialize_embedding([1.0, 0.5])), [1.0, 0.5])
        self.assertIsNone(parse_embedding("not-json"))

    def test_cosine_similarity(self):
        self.assertAlmostEqual(cosine_similarity([1.0, 0.0], [1.0, 0.0]), 1.0)
        self.assertAlmostEqual(cosine_similarity([1.0, 0.0], [0.0, 1.0]), 0.0)

    def test_openai_embedding_provider_parses_response(self):
        captured = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return None

            def read(self):
                return json.dumps(
                    {
                        "data": [
                            {"index": 1, "embedding": [0.0, 1.0]},
                            {"index": 0, "embedding": [1.0, 0.0]},
                        ]
                    }
                ).encode("utf-8")

        def fake_urlopen(request, timeout):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse()

        with patch("campus_notice_ai.embeddings.urlopen", side_effect=fake_urlopen):
            provider = OpenAIEmbeddingProvider(
                api_key="sk-test",
                model="text-embedding-3-small",
                dimensions=1536,
            )
            vectors = provider.create_embeddings(["one", "two"])

        self.assertEqual(vectors, [[1.0, 0.0], [0.0, 1.0]])
        self.assertEqual(captured["payload"]["model"], "text-embedding-3-small")
        self.assertEqual(captured["payload"]["dimensions"], 1536)

    def test_embed_notice_chunks_stores_vectors(self):
        class FakeProvider:
            model = "fake-embedding"
            dimensions = 2

            def is_available(self):
                return True

            def create_embeddings(self, texts):
                return [[1.0, 0.0] for _ in texts]

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
                reindex_notice(conn, notice_id)

                result = embed_notice_chunks(conn, provider=FakeProvider())
                row = conn.execute(
                    "SELECT embedding FROM notice_chunks WHERE notice_id = ?",
                    (notice_id,),
                ).fetchone()

        self.assertEqual(result["embedded"], 1)
        self.assertEqual(parse_embedding(row["embedding"]), [1.0, 0.0])


if __name__ == "__main__":
    unittest.main()
