from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Iterable


DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 150


@dataclass(frozen=True)
class TextChunk:
    text: str
    index: int


def normalize_text(text: str) -> str:
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]
    normalized_lines: list[str] = []
    previous_blank = False

    for line in lines:
        is_blank = line.strip() == ""
        if is_blank and previous_blank:
            continue
        normalized_lines.append(line)
        previous_blank = is_blank

    return "\n".join(normalized_lines).strip()


def build_notice_document(title: str, body_text: str) -> str:
    return normalize_text(f"{title}\n\n{body_text}")


def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[TextChunk]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0")
    if overlap < 0:
        raise ValueError("overlap must be greater than or equal to 0")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    normalized = normalize_text(text)
    if not normalized:
        return []

    chunks: list[TextChunk] = []
    start = 0
    text_length = len(normalized)

    while start < text_length:
        end = min(start + chunk_size, text_length)
        chunk_body = normalized[start:end].strip()
        if chunk_body:
            chunks.append(TextChunk(text=chunk_body, index=len(chunks)))
        if end >= text_length:
            break
        start = end - overlap

    return chunks


def stable_chunk_id(notice_id: str, attachment_id: str | None, chunk: TextChunk) -> str:
    source = attachment_id or "body"
    digest = sha256(chunk.text.encode("utf-8")).hexdigest()[:16]
    return f"chunk_{notice_id}_{source}_{chunk.index}_{digest}"


def iter_chunks(
    texts: Iterable[str],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[TextChunk]:
    document = normalize_text("\n\n".join(texts))
    return chunk_text(document, chunk_size=chunk_size, overlap=overlap)
