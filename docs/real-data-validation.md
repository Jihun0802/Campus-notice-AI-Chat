# Real Data Validation

실제 단국대 공개 공지 수집 품질은 다음 명령으로 확인한다.

```bash
python -m campus_notice_ai validate-real-data --limit 3
```

기본 동작:

- `config/sources.json`의 enabled source를 순회한다.
- source별 limit만큼 실제 공지를 수집한다.
- 제목, 본문, 원문 URL, 첨부파일, PDF 파싱, 이미지, OCR, chunk, embedding 상태를 요약한다.
- 실패 케이스는 `ingestion_logs`에 저장한다.

API 비용 없이 구조만 확인하려면 embedding을 건너뛴다.

```bash
python -m campus_notice_ai validate-real-data --limit 3 --no-embed
```

검증 결과에서 실패가 나와도 앱은 중단하지 않는다.
실패 원인은 `/api/ingestion/status`와 학생 홈의 데이터 상태 섹션에서 확인한다.

