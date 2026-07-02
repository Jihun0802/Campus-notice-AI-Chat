from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from campus_notice_ai.config import RAG_SYSTEM_PROMPT_PATH, load_dotenv
from campus_notice_ai.embeddings import create_query_embedding_for_search
from campus_notice_ai.search import build_extract_answer, search_chunks


NO_ANSWER_MESSAGE = "관련 공지를 찾지 못했습니다. 검색어를 더 구체적으로 입력해 주세요."


DEFAULT_SYSTEM_PROMPT = (
    "너는 단국대학교 공지 RAG 챗봇이다. 반드시 제공된 evidence 안의 정보만 사용한다. "
    "근거가 부족하면 모른다고 말하고, 답변은 한국어로 간결하게 작성한다."
)


def load_prompt(path: str | Path | None, *, default: str = DEFAULT_SYSTEM_PROMPT) -> str:
    if path is None:
        return default
    prompt_path = Path(path)
    try:
        prompt = prompt_path.read_text(encoding="utf-8").strip()
    except OSError:
        return default
    return prompt or default


class LLMProvider(Protocol):
    def is_available(self) -> bool:
        ...

    def generate_answer(
        self,
        query: str,
        evidence: list[dict[str, Any]],
        user_context: dict[str, Any],
    ) -> str:
        ...


class FallbackLLMProvider:
    mode = "fallback"

    def is_available(self) -> bool:
        return True

    def generate_answer(
        self,
        query: str,
        evidence: list[dict[str, Any]],
        user_context: dict[str, Any],
    ) -> str:
        if not evidence:
            return NO_ANSWER_MESSAGE

        top = evidence[0]
        parts: list[str] = [f"가장 관련 있는 공지는 '{top['title']}'입니다."]
        if top.get("deadline_at"):
            parts.append(f"마감일은 {top['deadline_at']}입니다.")
        if top.get("published_at"):
            parts.append(f"게시일은 {top['published_at']}입니다.")
        if top.get("publisher"):
            parts.append(f"작성자는 {top['publisher']}입니다.")

        target_parts = [
            str(value)
            for value in (top.get("department"), top.get("grade"), top.get("course_id"))
            if value
        ]
        if target_parts:
            parts.append(f"관련 대상은 {' / '.join(target_parts)}입니다.")

        comparable = [
            item
            for item in evidence[1:]
            if item.get("category") == top.get("category")
            and item.get("department") == top.get("department")
            and item.get("deadline_at")
            and top.get("deadline_at")
            and item.get("deadline_at") != top.get("deadline_at")
        ]
        if comparable:
            parts.append("검색된 공지들의 마감일이 서로 다를 수 있으니, 가장 구체적인 학과/수업 공지를 우선 확인하세요.")

        parts.append("해야 할 일은 아래 출처 카드의 근거 문장을 확인하고 원문 링크에서 세부 안내를 확인하는 것입니다.")
        return " ".join(parts)


class OpenAICompatibleProvider:
    mode = "llm"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        system_prompt_path: str | Path | None = RAG_SYSTEM_PROMPT_PATH,
        timeout_seconds: int = 20,
    ) -> None:
        load_dotenv()
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model or os.getenv("OPENAI_MODEL") or "gpt-4.1-mini"
        self.base_url = (base_url or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.system_prompt_path = system_prompt_path
        self.system_prompt = load_prompt(system_prompt_path)
        self.timeout_seconds = timeout_seconds

    def is_available(self) -> bool:
        return bool(self.api_key)

    def generate_answer(
        self,
        query: str,
        evidence: list[dict[str, Any]],
        user_context: dict[str, Any],
    ) -> str:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": self.system_prompt,
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "question": query,
                            "user_context": user_context,
                            "evidence": evidence,
                            "answer_rules": [
                                "deadline_at이 있으면 우선 언급한다.",
                                "학생이 해야 할 행동을 간단히 포함한다.",
                                "여러 공지가 충돌하면 충돌 가능성을 표시한다.",
                            ],
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            "temperature": 0.2,
        }
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            f"{self.base_url}/chat/completions",
            data=raw,
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
            raise RuntimeError(f"LLM provider request failed: {exc}") from exc

        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("LLM provider returned an unexpected response") from exc


def select_llm_provider() -> LLMProvider:
    provider = OpenAICompatibleProvider()
    if provider.is_available():
        return provider
    return FallbackLLMProvider()


def confidence_from_results(results: list[dict[str, Any]]) -> str:
    if not results:
        return "low"
    score = float(results[0].get("score") or 0)
    if score >= 20:
        return "high"
    if score >= 8:
        return "medium"
    return "low"


def build_evidence(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for result in results:
        metadata = result["metadata"]
        evidence.append(
            {
                "notice_id": result["notice_id"],
                "title": result["title"],
                "publisher": metadata.get("publisher"),
                "department": metadata.get("department"),
                "category": metadata.get("category"),
                "grade": metadata.get("grade"),
                "course_id": metadata.get("course_id"),
                "visibility": metadata.get("visibility"),
                "published_at": metadata.get("published_at"),
                "deadline_at": metadata.get("deadline_at"),
                "original_url": metadata.get("original_url"),
                "chunk_type": metadata.get("chunk_type") or "body",
                "attachment_id": metadata.get("attachment_id"),
                "attachment_file_name": metadata.get("attachment_file_name"),
                "attachment_file_url": metadata.get("attachment_file_url"),
                "attachment_file_type": metadata.get("attachment_file_type"),
                "media_id": metadata.get("media_id"),
                "media_file_name": metadata.get("media_file_name"),
                "media_original_url": metadata.get("media_original_url"),
                "media_file_type": metadata.get("media_file_type"),
                "media_alt_text": metadata.get("media_alt_text"),
                "media_caption": metadata.get("media_caption"),
                "media_local_path": metadata.get("media_local_path"),
                "media_thumbnail_path": metadata.get("media_thumbnail_path"),
                "matched_text": result.get("snippet") or "",
                "score": result.get("score"),
                "keyword_score": result.get("keyword_score"),
                "vector_score": result.get("vector_score"),
                "retrieval_mode": result.get("retrieval_mode"),
            }
        )
    return evidence


def filter_rag_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not results:
        return []
    top_score = float(results[0].get("score") or 0)
    if top_score < 12:
        return results[:1]
    threshold = max(8.0, top_score * 0.75)
    filtered = [
        result
        for result in results
        if float(result.get("score") or 0) >= threshold
    ]
    return filtered or results[:1]


def answer_question(
    conn,
    query: str,
    *,
    department: str | None = None,
    grade: str | None = None,
    course_id: str | None = None,
    limit: int = 5,
    provider: LLMProvider | None = None,
    include_debug: bool = True,
) -> dict[str, Any]:
    query = query.strip()
    if not query:
        raise ValueError("query is required")

    user_context = {
        "department": department,
        "grade": grade,
        "course_id": course_id,
    }
    query_embedding = create_query_embedding_for_search(conn, query)
    results = search_chunks(
        conn,
        query,
        department=department,
        grade=grade,
        course_id=course_id,
        limit=limit,
        query_embedding=query_embedding,
    )
    results = filter_rag_results(results)
    evidence = build_evidence(results)
    if not evidence:
        response = {
            "answer": NO_ANSWER_MESSAGE,
            "mode": "fallback",
            "confidence": "low",
            "sources": [],
        }
        if include_debug:
            response["debug"] = {"retrieved_count": 0}
        return response

    active_provider = provider or select_llm_provider()
    fallback = FallbackLLMProvider()
    mode = getattr(active_provider, "mode", "llm")
    try:
        if active_provider.is_available():
            answer = active_provider.generate_answer(query, evidence, user_context)
        else:
            raise RuntimeError("LLM provider is not available")
    except Exception:
        answer = build_extract_answer(query, results)
        if answer == NO_ANSWER_MESSAGE:
            answer = fallback.generate_answer(query, evidence, user_context)
        mode = "fallback"

    response = {
        "answer": answer,
        "mode": mode,
        "confidence": confidence_from_results(results),
        "sources": evidence,
    }
    if include_debug:
        response["debug"] = {"retrieved_count": len(results)}
    return response
