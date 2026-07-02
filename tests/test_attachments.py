import unittest
import zlib

from campus_notice_ai.attachments import (
    clean_file_name,
    extract_pdf_text,
    guess_file_type,
    parse_attachment_text,
)
from campus_notice_ai.crawler import parse_detail_attachments, parse_detail_media


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


class AttachmentTests(unittest.TestCase):
    def test_guess_file_type_uses_name_or_url(self):
        self.assertEqual(guess_file_type("notice.PDF", None), "pdf")
        self.assertEqual(guess_file_type("form.hwpx", None), "hwpx")
        self.assertEqual(guess_file_type(None, "https://example.test/file.hwp"), "hwp")
        self.assertIsNone(guess_file_type("notice", "https://example.test/file"))

    def test_clean_file_name_falls_back_to_url(self):
        self.assertEqual(
            clean_file_name(None, "https://example.test/files/guide%20file.pdf?download=1"),
            "guide file.pdf",
        )

    def test_extract_pdf_text_reads_compressed_literal_string(self):
        text = extract_pdf_text(make_pdf_stream("Final deadline 2026-07-03"))

        self.assertIn("Final deadline 2026-07-03", text)

    def test_parse_attachment_text_marks_unsupported_types(self):
        parsed = parse_attachment_text("guide.hwp", "https://example.test/guide.hwp", b"")

        self.assertEqual(parsed.download_status, "skipped")
        self.assertEqual(parsed.parse_status, "unsupported")

    def test_parse_detail_attachments_collects_links(self):
        html = """
        <html><body>
          <a href="/documents/guide.pdf">guide.pdf</a>
          <a href="/web/page">regular page</a>
          <a href="files/form.hwp">form.hwp</a>
        </body></html>
        """

        attachments = parse_detail_attachments(html, "https://example.test/notices/1")

        self.assertEqual(len(attachments), 2)
        self.assertEqual(attachments[0]["file_type"], "pdf")
        self.assertEqual(attachments[1]["file_type"], "hwp")

    def test_parse_detail_media_collects_body_and_linked_images(self):
        html = """
        <html><body>
          <img src="/images/poster.png" alt="행사 포스터" title="캡션" />
          <a href="/files/map.jpg" title="오시는 길">map</a>
          <a href="/documents/guide.pdf">guide.pdf</a>
        </body></html>
        """

        media = parse_detail_media(html, "https://example.test/notices/1")
        attachments = parse_detail_attachments(html, "https://example.test/notices/1")

        self.assertEqual(len(media), 2)
        self.assertEqual(media[0]["file_type"], "png")
        self.assertEqual(media[0]["alt_text"], "행사 포스터")
        self.assertEqual(media[1]["file_type"], "jpg")
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0]["file_type"], "pdf")


if __name__ == "__main__":
    unittest.main()
