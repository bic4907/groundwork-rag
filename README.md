# Groundwork

**Ask with evidence. Measure what changes.**

문서 기반 RAG QA, 인용 추적 GUI, Gold Set 평가, 통제된 검색 개선 실험을 제공하는
Python 프로젝트입니다. 로컬 Ollama와 원격 모델 API를 지원합니다.

![실제 평가 실행의 Before/After 비교](docs/images/experiment-comparison.jpg)

## 포함된 기능

- 공개 문서 **310개**, 문장 단위 Gold 근거가 있는 **40개 질문**.
- 문장 경계 청킹, 임베딩 캐시, 체크섬을 가진 불변 벡터 인덱스.
- Dense / BM25 / Hybrid(RRF) 검색, 근거 기반 생성, 주장별 인용과 exact-quote 검증.
- 명시적 답변 보류, 출력 수리, API 오류와 보류의 구분.
- FastAPI 요청·응답 schema 및 단계 SSE streaming.
- 질문·근거·문서 탐색·실험·결과 비교·사람 검토를 제공하는 웹 GUI.
- 전체 Gold Set 단일 명령 평가, 질문별 결과, 범주/split별 지표, paired comparison.
- 선택적 LLM Judge, 사람-Judge 정합성 측정, 재현성 manifest, GitHub Actions.

## 빠른 시작

Python 3.11 이상, [uv](https://docs.astral.sh/uv/)가 필요합니다. 아래 명령은 저장소 루트에서
실행합니다. 기본값은 로컬 Ollama입니다. hosted API를 쓰면 모델 다운로드를 건너뛰고
아래 원격 모델 설정을 사용하세요.

```bash
git clone https://github.com/bic4907/groundwork-rag.git
cd groundwork-rag
cp .env.example .env
uv sync --frozen

# Ollama가 실행 중이어야 합니다.
ollama pull llama3:latest
ollama pull nomic-embed-text:latest

# 데이터는 이미 포함되어 있습니다. 생성 모델이 아닌 임베딩을 호출합니다.
uv run groundwork ingest

# GUI + API
uv run groundwork serve
```

GUI: [http://127.0.0.1:8000](http://127.0.0.1:8000) · API schema:
[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

기본 모델은 실제 로컬 실행 경로를 제공하기 위한 출발점입니다.
`latest`는 불변 버전이 아니므로 실제 로컬 모델 digest를 실행 manifest에 기록합니다.
추가 모델을 선택할 때는 context 길이·비용·생성 품질·지원 API 형식을 함께 확인하세요.

## 환경 변수와 원격 모델

키는 `.env`에만 넣습니다. `.env`는 Git과 Docker build context에서 제외됩니다.
실제 값을 코드, README, query string, 브라우저 입력창에 넣지 마세요.

```dotenv
GENERATION_PROVIDER=remote
GENERATION_BASE_URL=https://your-provider.example/v1
GENERATION_MODEL=your-chat-model
GENERATION_API_KEY=

EMBEDDING_PROVIDER=remote
EMBEDDING_BASE_URL=https://your-provider.example/v1
EMBEDDING_MODEL=your-embedding-model
EMBEDDING_API_KEY=
```

`BASE_URL` 뒤에 `/chat/completions` 또는 `/embeddings`를 붙여 호출합니다. 서비스가
별도 모델별 endpoint를 주면 `/v1`까지 포함한 해당 base URL을 지정하세요. JSON object
출력과 지정한 generation parameters를 지원하는 endpoint가 필요합니다. provider마다
지원 범위가 달라 현재 모든 hosted 서비스와의 실호출 호환성을 보장하지 않습니다.

생성 모델만 원격으로 쓰고 임베딩은 로컬에 둘 수도 있습니다. 임베딩 모델이나 Corpus를
바꾸면 `groundwork ingest`를 다시 실행해야 합니다. 모델 설정은 `.env`에서 읽으며 키를
API 응답으로 노출하지 않습니다. 완전한 새 실험에서는 서버를 다시 시작해 설정을 명확히
고정하는 것을 권장합니다.

| 환경 변수 | 의미 / 기본값 |
| --- | --- |
| `GENERATION_*`, `EMBEDDING_*` | provider, base URL, model, API key |
| `JUDGE_PROVIDER` | `disabled` 기본; 선택적으로 `ollama` 또는 `remote` |
| `JUDGE_BASE_URL`, `JUDGE_MODEL`, `JUDGE_API_KEY` | Judge 전용 설정 |
| `API_TIMEOUT_SECONDS` | 180초 |
| `MAX_CONCURRENT_JOBS` | GUI 내 평가 작업 동시 실행 상한, 기본 1 |
| `GENERATION_INPUT_PRICE`, `GENERATION_OUTPUT_PRICE` | 100만 토큰당 가격; 미입력 시 비용 unknown |
| `JUDGE_INPUT_PRICE`, `JUDGE_OUTPUT_PRICE` | Judge 사용량의 비용 추정용 |
| `EMBEDDING_INPUT_PRICE` | 확장용 설정; 현재 generation 비용 합계에 미포함 |
| `SEND_REMOTE_SEED` | remote seed 지원 시에만 true; 기본 false |
| `APP_ACCESS_TOKEN` | 서버를 loopback 외부로 바인딩할 때 필수 |

## 질의 및 API

```bash
uv run groundwork ask 'Fred Mace played for which English football club in 1919?' --config hybrid

curl http://127.0.0.1:8000/api/qa \
  -H 'Content-Type: application/json' \
  -d '{"question":"Fred Mace played for which English football club in 1919?","config":"hybrid"}'
```

응답에는 `status`, `short_answer`, `claims[].evidence[]`, `citations`, 실제 `retrieval`,
모델 호출 `attempts`, 단계별 `timings`, 인용 검증 상태가 있습니다. `answered`와
`insufficient_evidence`를 구분하며 호출·출력 형식 오류는 HTTP 오류로 반환합니다.
인용 검사 성공은 의미적 정답 보장이 아닙니다.

`POST /api/qa/stream`은 검색/근거/생성/검증 완료를 단계별 SSE로 보냅니다. 토큰 단위
streaming은 지원하지 않습니다. 화면에 보여주는 최종 답변은 인용 검증을 통과한 결과입니다.

## 평가와 실험

```bash
# 전체 40개 질문을 한 명령으로 평가
uv run groundwork eval --config baseline --split all

# Dense → Hybrid 통제 실험, test split 비교까지 한 번에
uv run groundwork experiment --split all

# 두 저장된 실행 비교
uv run groundwork compare --before RUN_A --after RUN_B --split test

# Judge 사용 (JUDGE_* 설정 후)
uv run groundwork eval --config hybrid --split all --judge

# GUI에서 사람이 검토한 뒤 Judge와 일치도 측정
uv run groundwork calibrate --run RUN_ID
```

`runtime/runs/<run-id>/`에 `manifest.json`, `predictions.jsonl`, `progress.json`,
`summary.json`, `report.md`가 생깁니다. 비교는 `runtime/comparisons/`에 저장됩니다.
실험 중간 결과도 질문별로 저장하며, 완료되지 않은 실행은 최종 비교에서 거절합니다.
전체 runtime은 기본 Git ignore입니다. 공개 benchmark 결과 중 선별한 것만 `reports/`에
보관하며 실제 사용자 질문과 사람 검토 데이터를 자동 게시하지 않습니다.

주요 지표는 Evidence Recall, All Evidence Found, Answer Token F1, Citation Validity,
Abstention Precision/Recall/F1, Error Rate입니다. 선택적으로 의미적 Judge correctness와
Citation Support를 계산합니다. **Token F1은 의미적 정답성이 아니며, Citation Validity는
논리적 뒷받침이 아닙니다.** 상세 분모와 blind spot은 평가 문서에 설명했습니다.

### 첫 개선 실험

- **Hypothesis:** 정확한 이름·표현을 검색하는 BM25를 Dense에 RRF로 결합하면 근거
  회수율과 답변 품질이 개선될 수 있다.
- **Control:** 모델, 데이터, 청킹, top-k=6, 문맥 본문 16,000자, 생성 설정 및 prompt 고정.
- **Result:** 두 설정에서 각 40개 질문을 실제 실행했습니다. test 25개에서 Evidence Recall은
  **95.0% → 92.5%**, Answer Token F1은 **43.49% → 47.28%**였습니다.
  [측정 표](reports/local-v1/METRICS.md)와 [원인 분석](reports/local-v1/ANALYSIS.ko.md)을 공개했습니다.
- **Analysis:** lexical distractor가 bridge 문서를 밀어내 recall이 하락한 사례가 있었습니다.
  전체 no-answer 8개 중 올바른 보류는 양쪽 모두 1개로 낮았습니다. Token F1 상승을 의미적
  정답성 향상으로 간주하지 않으며, 이 로컬 baseline의 보류 신뢰성은 아직 부족합니다.
- **Next steps:** 다중 문서 추론용 반복 검색, reranker, 독립 Judge와 실제 사람 검수,
  한국어/도메인 데이터, 더 큰 holdout 및 반복 실행.

## 구조와 문서

```text
src/groundwork/
  dataset.py       고정된 공개 데이터 → Corpus / Gold
  retrieval.py     청킹 / embedding cache / index / 검색
  providers.py     로컬·원격 모델 어댑터
  pipeline.py      생성 / 인용 검사 / 보류
  schemas.py       요청·응답 및 데이터 계약
  evaluation.py    지표 / Judge / 실행 / 비교 / 사람 정합성
  api.py           HTTP / 단계 SSE / GUI 작업
  cli.py           단일 명령 실행 인터페이스
  web/             GUI (외부 CDN 없음)
configs/           통제된 실험 설정
data/              공개 Corpus / Gold / provenance / attribution
docs/              구현 의도, 평가 정의, 데이터 조사
tests/             의미 있는 offline 동작 검사
reports/           선별한 실제 공개 benchmark 측정
```

- [구현 방식과 설계 의도](docs/ARCHITECTURE.ko.md): 컴포넌트별 동작, 왜 선택했는지, tradeoff.
- [평가 설계와 한계](docs/EVALUATION.ko.md): 지표의 정확한 분모, Judge 신뢰성, CI 설계.
- [공개 데이터 조사](docs/DATASETS.ko.md): HotpotQA, SQuAD2, RGB, 공식 문서 후보 비교.
- [요구사항 대응표](docs/REQUIREMENTS.md): 요구사항과 구현·검증 위치.

## 검증과 운영 한계

```bash
uv run pytest -q
node --check src/groundwork/web/app.js
uv run python scripts/check_publication.py
```

GitHub Actions는 키가 필요 없는 검사를 수행합니다. 실제 모델 평가와 CI 회귀 기준은
별개입니다. `compare --max-recall-drop 0.03 --max-f1-drop 0.03`으로 threshold gate를
사용할 수 있으며 실제 임계값은 개발용 결과의 변동성으로 결정해야 합니다.

현재 구조는 한 명이 실험하는 로컬 workbench에 맞췄습니다. 전역 job queue는 process
메모리이며 서버 재시작 후 job handle을 복원하지 않습니다. 모델 출력은 실패할 수 있고,
인용이 실제로 있어도 주장과 무관할 수 있습니다. 실제 사람이 검토하지 않은 상태에서
Human Alignment 확보를 주장하지 않습니다. 작은 역사적 영어 benchmark를 전체 서비스
품질이나 최신 사실의 정확도로 일반화하지 않습니다.

Dockerfile도 제공하지만 실제 Docker image 실행 검증 여부는 검증 기록을 따릅니다.
컨테이너에서는 `APP_ACCESS_TOKEN`을 설정해야 하고 Ollama 주소는 호스트에 도달 가능한
주소로 별도 지정해야 합니다. `.env`를 이미지에 복사하지 말고 `--env-file`로 전달하세요.

## 데이터 및 라이선스

소프트웨어: MIT. 데이터: HotpotQA 및 Wikipedia에서 파생된 **CC BY-SA 4.0**.
[데이터 출처와 변경 사항](data/NOTICE.md)을 확인하세요. upstream 저자와의 제휴를 의미하지 않습니다.

## 근거 충분성 베이스라인

`Dense + Sufficiency gate`는 동일 검색 문맥으로 답할 수 있는지 생성 전에 별도로
판정합니다. 부족하면 답변을 보류하고 누락 사실을 기록합니다. 기존 Dense/Hybrid/BM25는
그대로 선택할 수 있습니다. 판정 호출의 비용·지연 및 과도한 보류도 함께 측정합니다.

```bash
uv run groundwork experiment --before baseline --after sufficient --split dev
```

GUI의 Configuration에서 `Dense + Sufficiency gate`를 선택한 뒤 Before/After를
실행하면 됩니다. 개발 결과 비교에는 Compare runs의 Split을 Development로 선택하세요.
[구현 의도·연구 출처·지표·한계](docs/SUFFICIENCY.ko.md)를 참고하세요.

첫 개발 비교에서는 과도한 보류와 출력 계약 오류로 **답변 F1이 33.01% → 0%**로
하락했습니다. 기본 설정으로 승격하지 않았습니다.
[측정 결과와 실패 분석](reports/sufficiency-v1/ANALYSIS.ko.md)을 함께 공개합니다.
