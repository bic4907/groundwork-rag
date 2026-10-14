# Dense → Hybrid 검색 실험 분석

## Hypothesis

고유명사와 정확한 표현을 검색하는 BM25를 Dense retrieval에 RRF로 결합하면 정답 근거
회수율과 답변 품질이 개선될 수 있다는 가설을 세웠다. 같은 Corpus, Nomic embedding,
Llama 3 생성 모델, 청킹, top-k=6, 문맥 본문 16,000자, temperature=0, seed=42를 사용했다.
변경한 실험 변수는 Dense 대 Dense+BM25+RRF 검색이다.

두 설정 모두 Gold Set **40개 전체**를 실제 로컬 모델로 실행했다. 공식 결과 비교는
개발용 15개와 분리된 **test 25개**이며 그중 answerable 20개, unanswerable 5개다.
범주별 및 전체 지표는 `METRICS.md`, 원시 결과는 각 run 디렉터리에 있다.

## Result

| Test 지표 | Dense | Hybrid | 변화 |
| --- | ---: | ---: | ---: |
| Evidence recall (answerable n=20) | 95.00% | 92.50% | -2.50 pp |
| All evidence found (answerable n=20) | 90.00% | 85.00% | -5.00 pp |
| Answer token F1 (answerable n=20) | 43.49% | 47.28% | +3.79 pp |
| Exact match (answerable n=20) | 30.00% | 30.00% | 0.00 pp |
| Abstention precision | 0.00% | 33.33% | +33.33 pp |
| Abstention recall (unanswerable n=5) | 0.00% | 20.00% | +20.00 pp |
| Error rate (전체 test n=25) | 8.00% | 4.00% | -4.00 pp |

전체 40개에서는 recall 96.875% → 93.75%, Token F1 39.56% → 45.23%, 오류 2건 → 1건이었다.
전체 unanswerable 8개에서 올바른 보류는 양쪽 모두 **1개**였다. test 보류 recall 상승은
작은 split에서 어느 질문을 보류했는지가 바뀐 결과이며 전체적인 보류 능력 개선으로
확대 해석할 수 없다.

Test recall delta의 cluster bootstrap 95% 구간은 약 [-11.76, +5.88] pp,
Token F1 delta는 약 [-14.63, +24.83] pp다. 모두 0을 포함한다. 한 번의 생성과 작은
표본으로 안정적인 향상을 입증한 결과가 아니다. 정확한 값은 comparison-test.json에 있다.

Semantic Judge 점수는 이 전체 실험에서 측정하지 않았다. 표의 Token F1을 의미적
정답성으로 해석하면 안 된다. 두 실행의 Citation Validity는 통과한 답변에서 100%였지만,
이는 인용 ID·구절 존재 검사이고 의미적 근거성의 증거가 아니다.

## Analysis

### 1. 정확한 단어가 연결 문서를 밀어냈다

“Ravi Khote의 음악이 포함된 2003년 영화” 질문에서 Dense는 `Ravi Khote`와 정답
영화 `Kal Ho Naa Ho`를 함께 찾았다. Hybrid는 연도·영화 유형이 비슷한 distractor를
상위로 올렸고 정답 영화 문서가 최종 6개에서 빠졌다. Recall이 1.0에서 0.5로 낮아졌다.

허리케인 질문에서도 Dense가 찾은 `Hurricane Faith`가 Hybrid에서 다른 hurricane season
문서들에 밀렸다. 단순 lexical fusion이 bridge entity를 자동으로 따라가 주지는 않는다.

개발용 Fred Mace 질문에서도 원 인물 문서는 유지했지만 연결된 `Stalybridge Celtic F.C.`
문서는 football 관련 distractor에 밀렸다. 짧은 답은 같아도 full-evidence 조건은 실패했다.
이는 단일 정답 문자열과 다중 근거 회수율을 함께 보아야 하는 사례다.

### 2. 검색 개선이 답변 개선과 항상 같이 움직이지 않았다

음반 회사 질문에서는 Hybrid가 필요한 근거를 더 회수해 Recall 0.5 → 1.0을 기록했지만,
양쪽 short answer는 모두 `Blackheart Records`였다. 반대로 일부 질문은 동일한 근거
회수율에서도 생성 형식 오류 여부가 달랐다. 예를 들어 영화감독 나이 비교 질문은
Dense에서 JSON schema 검증 실패, Hybrid에서는 답변 반환이었다.

따라서 Token F1 상승에는 검색 순서와 생성의 변동, 형식 오류 감소가 섞여 있다. 이를
순수하게 “더 좋은 문서를 찾았기 때문”이라고 설명할 수 없다.

### 3. 가장 큰 미해결 문제는 근거 부족 판별이다

필수 문서를 제거한 질문에도 로컬 모델이 `SpaceX`, `Ibanez`처럼 답변을 생성했다.
관련되지만 답을 증명하지 못하는 구절을 인용하는 경우가 있었다. 어떤 응답은 질문이
요구한 구체적인 값을 주지 않았는데 answered로 분류했다.

이 결과는 인용 존재 검사와 프롬프트만으로 사실적 grounding을 보장할 수 없다는 것을
보여준다. 현재 구현의 오류 처리와 평가 체계가 실패를 드러내지만, 보류 정책의 모델
수준 신뢰성은 부족하다. 현재 로컬 baseline을 신뢰도 높은 운영 QA라고 주장하지 않는다.

### 4. 지연과 재현성의 해석

실행 중 같은 로컬 runtime에서 GUI 질의, 별도의 개발용 평가, Judge 연동 확인을 수행했다.
따라서 p50/p95에는 장치 경쟁과 warm/cold 상태가 섞여 있다. 저장된 지연값은 관찰 기록이며
검색 방식만의 성능 차이나 운영 SLA로 해석하지 않는다.

두 전체 실험은 한 CLI 프로세스에서 순차 실행했다. baseline 시작 시점과 hybrid 시작
시점 사이에 GUI/API schema와 설명 문서 작업으로 working tree가 dirty 상태가 되었다.
실행 중 프로세스가 사용하는 평가·검색·생성 모듈은 교체하지 않았다. 두 manifest에
기록된 Git 상태를 그대로 보존했으며 clean이라고 수정하지 않았다. 다음 정식 실험은
깨끗한 고정 commit에서 대화형 작업을 멈춘 상태로 실행하는 편이 좋다.

## Next Steps

1. **보류 판별을 우선 개선한다.** 질문의 각 필수 사실을 cited evidence가 충족하는지
   확인하는 별도 검증 단계를 개발용에서 비교한다. 독립 verifier가 추가하는 비용과
   과도한 보류도 측정한다.
2. **다중 단계 검색을 비교한다.** 첫 검색의 bridge entity를 추출해 후속 문서를 검색하고,
   같은 최종 문맥 예산에서 reranker 또는 document diversity와 비교한다.
3. **사람의 검토를 확보한다.** 특히 no-answer, 형식 오류, 높은 lexical F1의 오답과 낮은
   lexical F1의 정답을 검토한다. 독립 Judge와 실제 human labels의 일치도를 측정한다.
4. **표본과 실행을 늘린다.** test를 재튜닝하지 않고 새 holdout을 마련한다. 여러 seed/
   반복 실행과 격리된 runtime으로 변동성과 지연을 측정한다.
5. **모델을 교체해 원인을 분리한다.** 같은 retriever에서 더 신뢰도 높은 생성 모델을
   비교하고 모델 교체 실험을 검색 실험과 별도로 보고한다.

지표 상승만 선택하여 보고하지 않았으며, 실패한 출력과 악화된 검색 결과도 공개 기록에
포함했다. 이 결과의 가장 유용한 결론은 다음 개발 우선순위가 단순한 검색 recall 증가보다
**근거 충분성 판별과 실제 의미적 정답 평가**에 있다는 것이다.
