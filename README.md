# Campus Notice AI

단국대학교 공지 RAG 챗봇 MVP입니다.

현재 구현된 흐름:

```text
DB → 크롤러 → 공지/첨부/이미지 저장 → PDF/OCR 텍스트 추출 → chunking → embedding → hybrid search → /api/chat → 학생 홈/챗봇 UI
```

주요 API:

- `GET /api/health`
- `GET /api/ingestion/status`
- `GET /api/notices`
- `GET /api/notice?id=...`
- `GET /api/notices/{notice_id}`
- `GET /api/search?q=...`
- `POST /api/chat`
- `POST /api/admin/crawl`
- `POST /api/admin/reindex`
- `POST /api/admin/embed`

## OpenAI provider

`.env` 파일에 API 키를 직접 입력하면 `/api/chat`이 OpenAI-compatible provider를 사용한다.
키가 비어 있으면 기존 fallback 답변으로 동작한다.
LLM system prompt는 `prompts/rag_system.md`에서 수정한다.

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4.1-mini
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_EMBEDDING_DIMENSIONS=1536
```

실행 중인 서버도 다음 `/api/chat` 요청 때 `.env`를 다시 읽는다.
단, OS 환경변수에 `OPENAI_API_KEY`가 이미 값이 있는 경우에는 OS 환경변수가 우선한다.

수집 source는 `config/sources.json`에서 관리한다.

단국대학교 공지 RAG 챗봇의 full-stack MVP입니다.

공지 데이터를 SQLite DB에 저장하고, RAG 검색용 `notice_chunks`로 변환한 뒤,
로컬 웹 화면에서 맞춤 공지 피드와 출처 기반 챗봇 답변을 확인할 수 있습니다.

API key가 없으면 fallback 답변으로 동작하고, `OPENAI_API_KEY`가 있으면 OpenAI-compatible provider를 사용할 수 있습니다.
학교 SSO, LMS 로그인, 교수님 메일 수신은 아직 구현하지 않았습니다.

## 실행

Python 3.10 이상이 필요합니다. 실제 PDF 텍스트 추출 품질을 위해 `pypdf`를 사용합니다.

```bash
python -m pip install -e .
```

```bash
python -m campus_notice_ai init-db
python -m campus_notice_ai seed-notices
python -m campus_notice_ai reindex-all
python -m campus_notice_ai embed-all
python -m campus_notice_ai serve
```

브라우저에서 `http://127.0.0.1:8000`을 열면 MVP 화면을 볼 수 있습니다.
위젯 연동 데모는 `http://127.0.0.1:8000/integration-demo.html`에서 확인합니다.
공지 상세 화면은 목록 또는 출처 카드의 상세 링크에서 열 수 있고, 직접 열 때는
`http://127.0.0.1:8000/notice-detail.html?id={notice_id}` 형태를 사용합니다.
학생 홈의 읽음/저장 상태는 서버 계정 없이 브라우저 `localStorage`에 저장됩니다.

## 공개 공지 수집

접근 가능한 공개 단국대 공지 페이지를 수집할 수 있습니다.
PDF 첨부파일은 다운로드 후 텍스트 추출을 시도하고, 추출된 텍스트는 reindex/embed 후 검색과 `/api/chat` 근거에 포함됩니다.
본문 이미지와 이미지 첨부는 `notice_media`에 저장하고, 썸네일/원본 링크를 출처 카드에서 표시합니다.
검색에는 이미지 자체를 넣지 않고 OCR 텍스트가 있는 경우에만 `image_ocr` chunk로 포함합니다.

```bash
python -m campus_notice_ai crawl-dku --limit 3
python -m campus_notice_ai validate-real-data --limit 3
```

현재 기본 수집 대상은 일반공지, 모바일시스템공학과 학과공지, 소프트웨어학과 학과공지, 대학원 공지사항입니다.
`validate-real-data`는 실제 공개 공지를 수집한 뒤 제목/본문/첨부/PDF/이미지/OCR/chunk/embedding 상태를 source별로 요약하고,
실패 케이스는 `ingestion_logs`에 저장합니다. API 비용 없이 검증하려면 `--no-embed`를 붙입니다.

## OCR

이미지 OCR은 optional입니다. OCR이 없어도 공지 수집, 이미지 표시, 챗봇 기본 동작은 계속 됩니다.
OCR provider가 없으면 이미지는 썸네일/원본 링크로 보여주고, RAG 검색에는 OCR 텍스트가 들어가지 않습니다.

로컬 OCR을 사용하려면 Pillow, pytesseract, Tesseract 실행 파일이 필요합니다.
현재 OCR 연결 상태는 `/api/ingestion/status`의 `ocr_health`에서 확인합니다.

## 검색

```bash
python -m campus_notice_ai search "졸업시험 언제까지 신청해?" --department 모바일시스템공학과 --grade 4
```

## 챗봇 답변

```bash
python -m campus_notice_ai chat "졸업시험 신청 언제까지야?" --department 모바일시스템공학과 --grade 4
```

HTTP API:

```bash
curl -X POST http://127.0.0.1:8000/api/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"query\":\"졸업시험 신청 언제까지야?\",\"department\":\"모바일시스템공학과\",\"grade\":\"4\"}"
```

## RAG 평가

검색 품질 평가는 `evals/rag_questions.json`에 있는 질문 세트를 사용합니다.
LLM 정답 채점이 아니라 source retrieval 중심으로 검사합니다.

```bash
python -m campus_notice_ai eval-rag
```

평가 결과는 pass/fail과 실패 이유를 출력합니다. PDF/OCR 실제 데이터가 부족하거나 no-answer 필터가 약한 경우 실패가 남을 수 있습니다.

특정 공지만 다시 chunking하려면 notice id 또는 `original_url`을 전달합니다.

```bash
python -m campus_notice_ai reindex-one mock://dku/mobile-systems/notice/graduation-exam-2026
```

기본 DB 경로는 `data/campus_notice_ai.sqlite3`입니다.
다른 경로를 사용하려면 `--db` 옵션 또는 `CAMPUS_NOTICE_DB_PATH` 환경 변수를 사용합니다.

```bash
python -m campus_notice_ai --db .tmp/dev.sqlite3 seed-notices
```

## 테스트

```bash
python -m unittest discover -s tests
```
