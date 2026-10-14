"""Explicitly export only completed runs of the checked-in public benchmark."""
import argparse
import json
import shutil

from groundwork.evaluation import compare_runs, run_folder
from groundwork.io import digest, read_jsonl, write_json, atomic_text
from groundwork.settings import ROOT

parser=argparse.ArgumentParser()
parser.add_argument('--before',required=True)
parser.add_argument('--after',required=True)
parser.add_argument('--name',default='local-v1')
parser.add_argument('--split', choices=('all','dev','test'), action='append',
                    help='Splits to export; repeat for multiple. Default: all, dev, test.')
args=parser.parse_args()
if not args.name.replace('-','').isalnum():
    raise SystemExit('Invalid report directory name')
gold={x['id']:x for x in read_jsonl(ROOT/'data/gold.jsonl')}
target=ROOT/'reports'/args.name
# Validate comparisons before writing a partially exported report.
comparisons={split:compare_runs(args.before,args.after,split) for split in (args.split or ('all','dev','test'))}
for run_id in (args.before,args.after):
    folder=run_folder(run_id)
    manifest=json.loads((folder/'manifest.json').read_text())
    if manifest['status']!='completed' or manifest['gold_sha256']!=digest((ROOT/'data/gold.jsonl').read_bytes()):
        raise SystemExit('Only completed runs of the current public benchmark may be exported')
    rows=read_jsonl(folder/'predictions.jsonl')
    if any(r['id'] not in gold or r['question']!=gold[r['id']]['question'] for r in rows):
        raise SystemExit('Question content is not the public benchmark')
    destination=target/run_id
    destination.mkdir(parents=True,exist_ok=True)
    for filename in ('manifest.json','predictions.jsonl','summary.json','report.md'):
        shutil.copyfile(folder/filename,destination/filename)
for split,comparison in comparisons.items():
    write_json(target/f'comparison-{split}.json',comparison)
table=['# Measured benchmark comparison','',f'Before: `{args.before}`',f'After: `{args.after}`','',
       'These are actual local model executions. Null semantic scores were not measured.',
       'Predictions contain only public benchmark questions and source excerpts (CC BY-SA 4.0).','']
for split,result in comparisons.items():
    table.extend([f'## {split} ({result["n"]} questions)','', '| Metric | Before | After | Delta (pp) |','| --- | ---: | ---: | ---: |'])
    for name,m in result['metrics'].items():
        values=['N/A' if m[k] is None else f'{m[k]*100:.2f}' for k in ('before','after','delta')]
        table.append(f'| {name} | '+ ' | '.join(values)+' |')
    table.append('')
atomic_text(target/'METRICS.md','\n'.join(table).rstrip()+'\n')
print(target)
