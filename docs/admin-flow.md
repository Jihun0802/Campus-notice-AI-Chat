# Admin Flow

## 수동 공지 등록

관리자는 공지 제목, 본문, 원본 URL, 게시자, 카테고리, 학과, 학년, 수업, 공개 범위, 게시일, 마감일을 입력한다.
저장된 공지는 `notices`에 들어가고, reindex를 실행하면 `notice_chunks`가 다시 생성된다.

## Seed 기반 등록

MVP에서는 관리자 UI가 없으므로 seed 명령으로 샘플 공지를 넣는다.
seed는 `original_url` 기준으로 upsert되어 여러 번 실행해도 같은 공지가 계속 중복 생성되지 않는다.

## 메일 후보 승인 흐름

추후 교수님 또는 학사팀 메일을 자동 수신하면 바로 공지로 공개하지 않는다.
먼저 `mail_notice_candidates`에 `pending` 상태로 저장한다.

관리자는 후보 메일의 제목, 본문, 첨부 텍스트를 확인한다.
공지로 전환할 가치가 있으면 승인하고, 승인된 후보는 `notices`에 저장된다.
승인 후 `mail_notice_candidates.status`는 `approved`가 되고 `approved_notice_id`로 생성된 공지와 연결된다.

공지로 쓰기 어렵거나 개인 정보가 포함된 메일은 `rejected`로 처리한다.

## 운영 기준

공지 등록 또는 승인 후에는 해당 공지를 reindex해야 한다.
전체 reindex는 대량 수정, chunking 정책 변경, embedding 재생성이 필요한 경우에 실행한다.

## 데이터 상태 확인

관리자는 학생 홈 왼쪽의 데이터 상태 섹션에서 다음을 확인한다.

- 전체 공지/chunk/첨부/이미지 수
- PDF 파싱 성공률
- OCR 성공/실패/미지원 상태
- embedding 완료/누락 수
- source별 마지막 수집 시간과 실패 수
- 최근 ingestion 실패 로그

상세한 JSON은 다음 API에서 확인한다.

```text
GET /api/ingestion/status
```

실제 단국대 공개 공지 수집 품질은 CLI로 확인한다.

```bash
python -m campus_notice_ai validate-real-data --limit 3
```

실패는 `ingestion_logs`에 저장된다.
이번 단계에서는 실패 항목 재처리 버튼은 운영 UX 방향만 열어두고, 복잡한 자동 재처리 API는 후순위로 둔다.
