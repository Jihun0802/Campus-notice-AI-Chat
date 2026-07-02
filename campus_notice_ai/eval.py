from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from campus_notice_ai.config import PROJECT_ROOT
from campus_notice_ai.search import build_extract_answer, search_chunks


DEFAULT_EVAL_PATH = PROJECT_ROOT / "evals" / "rag_questions.json"


def load_eval_questions(path: str | Path | None = None) -> list[dict[str, Any]]:
    eval_path = Path(path) if path else DEFAULT_EVAL_PATH
    items = json.loads(eval_path.read_text(encoding="utf-8"))
    if not isinstance(items, list):
        raise ValueError("RAG eval file must contain a JSON list")
    for item in items:
        if not isinstance(item, dict) or not item.get("id") or not item.get("query"):
            raise ValueError("Each RAG eval item must include id and query")
    return items


def combined_result_text(answer: str, sources: list[dict[str, Any]]) -> str:
    parts = [answer]
    for source in sources:
        metadata = source.get("metadata") or {}
        parts.extend(
            [
                str(source.get("title") or ""),
                str(source.get("snippet") or ""),
                str(metadata.get("chunk_type") or ""),
                str(metadata.get("publisher") or ""),
                str(metadata.get("department") or ""),
                str(metadata.get("category") or ""),
                str(metadata.get("original_url") or ""),
            ]
        )
    return " ".join(parts).lower()


def evaluate_question(conn: sqlite3.Connection, item: dict[str, Any], *, limit: int = 5) -> dict[str, Any]:
    context = item.get("user_context") or {}
    expected = item.get("expected") or {}
    results = search_chunks(
        conn,
        str(item["query"]),
        department=context.get("department") or None,
        grade=str(context.get("grade")) if context.get("grade") not in (None, "") else None,
        course_id=context.get("course_id") or None,
        limit=limit,
    )
    answer = build_extract_answer(str(item["query"]), results)
    combined = combined_result_text(answer, results)
    failures: list[str] = []

    if expected.get("no_answer"):
        if results:
            failures.append("expected no sources, but sources were returned")
    else:
        if not results:
            failures.append("expected at least one source")

    for keyword in expected.get("must_include_keywords") or []:
        if str(keyword).lower() not in combined:
            failures.append(f"missing keyword: {keyword}")

    preferred_chunk_types = set(expected.get("preferred_chunk_types") or [])
    if preferred_chunk_types and results:
        result_chunk_types = {
            (result.get("metadata") or {}).get("chunk_type") or "body"
            for result in results
        }
        if not (result_chunk_types & preferred_chunk_types):
            failures.append(
                "missing preferred chunk type: "
                + ", ".join(sorted(preferred_chunk_types))
            )

    blocked_visibility = set(expected.get("must_not_include_visibility") or [])
    if blocked_visibility:
        leaked = [
            (result.get("metadata") or {}).get("visibility")
            for result in results
            if (result.get("metadata") or {}).get("visibility") in blocked_visibility
        ]
        if leaked:
            failures.append("blocked visibility returned: " + ", ".join(sorted(set(leaked))))

    return {
        "id": item["id"],
        "query": item["query"],
        "passed": not failures,
        "failures": failures,
        "source_count": len(results),
        "top_source": results[0]["title"] if results else None,
        "top_chunk_type": (results[0].get("metadata") or {}).get("chunk_type") if results else None,
    }


def run_rag_eval(
    conn: sqlite3.Connection,
    questions: list[dict[str, Any]],
    *,
    limit: int = 5,
) -> dict[str, Any]:
    results = [evaluate_question(conn, item, limit=limit) for item in questions]
    passed = sum(1 for result in results if result["passed"])
    total = len(results)
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round((passed / total) * 100, 1) if total else 0.0,
        "results": results,
    }
