# 공개 데이터셋 조사와 선정

공식 프로젝트 및 저자 저장소를 기준으로 다음 후보를 확인했다.

| 후보 | 제공 데이터 | 장점 | 이번 기본 데이터로 쓰지 않은 이유 / 사용 방식 |
| --- | --- | --- | --- |
| [HotpotQA](https://hotpotqa.github.io/) | Wikipedia 문서, 질문/답, 문장별 supporting facts | 여러 문서를 연결하는 추론과 근거 회수율 평가 | **기본 선택**. 310개 문서와 40개 파생 평가 질문으로 제한 |
| [SQuAD 2.0](https://rajpurkar.github.io/SQuAD-explorer/) | 지문, 정답 span, adversarial unanswerable 질문 | 답변 보류와 사실 추출 평가 | 기본은 단일 지문 QA. 여러 지문을 합치면 원래 unanswerable 조건을 다시 검토해야 함 |
| [RGB](https://github.com/chen700564/RGB) | 영어/중국어 RAG 평가 질문과 문서 | noise robustness, information integration, counterfactual 등 강건성 | 이번엔 검색 Corpus와 sentence gold를 통일하기 위해 후속 강건성 실험 후보로 남김 |
| [FastAPI 공식 문서](https://fastapi.tiangolo.com/tutorial/) | 개발 문서와 코드 예제 | 실용적 도메인 QA, 고유명사·버전 조건 평가 | 정답/근거 Gold Set을 별도로 모두 작성해야 함 |

## 현재 데이터 구성

- 원본: HotpotQA validation / distractor split의 공식 저자 Hugging Face 배포.
- upstream revision: `1908d6afbbead072334abe2965f91bd2709910ab`.
- upstream SHA-256: `c20b638ca82b21d04fe12e14ff417ad05153d4d215a65de54497fca4e972f7c6`.
- 문서 310개, 기본 청킹 시 332개 청크.
- Gold: bridge 12, comparison 12, summary 8, unanswerable 8.
- 개발용 15개, 최종 비교용 25개. 같은 원 질문에서 파생된 요약은 같은 split에 배치.
- 실제 파일이 저장소에 포함되므로 다운로드 없이 ingest 가능.
- `uv run groundwork dataset`으로 checksum을 검증하면서 원본부터 재생성 가능.

초기 공식 사이트의 다운로드 서버 연결이 실패하여, 동일 프로젝트 저자의 Hugging Face
저장소에서 고정 revision의 Parquet 파일을 사용했다. 가변 API의 첫 페이지를 임의로
저장하는 방식은 사용하지 않았다.

## 저작권과 출처

HotpotQA는 CC BY-SA 4.0으로 공개된다. Corpus와 파생 Gold는 같은 라이선스를 유지하고,
프로젝트·논문·원 Wikipedia 문서에 대한 attribution을 `data/NOTICE.md`에 둔다.
소프트웨어 MIT 라이선스와 데이터 라이선스는 구분한다.

## 편향과 한계

1. 영어, 백과사전 도입부, 과거 사실에 편중되어 있다. 한국어 업무 문서 품질을 대표하지 않는다.
2. 공개 벤치마크가 모델 학습에 사용되었을 가능성이 있다. 답변 정확도만으로 검색 사용을 증명하지 않는다.
3. 요약은 원문 사실을 보존하는 과제로 규칙 기반 생성했다. 참조 문장은 발췌형이고 사람이 작성한 자연스러운 요약은 아니다.
4. 근거 부족 질문은 문서 제거 방식이라 실제 모호한 질문·문서 충돌과 분포가 다르다.
5. 답 문자열 부재 검사로 대체 추론 경로를 완전히 배제할 수 없다.
6. 40개 소규모 목적 표본의 점수를 전체 HotpotQA 공식 성적으로 표시하면 안 된다.
7. 정답 데이터에 모델 출력으로 추가한 pseudo-label은 없지만, 파생 질문의 실제 human review는 별도 수행이 필요하다.

후속 작업은 도메인 문서 corpus, 한국어 질문, 버전 충돌, 자연스러운 unanswerable,
문서 내부 prompt injection, 사람의 독립 검수 및 재작성으로 확장하는 것이다.
