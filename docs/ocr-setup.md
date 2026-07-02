# OCR Setup

OCR은 optional이다.
설치하지 않아도 공지 수집, PDF 파싱, 검색, 챗봇, 이미지 표시 기능은 동작한다.

OCR provider가 없으면:

- 이미지는 `notice_media`에 저장된다.
- 썸네일/원본 링크는 UI에 표시된다.
- OCR 텍스트가 없으므로 `image_ocr` chunk는 생성되지 않는다.
- RAG 검색에는 이미지 내용이 들어가지 않는다.

로컬 OCR을 사용하려면 다음이 필요하다.

- Pillow
- pytesseract
- Tesseract 실행 파일

상태 확인:

```bash
python -m campus_notice_ai init-db
```

또는 서버 실행 후:

```text
GET /api/ingestion/status
```

응답의 `ocr_health`에 `pillow_available`, `pytesseract_available`, `tesseract_available`, `ocr_provider_available`, `message`가 포함된다.
