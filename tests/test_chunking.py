import unittest

from campus_notice_ai.chunking import build_notice_document, chunk_text, iter_chunks


class ChunkingTests(unittest.TestCase):
    def test_short_text_creates_one_chunk(self):
        chunks = chunk_text("짧은 공지입니다.", chunk_size=1000, overlap=150)

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].index, 0)
        self.assertEqual(chunks[0].text, "짧은 공지입니다.")

    def test_long_text_uses_size_and_overlap(self):
        text = "".join(str(i % 10) for i in range(2500))
        chunks = chunk_text(text, chunk_size=1000, overlap=150)

        self.assertEqual(len(chunks), 3)
        self.assertTrue(all(len(chunk.text) <= 1000 for chunk in chunks))
        self.assertEqual(chunks[0].text[-150:], chunks[1].text[:150])
        self.assertEqual(chunks[1].text[-150:], chunks[2].text[:150])

    def test_overlap_must_be_smaller_than_chunk_size(self):
        with self.assertRaises(ValueError):
            chunk_text("test", chunk_size=100, overlap=100)

    def test_notice_document_combines_title_and_body(self):
        document = build_notice_document("제목", "본문")

        self.assertEqual(document, "제목\n\n본문")

    def test_iter_chunks_combines_multiple_texts(self):
        chunks = iter_chunks(["제목", "본문"], chunk_size=1000, overlap=150)

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].text, "제목\n\n본문")


if __name__ == "__main__":
    unittest.main()
