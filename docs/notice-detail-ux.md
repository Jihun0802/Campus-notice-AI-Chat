# Notice Detail UX

공지 상세 화면은 다음 URL에서 열린다.

```text
http://127.0.0.1:8000/notice-detail.html?id={notice_id}
```

진입 위치:

- 학생 홈 맞춤 공지 카드
- 마감 임박 공지 카드
- 새 공지 카드
- 저장한 공지 카드
- 최근 DB 공지 카드
- 챗봇 출처 카드

상세 화면은 다음 정보를 보여준다.

- 공지 제목, 작성자, 부서, 게시일, 마감일
- 원문 링크
- 본문
- 첨부파일 목록과 PDF 파싱 상태
- 이미지 썸네일과 OCR 상태
- chunk type별 개수
- embedding 완료/누락 수
- localStorage 기반 읽음/저장 버튼
- 이 공지 제목으로 챗봇 질문하기 링크

로그인/SSO가 없으므로 읽음/저장 상태는 브라우저 localStorage에만 저장된다.

