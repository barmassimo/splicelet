"""Late source cuts: decoded export equality with and without bounded input seeks."""
from bisect import bisect_left
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import av
import numpy as np
from PySide6.QtCore import QCoreApplication
from splicelet.editing import Clip,Clips
from splicelet.effects import Fades
from splicelet.exporting import ExportSpec,ExportTask
from splicelet.source import inspect_and_index
from test_fixture import ensure_fixture

app = QCoreApplication([])
out = ROOT/'artifacts/export-seek-tests'
out.mkdir(parents=True,exist_ok=True)
run = Path(tempfile.mkdtemp(prefix='run-',dir=out))
source = ensure_fixture()
data = {}
inspect_and_index(str(source),threading.Event(),lambda kind,value:data.__setitem__(kind,value))
assert 'error' not in data,data
metadata,index = data['metadata'],data['index']
base = Fraction(index['time_base']); pts = tuple(index['pts'])
times = tuple(p*base-Fraction(str(metadata['origin'])) for p in pts)
first = bisect_left(times,Fraction(240))
checks = []

def decoded(path,kind):
    with av.open(str(path)) as container:
        return [(str(f.pts*f.time_base),hashlib.sha256(f.to_ndarray().tobytes()).hexdigest())
                for f in container.decode(**{kind:0})]

for name,clips,start,end in (
    ('late-overlap',[Clip(0,Fraction(0),((first,first+90),)),
                     Clip(1,Fraction(2),((first-120,first-30),),Fades(audio_out=.3))],0.,5.),
    ('partial-overlap',[Clip(0,Fraction(0),((first,first+90),)),
                        Clip(1,Fraction(2),((first-120,first-30),))],2.123,2.789),
    ('reordered-gap',[Clip(0,Fraction(0),((first,first+30),)),
                      Clip(1,Fraction(2),((first-120,first-90),))],0.,3.),
    ('one-frame',[Clip(0,Fraction(0),((first,first+1),))],0.,float(times[first+1]-times[first])),
    ('irregular-tail',[Clip(0,Fraction(0),((len(pts)-8,len(pts)),))],0.,None),
):
    model = Clips(len(pts),times,Fraction(str(metadata['duration']))-Fraction(str(metadata['origin'])))
    model.clips = clips
    end = end if end is not None else float(model.end(clips[-1]))
    spec = ExportSpec(str(source),0,len(pts),pts[0],round(metadata['duration']/float(base)),base,
                      metadata['origin'],metadata['audio_timeline'],parts=model.parts(),
                      timeline_start=start,timeline_end=end,audio_parts=model.parts(),
                      audio_effects=model.effect_spans(),video_effects=model.effect_spans(),
                      fps=metadata['fps'],width=metadata['width'],height=metadata['height'],source_pts=pts)
    durations = {}
    for bounded in (False,True):
        target = run/f'{name}-{bounded}.mp4'
        task = ExportTask(); began = time.monotonic()
        if bounded:
            status,message = task._execute(spec,target)
        else:
            with patch('splicelet.exporting.video_input_window',return_value=[]):
                status,message = task._execute(spec,target)
        assert status=='success',message
        durations[str(bounded)] = time.monotonic()-began
    for kind in ('video','audio'):
        a,b = decoded(run/f'{name}-False.mp4',kind),decoded(run/f'{name}-True.mp4',kind)
        assert a and a==b,(name,kind,len(a),len(b))
    checks.append({'name':name,'status':'pass','seconds_unbounded_bounded':durations})
    print('PASS',name,durations,flush=True)

# A partial window can begin seconds after its covering source frame. Also use
# a fractional, nonzero container origin so seek offsets cannot assume zero.
sparse = run/'sparse-offset.nut'
with av.open(str(sparse),'w',format='nut') as output:
    stream = output.add_stream('ffv1',rate=30)
    stream.width,stream.height,stream.pix_fmt = 160,90,'bgr0'
    stream.time_base = stream.codec_context.time_base = Fraction(1,1000)
    for i,stamp in enumerate((17125,17400,19125,20125,28125,29125)):
        pixels = np.full((90,160,3),20+i*30,dtype=np.uint8)
        frame = av.VideoFrame.from_ndarray(pixels,format='rgb24')
        frame.pts,frame.time_base = stamp,Fraction(1,1000)
        for packet in stream.encode(frame): output.mux(packet)
    for packet in stream.encode(): output.mux(packet)
with av.open(str(sparse)) as container:
    frames = list(container.decode(video=0))
vbase = frames[0].time_base; vpts = tuple(f.pts for f in frames)
origin = vpts[0]*vbase
model = Clips(len(vpts),tuple(p*vbase-origin for p in vpts),Fraction(13))
vspec = ExportSpec(str(sparse),0,len(vpts),vpts[0],round((origin+13)/vbase),vbase,float(origin),None,
                   parts=model.parts(),timeline_start=5.345,timeline_end=6.789,
                   video_effects=model.effect_spans(),width=160,height=90,source_pts=vpts)
with patch('splicelet.exporting.video_input_window',return_value=[]):
    status,message = ExportTask()._execute(vspec,run/'sparse-reference.mp4')
assert status=='success',message
status,message = ExportTask()._execute(vspec,run/'sparse-bounded.mp4')
assert status=='success',message
reference = decoded(run/'sparse-reference.mp4','video')
assert reference and reference==decoded(run/'sparse-bounded.mp4','video')
checks.append({'name':'long-vfr-hold-with-fractional-container-origin','status':'pass'})
print('PASS long-vfr-hold-with-fractional-container-origin',flush=True)

(out/'report.json').write_text(json.dumps({'checks':checks,'run':str(run)},indent=2),encoding='utf-8')
print('Report:',out/'report.json')
