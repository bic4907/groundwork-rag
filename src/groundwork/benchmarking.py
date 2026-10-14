"""Sequential, persisted evaluation of every registered RAG baseline."""
from datetime import datetime, timezone
import uuid

from .evaluation import compare_runs, evaluate
from .io import read_jsonl, write_json
from .providers import Models
from .retrieval import ingest
from .settings import ROOT, Settings, load_config

SUITE_CONFIGS = ('baseline', 'bm25', 'hybrid', 'sufficient')


def run_suite(split='all', use_judge=False, progress=None):
    if split not in {'all', 'dev', 'test'}:
        raise ValueError('Invalid split')
    count = sum(split == 'all' or row['split'] == split
                for row in read_jsonl(ROOT / 'data/gold.jsonl'))
    if not count:
        raise ValueError('No questions in the selected split')
    suite_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-suite-' + uuid.uuid4().hex[:6]
    path = ROOT / 'runtime/suites' / (suite_id + '.json')
    state = {'suite_id': suite_id, 'status': 'running', 'split': split,
             'configs': list(SUITE_CONFIGS), 'runs': [], 'comparisons': [], 'progress': None,
             'created_at': datetime.now(timezone.utc).isoformat()}
    write_json(path, state)
    try:
        for position, config in enumerate(SUITE_CONFIGS, 1):
            def update(value):
                item = {**value, 'config': config, 'config_index': position,
                        'config_count': len(SUITE_CONFIGS),
                        'overall_completed': (position-1)*count + value['completed'],
                        'overall_total': len(SUITE_CONFIGS)*count}
                state['progress'] = item
                write_json(path, state)
                if progress:
                    progress(item)
            update({'completed': 0, 'total': count, 'question': 'Preparing index'})
            ingest(load_config(config), Models(Settings()))
            result = evaluate(config, split, use_judge, update)
            state['runs'].append({'config': config, 'run_id': result['run_id']})
            write_json(path, state)
        splits = ('all', 'dev', 'test') if split == 'all' else (split,)
        for after in state['runs'][1:]:
            for part in splits:
                report = compare_runs(state['runs'][0]['run_id'], after['run_id'], part)
                relative = 'runtime/comparisons/' + suite_id + '-' + after['config'] + '-' + part + '.json'
                write_json(ROOT / relative, report)
                state['comparisons'].append({'config': after['config'], 'split': part, 'path': relative})
        state.update(status='completed', completed_at=datetime.now(timezone.utc).isoformat())
        write_json(path, state)
        return state
    except Exception as exc:
        # Persist partial progress without exposing provider exception payloads.
        state.update(status='failed', error_type=type(exc).__name__)
        write_json(path, state)
        raise
