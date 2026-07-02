from __future__ import annotations

import re
import zlib
from dataclasses import dataclass
from html import unescape
from io import BytesIO
from typing import Literal
from urllib.parse import unquote
from urllib.request import Request, urlopen

from campus_notice_ai.chunking import normalize_text
from campus_notice_ai.crawler import USER_AGENT


DOWNLOAD_STATUSES = {"pending", "downloaded", "skipped", "failed"}
PARSE_STATUSES = {"pending", "parsed", "unsupported", "empty", "failed"}
SUPPORTED_PARSE_TYPES = {"pdf"}
MAX_ATTACHMENT_BYTES = 8 * 1024 * 1024

DownloadStatus = Literal["pending", "downloaded", "skipped", "failed"]
ParseStatus = Literal["pending", "parsed", "unsupported", "empty", "failed"]


@dataclass(frozen=True)
class ParsedAttachment:
    file_type: str | None
    download_status: DownloadStatus
    parse_status: ParseStatus
    extracted_text: str | None = None
    error_message: str | None = None


def guess_file_type(file_name: str | None, file_url: str | None = None) -> str | None:
    source = f"{file_name or ''} {file_url or ''}".lower()
    for extension in (
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
    ):
        if extension in source:
            return extension.lstrip(".")
    return None


def clean_file_name(file_name: str | None, file_url: str | None = None) -> str:
    if file_name:
        return normalize_text(unescape(file_name))
    if file_url:
        clean_url = file_url.split("?", 1)[0].split("#", 1)[0].rstrip("/")
        name = unquote(clean_url.rsplit("/", 1)[-1])
        if name:
            return normalize_text(unescape(name))
    return "attachment"


def download_attachment_bytes(url: str, *, max_bytes: int = MAX_ATTACHMENT_BYTES) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = response.read(64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise ValueError(f"attachment exceeds {max_bytes} bytes")
            chunks.append(chunk)
    return b"".join(chunks)


def decode_pdf_text_bytes(raw: bytes) -> str:
    if raw.startswith(b"\xfe\xff"):
        return raw[2:].decode("utf-16-be", errors="replace")
    if raw.startswith(b"\xff\xfe"):
        return raw[2:].decode("utf-16-le", errors="replace")
    for encoding in ("utf-8", "cp949", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def extract_literal_strings(data: bytes) -> list[bytes]:
    strings: list[bytes] = []
    index = 0
    while index < len(data):
        if data[index] != ord("("):
            index += 1
            continue
        index += 1
        depth = 1
        buffer = bytearray()
        while index < len(data) and depth > 0:
            byte = data[index]
            index += 1
            if byte == ord("\\") and index < len(data):
                escaped = data[index]
                index += 1
                if escaped in b"nrtbf":
                    buffer.append(
                        {
                            ord("n"): ord("\n"),
                            ord("r"): ord("\r"),
                            ord("t"): ord("\t"),
                            ord("b"): ord("\b"),
                            ord("f"): ord("\f"),
                        }[escaped]
                    )
                elif escaped in b"()\\":
                    buffer.append(escaped)
                elif ord("0") <= escaped <= ord("7"):
                    octal = bytes([escaped])
                    for _ in range(2):
                        if index < len(data) and ord("0") <= data[index] <= ord("7"):
                            octal += bytes([data[index]])
                            index += 1
                    buffer.append(int(octal, 8))
                else:
                    buffer.append(escaped)
                continue
            if byte == ord("("):
                depth += 1
                buffer.append(byte)
                continue
            if byte == ord(")"):
                depth -= 1
                if depth:
                    buffer.append(byte)
                continue
            buffer.append(byte)
        strings.append(bytes(buffer))
    return strings


def extract_hex_strings(data: bytes) -> list[bytes]:
    strings: list[bytes] = []
    for match in re.finditer(rb"(?<!<)<([0-9A-Fa-f\s]+)>(?!>)", data):
        raw_hex = re.sub(rb"\s+", b"", match.group(1))
        if len(raw_hex) < 2:
            continue
        if len(raw_hex) % 2:
            raw_hex += b"0"
        try:
            strings.append(bytes.fromhex(raw_hex.decode("ascii")))
        except ValueError:
            continue
    return strings


def iter_pdf_streams(data: bytes) -> list[bytes]:
    streams: list[bytes] = []
    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, flags=re.S):
        payload = match.group(1).strip(b"\r\n")
        if not payload:
            continue
        try:
            streams.append(zlib.decompress(payload))
        except zlib.error:
            streams.append(payload)
    return streams or [data]


def extract_pdf_text(data: bytes) -> str:
    pypdf_text = extract_pdf_text_with_pypdf(data)
    if pypdf_text:
        return pypdf_text

    parts: list[str] = []
    for stream in iter_pdf_streams(data):
        for raw_text in extract_literal_strings(stream) + extract_hex_strings(stream):
            text = decode_pdf_text_bytes(raw_text)
            if text.strip():
                parts.append(text)
    return normalize_text(" ".join(parts))


def extract_pdf_text_with_pypdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""

    try:
        reader = PdfReader(BytesIO(data))
        parts = [page.extract_text() or "" for page in reader.pages]
    except Exception:
        return ""
    return normalize_text("\n\n".join(part for part in parts if part.strip()))


def parse_attachment_text(file_name: str, file_url: str | None, data: bytes) -> ParsedAttachment:
    file_type = guess_file_type(file_name, file_url)
    if file_type not in SUPPORTED_PARSE_TYPES:
        return ParsedAttachment(
            file_type=file_type,
            download_status="skipped",
            parse_status="unsupported",
        )

    if file_type == "pdf":
        text = extract_pdf_text(data)
        if not text:
            return ParsedAttachment(
                file_type=file_type,
                download_status="downloaded",
                parse_status="empty",
            )
        return ParsedAttachment(
            file_type=file_type,
            download_status="downloaded",
            parse_status="parsed",
            extracted_text=text,
        )

    return ParsedAttachment(
        file_type=file_type,
        download_status="skipped",
        parse_status="unsupported",
    )
