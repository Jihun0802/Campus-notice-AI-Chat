# MVP Scope

## Current included scope

- 단국대학교 공개 공지 source config 관리
- 공개 공지 크롤링
- 공지 본문 저장 및 chunking
- 첨부파일 링크 수집
- PDF 첨부파일 텍스트 추출
- 첨부파일 텍스트의 RAG 검색 포함
- OpenAI embedding 생성
- keyword + embedding hybrid search
- `/api/chat` 기반 fallback RAG 답변
- 출처 카드와 근거 문장 표시
- 연동 데모 페이지
- 데이터 수집 상태 API와 UI 표시
- 실제 공개 공지 데이터 검증 CLI
- 공지 상세 API와 정적 상세 화면
- ingestion 실패 로그 저장
- RAG 검색 품질 평가 세트와 CLI
- OCR provider 상태 표시

## Current deferred scope

- PostgreSQL/pgvector 전환
- SSO/LMS/메일 자동 수신
- HWP/HWPX 본문 파싱
- 운영 배포와 스케줄러
- React/Next.js 전환
- Vision summary 자동 생성
- image embedding

## MVP 목표

이번 MVP의 목표는 단국대학교 공지 RAG 챗봇을 로컬에서 끝까지 시연할 수 있게 만드는 것이다.
공지 데이터가 DB에 저장되고 RAG 검색에 사용할 수 있는 chunk로 변환되며, 웹 화면에서 출처 기반 챗봇 답변을 확인할 수 있다.

## 포함 기능

- 공지 관련 DB schema 준비
- 사용자 context, 공지 출처, 공지, 첨부파일, chunk, 메일 후보 모델 준비
- 모바일시스템공학과 학생이 물어볼 법한 샘플 공지 10개 seed
- 공지의 `title + body_text`를 약 1000자 단위, 약 150자 overlap으로 chunking
- 한 공지 또는 전체 공지를 다시 chunking하는 reindex 명령
- pgvector나 OpenAI API 없이도 로컬 SQLite로 동작하는 fallback 구조
- 단국대학교 공개 공지 페이지 일부 수집
- keyword 기반 검색과 학생 context filter
- `/api/chat` 기반 RAG 답변 생성
- LLM provider abstraction과 API key 없는 fallback 답변
- 출처 카드와 근거 문장 표시
- 로컬 백엔드 API
- 학생용 챗봇 웹 MVP 화면
- 플로팅 챗봇 위젯 integration demo
- 공지 상세 화면에서 본문, 첨부, 이미지, OCR 상태, chunk 상태 확인
- 관리자/데이터 상태 화면에서 source별 상태와 최근 실패 로그 확인
- `validate-real-data`, `eval-rag` CLI로 실제 데이터와 검색 품질 점검

## 제외 기능

- 실제 LMS 로그인 연동
- 실제 학교 SSO 연동
- 실제 교수님 메일 자동 수신
- 운영 수준 LLM 답변 품질 보장
- 운영 수준의 관리자 UI
- 푸시 알림
- Vision summary 자동 실행
- image embedding

## 추후 확장 기능

- 공개 공지 자동 크롤러 스케줄링
- 포털 또는 LMS 인증 세션 기반 수집
- HWP/HWPX 본문 파싱
- pgvector 기반 vector search
- RAG 답변 품질 고도화
- 관리자 승인 흐름과 알림 기능

## 졸업작품 기준 구현 범위

졸업작품 1차 범위에서는 데이터 저장, seed, 공개 공지 수집, 첨부/PDF/이미지 구조, chunking, embedding, hybrid search, `/api/chat`, 학생 홈, 공지 상세, integration demo까지 구현한다.
이 단계가 끝나면 "학생 질문에 대해 관련 공지를 찾고, 출처와 근거 문장을 함께 보여주며, 공지 상세와 수집 상태까지 확인할 수 있는 RAG 공지 플랫폼"을 시연할 수 있다.
운영 수준 LLM 답변 품질, 운영 수준 크롤링 안정성, 로그인 연동, 메일 수신, 배포는 다음 단계에서 별도로 검증한다.
