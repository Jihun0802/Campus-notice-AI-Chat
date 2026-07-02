import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class FrontendTests(unittest.TestCase):
    def test_student_home_dom_targets_exist(self):
        html = (PROJECT_ROOT / "static" / "index.html").read_text(encoding="utf-8")

        for element_id in (
            "homeMetrics",
            "personalizedFeed",
            "deadlineFeed",
            "newFeed",
            "savedFeed",
            "homeUpdatedAt",
        ):
            self.assertIn(f'id="{element_id}"', html)

    def test_student_home_uses_local_storage_notice_state(self):
        app_js = (PROJECT_ROOT / "static" / "app.js").read_text(encoding="utf-8")

        self.assertIn("campusNoticeAi.readNoticeIds", app_js)
        self.assertIn("campusNoticeAi.savedNoticeIds", app_js)
        self.assertIn("function renderStudentHome", app_js)
        self.assertIn("data-notice-action=\"read\"", app_js)
        self.assertIn("data-notice-action=\"save\"", app_js)
        self.assertIn("visibleForCurrentStudent", app_js)

    def test_source_card_can_render_image_media_data(self):
        app_js = (PROJECT_ROOT / "static" / "app.js").read_text(encoding="utf-8")
        app_css = (PROJECT_ROOT / "static" / "app.css").read_text(encoding="utf-8")

        self.assertIn("function chunkTypeLabel", app_js)
        self.assertIn("image_ocr", app_js)
        self.assertIn("media_thumbnail_path", app_js)
        self.assertIn("media_original_url", app_js)
        self.assertIn("이미지 원본", app_js)
        self.assertIn("function renderNoticeMediaPreview", app_js)
        self.assertIn(".media-preview", app_css)
        self.assertIn(".notice-media-strip", app_css)

    def test_notice_detail_page_and_links_exist(self):
        app_js = (PROJECT_ROOT / "static" / "app.js").read_text(encoding="utf-8")
        detail_html = (PROJECT_ROOT / "static" / "notice-detail.html").read_text(encoding="utf-8")
        detail_js = (PROJECT_ROOT / "static" / "notice-detail.js").read_text(encoding="utf-8")
        app_css = (PROJECT_ROOT / "static" / "app.css").read_text(encoding="utf-8")

        self.assertIn("noticeDetailUrl", app_js)
        self.assertIn("notice-detail.html?id=", app_js)
        self.assertIn("detailBody", detail_html)
        self.assertIn("attachmentList", detail_html)
        self.assertIn("mediaGallery", detail_html)
        self.assertIn("/api/notice?id=", detail_js)
        self.assertIn("campusNoticeAi.readNoticeIds", detail_js)
        self.assertIn(".detail-layout", app_css)

    def test_admin_status_details_are_rendered(self):
        html = (PROJECT_ROOT / "static" / "index.html").read_text(encoding="utf-8")
        app_js = (PROJECT_ROOT / "static" / "app.js").read_text(encoding="utf-8")

        self.assertIn('id="adminStatusDetails"', html)
        self.assertIn("failure_logs", app_js)
        self.assertIn("ocr_health", app_js)
        self.assertIn("Source 상태", app_js)


if __name__ == "__main__":
    unittest.main()
