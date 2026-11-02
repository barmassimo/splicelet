"""Run the bundled application with no development runtime in its environment."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from test_fixture import ensure_fixture
import subprocess
import time


parser = argparse.ArgumentParser()
parser.add_argument('source',type=Path,nargs='?',help='Defaults to the generated integration fixture.')
parser.add_argument('--exe',type=Path,default=Path('artifacts/portable/Splicelet/Splicelet.exe'))
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
exe = args.exe.resolve(strict=True)
source = (args.source or ensure_fixture()).resolve(strict=True)
out = root/'artifacts'/'portable-tests'
cwd = out/'unrelated working directory'
cwd.mkdir(parents=True,exist_ok=True)


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


env = {key:value for key,value in os.environ.items()
       if not key.upper().startswith(('CONDA','PYTHON','QT_','QML','_CE_'))}
env['PATH'] = str(Path(env.get('SystemRoot','C:/Windows'))/'System32')
before = sha(source)
started = time.time()
report = {'executable':str(exe),'source':str(source),'cwd':str(cwd),
          'path':env['PATH'],'status':'fail',
          'limitations':['Same Windows computer as development; not a clean-machine test.',
                         'Offscreen rendering and muted audio.']}
try:
    process = subprocess.run([str(exe),str(source),'--smoke-test'],cwd=cwd,env=env,timeout=120)
    report['exit_code'] = process.returncode
    smoke_path = exe.parent/'artifacts'/'smoke-tests'/'smoke-report.json'
    assert smoke_path.stat().st_mtime>=started,'No fresh bundled smoke report.'
    smoke = json.loads(smoke_path.read_text(encoding='utf-8'))
    report['smoke_report'] = str(smoke_path)
    report['smoke_checks'] = len(smoke['checks'])
    assert process.returncode==0 and smoke['status']=='pass',smoke
    report['status'] = 'pass'
except Exception as exc:
    report['error'] = str(exc)
finally:
    report['source_unchanged'] = sha(source)==before
    if not report['source_unchanged']: report['status'] = 'fail'
    report['elapsed_seconds'] = time.time()-started
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
raise SystemExit(0 if report['status']=='pass' else 1)
