"""Real decoder/export tests of fades and non-destructive joins on synthetic source."""
from dataclasses import replace
from fractions import Fraction
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import av
import numpy as np
from PySide6.QtCore import QCoreApplication
from splicelet.effects import Fades,EffectSpan,video_gain
from splicelet.editing import Clips
from splicelet.source import Decoder,Job,inspect_and_index
from splicelet.exporting import ExportSpec,ExportTask

app=QCoreApplication([])
out=ROOT/'artifacts'/'effects-tests'
out.mkdir(parents=True,exist_ok=True)
run=Path(tempfile.mkdtemp(prefix='run-',dir=out))
ffmpeg=Path(sys.executable).parent/'Library/bin/ffmpeg.exe'
source=run/'white-and-tone.mkv'
checks=[]

def record(name,**details):
    checks.append({'name':name,'status':'pass',**details})
    print('PASS',name,details,flush=True)

try:
    subprocess.run([str(ffmpeg),'-v','error','-n','-f','lavfi','-i','color=white:size=320x180:rate=30:duration=4',
                    '-f','lavfi','-i','aevalsrc=0.25*sin(2*PI*440*t)|0.125*sin(2*PI*880*t):s=48000:d=4',
                    '-c:v','libx264','-crf','0','-threads','4','-c:a','pcm_s24le',str(source)],check=True,timeout=30)
    data={}
    inspect_and_index(str(source),threading.Event(),lambda kind,value:data.__setitem__(kind,value))
    assert 'error' not in data,data.get('error')
    audio=data['metadata']['audio_timeline']
    base=Fraction(data['index']['time_base'])
    fades=Fades(.5,1.,.5,1.)
    span=EffectSpan(0.,4.,fades)
    spec=ExportSpec(str(source),0,120,0,round(4/float(base)),base,0.,audio,fades)
    task=ExportTask()
    pcm=run/'faded.f32le'
    task._audio(spec,pcm)
    actual=np.fromfile(pcm,dtype='<f4')
    reference=subprocess.check_output([str(ffmpeg),'-v','error','-i',str(source),'-map','0:a:0','-af',
              'aformat=sample_fmts=flt,afade=t=in:ss=0:ns=24000,afade=t=out:ss=144000:ns=48000',
              '-f','f32le','-'],timeout=30)
    expected=np.frombuffer(reference,dtype='<f4')
    assert actual.shape==expected.shape
    difference=float(np.max(abs(actual-expected)))
    assert difference<1e-7,difference
    record('audio_preview_export_envelope_matches_independent_ffmpeg',max_sample_error=difference,samples_per_channel=len(actual)//2)

    worker=Decoder('audio')
    worker.request(1,Job(1,str(source),3.25,0.,3.75,True,audio,(span,)))
    chunks=[];deadline=time.monotonic()+5
    try:
        while True:
            chunk=worker.take_audio(8192)
            if chunk:chunks.append(chunk)
            count,_,eof,error=worker.status()
            assert not error,error
            if eof and not count:break
            assert time.monotonic()<deadline
            time.sleep(.001)
    finally:
        worker.close();worker.thread.join(2)
    sought=np.frombuffer(b''.join(chunks),dtype='<f4')
    assert np.array_equal(sought,actual[round(3.25*48000)*2:round(3.75*48000)*2])
    record('audio_seek_keeps_original_fade_phase')

    result,message=task._execute(spec,run/'fades.mp4')
    assert result=='success',message
    errors=[];count=0
    with av.open(str(run/'fades.mp4')) as container:
        for frame in container.decode(video=0):
            position=float(frame.pts*frame.time_base)
            mean=float(frame.to_ndarray(format='rgb24').mean())
            errors.append(abs(mean-255*video_gain(position,span)))
            count+=1
    assert count==120
    assert max(errors)<5,max(errors)
    record('black_video_fades_match_preview_opacity',max_rgb_luma_error=max(errors),frames=count)

    long_fades=Fades(10.,12.,10.,12.)
    long_spec=replace(spec,fades=long_fades)
    result,message=task._execute(long_spec,run/'long-fades.mp4')
    assert result=='success',message
    with av.open(str(run/'long-fades.mp4')) as container:
        errors=[abs(float(frame.to_ndarray(format='rgb24').mean())-255*video_gain(float(frame.pts*frame.time_base),EffectSpan(0.,4.,long_fades))) for frame in container.decode(video=0)]
    assert max(errors)<5,max(errors)
    record('values_above_slider_range_and_overlapping_fades',max_rgb_error=max(errors))

    model=Clips(120)
    for cut in (30,60,90):assert model.split(cut)
    model.select(0);model.set_fade('audio_in',.3);model.set_fade('video_in',.4)
    model.select(1);model.set_fade('audio_out',.5);model.set_fade('video_out',.6)
    model.select(0);model.select(1,True)
    assert model.can_join and model.selected==-1
    assert model.join() and model.boundaries==[0,60,90,120]
    assert model.effects[0]==Fades(.3,.5,.4,.6)
    model.undo();assert model.boundaries==[0,30,60,90,120] and model.selected_indices=={0,1}
    model.redo();assert model.boundaries==[0,60,90,120]
    record('join_preserves_outer_fades_and_undo_restores_clips')
    model.select(0);model.select(2,True)
    assert not model.join()
    model.select(0);model.select(0,True)
    assert model.selected_indices==set() and model.selected==-1
    model.select(0)
    assert model.set_fade('video_in',8.25)
    assert not model.set_fade('video_in',float('nan')) and not model.set_fade('video_in',-1)
    assert model.split(15)
    assert model.effects[0].video_in==8.25 and model.effects[0].video_out==0
    assert model.effects[1].video_in==0 and model.effects[1].video_out==.6
    record('multi_selection_empty_selection_join_validation_and_split_fades')
except Exception:
    import traceback
    checks.append({'name':'failure','status':'fail','error':traceback.format_exc()})
finally:
    report={'checks':checks,'status':'pass' if all(c['status']=='pass' for c in checks) else 'fail','output_directory':str(run)}
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2),flush=True)
sys.exit(0 if report['status']=='pass' else 1)
