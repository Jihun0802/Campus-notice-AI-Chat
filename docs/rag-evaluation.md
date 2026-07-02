# RAG Evaluation

평가 질문은 `evals/rag_questions.json`에 있다.
현재 세트는 30개 질문이며 졸업시험, 휴학/복학, 장학금, 수강신청 정정, 수업 공지, 캡스톤, 현장실습, PDF, 이미지 OCR, no-answer 케이스를 포함한다.

실행:

```bash
python -m campus_notice_ai eval-rag
```

평가는 LLM 답변의 문체를 채점하지 않는다.
검색 결과와 source metadata를 보고 다음을 검사한다.

- source가 필요한 질문에서 source가 나왔는지
- no-answer 질문에서 source가 나오지 않았는지
- 기대 키워드가 answer/source/snippet에 포함됐는지
- 기대 `chunk_type`이 포함됐는지
- `course` visibility가 course_id 없이 노출되지 않았는지

PDF/OCR 질문은 실제 DB에 `pdf_text`, `image_ocr` chunk가 충분히 없으면 실패할 수 있다.
이 실패는 데이터 품질 보강이 필요하다는 신호다.

