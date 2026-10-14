# 평가 설계, 지표와 실험 해석

## 평가가 답해야 하는 질문

1. 필요한 원문 근거를 찾았는가?
2. 최종 답변이 질문의 수용 기준을 만족하는가?
3. 인용된 구절이 실제 문서에 존재하고 그 주장을 지지하는가?
4. 근거가 부족할 때 추측을 보류하고, 답할 수 있는 질문은 실제로 답하는가?
5. 변경으로 이 지표들이 어떻게 달라지고 비용과 지연이 얼마나 발생하는가?

검색, 답변, 인용, 보류를 하나의 점수로 섞지 않는다. 서로 다른 실패 원인을 추적하기
위해 여러 지표를 함께 제시한다.

## Gold Set

현재 `data/gold.jsonl`은 40개 질문이다. 원본 질문/정답/문장 근거는 HotpotQA에서
가져왔고, 요약과 근거 부족 질문은 `dataset.py`에서 명시적으로 파생했다.
각 사례에 `id`, `source_id`, `split`, `category`, `question`, `answerable`, `answers`,
`required_evidence`, `acceptance`, `construction`이 있다. 생성 pipeline에는 이 중
**question만** 전달한다. Judge에게는 실행 후 reference와 acceptance를 전달한다.

개발용 15개와 test 25개를 나눴다. 모델·임계값·프롬프트 선택은 개발용에서 수행하고
test는 고정한 설정의 최종 비교에 사용한다. 원 질문과 요약 변형은 같은 그룹이다.
이 데이터는 사람이 모두 검수한 새로운 Gold라고 주장하지 않는다. 원본 crowdworker
라벨과 규칙 기반 파생 라벨의 provenance를 구분한다.

## 지표의 정확한 정의

### Evidence recall

답변 가능한 질문 q에 대해 필요한 원문 문장 ID 집합을 G, 모델에 실제 제공한 검색 청크의
문장 ID 합집합을 R이라고 하면 `|G ∩ R| / |G|`다. 질문별 비율을 macro average한다.
답이 없는 질문은 N/A다. 검색 자체가 실패하면 recall은 0으로 남는다. 검색 성공 뒤
생성이 실패하면 관찰된 검색 결과로 recall을 계산하고 generation error는 별도 기록한다.

All evidence found는 `G ⊆ R`일 때 1, 아니면 0이다. 다중 문서 추론에서 근거 하나만
찾아도 평균 recall이 높아 보이는 문제를 보완한다. 정답 문장에 꼭 필요한 구절이 하나뿐인
경우에는 문장 단위 기준이 coarse하다는 한계가 있다.

### Answer token F1 / exact match

정답과 short_answer를 소문자화하고 ASCII 구두점과 영어 관사를 제거한 뒤 token multiset
overlap을 계산한다. 여러 reference가 있으면 최대 F1을 취한다. 요약은 claims를 연결한
전체 답변과 reference를 비교한다. 답변 가능한 전체 질문이 분모이며 보류·오류는 0이다.

이 지표는 cheap lexical proxy이며 의미적 correctness가 아니다. 동의어, 번역, 정확한
paraphrase를 과소평가하고, 정답 단어만 나열한 오답을 과대평가할 수 있다. 특히 요약의
품질을 이 점수 하나로 판단하면 안 된다. Exact match는 더 엄격한 문자열 기준이다.

### Citation validity

답변을 반환한 사례에서 모든 인용 ID가 실제 검색 결과에 존재하고 quote가 원문에
나타나는지 검사한다. pipeline이 잘못된 인용을 차단하므로 통과한 답변의 이 값은
일반적으로 1이다. 이 값이 높다고 hallucination이 없다는 뜻은 아니다. 차단된 잘못된
출력은 error rate에 포함되고 수리 호출은 attempts에 기록된다.

### Abstention precision / recall / F1

- TP: Gold는 답변 불가능하고 서비스가 insufficient_evidence를 반환한 수.
- Precision: TP / 서비스가 보류한 전체 질문 수. 아무 것도 보류하지 않으면 N/A.
- Recall: TP / Gold의 답변 불가능 질문 수. 호출 오류도 분모에 포함된다.
- F1: `2*TP / (보류 수 + 답변 불가능 질문 수)`.

오류는 보류가 아니다. 모든 질문을 거절하면 recall은 높아질 수 있지만 precision과
answerable correctness가 나빠진다. 두 축을 함께 읽어야 한다.

### Semantic judge metrics (opt-in)

Judge correctness: reference/acceptance/Gold 근거와 비교한 0, 1, 2점을 0~1로 정규화한다.
Citation support: 각 claim을 **그 claim이 인용한 quote만** 보고 supported / unsupported /
ambiguous로 판정한다. ambiguous는 supported로 세지 않는다.

Judge가 꺼져 있으면 null이며 0으로 대체하지 않는다. 답변 호출 오류는 Judge correctness
0으로 계산한다. Judge 자체가 실패한 경우 semantic 점수는 null로 두고 judge_errors와
coverage를 공개한다. coverage가 100% 미만인 의미 지표는 완전한 집합의 성능으로
해석하지 않는다. 서로 다른 coverage의 실행 비교에는 특히 주의해야 한다.

### 시간과 비용

질문별 end-to-end ms, 검색 ms, 전체 p50/p95, 반환된 생성 토큰 수를 저장한다.
생성 시도별 사용량을 기록해 citation repair 호출도 합산한다. 단가를 입력하지 않으면
비용은 unknown/null이며 무료라고 표시하지 않는다. 현재 비용 필드는 성공적으로
반환된 generation 응답에 대한 추정이며 embedding·실패 호출·GPU 전력/시간 비용을
포함하지 않는다. provider 청구서와의 정산 지표라고 사용하면 안 된다.

## Judge 신뢰성, 일관성, Human Alignment

Judge prompt는 `evaluation.py`의 JUDGE_PROMPT이며 해시를 실행 manifest에 기록한다.
판정 기준과 점수 범위를 명시하고 answer/evidence 내부 지시를 무시하도록 한다.
verbosity를 보상하지 않도록 명시하며 질문별 reason과 claim 순서별 판정을 저장한다.
현재 단일 답변을 absolute rubric으로 채점하므로 A/B 답변 순서 편향은 직접 발생하지
않지만 자기 모델 선호, 근거 오독, 장문 편향, 프롬프트 민감도는 남는다.

권장 검증 절차:

1. 개발용 질문에 정답·부분 정답·근거 없는 주장이 섞인 응답을 확보한다.
2. GUI Human review에서 정답 기준과 근거를 읽고 사람이 0/1/2 점수와 faithfulness를 기록한다.
3. Judge 점수는 사람 검토 화면에서 먼저 보여주지 않는다. 제출 후 일치도와 비교한다.
4. `groundwork calibrate --run <id>`로 exact agreement, Cohen's kappa, MAE를 확인한다.
5. 불일치 사례를 읽어 rubric을 수정하고 prompt version을 바꾼 뒤 개발용에서 다시 평가한다.
6. 실제 모델 일관성은 같은 고정 설정을 반복 실행하여 판정 변화율을 확인한다.

사람의 점수는 해당 response hash와 묶어 답변이 바뀐 뒤 옛 점수를 재사용하지 않는다.
현재 사람이 입력한 라벨이 없으면 calibration은 pending을 반환한다. 이 상태에서
Human Alignment를 확보했다고 주장하지 않는다. 단일 평가자와 소표본 일치도 역시
확정적인 품질 인증은 아니다. 초기 공개 측정은 Judge 없는 지표로 수행할 수 있으며,
Judge는 .env 설정 후 `--judge`로 명시적으로 활성화한다.

## 자동화와 재현성

```bash
# 전체 Gold Set을 한 번에 실행
uv run groundwork eval --config baseline --split all

# 조건을 고정한 Dense / Hybrid 실험 및 test 비교
uv run groundwork experiment --split all

# 의미 판정 활성화: JUDGE_* 환경 변수 설정 필요
uv run groundwork eval --config hybrid --split all --judge

# 저장된 두 실행 비교
uv run groundwork compare --before RUN_A --after RUN_B --split test
```

각 실행 디렉터리에 manifest, incremental predictions, progress, summary, report가
생긴다. manifest에는 Git commit/dirty, dependency lock hash, Corpus 및 Gold 해시,
청킹/검색/생성 설정, model/provider/로컬 digest, 프롬프트 해시, seed, 실행 시각이 있다.
외부 모델 alias와 비결정적 연산 때문에 seed=42/temperature=0도 동일 출력을 보장하지
않는다. 저장된 실행 기록 재검토와 새 모델 실행의 재현 가능성은 구분한다.

오류 사례를 삭제하지 않으며 성공 응답에만 평균을 내어 overall 결과라고 표시하지
않는다. 파일은 질문마다 갱신하므로 중단 시 부분 결과를 확인할 수 있다. 완료되지 않은
실행은 comparison에서 거절한다. CLI 프로세스와 GUI job은 별개이며 실행 중 모델을
경쟁적으로 사용하면 latency가 변할 수 있다. 로컬 latency는 운영 SLA로 해석하지 않는다.

## 통제된 첫 실험

가설: Dense에 BM25와 RRF를 추가하면 고유명사·정확한 용어가 필요한 질문의 근거 회수율과
답변 품질이 좋아질 수 있다. `baseline.yaml`과 `hybrid.yaml`의 검색 방식만 바꾸고,
생성 모델·프롬프트·청킹·top_k·문맥 예산·temperature·seed를 고정한다.

comparison은 Corpus/Gold/index/model/prompt/context 조건과 질문 ID 집합이 같은지
검사한다. 평균만 보고 개선이라고 말하지 않고 질문별 delta와 실패 유형을 본다.
source_id 그룹을 단위로 bootstrap 1,000회를 수행해 상관된 요약 변형을 묶는다.
ratio metric인 abstention precision/recall에는 이 단순 per-question bootstrap CI를
적용하지 않아 N/A로 남긴다. 작은 표본의 CI는 설명적 지표이며 강한 일반화 근거가 아니다.

## CI와 회귀 방지

기본 GitHub Actions는 키 없이 unit/API/data integrity 검사와 JavaScript syntax 검사를
실행한다. 이 검사는 모델 성능 검사를 대신하지 않는다. 실제 모델 평가를 PR마다 실행하면
비용·속도·비결정성 및 외부 fork secret 접근 문제가 생긴다.

운영 확장 시 trusted branch의 manual/nightly workflow에서 고정 모델·고정 데이터로
평가하고, `compare --max-recall-drop 0.03 --max-f1-drop 0.03` 같은 명시적 budget을 gate로
사용한다. 이 숫자는 예시이며 개발용 변동성으로 calibration해야 한다. generation error rate,
unanswerable recall, latency budget도 별도 gate로 확장한다. 실패하면 artifact를 보존하고
사람이 질문별 회귀를 검토한다. 외부 PR에는 API secret을 제공하지 않는다.
