# RAG Pipeline

## Attachment-aware retrieval

현재 RAG 검색 대상은 공지 본문, PDF 첨부파일 추출 텍스트, 이미지 OCR 텍스트다.

```text
사용자 질문
→ keyword search + embedding search
→ notice_chunks hybrid 검색
→ fallback 또는 OpenAI-compatible provider 답변 생성
→ 출처 카드 + 근거 문장 표시
```

embedding이 생성된 chunk가 있으면 질문도 `OPENAI_EMBEDDING_MODEL`로 embedding한 뒤 cosine similarity를 계산한다.
현재 MVP 기본값은 `text-embedding-3-small`이며, SQLite의 `notice_chunks.embedding`에 JSON 문자열로 저장한다.
저장된 embedding이 없거나 embedding 생성에 실패하면 기존 keyword search로 fallback된다.

첨부파일이 있는 공지는 다음 순서로 검색 대상에 들어간다.

```text
공지 상세 페이지
→ 첨부 링크 수집
→ notice_attachments 저장
→ PDF 다운로드 및 텍스트 추출
→ notice_chunks에 attachment chunk 생성
→ /api/chat 검색 결과에 첨부 metadata 포함
```

이미지가 있는 공지는 다음 순서로 표시/검색 대상에 들어간다.

```text
공지 상세 페이지
→ 본문 img와 이미지 첨부 링크 수집
→ notice_media 저장
→ 이미지 캐시와 썸네일 경로 저장
→ OCR 텍스트가 있으면 notice_chunks에 image_ocr chunk 생성
→ /api/chat 검색 결과에 media metadata 포함
```

현재 PDF 추출은 `pypdf`를 우선 사용하고, 실패하거나 설치되어 있지 않으면 Python 표준 라이브러리 기반 best-effort 파서로 fallback한다.
텍스트 레이어가 있는 PDF는 테스트로 확인했지만, 스캔본/OCR PDF는 미확인이다.
이미지 OCR은 optional OCR provider가 있을 때만 자동 시도한다.
OCR 실패 또는 provider 미설정 시 앱은 중단하지 않고 `parse_status`와 `error_message`만 저장한다.
Vision summary와 image embedding은 `summary_text`, `image_summary` chunk 구조만 열어두고 기본 자동 실행하지 않는다.

## 전체 흐름

```text
공지 수집 또는 등록
→ 원문 정리
→ chunking
→ metadata 저장
→ metadata filter
→ keyword retrieval
→ evidence context 구성
→ LLM provider 또는 fallback provider
→ RAG 답변 생성
→ 출처 카드와 근거 문장 표시
```

## 현재 구현한 범위

현재는 chunking, keyword 기반 검색, 출처 기반 RAG 답변 생성까지 구현한다.
`notices.title`과 `notices.body_text`를 합친 뒤 약 1000자 단위로 나누고, 다음 chunk와 약 150자 overlap을 둔다.

한 공지를 다시 색인할 때는 기존 `notice_chunks`를 삭제하고 새 chunk를 생성한다.
이 방식은 공지 본문이 수정되어도 오래된 chunk가 남지 않게 하기 위한 것이다.
`notice_chunks.chunk_type`은 `body`, `pdf_text`, `image_ocr`, `image_summary` 중 하나다.

`/api/chat`은 질문과 학생 context를 받아 기존 검색 엔진으로 관련 chunk를 찾고, 검색 결과를 evidence로 변환한다.
검색 결과가 없으면 출처 없이 모른다고 답한다.
검색 결과가 있으면 LLM provider가 사용 가능한 경우 LLM 답변을 생성하고, 사용할 수 없거나 실패하면 fallback 답변을 반환한다.

## Metadata filter

검색 단계에서는 chunk metadata를 사용해 검색 대상을 먼저 좁힌다.
예를 들어 모바일시스템공학과 4학년 학생이 질문하면 `department`, `grade`, `course_id`, `visibility`를 기준으로 관련 없는 공지를 제외할 수 있다.
`course` 공개 범위의 공지는 `course_id`가 정확히 일치할 때만 검색과 답변 근거로 사용할 수 있다.

## Embedding

`OPENAI_EMBEDDING_MODEL`이 설정되어 있으면 `/api/admin/embed` 또는 `embed_after` 옵션으로 각 chunk embedding을 생성한다.
기본 모델은 `text-embedding-3-small`이고, SQLite의 `notice_chunks.embedding`에 JSON 문자열로 저장한다.
PostgreSQL과 pgvector를 사용할 경우 이후 `notice_chunks.embedding`을 vector 타입으로 전환할 수 있다.

## Search

현재 검색 기능은 keyword score와 cosine similarity를 함께 사용하는 hybrid search로 구현한다.
저장된 embedding이 없거나 query embedding 생성에 실패하면 keyword search만 사용한다.
공지 제목, 마감일, 학과, 수업명은 keyword 검색에도 중요하므로 hybrid search에서도 계속 가중치에 포함한다.

## Answer generation

현재 답변 생성은 provider abstraction으로 분리되어 있다.
`FallbackLLMProvider`는 API key 없이 항상 동작하며, 검색된 evidence만 사용해 마감일, 게시일, 작성자, 대상, 학생이 해야 할 일을 요약한다.
`OpenAICompatibleProvider`는 `OPENAI_API_KEY`가 있을 때만 사용되며, 실패하면 fallback으로 전환한다.

답변은 출처 없는 사실을 말하지 않는다.
출처 카드에는 제목, 작성자, 학과, 카테고리, 게시일, 마감일, 원문 URL, 근거 문장이 포함된다.
PDF 근거는 `pdf_text`, 이미지 OCR 근거는 `image_ocr`로 표시한다.
이미지 근거가 있으면 썸네일과 원본 링크를 함께 내려보내 상세 화면과 출처 카드에서 확인할 수 있다.

## Evaluation

`evals/rag_questions.json`은 검색 품질을 확인하기 위한 30개 질문 세트다.
평가 CLI는 LLM 정답 채점이 아니라 다음 조건을 검사한다.

- 관련 source가 반환됐는지
- 기대 키워드가 answer/source/snippet에 포함됐는지
- 기대 `chunk_type`이 포함됐는지
- `course` 같은 제한 visibility가 잘못 노출되지 않는지
- no-answer 케이스에서 관련 없는 source가 반환되지 않는지

실행:

```bash
python -m campus_notice_ai eval-rag
```

현재 로컬 DB의 실제 데이터 분포에 따라 PDF/OCR 질문은 실패할 수 있다.
이는 평가 세트가 깨졌다는 뜻이 아니라, 실제 `pdf_text` 또는 `image_ocr` chunk가 부족하다는 신호다.
