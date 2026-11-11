"""Run maintained probes sequentially with generated media and per-process logs."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from test_fixture import ensure_fixture


ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--portable',action='store_true',help='Also test an already built portable folder.')
args = parser.parse_args()
fixture = ensure_fixture()
output = ROOT/'artifacts'/'test-suite'/datetime.now().strftime('%Y%m%d-%H%M%S-%f')
output.mkdir(parents=True)
runtime = Path(sys.executable).parent
env = os.environ.copy()
env['PATH'] = os.pathsep.join([str(runtime),str(runtime/'Library'/'bin'),str(runtime/'Scripts'),env.get('PATH','')])
env['CONDA_PREFIX'] = str(runtime)
commands = [
    ('synthetic-source',['scripts/probe_source.py','--ffmpeg',str(runtime/'Library/bin/ffmpeg.exe'),
                         '--ffprobe',str(runtime/'Library/bin/ffprobe.exe')]),
    ('smoke',['-m','splicelet',str(fixture),'--smoke-test']),
]
commands.extend((name.removeprefix('probe_'),[f'scripts/{name}.py']) for name in (
    'probe_appearance','probe_audio_tracks','probe_clip_effects','probe_clip_export',
    'probe_crossfades','probe_edge_space','probe_export_options','probe_export_seeks','probe_group_edits',
    'probe_layout','probe_multi_source','probe_playhead_clock','probe_projects',
    'probe_splicelet_audio','probe_timeline_edits','probe_timeline_visuals','probe_real_source'))
if args.portable:
    commands.append(('portable',['scripts/probe_portable.py']))
report = {'fixture':str(fixture.relative_to(ROOT)),'checks':[],
          'expected_checks':len(commands),'complete':False,
          'limitations':['Synthetic correctness/UI checks; no physical listening or real-footage performance claim.',
                         'Portable check requires a separately built executable.']}
for name,arguments in commands:
    print(f'RUN {name}',flush=True)
    started = time.monotonic()
    entry = {'name':name,'command':[sys.executable,*arguments],'log':f'{name}.log'}
    with (output/entry['log']).open('wb') as log:
        try:
            with subprocess.Popen([sys.executable,*arguments],cwd=ROOT,env=env,
                                  stdout=log,stderr=subprocess.STDOUT) as process:
                try:
                    returncode = process.wait(timeout=300)
                except (subprocess.TimeoutExpired,KeyboardInterrupt):
                    taskkill = Path(env.get('SystemRoot','C:/Windows'))/'System32'/'taskkill.exe'
                    try:
                        subprocess.run([str(taskkill),'/PID',str(process.pid),'/T','/F'],
                                       stdout=log,stderr=subprocess.STDOUT,timeout=15)
                    finally:
                        if process.poll() is None:
                            process.kill()
                        process.wait()
                    raise
            entry.update(returncode=returncode,status='pass' if returncode==0 else 'fail')
        except subprocess.TimeoutExpired:
            entry.update(status='fail',error='Process exceeded 300 seconds.')
    entry['seconds'] = round(time.monotonic()-started,2)
    report['checks'].append(entry)
    report['status'] = 'pass' if all(check['status']=='pass' for check in report['checks']) else 'fail'
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(f'{entry["status"].upper()} {name} ({entry["seconds"]} s)',flush=True)
report['complete'] = True
(output/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(f'Report: {output.relative_to(ROOT) / "report.json"}',flush=True)
sys.exit(0 if report['status']=='pass' else 1)
