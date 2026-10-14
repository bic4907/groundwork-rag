# 근거 충분성 베이스라인

## 연구와 구현 범위

[Sufficient Context (ICLR 2025)](https://arxiv.org/abs/2411.06037)의 근거 충분성 개념을
차용한 **프롬프트 기반 베이스라인**이다. 논문의 학습·보정 절차나 보고 성능을 재현했다는
주장이 아니다. [S2G-RAG (ACL 2026)](https://aclanthology.org/2026.acl-long.1185/)의
구조화된 정보 공백 기록도 참고하지만, 이번 버전은 추가 검색을 하지 않는다. 반복 검색은
별도 실험으로 분리해야 충분성 판정 자체의 영향을 알 수 있다.

## 통제된 변경

`configs/sufficient.yaml`은 `baseline`과 같은 Dense 검색, top-6, 후보 24개, 청크,
16,000자 문맥 예산, 생성 모델, 답변 프롬프트, temperature, seed, 출력 한도를 사용한다.
추가하는 처리는 다음 하나다.

1. 검색한 **동일 문맥**을 생성 모델에 먼저 보내 충분성을 판정한다.
2. `sufficient`, `reason`, `missing_facts`, `evidence`를 JSON으로 받는다.
3. 충분하면 기존 생성기로 같은 입력을 전달한다. 판정 이유나 임시 답은 생성 입력에 넣지 않는다.
4. 부족하면 생성 호출을 생략하고 `insufficient_evidence`를 반환한다.

판정은 생성 모델과 같은 provider/model을 별도 호출한다. 평가용 `JUDGE_*`와 다르며
별도 API 키가 필요 없다. 골드 정답, answerable 라벨, 정답 근거는 판정 입력에 들어가지 않는다.
기본 판정 출력 한도는 500토큰이고 답변 한도는 기존 650토큰이다. 연산 예산은 증가하므로
추가 호출과 토큰을 함께 기록한다. 판정이 통과해도 생성기는 자체적으로 보류할 수 있다.

## 계약과 실패 처리

- 충분하다고 판단하려면 하나 이상의 원문 인용과 빈 `missing_facts`가 필요하다.
- 부족하다고 판단하면 구체적인 누락 사실이 하나 이상 필요하다.
- 판정의 인용 ID 및 인용문도 실제 검색 문맥에 있는지 검증한다.
- 잘못된 JSON/인용은 한 번 수리한다. 두 번 실패하거나 provider 오류가 나면 **오류**이다.
  실패를 정상 보류로 치환하면 보류 성능이 과장되므로 그렇게 하지 않는다.
- 검색 결과가 없으면 모델을 호출하지 않고 기존 `no_evidence` 경로로 보류한다.
- 인용의 존재는 의미적 충분성을 증명하지 않는다. 모델이 관련성만으로 통과시키거나,
  답이 있는 문맥을 부족하다고 잘못 판단할 수 있다.

## 추적과 지표

응답에 `sufficiency`, `sufficiency_prompt_sha256`, `timings.sufficiency_ms`가 추가된다.
`attempts[].stage`는 `sufficiency`와 `answer`를 구별한다. 모델 응답을 받은 뒤 검증에
실패한 호출도 기록하며, 최종 오류가 나면 평가 행의 `attempts_on_error`로 보존한다.
사용량을 반환하지 못한 요청과 임베딩 비용은 합산할 수 없으며 비용 범위에 명시한다.

실행 manifest에는 판정 프롬프트 해시와 모델 식별자를 저장한다. 비교 시 기존 생성·데이터·
인덱스 일치 검사를 유지하고, `changed_settings`로 개입을 명시한다. 판정 모델은 생성
모델과 일치해야 하며, 판정을 켠 두 실행의 판정 프롬프트가 다르면 비교를 거절한다.

기존 지표에 다음을 추가한다.

| 지표 | 분모와 의미 |
| --- | --- |
| `unanswerable_answer_rate` | Gold의 답변 불가 질문 중 실제 답변한 비율; 낮을수록 좋음 |
| `answerable_abstention_rate` | Gold의 답변 가능 질문 중 정상 보류한 비율; 과도한 보류 확인 |
| `answered_token_f1` | 답변 가능하며 실제 답변한 항목의 평균 Token F1; 응답률과 함께 해석 |
| `model_calls_by_stage` | 응답을 받은 판정/답변 호출 수; 수리 포함 |

`answered_token_f1`은 의미적 정확도나 환각률이 아니다. 보류한 어려운 질문이 분모에서
빠져 높아질 수 있다. 오류율, 전체 질문 F1, 답변률을 같이 봐야 한다. Gold의 answerable은
**전체 corpus 기준**이며 검색된 문맥의 충분성 라벨이 아니므로 판정기 정확도로 부르지 않는다.

## 실행

```bash
uv run groundwork ask 'Fred Mace played for which English football club in 1919?' --config sufficient
uv run groundwork experiment --before baseline --after sufficient --split dev
uv run groundwork eval --config sufficient --split all
```

GUI의 Pipeline/Configuration에서 `Dense + Sufficiency gate`를 선택한다.
Before/After 버튼은 Dense baseline과 선택한 설정을 실행한다. 비교 Split을 선택해
Development 실행끼리도 비교할 수 있다. 답변에는 충분성 판정과 누락 사실·인용을 표시한다.

## 평가 해석

우선 기존 dev 15개로 통합 동작과 과도한 보류를 확인한다. 이 데이터는 이미 알려진
개발 데이터이다. 기존 test 25개 역시 이전 분석에 사용했으므로 새 개선의 독립적
일반화 증거로 취급하지 않는다. 임계값 보정이나 프롬프트 개선을 진행한다면 별도의
개발/보정 세트를 확장하고, 새로운 최종 평가 세트를 먼저 고정해야 한다.

이번 이진 판정은 확률이나 신뢰도 임계값을 제공하지 않는다. 따라서 임계값을 바꾼
risk–coverage 곡선이나 calibration을 측정했다고 주장하지 않는다. 해당 실험은 더 많은
레이블과 보정 절차가 준비되면 추가한다.

## 현재 Sonnet 평가

전체 40문항에서 Dense와 Sufficiency를 비교하고, BM25와 Hybrid도 같은 모델로 평가했다.
이전 실행의 숫자는 현재 보고서에서 제거했다.
[Sonnet 결과·실패·비용 분석](../reports/sonnet-v1/ANALYSIS.ko.md)과
[전체 측정 표](../reports/sonnet-v1/METRICS.md)를 확인할 수 있다.

모든 방식을 한 번에 실행하려면 `uv run groundwork benchmark --split all` 또는
GUI의 **전체 방식 순차 평가**를 사용한다.
