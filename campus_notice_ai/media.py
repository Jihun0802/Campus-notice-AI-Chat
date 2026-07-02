from __future__ import annotations

import base64
import shutil
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from typing import Literal
from urllib.parse import unquote

from campus_notice_ai.chunking import normalize_text
from campus_notice_ai.config import PROJECT_ROOT


IMAGE_FILE_TYPES = {"jpg", "jpeg", "png", "gif", "webp"}
MEDIA_CACHE_DIR = PROJECT_ROOT / "static" / "media_cache"

DownloadStatus = Literal["pending", "downloaded", "skipped", "failed"]
ParseStatus = Literal["pending", "parsed", "unsupported", "empty", "failed"]


@dataclass(frozen=True)
class ProcessedMedia:
    file_name: str
    original_url: str | None
    file_type: str | None
    alt_text: str | None = None
    caption: str | None = None
    local_path: str | None = None
    thumbnail_path: str | None = None
    ocr_text: str | None = None
    summary_text: str | None = None
    download_status: DownloadStatus = "pending"
    parse_status: ParseStatus = "pending"
    summary_status: ParseStatus = "pending"
    error_message: str | None = None


def is_image_file_type(file_type: str | None) -> bool:
    return (file_type or "").lower().lstrip(".") in IMAGE_FILE_TYPES


def guess_image_file_type(file_name: str | None, file_url: str | None = None) -> str | None:
    source = f"{file_name or ''} {file_url or ''}".lower()
    for extension in (".jpeg", ".jpg", ".png", ".gif", ".webp"):
        if extension in source:
            return extension.lstrip(".")
    return None


def clean_media_file_name(file_name: str | None, file_url: str | None = None) -> str:
    if file_name:
        return normalize_text(unescape(file_name))
    if file_url:
        clean_url = file_url.split("?", 1)[0].split("#", 1)[0].rstrip("/")
        name = unquote(clean_url.rsplit("/", 1)[-1])
        if name:
            return normalize_text(unescape(name))
    return "image"


def decode_base64_media(value: str | None) -> bytes | None:
    if not value:
        return None
    return base64.b64decode(value, validate=True)


def cache_image_file(media_id: str, file_type: str | None, data: bytes) -> tuple[str, str]:
    extension = (file_type or "image").lower()
    if extension == "jpeg":
        extension = "jpg"
    MEDIA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    file_path = MEDIA_CACHE_DIR / f"{media_id}.{extension}"
    file_path.write_bytes(data)

    thumbnail_path = create_thumbnail_if_possible(file_path, media_id, extension)
    return to_static_path(file_path), to_static_path(thumbnail_path)


def create_thumbnail_if_possible(file_path: Path, media_id: str, extension: str) -> Path:
    try:
        from PIL import Image
    except ImportError:
        return file_path

    try:
        with Image.open(file_path) as image:
            image.thumbnail((420, 280))
            thumbnail_path = MEDIA_CACHE_DIR / f"{media_id}.thumb.{extension}"
            image.save(thumbnail_path)
            return thumbnail_path
    except Exception:
        return file_path


def to_static_path(path: Path) -> str:
    return "/" + path.relative_to(PROJECT_ROOT / "static").as_posix()


def get_ocr_health() -> dict[str, bool | str]:
    pillow_available = True
    pytesseract_available = True
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        pillow_available = False
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        pytesseract_available = False

    tesseract_available = shutil.which("tesseract") is not None
    provider_available = pillow_available and pytesseract_available and tesseract_available
    if provider_available:
        message = "Local OCR is available."
    elif not pillow_available:
        message = "Pillow is not installed; images can be stored but OCR text will not be generated."
    elif not pytesseract_available:
        message = "pytesseract is not installed; images can be stored but OCR text will not be generated."
    else:
        message = "Tesseract executable is not available; images can be stored but OCR text will not be generated."

    return {
        "ocr_provider_available": provider_available,
        "ocr_provider_name": "pytesseract+tesseract",
        "tesseract_available": tesseract_available,
        "pytesseract_available": pytesseract_available,
        "pillow_available": pillow_available,
        "message": message,
    }


def extract_image_ocr_text(data: bytes) -> tuple[str | None, ParseStatus, str | None]:
    try:
        from PIL import Image
        import pytesseract
    except ImportError:
        return None, "unsupported", "OCR provider is not configured"

    try:
        from io import BytesIO

        with Image.open(BytesIO(data)) as image:
            text = normalize_text(pytesseract.image_to_string(image))
    except Exception as exc:
        return None, "failed", str(exc)[:500]

    if not text:
        return None, "empty", "OCR returned no text"
    return text, "parsed", None


def process_image_media(
    *,
    media_id: str,
    file_name: str | None,
    original_url: str | None,
    file_type: str | None,
    alt_text: str | None = None,
    caption: str | None = None,
    data: bytes | None = None,
    ocr_text: str | None = None,
    summary_text: str | None = None,
) -> ProcessedMedia:
    clean_name = clean_media_file_name(file_name, original_url)
    resolved_type = file_type or guess_image_file_type(clean_name, original_url)
    if not is_image_file_type(resolved_type):
        return ProcessedMedia(
            file_name=clean_name,
            original_url=original_url,
            file_type=resolved_type,
            alt_text=alt_text,
            caption=caption,
            download_status="skipped",
            parse_status="unsupported",
            error_message="media is not a supported image type",
        )

    local_path = None
    thumbnail_path = None
    download_status: DownloadStatus = "pending"
    error_message = None
    if data:
        try:
            local_path, thumbnail_path = cache_image_file(media_id, resolved_type, data)
            download_status = "downloaded"
        except Exception as exc:
            download_status = "failed"
            error_message = str(exc)[:500]
    elif original_url:
        download_status = "skipped"
    else:
        download_status = "failed"
        error_message = "image media has no URL or file content"

    clean_ocr = normalize_text(ocr_text or "")
    if clean_ocr:
        parse_status: ParseStatus = "parsed"
    elif data and download_status == "downloaded":
        clean_ocr, parse_status, ocr_error = extract_image_ocr_text(data)
        if ocr_error:
            error_message = error_message or ocr_error
    else:
        parse_status = "unsupported" if original_url else "failed"
        error_message = error_message or "OCR requires cached image bytes"

    clean_summary = normalize_text(summary_text or "")
    summary_status: ParseStatus = "parsed" if clean_summary else "pending"

    return ProcessedMedia(
        file_name=clean_name,
        original_url=original_url,
        file_type=resolved_type,
        alt_text=normalize_text(alt_text or "") or None,
        caption=normalize_text(caption or "") or None,
        local_path=local_path,
        thumbnail_path=thumbnail_path,
        ocr_text=clean_ocr or None,
        summary_text=clean_summary or None,
        download_status=download_status,
        parse_status=parse_status,
        summary_status=summary_status,
        error_message=error_message,
    )
