from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from typing import Any

from campus_notice_ai.embeddings import cosine_similarity, parse_embedding


TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]+")
VECTOR_SCORE_WEIGHT = 20.0
VECTOR_ONLY_MIN_SCORE = 0.2
GENERIC_TERMS = {
    "공지",
    "신청",
    "알려줘",
    "언제",
    "어디서",
    "뭐",
    "있어",
    "해야",
    "해",
    "기준",
}
KOREAN_SUFFIXES = (
    "까지야",
    "하려면",
    "해야",
    "인가요",
    "나요",
    "에서",
    "으로",
    "부터",
    "까지",
    "이며",
    "이고",
    "은",
    "는",
    "이",
    "가",
    "을",
    "를",
    "에",
    "의",
    "도",
    "와",
    "과",
    "로",
    "야",
)


@dataclass(frozen=True)
class SearchResult:
    notice_id: str
    title: str
    chunk_text: str
    score: float
    keyword_score: float
    vector_score: float | None
    metadata: dict[str, Any]


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text) if len(token) >= 2]


def normalize_query_term(term: str) -> str:
    normalized = term.lower()
    for suffix in KOREAN_SUFFIXES:
        if normalized.endswith(suffix) and len(normalized) > len(suffix) + 1:
            return normalized[: -len(suffix)]
    return normalized


def important_query_terms(terms: list[str]) -> list[str]:
    important: list[str] = []
    for term in terms:
        normalized = normalize_query_term(term)
        if len(normalized) < 2 or normalized in GENERIC_TERMS:
            continue
        if normalized not in important:
            important.append(normalized)
    return important


def visible_for_context(
    metadata: dict[str, Any],
    department: str | None = None,
    grade: str | None = None,
    course_id: str | None = None,
) -> bool:
    visibility = metadata.get("visibility") or "public"
    if visibility == "public":
        return True
    if visibility == "department":
        return not department or not metadata.get("department") or metadata.get("department") == department
    if visibility == "grade":
        return not grade or not metadata.get("grade") or metadata.get("grade") == grade
    if visibility == "course":
        return bool(course_id and metadata.get("course_id") == course_id)
    if visibility == "private":
        return False
    return True


def make_snippet(text: str, terms: list[str], size: int = 220) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    lowered = compact.lower()
    hit_positions = [lowered.find(term) for term in terms if term and lowered.find(term) >= 0]
    if not hit_positions:
        return compact[:size]
    center = min(hit_positions)
    start = max(center - size // 3, 0)
    end = min(start + size, len(compact))
    snippet = compact[start:end]
    if start > 0:
        snippet = "..." + snippet
    if end < len(compact):
        snippet = snippet + "..."
    return snippet


def score_chunk(query: str, terms: list[str], title: str, chunk_text: str, metadata: dict[str, Any]) -> float:
    title_lower = title.lower()
    text_lower = chunk_text.lower()
    query_lower = query.strip().lower()
    score = 0.0

    if query_lower and query_lower in title_lower:
        score += 25
    if query_lower and query_lower in text_lower:
        score += 12

    for term in terms:
        if term in title_lower:
            score += 8 + title_lower.count(term)
        if term in text_lower:
            score += 3 + min(text_lower.count(term), 6)
        for key in ("category", "department", "publisher", "course_id"):
            value = str(metadata.get(key) or "").lower()
            if term in value:
                score += 2

    if score > 0 and metadata.get("deadline_at"):
        score += 0.5
    return score


def count_matched_terms(terms: list[str], title: str, chunk_text: str, metadata: dict[str, Any]) -> int:
    if not terms:
        return 0
    searchable = " ".join(
        [
            title,
            chunk_text,
            str(metadata.get("category") or ""),
            str(metadata.get("department") or ""),
            str(metadata.get("publisher") or ""),
            str(metadata.get("course_id") or ""),
        ]
    ).lower()
    return sum(1 for term in set(terms) if term in searchable)


def hybrid_score(keyword_score: float, vector_score: float | None) -> float:
    if vector_score is None or vector_score < VECTOR_ONLY_MIN_SCORE:
        return keyword_score
    return keyword_score + (vector_score * VECTOR_SCORE_WEIGHT)


def search_chunks(
    conn: sqlite3.Connection,
    query: str,
    *,
    department: str | None = None,
    grade: str | None = None,
    course_id: str | None = None,
    limit: int = 8,
    query_embedding: list[float] | None = None,
) -> list[dict[str, Any]]:
    terms = tokenize(query)
    rows = conn.execute(
        """
        SELECT
            notice_chunks.notice_id,
            notice_chunks.chunk_text,
            notice_chunks.chunk_index,
            notice_chunks.metadata,
            notice_chunks.embedding,
            notices.title
        FROM notice_chunks
        JOIN notices ON notices.id = notice_chunks.notice_id
        ORDER BY
            COALESCE(notices.published_at, '') DESC,
            notice_chunks.chunk_index ASC
        """
    ).fetchall()

    results: list[SearchResult] = []
    for row in rows:
        metadata = json.loads(row["metadata"])
        if not visible_for_context(metadata, department, grade, course_id):
            continue
        keyword_score = score_chunk(query, terms, row["title"], row["chunk_text"], metadata)
        vector_score = None
        if query_embedding is not None:
            chunk_embedding = parse_embedding(row["embedding"])
            if chunk_embedding is not None:
                vector_score = cosine_similarity(query_embedding, chunk_embedding)
        score = hybrid_score(keyword_score, vector_score)
        if query.strip() and score <= 0:
            continue
        if query.strip() and query_embedding is None:
            important_terms = important_query_terms(terms)
            required_matches = 2 if len(important_terms) >= 3 else 1
            if important_terms and count_matched_terms(important_terms, row["title"], row["chunk_text"], metadata) < required_matches:
                continue
        results.append(
            SearchResult(
                notice_id=row["notice_id"],
                title=row["title"],
                chunk_text=row["chunk_text"],
                score=score,
                keyword_score=keyword_score,
                vector_score=vector_score,
                metadata=metadata,
            )
        )

    results.sort(key=lambda item: item.score, reverse=True)
    best_by_notice: list[SearchResult] = []
    seen_notice_ids: set[str] = set()
    for result in results:
        if result.notice_id in seen_notice_ids:
            continue
        seen_notice_ids.add(result.notice_id)
        best_by_notice.append(result)

    return [
        {
            "notice_id": item.notice_id,
            "title": item.title,
            "score": round(item.score, 2),
            "keyword_score": round(item.keyword_score, 2),
            "vector_score": round(item.vector_score, 4) if item.vector_score is not None else None,
            "retrieval_mode": "hybrid" if item.vector_score is not None else "keyword",
            "snippet": make_snippet(item.chunk_text, terms),
            "metadata": item.metadata,
        }
        for item in best_by_notice[:limit]
    ]


def build_extract_answer(query: str, results: list[dict[str, Any]]) -> str:
    if not results:
        return "관련 공지를 찾지 못했습니다. 검색어를 더 구체적으로 입력해 주세요."

    top = results[0]
    metadata = top["metadata"]
    parts = [f"가장 관련 있는 공지는 '{top['title']}'입니다."]
    if metadata.get("deadline_at"):
        parts.append(f"마감일은 {metadata['deadline_at']}입니다.")
    if metadata.get("published_at"):
        parts.append(f"게시일은 {metadata['published_at']}입니다.")
    if metadata.get("publisher"):
        parts.append(f"작성자는 {metadata['publisher']}입니다.")
    parts.append("아래 결과에서 원문 출처를 확인할 수 있습니다.")
    return " ".join(parts)
