# Prompts

이 폴더는 Campus Notice AI MVP의 LLM 프롬프트를 관리한다.

- `rag_system.md`: `/api/chat`에서 OpenAI-compatible provider가 사용하는 system prompt

수정 원칙:

- 공지 근거 밖의 사실을 만들지 않는다.
- 날짜, 마감일, 대상, 신청 방법, 제출 위치를 우선한다.
- 답변은 한국어로 짧고 학생이 바로 행동할 수 있게 쓴다.
- 근거가 부족하면 원문 또는 첨부파일 확인이 필요하다고 말한다.
- 출처 표시는 프론트의 출처 카드가 담당하므로 본문에는 긴 URL을 반복하지 않는다.
