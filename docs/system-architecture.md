# System Architecture

## Ingestion quality architecture

수집 source는 `config/sources.json`에서 관리한다.
각 source는 `source_id`, `name`, `source_type`, `url`, `detail_base_url`, `department`, `category`, `enabled`, `crawl_limit`을 가진다.
`config/sources.json`이 없거나 비어 있으면 코드의 기본 DKU source 목록으로 fallback된다.

```text
source config
→ DKU list page
→ DKU detail page
→ notice 저장
→ attachment metadata 저장
→ PDF parse
→ image cache/OCR
→ reindex
→ embed-all
→ /api/chat
```

상태 확인 API:

- `GET /api/health`: 테이블 row count 중심의 기본 상태
- `GET /api/ingestion/status`: 공지, chunk, 첨부파일, PDF 파싱, 이미지/OCR, source별 상태, 최근 실패 로그, OCR provider 상태
- `GET /api/notice?id=...`: 공지 상세, 첨부파일, 이미지, chunk/embedding 요약
- `GET /api/notices/{notice_id}`: path 기반 공지 상세
- `POST /api/admin/embed`: embedding이 없는 chunk에 OpenAI embedding 생성

## 현재 MVP 흐름

```text
공지 수동 등록 또는 seed 데이터
→ notices 저장
→ chunking
→ notice_chunks 저장
→ keyword search 및 metadata filter
→ evidence context 구성
→ /api/chat
→ LLM provider 또는 fallback answer
→ 웹 화면에 챗봇 답변, 출처 카드, 근거 문장 표시
→ 이후 embedding/vector search 가능
```

## 구성 요소

`notice_sources`는 공지가 어디에서 왔는지 저장한다.
학교 공지, 학과 공지, 장학 공지, 학사 일정, 메일 후보, LMS, 수동 등록 같은 출처를 구분한다.

`notices`는 챗봇이 참고할 공지 원문이다.
제목, 본문, 원본 URL, 작성 부서, 카테고리, 학과, 학년, 수업, 공개 범위, 게시일, 마감일을 저장한다.

`notice_chunks`는 RAG 검색을 위한 단위 데이터다.
현재는 본문, PDF 추출 텍스트, 이미지 OCR 텍스트를 `chunk_type`으로 구분해 저장한다.
`embedding` 컬럼은 nullable JSON 문자열이며, OpenAI embedding 생성 후 hybrid search에 사용한다.

`ingestion_logs`는 source/notice/attachment/media/chunk/embedding 단계의 실패와 경고를 저장한다.
관리자 상태 화면과 real-data validation CLI가 이 로그를 사용해 재처리 대상을 확인한다.

`crawler`는 접근 가능한 공개 단국대학교 게시판 HTML에서 목록과 상세 본문을 읽어 `notices`에 저장한다.
현재 수집 대상은 일반공지, 모바일시스템공학과 학과공지, 소프트웨어학과 학과공지, 대학원 공지사항이다.

`server`는 Python 표준 라이브러리의 HTTP 서버로 로컬 API와 정적 프론트엔드를 제공한다.
학생은 웹 화면에서 학과, 학년, 수업 context를 입력하고 질문할 수 있다.

`rag`는 질문 답변 흐름을 담당한다.
기존 `search`로 관련 chunk를 찾고, source/evidence를 만든 뒤 LLM provider 또는 fallback provider로 답변을 생성한다.
`/api/chat`은 이 `rag` 서비스를 호출하는 상위 API다.

`static/integration-demo.html`은 독립 웹앱이 아닌 기존 앱/포털에 플로팅 챗봇 위젯을 붙이는 방식을 보여주는 발표용 mock shell이다.
공식 단국대 UI를 복제하지 않고, 위젯이 실제 `/api/chat`을 호출하는지만 보여준다.

`static/notice-detail.html`은 공지 하나의 상세 화면이다.
홈 피드, 최근 공지, 챗봇 출처 카드에서 이동할 수 있고 본문, 첨부, 이미지, OCR 상태, chunk/embedding 상태를 보여준다.

## 로컬 개발 fallback

현재 구현은 SQLite와 Python 표준 라이브러리만 사용한다.
pgvector와 OpenAI API key가 없어도 seed, 공개 공지 수집, chunking, 검색, 챗봇 답변, 웹 화면을 실행할 수 있다.
추후 PostgreSQL로 옮길 때 `notice_chunks.embedding`을 vector 타입으로 바꾸거나 별도 embedding 테이블을 추가할 수 있다.

## 추후 RAG 확장

현재 단계에서는 SQLite에 저장한 embedding을 cosine similarity로 계산해 keyword 점수와 합친다.
다음 운영 단계에서는 PostgreSQL/pgvector로 옮겨 대량 데이터 검색 성능을 개선할 수 있다.
