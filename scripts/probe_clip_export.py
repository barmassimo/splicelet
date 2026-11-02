"""Integration checks: exact cut boundaries, cancellation, no overwrite, source hash."""
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
from test_fixture import ensure_fixture
import sys
import tempfile
import threading

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import av
import numpy as np
from PySide6.QtCore import QCoreApplication, Qt
from splicelet.source import inspect_and_index
from splicelet.editing import Clip,Clips
from splicelet.exporting import ExportSpec,ExportTask,validate_destination

app=QCoreApplication([])
source=(Path(sys.argv[1]) if len(sys.argv)>1 else ensure_fixture()).resolve(strict=True)
out=ROOT/'artifacts'/'export-tests'
out.mkdir(parents=True,exist_ok=True)
run=Path(tempfile.mkdtemp(prefix='run-',dir=out))
checks=[]

def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): digest.update(chunk)
    return digest.hexdigest()

before=sha(source)
data={}
inspect_and_index(str(source),threading.Event(),lambda kind,value:data.__setitem__(kind,value))
assert 'error' not in data,data.get('error')
metadata,index=data['metadata'],data['index']
pts=index['pts']; base=Fraction(index['time_base'])

def spec(a,b):
    end=pts[b] if b<len(pts) else round((metadata['origin']+metadata['duration'])/float(base))
    times=[p*base-Fraction(str(metadata['origin'])) for p in pts]
    model=Clips(len(pts),times,Fraction(str(metadata['duration'])))
    clip=Clip(0,Fraction(0),((a,b),)); model.clips=[clip]
    parts=model.parts()
    return ExportSpec(str(source),a,b,pts[a],end,base,metadata['origin'],metadata['audio_timeline'],
                      parts=parts,timeline_start=0.,timeline_end=float(model.length(clip)),
                      audio_parts=parts,audio_effects=(),video_effects=(),
                      fps=metadata['fps'],width=metadata['width'],height=metadata['height'],source_pts=tuple(pts))

def record(name,**details):
    checks.append({'name':name,'status':'pass',**details})
    print('PASS',name,details,flush=True)

try:
    model=Clips(len(pts))
    assert model.split(37) and model.split(97)
    assert not model.split(37) and not model.split(0)
    model.select(1)
    assert model.selected_frames==(37,97)
    model.undo();assert model.boundaries==[0,37,len(pts)]
    model.redo();assert model.boundaries==[0,37,97,len(pts)]
    record('split_select_undo_redo')

    for a,b,label in ((37,97,'middle'),(37,38,'one-frame'),(len(pts)-8,len(pts),'tail')):
        target=run/f'{label}.mp4'
        job=spec(a,b)
        result,message=ExportTask()._execute(job,target)
        assert result=='success',message
        minimum_psnr=math.inf
        timestamps=[]
        with av.open(str(source)) as original,av.open(str(target)) as rendered:
            stream=original.streams.video[0]
            original.seek(pts[a],stream=stream,backward=True)
            reference=(f for f in original.decode(stream) if f.pts>=pts[a])
            frames=0
            for frame in rendered.decode(video=0):
                expected=next(reference)
                expected_time=(expected.pts-pts[a])*base
                actual_time=frame.pts*frame.time_base
                assert abs(actual_time-expected_time)<=Fraction(1,1000),(actual_time,expected_time)
                actual=frame.to_ndarray(format='yuv420p').astype(np.float32)
                expected_pixels=expected.to_ndarray(format='yuv420p').astype(np.float32)
                mse=float(np.mean((actual-expected_pixels)**2))
                psnr=10*math.log10(255**2/mse) if mse else math.inf
                minimum_psnr=min(minimum_psnr,psnr)
                frames+=1
            assert frames==b-a,(frames,b-a)
            assert minimum_psnr>30,minimum_psnr
        with av.open(str(target)) as rendered:
            audio=rendered.streams.audio[0]
            audio_duration=float(audio.duration*audio.time_base)
            assert abs(audio_duration-job.duration)<.003,(audio_duration,job.duration)
        record('export_'+label,frames=frames,duration_seconds=job.duration,min_psnr_db=minimum_psnr,file=str(target))

    sentinel=run/'existing.mp4';sentinel.write_bytes(b'KEEP EXISTING FILE')
    fixture=run/'fixture-source.bin';fixture.write_bytes(b'UNCHANGED SOURCE FIXTURE')
    alias=run/'source-hardlink.mp4'
    os.link(fixture,alias)
    try:
        for input_path,target in ((source,source),(source,sentinel),(fixture,alias)):
            try: validate_destination(input_path,target)
            except ValueError: pass
            else: raise AssertionError(f'Unsafe destination accepted: {target}')
    finally:
        alias.unlink()
    assert sentinel.read_bytes()==b'KEEP EXISTING FILE'
    assert fixture.read_bytes()==b'UNCHANGED SOURCE FIXTURE'
    record('source_existing_file_and_hardlink_destinations_rejected')

    target=run/'created-during-export.mp4'
    task=ExportTask()
    def create_late(fraction,text):
        if text=='Exporting MP4…' and not target.exists(): target.write_bytes(b'LATE FILE')
    task.updated.connect(create_late,Qt.ConnectionType.DirectConnection)
    result,_=task._execute(spec(37,97),target)
    assert result=='error' and target.read_bytes()==b'LATE FILE'
    record('destination_race_does_not_overwrite')

    target=run/'cancelled.mp4'
    task=ExportTask()
    def cancel_running(fraction,text):
        if text=='Exporting MP4…' and fraction>.10001: task.cancel()
    task.updated.connect(cancel_running,Qt.ConnectionType.DirectConnection)
    watchdog=threading.Timer(8,task.cancel)
    watchdog.start()
    try: result,message=task._execute(spec(0,min(3600,len(pts))),target)
    finally: watchdog.cancel()
    assert result=='cancelled' and not target.exists(),(result,message)
    assert not list(run.glob('.video-export-*'))
    record('cancel_cleans_temporary_files_and_leaves_no_destination')
    assert sha(source)==before
    record('original_sha256_unchanged',sha256=before)
except Exception:
    import traceback
    checks.append({'name':'failure','status':'fail','error':traceback.format_exc()})
finally:
    report={'checks':checks,'status':'pass' if all(c['status']=='pass' for c in checks) else 'fail','output_directory':str(run)}
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2),flush=True)
sys.exit(0 if report['status']=='pass' else 1)
