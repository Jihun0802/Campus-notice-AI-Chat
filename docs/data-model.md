# Data Model

## Ingestion quality update

`notice_attachments`는 이제 첨부파일 메타데이터와 수집/파싱 상태를 함께 저장한다.

- `download_status`: `pending`, `downloaded`, `skipped`, `failed`
- `parse_status`: `pending`, `parsed`, `unsupported`, `empty`, `failed`
- `error_message`: 다운로드 또는 파싱 실패 원인
- `updated_at`: 마지막 첨부 상태 갱신 시각

PDF 첨부파일은 텍스트 추출을 시도하고, 성공하면 `extracted_text`에 저장한다.
HWP/HWPX 등은 현재 파일명과 링크만 저장하고 `unsupported`로 남긴다.

`notice_media`는 본문 이미지와 이미지 첨부파일 정보를 저장한다.

- `original_url`: 원본 이미지 URL
- `local_path`: 로컬 캐시 이미지 경로
- `thumbnail_path`: 썸네일 경로. 현재는 썸네일 생성 라이브러리가 없으면 원본 캐시 경로와 같다.
- `ocr_text`: OCR로 읽은 텍스트
- `summary_text`: 추후 Vision summary용 텍스트. 이번 단계에서는 자동 생성하지 않는다.
- `parse_status`: OCR 처리 상태
- `error_message`: 이미지 다운로드, 캐시, OCR 실패 원인

`notice_chunks`는 본문 chunk, PDF 첨부 chunk, 이미지 OCR chunk, 이미지 요약 chunk를 모두 담는다.
첨부에서 생성된 chunk는 `attachment_id`가 채워지고, 이미지에서 생성된 chunk는 `media_id`가 채워진다.
`chunk_type`은 `body`, `pdf_text`, `image_ocr`, `image_summary` 중 하나다.
metadata에는 `attachment_file_name`, `media_thumbnail_path`, `media_original_url`, `chunk_type` 같은 출처 카드 표시용 정보가 들어간다.
`embedding`에는 OpenAI embedding vector를 JSON 문자열로 저장한다.
현재 MVP는 SQLite scan + cosine similarity 방식이며, 데이터가 커지면 PostgreSQL + pgvector로 전환하는 것이 다음 단계다.

`crawl_runs`는 source별 수집 결과를 기록한다.
`/api/ingestion/status`에서 최근 수집 상태, 첨부 수, PDF 파싱 성공 수를 확인할 수 있다.

`ingestion_logs`는 수집/파싱/색인/임베딩 실패와 검증 결과를 저장한다.

- `target_type`: `source`, `notice`, `attachment`, `media`, `chunk`, `embedding`
- `step`: `crawl`, `parse`, `pdf_extract`, `image_cache`, `ocr`, `reindex`, `embed`
- `status`: `success`, `warning`, `failed`
- `retryable`: 재시도 가능한 실패인지 표시
- `error_message`: 관리자 화면에 보여줄 실패 원인

## users

`users`는 실제 로그인 구현 전에도 학생 context를 표현하기 위해 준비한다.
이메일, 이름, 학과, 학년, 역할을 저장하고, 추후 개인화 검색과 관리자 권한 필터에 사용한다.

## notice_sources

`notice_sources`는 공지 출처를 나타낸다.
학교 공지, 학과 공지, 장학 공지, 학사 일정, 메일 공지, LMS 공지, 수동 등록을 구분할 수 있다.

## notices

`notices`는 공지의 핵심 원문 테이블이다.
RAG의 기준 데이터는 이 테이블에 저장된 제목, 본문, 게시자, 카테고리, 학과, 학년, 수업, 공개 범위, 게시일, 마감일이다.

`visibility`는 공지가 누구에게 보여야 하는지 표현한다.
예시는 `public`, `department`, `grade`, `course`, `private`이다.

## notice_attachments

`notice_attachments`는 공지에 딸린 PDF, HWP 같은 문서 첨부 정보를 저장한다.
PDF는 텍스트 추출에 성공하면 `extracted_text`를 채우고 `pdf_text` chunk로 연결한다.
이미지 파일은 `notice_attachments`가 아니라 `notice_media`에 저장한다.

## notice_media

`notice_media`는 본문 이미지와 이미지 첨부를 저장한다.
이미지는 사용자에게 썸네일/원본 링크로 보여주고, 검색/RAG에는 OCR 텍스트만 사용한다.
OCR 실패 시에도 row는 유지하고 `parse_status`, `error_message`로 상태를 남긴다.

## notice_chunks

`notice_chunks`는 검색 가능한 RAG 단위다.
각 chunk는 하나의 공지와 연결되고, 본문 chunk인 경우 `attachment_id`와 `media_id`는 `null`이다.

`metadata`는 JSON 문자열로 저장한다.
현재 metadata에는 `notice_id`, `title`, `department`, `grade`, `course_id`, `visibility`, `published_at`, `deadline_at`, `original_url`, `chunk_type`, 첨부/이미지 표시 정보 등이 들어간다.

`embedding`은 OpenAI embedding vector를 JSON 문자열로 저장한다.
추후 pgvector를 사용하는 환경에서는 vector 타입으로 바꾸거나 별도 embedding 저장소로 분리할 수 있다.

## ingestion_logs

`ingestion_logs`는 실제 단국대 데이터 검증과 운영 상태 확인을 위한 로그 테이블이다.
앱은 PDF 파싱, 이미지 캐시, OCR, reindex, embedding 실패가 발생해도 중단하지 않고 이 테이블에 실패 원인을 남긴다.
관리자 상태 화면은 최근 실패 20개를 표시하고, 추후 재처리 API는 이 테이블을 기준으로 대상을 고를 수 있다.

## mail_notice_candidates

`mail_notice_candidates`는 교수님 또는 학사팀 메일을 바로 공지로 넣지 않고 관리자 검토 후보로 보관하기 위한 모델이다.
이번 작업에서는 실제 메일 수신을 구현하지 않는다.
추후 관리자가 `pending` 후보를 확인하고 승인하면 `notices`로 전환하고 `approved_notice_id`로 연결한다.
