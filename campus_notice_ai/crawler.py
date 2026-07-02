from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

from campus_notice_ai.chunking import normalize_text
from campus_notice_ai.config import SOURCES_CONFIG_PATH
from campus_notice_ai.media import guess_image_file_type, is_image_file_type


USER_AGENT = "CampusNoticeAI-MVP/0.1 (+local development)"


@dataclass(frozen=True)
class DkuNoticeSource:
    key: str
    name: str
    source_type: str
    list_url: str
    detail_base_url: str
    department: str | None = None
    default_category: str | None = None
    crawl_limit: int = 3


DEFAULT_DKU_SOURCES = [
    DkuNoticeSource(
        key="school-general",
        name="단국대학교 일반공지",
        source_type="school_notice",
        list_url="https://www.dankook.ac.kr/-390",
        detail_base_url="https://www.dankook.ac.kr/web/kor/-390",
    ),
    DkuNoticeSource(
        key="mobile-systems",
        name="단국대학교 모바일시스템공학과 학과공지",
        source_type="department_notice",
        list_url="https://cms.dankook.ac.kr/web/mobilesystems/-8",
        detail_base_url="https://cms.dankook.ac.kr/web/mobilesystems/-8",
        department="모바일시스템공학과",
    ),
    DkuNoticeSource(
        key="software",
        name="단국대학교 소프트웨어학과 학과공지",
        source_type="department_notice",
        list_url="https://cms.dankook.ac.kr/web/sw/-1",
        detail_base_url="https://cms.dankook.ac.kr/web/sw/-1",
        department="소프트웨어학과",
    ),
    DkuNoticeSource(
        key="graduate",
        name="단국대학교 대학원 공지사항",
        source_type="school_notice",
        list_url="https://grad.dankook.ac.kr/-22",
        detail_base_url="https://grad.dankook.ac.kr/-22",
        default_category="대학원",
    ),
]


ATTACHMENT_EXTENSIONS = (
    ".pdf",
    ".hwpx",
    ".hwp",
    ".docx",
    ".doc",
    ".xlsx",
    ".xls",
    ".pptx",
    ".ppt",
    ".zip",
)

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp")


def source_from_config(item: dict[str, Any]) -> DkuNoticeSource | None:
    if item.get("enabled", True) is False:
        return None

    list_url = str(item.get("url") or item.get("list_url") or "").strip()
    if not list_url:
        raise ValueError("source url is required")

    return DkuNoticeSource(
        key=str(item.get("source_id") or item.get("key") or list_url),
        name=str(item.get("name") or item.get("source_id") or list_url),
        source_type=str(item.get("source_type") or "school_notice"),
        list_url=list_url,
        detail_base_url=str(item.get("detail_base_url") or list_url),
        department=item.get("department") or None,
        default_category=item.get("category") or item.get("default_category") or None,
        crawl_limit=int(item.get("crawl_limit") or 3),
    )


def load_dku_sources(config_path: Path | None = None) -> list[DkuNoticeSource]:
    path = config_path or SOURCES_CONFIG_PATH
    if not path.exists():
        return list(DEFAULT_DKU_SOURCES)

    with path.open("r", encoding="utf-8") as file:
        raw_sources = json.load(file)
    if not isinstance(raw_sources, list):
        raise ValueError("sources config must be a list")

    sources = [
        source
        for item in raw_sources
        if isinstance(item, dict)
        for source in [source_from_config(item)]
        if source is not None
    ]
    return sources or list(DEFAULT_DKU_SOURCES)


def fetch_html(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=25) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def strip_tags(html: str) -> str:
    text = re.sub(r"<script\b.*?</script>", " ", html, flags=re.I | re.S)
    text = re.sub(r"<style\b.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return normalize_text(unescape(text))


def normalize_date(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"(\d{4})[.\-/]\s*(\d{1,2})[.\-/]\s*(\d{1,2})", value)
    if not match:
        return None
    year, month, day = match.groups()
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def build_detail_url(source: DkuNoticeSource, message_id: str) -> str:
    query = {
        "p_p_id": "dku_bbs_web_BbsPortlet",
        "p_p_lifecycle": "0",
        "p_p_state": "normal",
        "p_p_mode": "view",
        "_dku_bbs_web_BbsPortlet_cur": "1",
        "_dku_bbs_web_BbsPortlet_action": "view_message",
        "_dku_bbs_web_BbsPortlet_orderBy": "createDate",
        "_dku_bbs_web_BbsPortlet_bbsMessageId": message_id,
    }
    return f"{source.detail_base_url}?{urlencode(query)}"


def split_list_items(html: str) -> list[str]:
    match = re.search(r'<div[^>]+class="[^"]*dku-list-body-inner\s+notice[^"]*"[^>]*>', html, re.I)
    if not match:
        return []
    body = html[match.end() :]
    end_match = re.search(r'<div[^>]+class="[^"]*dku-list-footer', body, re.I)
    if end_match:
        body = body[: end_match.start()]
    return re.findall(
        r'<div[^>]+class="[^"]*dku-list-body-item(?!-col)[^"]*"[^>]*>.*?(?=<div[^>]+class="[^"]*dku-list-body-item(?!-col)|\Z)',
        body,
        flags=re.I | re.S,
    )


def parse_list_items(html: str, source: DkuNoticeSource, limit: int) -> list[dict[str, str | None]]:
    items: list[dict[str, str | None]] = []
    for block in split_list_items(html):
        if "header" in block:
            continue
        message_match = re.search(r"_dku_bbs_web_BbsPortlet_viewMessage\((\d+)", block)
        if not message_match:
            continue

        message_id = message_match.group(1)
        title_match = re.search(r'<a[^>]+title="([^"]+)"[^>]*>(.*?)</a>', block, re.S | re.I)
        title = strip_tags(title_match.group(1) if title_match else block)
        if not title:
            continue

        category_match = re.search(r'<span[^>]+class="[^"]*category[^"]*"[^>]*>(.*?)</span>', block, re.S | re.I)
        category = strip_tags(category_match.group(1)) if category_match else source.default_category

        cells = re.findall(
            r'<div[^>]+class="[^"]*dku-list-body-item-col(?![^"]*item-title)[^"]*"[^>]*>(.*?)</div>',
            block,
            flags=re.I | re.S,
        )
        cell_texts = [strip_tags(cell) for cell in cells]
        dates = [normalize_date(text) for text in cell_texts]
        published_at = next((date for date in dates if date), None)
        publisher = None
        if len(cell_texts) >= 3:
            candidate = cell_texts[1]
            if candidate and not candidate.isdigit() and not normalize_date(candidate):
                publisher = candidate

        items.append(
            {
                "message_id": message_id,
                "title": title,
                "category": category,
                "publisher": publisher,
                "published_at": published_at,
                "original_url": build_detail_url(source, message_id),
            }
        )
        if len(items) >= limit:
            break
    return items


class ContentCellParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._capturing = False
        self._td_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        class_name = attrs_dict.get("class") or ""
        if tag.lower() == "td" and "r_cont" in class_name:
            self._capturing = True
            self._td_depth = 1
            return
        if self._capturing and tag.lower() == "td":
            self._td_depth += 1
        if self._capturing and tag.lower() in {"br", "p", "tr", "li"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if not self._capturing:
            return
        if tag.lower() in {"p", "tr", "li", "table"}:
            self.parts.append("\n")
        if tag.lower() == "td":
            self._td_depth -= 1
            if self._td_depth <= 0:
                self._capturing = False

    def handle_data(self, data: str) -> None:
        if self._capturing:
            self.parts.append(data)

    def text(self) -> str:
        return normalize_text(unescape(" ".join(self.parts)))


def parse_detail_body(html: str) -> str:
    parser = ContentCellParser()
    parser.feed(html)
    return parser.text()


class AttachmentLinkParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self._active_link: dict[str, str] | None = None
        self._active_text: list[str] = []
        self.attachments: list[dict[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attrs_dict = dict(attrs)
        href = attrs_dict.get("href") or ""
        if not href:
            return
        absolute_url = urljoin(self.base_url, unescape(href))
        if not looks_like_attachment_url(absolute_url):
            return
        self._active_link = {
            "file_url": absolute_url,
            "title": attrs_dict.get("title") or "",
            "download": attrs_dict.get("download") or "",
        }
        self._active_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or not self._active_link:
            return
        text = normalize_text(unescape(" ".join(self._active_text)))
        file_name = (
            text
            or self._active_link.get("title")
            or self._active_link.get("download")
            or guess_file_name_from_url(self._active_link["file_url"])
        )
        self.attachments.append(
            {
                "file_name": file_name,
                "file_url": self._active_link["file_url"],
                "file_type": guess_file_type(file_name, self._active_link["file_url"]),
            }
        )
        self._active_link = None
        self._active_text = []

    def handle_data(self, data: str) -> None:
        if self._active_link:
            self._active_text.append(data)


class ImageMediaParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.media: list[dict[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        tag_name = tag.lower()
        if tag_name == "img":
            src = attrs_dict.get("src") or attrs_dict.get("data-src") or ""
            if not src:
                return
            image_url = urljoin(self.base_url, unescape(src))
            file_name = (
                attrs_dict.get("alt")
                or attrs_dict.get("title")
                or guess_file_name_from_url(image_url)
            )
            self.media.append(
                {
                    "file_name": file_name,
                    "original_url": image_url,
                    "file_type": guess_image_file_type(file_name, image_url),
                    "alt_text": attrs_dict.get("alt") or None,
                    "caption": attrs_dict.get("title") or None,
                    "source": "body_image",
                }
            )
            return

        if tag_name != "a":
            return
        href = attrs_dict.get("href") or ""
        if not href:
            return
        image_url = urljoin(self.base_url, unescape(href))
        file_type = guess_image_file_type(attrs_dict.get("download"), image_url)
        if not is_image_file_type(file_type):
            return
        file_name = (
            attrs_dict.get("title")
            or attrs_dict.get("download")
            or guess_file_name_from_url(image_url)
        )
        self.media.append(
            {
                "file_name": file_name,
                "original_url": image_url,
                "file_type": file_type,
                "alt_text": None,
                "caption": attrs_dict.get("title") or None,
                "source": "image_attachment",
            }
        )


def guess_file_name_from_url(url: str) -> str:
    clean_url = url.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    name = clean_url.rsplit("/", 1)[-1]
    return unescape(name) or "attachment"


def guess_file_type(file_name: str | None, file_url: str | None = None) -> str | None:
    source = f"{file_name or ''} {file_url or ''}".lower()
    for extension in ATTACHMENT_EXTENSIONS:
        if extension in source:
            return extension.lstrip(".")
    return None


def looks_like_attachment_url(url: str) -> bool:
    lowered = url.lower()
    if any(extension in lowered for extension in IMAGE_EXTENSIONS):
        return False
    if "/documents/" in lowered or "fileentryid" in lowered:
        return True
    return any(extension in lowered for extension in ATTACHMENT_EXTENSIONS)


def deduplicate_attachments(attachments: list[dict[str, str | None]]) -> list[dict[str, str | None]]:
    seen: set[str] = set()
    unique: list[dict[str, str | None]] = []
    for attachment in attachments:
        key = attachment.get("file_url") or attachment.get("file_name") or ""
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(attachment)
    return unique


def deduplicate_media(media_items: list[dict[str, str | None]]) -> list[dict[str, str | None]]:
    seen: set[str] = set()
    unique: list[dict[str, str | None]] = []
    for media in media_items:
        key = media.get("original_url") or media.get("file_name") or ""
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(media)
    return unique


def parse_detail_attachments(html: str, base_url: str) -> list[dict[str, str | None]]:
    parser = AttachmentLinkParser(base_url)
    parser.feed(html)
    return deduplicate_attachments(parser.attachments)


def parse_detail_media(html: str, base_url: str) -> list[dict[str, str | None]]:
    parser = ImageMediaParser(base_url)
    parser.feed(html)
    return deduplicate_media(parser.media)


def crawl_dku_source(source: DkuNoticeSource, *, limit: int = 5, delay_seconds: float = 0.25) -> list[dict[str, Any]]:
    list_html = fetch_html(source.list_url)
    list_items = parse_list_items(list_html, source, limit=limit)
    notices: list[dict[str, Any]] = []

    for item in list_items:
        attachments: list[dict[str, str | None]] = []
        media: list[dict[str, str | None]] = []
        try:
            detail_html = fetch_html(str(item["original_url"]))
            body_text = parse_detail_body(detail_html)
            attachments = parse_detail_attachments(detail_html, str(item["original_url"]))
            media = parse_detail_media(detail_html, str(item["original_url"]))
        except Exception as exc:  # Network/HTML drift fallback keeps MVP usable.
            body_text = f"{item['title']}\n\n상세 본문 수집 실패: {exc}"

        notices.append(
            {
                "title": item["title"],
                "body_text": body_text or str(item["title"]),
                "original_url": item["original_url"],
                "publisher": item["publisher"],
                "category": item["category"] or source.default_category,
                "department": source.department,
                "grade": None,
                "course_id": None,
                "visibility": "public" if source.department is None else "department",
                "published_at": item["published_at"],
                "deadline_at": None,
                "source_name": source.name,
                "source_type": source.source_type,
                "source_base_url": source.list_url,
                "source_department": source.department,
                "attachments": attachments,
                "media": media,
            }
        )
        if delay_seconds > 0:
            time.sleep(delay_seconds)

    return notices


def iter_sources(source_keys: Iterable[str] | None = None) -> list[DkuNoticeSource]:
    sources = load_dku_sources()
    if not source_keys:
        return sources
    wanted = set(source_keys)
    return [source for source in sources if source.key in wanted]
