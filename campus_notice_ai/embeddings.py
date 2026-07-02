from __future__ import annotations

import json
import math
import os
import sqlite3
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from campus_notice_ai.config import load_dotenv


DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_EMBEDDING_BATCH_SIZE = 32


def parse_embedding_dimensions(value: str | None) -> int | None:
    if value in (None, ""):
        return None
    try:
        dimensions = int(value)
    except ValueError as exc:
        raise ValueError("OPENAI_EMBEDDING_DIMENSIONS must be an integer") from exc
    if dimensions <= 0:
        raise ValueError("OPENAI_EMBEDDING_DIMENSIONS must be greater than 0")
    return dimensions


def serialize_embedding(embedding: list[float]) -> str:
    return json.dumps(embedding, separators=(",", ":"))


def parse_embedding(value: str | None) -> list[float] | None:
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, list):
        return None
    try:
        return [float(item) for item in parsed]
    except (TypeError, ValueError):
        return None


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


class OpenAIEmbeddingProvider:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        dimensions: int | None = None,
        timeout_seconds: int = 30,
    ) -> None:
        load_dotenv()
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model or os.getenv("OPENAI_EMBEDDING_MODEL") or DEFAULT_EMBEDDING_MODEL
        self.base_url = (base_url or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        configured_dimensions = dimensions
        if configured_dimensions is None:
            configured_dimensions = parse_embedding_dimensions(os.getenv("OPENAI_EMBEDDING_DIMENSIONS"))
        self.dimensions = configured_dimensions
        self.timeout_seconds = timeout_seconds

    def is_available(self) -> bool:
        return bool(self.api_key)

    def create_embeddings(self, texts: list[str]) -> list[list[float]]:
        clean_texts = [text.replace("\n", " ").strip() for text in texts if text.strip()]
        if not clean_texts:
            return []
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")

        payload: dict[str, Any] = {
            "model": self.model,
            "input": clean_texts,
            "encoding_format": "float",
        }
        if self.dimensions:
            payload["dimensions"] = self.dimensions

        request = Request(
            f"{self.base_url}/embeddings",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"embedding provider request failed: {exc}") from exc

        try:
            items = sorted(data["data"], key=lambda item: int(item["index"]))
            return [[float(value) for value in item["embedding"]] for item in items]
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("embedding provider returned an unexpected response") from exc

    def create_embedding(self, text: str) -> list[float]:
        embeddings = self.create_embeddings([text])
        if not embeddings:
            raise RuntimeError("embedding provider returned no embedding")
        return embeddings[0]


def select_embedding_provider() -> OpenAIEmbeddingProvider:
    return OpenAIEmbeddingProvider()


def stored_embeddings_available(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT 1 FROM notice_chunks WHERE embedding IS NOT NULL LIMIT 1"
    ).fetchone()
    return row is not None


def create_query_embedding_for_search(
    conn: sqlite3.Connection,
    query: str,
    provider: OpenAIEmbeddingProvider | None = None,
) -> list[float] | None:
    if not query.strip() or not stored_embeddings_available(conn):
        return None
    active_provider = provider or select_embedding_provider()
    if not active_provider.is_available():
        return None
    try:
        return active_provider.create_embedding(query)
    except Exception:
        return None


def embed_notice_chunks(
    conn: sqlite3.Connection,
    *,
    provider: OpenAIEmbeddingProvider | None = None,
    batch_size: int = DEFAULT_EMBEDDING_BATCH_SIZE,
    limit: int | None = None,
    force: bool = False,
) -> dict[str, int | str]:
    if batch_size <= 0:
        raise ValueError("batch_size must be greater than 0")
    active_provider = provider or select_embedding_provider()
    if not active_provider.is_available():
        raise RuntimeError("OPENAI_API_KEY is not configured")

    where = "" if force else "WHERE embedding IS NULL"
    params: list[Any] = []
    limit_clause = ""
    if limit is not None:
        if limit <= 0:
            raise ValueError("limit must be greater than 0")
        limit_clause = "LIMIT ?"
        params.append(limit)

    rows = conn.execute(
        f"""
        SELECT id, chunk_text
        FROM notice_chunks
        {where}
        ORDER BY created_at ASC, id ASC
        {limit_clause}
        """,
        params,
    ).fetchall()

    embedded = 0
    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        vectors = active_provider.create_embeddings([row["chunk_text"] for row in batch])
        if len(vectors) != len(batch):
            raise RuntimeError("embedding provider returned a mismatched batch size")
        for row, vector in zip(batch, vectors):
            conn.execute(
                "UPDATE notice_chunks SET embedding = ? WHERE id = ?",
                (serialize_embedding(vector), row["id"]),
            )
            embedded += 1
        conn.commit()

    return {
        "embedded": embedded,
        "total_selected": len(rows),
        "model": active_provider.model,
        "dimensions": active_provider.dimensions or "",
    }
