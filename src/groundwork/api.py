"""One-origin workbench. Model credentials never enter a response."""
import hmac
import json
import queue
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .evaluation import calibration, compare_runs, evaluate, run_folder
from .io import digest, read_jsonl, write_json
from .pipeline import Pipeline
from .providers import Models, ProviderError
from .retrieval import ingest
from .schemas import QueryRequest, QueryResponse
from .settings import ROOT, CONFIG_NAMES, ConfigName, Settings, load_config

app = FastAPI(title='Groundwork API', version='0.1.0', docs_url=None, redoc_url=None)
pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='groundwork')
job_lock = threading.Lock()
review_lock = threading.Lock()
jobs = {}


@app.middleware('http')
async def access_boundary(request: Request, call_next):
    if request.url.path.startswith('/api/'):
        token = Settings().app_access_token.get_secret_value()
        supplied = request.headers.get('authorization', '').removeprefix('Bearer ')
        if token and not hmac.compare_digest(token, supplied):
            return JSONResponse({'detail': 'Access token required'}, status_code=401)
        # Without a token, require local Host and reject cross-origin mutations.
        if not token and request.url.hostname not in {'127.0.0.1', 'localhost', '::1', 'testserver'}:
            return JSONResponse({'detail': 'Local host required'}, status_code=403)
        origin = request.headers.get('origin')
        if request.method not in {'GET', 'HEAD', 'OPTIONS'} and origin and origin.rstrip('/') != str(request.base_url).rstrip('/'):
            return JSONResponse({'detail': 'Cross-origin mutation rejected'}, status_code=403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'"
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    return response


@app.exception_handler(ProviderError)
async def provider_error(request, exc):
    return JSONResponse({'detail': str(exc)}, status_code=502)


@app.exception_handler(FileNotFoundError)
async def not_found(request, exc):
    return JSONResponse({'detail': str(exc) if 'Index missing' in str(exc) else 'Resource not found'}, status_code=404)


@app.exception_handler(ValueError)
async def invalid_request(request, exc):
    return JSONResponse({'detail': str(exc)}, status_code=400)


@app.get('/api/status')
def status():
    s = Settings()
    manifest_path = ROOT / 'data/manifest.json'
    return {'name': 'Groundwork', 'dataset': json.loads(manifest_path.read_text()) if manifest_path.exists() else None,
            'models': {'generation': {'provider': s.generation_provider, 'model': s.generation_model},
                       'embedding': {'provider': s.embedding_provider, 'model': s.embedding_model},
                       'judge': {'provider': s.judge_provider, 'model': s.judge_model}},
            'indexes': [json.loads(p.read_text()) for p in sorted((ROOT / 'runtime/indexes').glob('*/manifest.json'))],
            'configs': [load_config(x).model_dump() for x in CONFIG_NAMES]}


@app.post('/api/qa', response_model=QueryResponse)
def qa(request: QueryRequest):
    return Pipeline(load_config(request.config), Models(Settings())).answer(request.question)


@app.post('/api/qa/stream')
def qa_stream(request: QueryRequest):
    events = queue.Queue()

    def work():
        try:
            result = Pipeline(load_config(request.config), Models(Settings())).answer(
                request.question, lambda stage, payload: events.put((stage, payload)))
            events.put(('answer', result))
        except Exception as exc:
            events.put(('error', {'detail': str(exc) if isinstance(exc, (ProviderError, FileNotFoundError)) else type(exc).__name__}))
        finally:
            events.put(('done', {}))

    pool.submit(work)

    def stream():
        while True:
            try:
                event, payload = events.get(timeout=15)
                yield f'event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n'
                if event == 'done':
                    break
            except queue.Empty:
                yield ': keep-alive\n\n'
    return StreamingResponse(stream(), media_type='text/event-stream', headers={'X-Accel-Buffering': 'no'})


@app.get('/api/corpus')
def corpus(q: str = '', offset: int = 0, limit: int = 30):
    if offset < 0 or limit not in range(1, 101):
        raise HTTPException(400, 'Invalid pagination')
    docs = [d for d in read_jsonl(ROOT / 'data/corpus.jsonl') if q.lower() in (d['title'] + ' ' + ' '.join(s['text'] for s in d['sentences'])).lower()]
    return {'total': len(docs), 'offset': offset, 'documents': docs[offset:offset+limit]}


@app.get('/api/gold')
def gold():
    return read_jsonl(ROOT / 'data/gold.jsonl')


@app.get('/api/gold/{question_id}')
def gold_detail(question_id: str):
    case = next((g for g in read_jsonl(ROOT / 'data/gold.jsonl') if g['id'] == question_id), None)
    if not case:
        raise HTTPException(404, 'Question not found')
    required = set(case['required_evidence'])
    evidence = [{'sentence_id': s['id'], 'text': s['text'], 'title': d['title'], 'url': d['url']}
                for d in read_jsonl(ROOT / 'data/corpus.jsonl') for s in d['sentences'] if s['id'] in required]
    return {'case': case, 'evidence': evidence}


class JobRequest(BaseModel):
    kind: Literal['ingest', 'eval', 'experiment']
    config: ConfigName = 'baseline'
    before_config: ConfigName = 'baseline'
    after_config: ConfigName = 'hybrid'
    split: Literal['all', 'dev', 'test'] = 'dev'
    judge: bool = False


@app.post('/api/jobs', status_code=202)
def start_job(request: JobRequest):
    with job_lock:
        if sum(j['status'] in {'queued', 'running'} for j in jobs.values()) >= Settings().max_concurrent_jobs:
            raise HTTPException(409, 'Another job is active; wait for it to finish')
        job_id = uuid.uuid4().hex
        jobs[job_id] = {'id': job_id, 'status': 'queued', 'request': request.model_dump(), 'progress': None, 'result': None}

    def update_progress(value):
        with job_lock:
            jobs[job_id]['progress'] = value

    def work():
        with job_lock:
            jobs[job_id]['status'] = 'running'
        try:
            if request.kind == 'ingest':
                result = ingest(load_config(request.config), Models(Settings()))
            elif request.kind == 'eval':
                result = evaluate(request.config, request.split, request.judge, update_progress)
            else:
                ingest(load_config(request.before_config), Models(Settings()))
                ingest(load_config(request.after_config), Models(Settings()))
                before = evaluate(request.before_config, request.split, request.judge, update_progress)
                after = evaluate(request.after_config, request.split, request.judge, update_progress)
                result = compare_runs(before['run_id'], after['run_id'], 'test' if request.split != 'dev' else 'dev')
                write_json(ROOT / 'runtime/comparisons' / (after['run_id'] + '.json'), result)
            with job_lock:
                jobs[job_id].update(status='completed', result=result)
        except Exception as exc:
            with job_lock:
                jobs[job_id].update(status='failed', error=str(exc) if isinstance(exc, (ProviderError, ValueError, FileNotFoundError)) else type(exc).__name__)
    pool.submit(work)
    return {'id': job_id, 'status': 'queued'}


@app.get('/api/jobs/{job_id}')
def get_job(job_id: str):
    with job_lock:
        if job_id not in jobs:
            raise HTTPException(404, 'Job not found; job handles do not survive server restarts')
        return dict(jobs[job_id])


@app.get('/api/runs')
def list_runs():
    runs = []
    for path in sorted((ROOT / 'runtime/runs').glob('*/manifest.json'), reverse=True):
        manifest = json.loads(path.read_text())
        summary = path.parent / 'summary.json'
        runs.append({'manifest': manifest, 'summary': json.loads(summary.read_text()) if summary.exists() else None})
    return runs


@app.get('/api/runs/{run_id}')
def get_run(run_id: str):
    folder = run_folder(run_id)
    return {'manifest': json.loads((folder / 'manifest.json').read_text()),
            'summary': json.loads((folder / 'summary.json').read_text()) if (folder / 'summary.json').exists() else None,
            'predictions': read_jsonl(folder / 'predictions.jsonl') if (folder / 'predictions.jsonl').exists() else [],
            'calibration': calibration(run_id) if (folder / 'predictions.jsonl').exists() else {'status': 'pending', 'n': 0}}


@app.get('/api/compare')
def comparison(before: str, after: str, split: Literal['all', 'dev', 'test'] = 'test'):
    return compare_runs(before, after, split)


class HumanReview(BaseModel):
    question_id: str
    correctness: int = Field(ge=0, le=2)
    faithful: bool
    notes: str = Field(default='', max_length=3000)
    reviewed_by_human: Literal[True]


@app.post('/api/runs/{run_id}/reviews')
def save_review(run_id: str, review: HumanReview):
    folder = run_folder(run_id)
    rows = {r['id']: r for r in read_jsonl(folder / 'predictions.jsonl')}
    if review.question_id not in rows or not rows[review.question_id].get('response'):
        raise HTTPException(400, 'Select an existing generated response')
    with review_lock:
        path = folder / 'human_reviews.json'
        reviews = json.loads(path.read_text()) if path.exists() else {}
        reviews[review.question_id] = {**review.model_dump(), 'response_sha256': digest(rows[review.question_id]['response']),
                                       'saved_at_unix': time.time()}
        write_json(path, reviews)
    return calibration(run_id)


@app.get('/')
def home():
    return FileResponse(ROOT / 'src/groundwork/web/index.html')


@app.get('/docs', include_in_schema=False)
def api_reference():
    return FileResponse(ROOT / 'src/groundwork/web/api-docs.html')


app.mount('/assets', StaticFiles(directory=ROOT / 'src/groundwork/web'), name='assets')
