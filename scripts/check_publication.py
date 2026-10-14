"""Check tracked content without printing matched secrets or private wording."""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
files = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
patterns = [re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
            re.compile(rb'gh[pousr]_[A-Za-z0-9]{30,}'),
            re.compile(rb'sk-[A-Za-z0-9_-]{24,}')]
forbidden = [x.casefold().encode() for x in sys.argv[1:]]
failures = []
for name in files:
    if not name:
        continue
    path = ROOT/name
    if path.name.startswith('.env') and path.name != '.env.example':
        failures.append((name, 'tracked environment file'))
    if not path.is_file():
        continue
    content=path.read_bytes()
    if any(p.search(content) for p in patterns):
        failures.append((name, 'credential-like pattern'))
    if any(word in content.lower() for word in forbidden):
        failures.append((name, 'restricted wording'))
for filename, reason in failures:
    print(f'{filename}: {reason}')
print(f'Checked {len([x for x in files if x])} tracked files; findings={len(failures)}')
raise SystemExit(bool(failures))
