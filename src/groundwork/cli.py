import json
from pathlib import Path

import typer

from .benchmarking import run_suite
from .dataset import build_dataset
from .evaluation import calibration, compare_runs, evaluate, run_folder
from .io import write_json
from .pipeline import Pipeline
from .providers import Models
from .retrieval import ingest as build_index
from .settings import ROOT, Settings, load_config

app = typer.Typer(help='Groundwork evidence and evaluation workbench')


@app.command()
def dataset():
    """Rebuild the versioned public corpus and gold set."""
    typer.echo(json.dumps(build_dataset(), indent=2))


@app.command()
def ingest(config: str = 'baseline'):
    """Build a persistent, content-addressed embedding index."""
    typer.echo(json.dumps(build_index(load_config(config), Models(Settings())), indent=2))


@app.command()
def ask(question: str, config: str = 'hybrid'):
    """Ask a question and print the full evidence trace."""
    typer.echo(json.dumps(Pipeline(load_config(config), Models(Settings())).answer(question), indent=2, ensure_ascii=False))


@app.command('eval')
def eval_command(config: str = 'baseline', split: str = 'all', judge: bool = False, limit: int | None = None):
    """Run the full gold set and persist scores plus per-question traces."""
    result = evaluate(config, split, judge, lambda x: typer.echo(json.dumps(x)), limit)
    typer.echo(json.dumps({'run_id': result['run_id'], 'summary': result['summary']}, indent=2))


@app.command()
def compare(before: str, after: str, split: str = 'test', output: Path | None = None,
            max_recall_drop: float | None = None, max_f1_drop: float | None = None):
    """Compare compatible paired runs; optional thresholds provide CI exit gates."""
    report = compare_runs(before, after, split)
    if output:
        write_json(output, report)
    typer.echo(json.dumps(report, indent=2))
    for key, threshold in [('evidence_recall', max_recall_drop), ('answer_token_f1', max_f1_drop)]:
        delta = report['metrics'][key]['delta']
        if threshold is not None and (delta is None or delta < -threshold):
            raise typer.Exit(code=1)


@app.command()
def experiment(split: str = 'all', judge: bool = False, before: str = 'baseline', after: str = 'hybrid'):
    """Run a paired experiment; e.g. --before baseline --after sufficient --split dev."""
    load_config(before)
    load_config(after)
    outputs = []
    for config in (before, after):
        build_index(load_config(config), Models(Settings()))
        outputs.append(evaluate(config, split, judge, lambda x: typer.echo(json.dumps(x))))
    report = compare_runs(outputs[0]['run_id'], outputs[1]['run_id'], 'test' if split != 'dev' else 'dev')
    path = ROOT / 'runtime/comparisons' / (outputs[1]['run_id'] + '.json')
    write_json(path, report)
    typer.echo(json.dumps({'comparison': str(path), 'runs': [r['run_id'] for r in outputs], 'metrics': report['metrics']}, indent=2))


@app.command()
def benchmark(split: str = 'all', judge: bool = False):
    """Evaluate Dense, BM25, Hybrid and Sufficiency sequentially, then compare."""
    result = run_suite(split, judge, lambda x: typer.echo(json.dumps(x)))
    typer.echo(json.dumps(result, indent=2))


@app.command()
def calibrate(run: str):
    """Measure agreement against actual human review labels."""
    typer.echo(json.dumps(calibration(run), indent=2))


@app.command()
def serve(host: str = '127.0.0.1', port: int = 8000):
    """Serve the API and browser workbench from one origin."""
    import uvicorn
    if host not in {'127.0.0.1', 'localhost', '::1'} and not Settings().app_access_token.get_secret_value():
        raise typer.BadParameter('Set APP_ACCESS_TOKEN before binding a non-loopback interface')
    uvicorn.run('groundwork.api:app', host=host, port=port, workers=1)


if __name__ == '__main__':
    app()
