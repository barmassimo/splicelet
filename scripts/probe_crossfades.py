"""Automatic crossfades: real PTS/PCM, export windows, QML gestures and history."""
from dataclasses import replace
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ.setdefault('QT_QUICK_BACKEND','software')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import av
import numpy as np
from PySide6.QtCore import QUrl,Qt,QPointF,QPoint,QCoreApplication,QEvent,QLocale
from PySide6.QtGui import QGuiApplication,QMouseEvent,QFontDatabase
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from splicelet.editing import Clip,Clips
from splicelet.tracks import Tracks
from splicelet.effects import Fades,video_gain,cross_gain
from splicelet.source import Decoder,Job,inspect_and_index
from splicelet.exporting import ExportSpec,ExportTask
from splicelet.controller import Preview,FrameProvider
from splicelet import project

OUT = ROOT/'artifacts/crossfade-tests'
OUT.mkdir(parents=True,exist_ok=True)
run = Path(tempfile.mkdtemp(prefix='run-',dir=OUT))
checks = []
def passed(name):
    checks.append(name); print('PASS',name,flush=True)

def read(kind,job,sample_format='flt'):
    worker = Decoder(kind,sample_format=sample_format,bytes_per_sample=4 if sample_format=='flt' else 2)
    worker.request(job.generation,job)
    result = []; deadline = time.monotonic()+30
    try:
        while True:
            item = worker.take_video() if kind=='video' else worker.take_audio(32768)
            if item: result.append(item)
            count,_,eof,error = worker.status()
            assert not error,error
            if eof and not count: break
            assert time.monotonic()<deadline,'Decoder timeout'
            time.sleep(.001)
    finally:
        worker.close(); worker.thread.join(3)
    return result if kind=='video' else np.frombuffer(b''.join(result),dtype='<f4' if sample_format=='flt' else '<i2').reshape(-1,2)

QLocale.setDefault(QLocale('en_US'))
app = QGuiApplication([]); QQuickStyle.setStyle('Basic')
if not QFontDatabase.families():
    QFontDatabase.addApplicationFont(str(Path(os.environ.get('SystemRoot','C:/Windows'))/'Fonts'/'segoeui.ttf'))
ffmpeg = Path(sys.executable).parent/'Library/bin/ffmpeg.exe'
source = run/'red-blue.mkv'
subprocess.run([str(ffmpeg),'-v','error','-n','-f','lavfi','-i','color=red:s=320x180:r=30:d=2',
                '-f','lavfi','-i','color=blue:s=320x180:r=30:d=2',
                '-f','lavfi','-i','aevalsrc=if(lt(t\\,2)\\,0.2\\,-0.1)|if(lt(t\\,2)\\,0.1\\,-0.2):s=48000:d=4',
                '-filter_complex','[0:v][1:v]concat=n=2:v=1:a=0[v]','-map','[v]','-map','2:a',
                '-c:v','libx264','-crf','0','-threads','4','-c:a','pcm_s24le',str(source)],check=True,timeout=30)
digest = hashlib.sha256(source.read_bytes()).hexdigest()
data = {}
inspect_and_index(str(source),threading.Event(),lambda kind,value:data.__setitem__(kind,value))
assert 'error' not in data,data
base = Fraction(data['index']['time_base']); pts = tuple(data['index']['pts'])
times = tuple(p*base for p in pts)
audio = data['metadata']['audio_timeline']
model = Tracks(Clips(len(times),times,Fraction(4)))
assert model.split_at(2)
before = model.snapshot()
assert model.move_selection(1,1) and model.video.has_overlaps
assert model.duration==3 and model.video.clips==model.audio.clips
after = model.snapshot(); model.undo(); assert model.snapshot()==before
model.redo(); assert model.snapshot()==after
assert project.timeline(project.restore(project.document(model,source),times,4))==project.timeline(model)
assert not model.move_selection(1,0)
assert not model.split_at(1.5)
assert model.video.gaps()==()
assert model.resize(1,'left',1.5) and model.video.effect_spans()[1].cross_in==.5
assert model.video.clips[1].pieces==((75,120),)
model.undo(); assert model.snapshot()==after
assert model.resize(0,'right',1) and not model.video.has_overlaps
model.undo(); assert model.snapshot()==after
passed('linked_overlap_duration_history_project_roundtrip_and_invalid_nesting')

def job(lane='video',position=0.,duration=3.):
    lane = getattr(model,lane)
    return Job(1,str(source),position,0.,duration,True,audio,lane.effect_spans(),lane.parts(),30.,320,180,tuple(map(float,times)))

pcm = read('audio',job('audio'))
n = np.arange(144000)
alpha = np.clip((n-48000)/48000,0,1)
expected = np.column_stack((.2*(1-alpha)-.1*alpha,.1*(1-alpha)-.2*alpha))
assert pcm.shape==expected.shape and np.max(abs(pcm-expected))<2e-7,np.max(abs(pcm-expected))
sought = read('audio',job('audio',1.25,2.5))
assert np.array_equal(sought,pcm[60000:120000])
integer = read('audio',job('audio'),'s16')
assert np.max(abs(integer.astype(float)-np.rint(pcm*32768)))<=1
passed('sample_exact_linear_stereo_mix_seek_phase_and_int16')
frames = read('video',job())
assert len(frames)==90,len(frames)
assert all(a[1]<b[1] for a,b in zip(frames,frames[1:]))
assert np.allclose([f[1] for f in frames],[s for s,_ in model.frames()],atol=1e-9)
def rgb(image):
    return np.frombuffer(image.constBits(),dtype=np.uint8).reshape(image.height(),image.bytesPerLine())[:,:image.width()*3].reshape(image.height(),image.width(),3)
red,blue = rgb(frames[0][2]).astype(float),rgb(frames[-1][2]).astype(float)
for _,stamp,image in frames:
    a = np.clip(stamp-1,0,1)
    assert np.max(abs(rgb(image)-(red*(1-a)+blue*a)))<=1
seek_frames = read('video',job(position=1.5,duration=1.8))
assert np.array_equal(rgb(seek_frames[0][2]),rgb(frames[45][2]))
passed('video_linear_mix_monotonic_source_pts_frame_schedule_and_seek')

def spec(start=0.,end=3.):
    return ExportSpec(str(source),0,len(pts),pts[0],4000,base,0.,audio,
                      parts=model.video.parts(),timeline_start=start,timeline_end=end,
                      audio_parts=model.audio.parts(),audio_effects=model.audio.effect_spans(),video_effects=model.video.effect_spans(),
                      fps=30.,width=320,height=180,source_pts=pts)
task = ExportTask()
for start,end in ((0.,3.),(1.25,1.75),(2.25,2.75)):
    destination = run/f'export-{start}.mp4'
    status,message = task._execute(spec(start,end),destination)
    assert status=='success',message
    with av.open(str(destination)) as container:
        exported = list(container.decode(video=0))
    assert abs(float(exported[0].pts*exported[0].time_base))<1e-6
    for frame in exported:
        stamp = start+float(frame.pts*frame.time_base)
        a = np.clip(stamp-1,0,1)
        error = np.abs(frame.to_ndarray(format='rgb24').astype(float)-(red*(1-a)+blue*a)).mean()
        assert error<5,(stamp,error)
    if start==0: assert len(exported)==90,len(exported)
    pcm_path = run/f'export-{start}.f32le'; task._audio(spec(start,end),pcm_path)
    assert np.array_equal(np.fromfile(pcm_path,dtype='<f4').reshape(-1,2),pcm[round(start*48000):round(end*48000)])
passed('real_export_full_and_partial_transition_windows_and_unaffected_window')

model.select(1); assert model.set_fade('audio_in',.5) and model.set_fade('video_in',.5)
faded = read('audio',job('audio'))
gain = np.clip((n-48000)/24000,0,1)
manual = np.column_stack((.2*(1-alpha)-.1*alpha*gain,.1*(1-alpha)-.2*alpha*gain))
assert np.max(abs(faded-manual))<2e-7
status,message = task._execute(spec(),run/'manual-fades.mp4'); assert status=='success',message
preview_frames = read('video',job())
with av.open(str(run/'manual-fades.mp4')) as container:
    for frame,(_,stamp,image) in zip(container.decode(video=0),preview_frames):
        assert np.abs(frame.to_ndarray(format='rgb24').astype(float)-rgb(image)).mean()<5
passed('manual_fades_remain_independent_and_preview_export_agree')

# Uneven source PTS, a nonzero container origin, and an overlap edge between frames.
vfr = run/'offset-vfr.nut'
with av.open(str(vfr),'w',format='nut') as output:
    stream = output.add_stream('ffv1',rate=30)
    stream.width,stream.height,stream.pix_fmt = 320,180,'bgr0'
    stream.time_base = stream.codec_context.time_base = Fraction(1,1000)
    for i,stamp in enumerate((1000,1100,1250,1400,1600,1700,1900,2200)):
        array = np.zeros((180,320,3),dtype=np.uint8)
        array[:,:,:] = (200-i*20,i*20,30+i*20)
        frame = av.VideoFrame.from_ndarray(array,format='rgb24')
        frame.pts,frame.time_base = stamp,Fraction(1,1000)
        for packet in stream.encode(frame): output.mux(packet)
    for packet in stream.encode(): output.mux(packet)
with av.open(str(vfr)) as container:
    vframes = list(container.decode(video=0))
vbase = vframes[0].time_base
vpts = tuple(f.pts for f in vframes)
vtimes = tuple(p*vbase-1 for p in vpts)
vm = Clips(len(vtimes),vtimes,Fraction(13,10))
assert vm.split_at(.6) and vm.move(1,.4)
vjob = Job(1,str(vfr),0.,1.,float(vm.duration),True,effects=vm.effect_spans(),parts=vm.parts(),width=320,height=180,source_times=tuple(map(float,vtimes)))
mixed_frames = read('video',vjob)
assert np.allclose([f[1] for f in mixed_frames],[t for t,_ in vm.frames()],atol=1e-9)
vspec = ExportSpec(str(vfr),0,len(vpts),vpts[0],round(Fraction(23,10)/vbase),vbase,1.,None,
                   parts=vm.parts(),timeline_start=0.,timeline_end=float(vm.duration),audio_parts=(),audio_effects=(),
                   video_effects=vm.effect_spans(),width=320,height=180,source_pts=vpts)
status,message = task._execute(vspec,run/'offset-vfr.mp4'); assert status=='success',message
with av.open(str(run/'offset-vfr.mp4')) as container:
    exported = list(container.decode(video=0))
assert len(exported)==len(mixed_frames),(len(exported),len(mixed_frames))
for frame,(_,stamp,image) in zip(exported,mixed_frames):
    assert abs(float(frame.pts*frame.time_base)-stamp)<.001
    assert np.abs(frame.to_ndarray(format='rgb24').astype(float)-rgb(image)).mean()<5
passed('uneven_pts_nonzero_source_origin_and_frame_hold_at_overlap_end')

for kind in ('audio','video'):
    worker = Decoder(kind)
    try:
        worker.request(1,job('audio' if kind=='audio' else 'video'))
        time.sleep(.05)
        newer = replace(job('audio' if kind=='audio' else 'video',2.25,2.5),generation=2)
        worker.request(2,newer)
        deadline = time.monotonic()+5
        while True:
            item = worker.take_video() if kind=='video' else worker.take_audio(8192)
            if item:
                if kind=='video': assert item[0]==2 and item[1]>=2.25-1e-9
                break
            assert not worker.status()[3],worker.status()
            assert time.monotonic()<deadline
            time.sleep(.001)
    finally:
        worker.close(); worker.thread.join(3)
    assert not worker.thread.is_alive()
passed('bounded_audio_video_queues_cancel_stale_overlap_jobs')

joined = Clips(len(times),times,Fraction(4))
joined.clips = [Clip(0,Fraction(0),((0,15),(30,60))),Clip(1,Fraction(1),((60,120),)),Clip(2,Fraction(11,4),((0,30),))]
joined.extent = Fraction(15,4)
jjob = replace(job(),duration=3.75,parts=joined.parts(),effects=joined.effect_spans())
jpcm = read('audio',jjob)
samples = np.arange(180000)
a = np.clip((samples-48000)/24000,0,1)
b = np.clip((samples-132000)/12000,0,1)
reference = np.column_stack((.2*(1-a+b)-.1*(a-b),.1*(1-a+b)-.2*(a-b)))
assert np.max(abs(jpcm-reference))<2e-7
jspec = replace(spec(),parts=joined.parts(),audio_parts=joined.parts(),video_effects=joined.effect_spans(),audio_effects=joined.effect_spans(),timeline_end=3.75)
status,message = task._execute(jspec,run/'joined-transitions.mp4'); assert status=='success',message
jframes = read('video',jjob)
with av.open(str(run/'joined-transitions.mp4')) as container:
    exported = list(container.decode(video=0))
assert len(exported)==len(jframes)
for frame,(_,stamp,image) in zip(exported,jframes):
    assert abs(float(frame.pts*frame.time_base)-stamp)<.001
    assert np.abs(frame.to_ndarray(format='rgb24').astype(float)-rgb(image)).mean()<5
passed('joined_source_pieces_and_multiple_separate_transitions_preserve_mapping')

cancelled = ExportTask()
cancelled.updated.connect(lambda fraction,message:cancelled.cancel() if message=='Preparing transitions…' else None)
destination = run/'cancelled.mp4'
status,message = cancelled._execute(spec(),destination)
assert status=='cancelled' and not destination.exists() and not list(run.glob('.video-export-*'))
passed('overlap_export_cancellation_removes_lossless_transition_and_pcm_temporaries')

provider = FrameProvider(); preview = Preview(provider,muted=True)
engine = QQmlApplicationEngine(); engine.addImageProvider('frames',provider)
engine.setInitialProperties({'preview':preview}); engine.load(QUrl.fromLocalFile(str(ROOT/'splicelet/Main.qml')))
window = engine.rootObjects()[0]
def wait(predicate):
    deadline = time.monotonic()+30
    while not predicate():
        assert time.monotonic()<deadline,preview.status
        app.processEvents(); QTest.qWait(10)
try:
    preview.open_path(str(source)); wait(lambda:preview.indexedReady and not preview.busy)
    preview.seek(2); wait(lambda:not preview.busy); preview.cut(); wait(lambda:not preview.busy)
    timeline = window.findChild(QQuickItem,'editTimeline')
    def item(index): return next(c for c in timeline.childItems() if c.objectName()==f'clip-{index}')
    begin = item(1).mapToScene(QPointF(item(1).width()/2,26)).toPoint()
    end = QPoint(begin.x()-round(1/timeline.property('secondsPerPixel')),begin.y())
    QTest.mousePress(window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.AltModifier,begin)
    event = QMouseEvent(QEvent.Type.MouseMove,QPointF(end),QPointF(end),QPointF(window.mapToGlobal(end)),Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.AltModifier)
    QCoreApplication.sendEvent(window,event); QTest.qWait(50)
    QTest.mouseRelease(window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.AltModifier,end)
    wait(lambda:not preview.busy)
    assert preview._clips.video.has_overlaps and preview._clips.video.clips==preview._clips.audio.clips
    preview.seek(1.5); wait(lambda:not preview.busy); QTest.qWait(100)
    assert preview.videoGain==1.
    window.grabWindow().save(str(run/'crossfade.png'))
    def visual_item(name,parent=timeline):
        if parent.objectName()==name: return parent
        for child in parent.childItems():
            found = visual_item(name,child)
            if found is not None: return found
    for selected in (0,1,None):
        if selected is None: preview.selectClip(1,True)
        else: preview.selectClip(selected)
        QTest.qWait(70)
        overlap = visual_item('overlap-0-1')
        assert overlap and overlap.isVisible()
        audio_overlap = visual_item('overlap-1000000-1000001')
        assert audio_overlap and audio_overlap.isVisible() and audio_overlap.width()==overlap.width()
        assert abs(overlap.width()-1/timeline.property('secondsPerPixel'))<.01
        assert abs(overlap.mapToItem(timeline,QPointF()).x()-timeline.property('inset')-1/timeline.property('secondsPerPixel'))<.01
        for index in (0,1):
            outline = visual_item(f'clip-outline-{index}')
            assert outline and outline.isVisible()
            assert outline.z()==(1 if selected==index else 0)
        # Tint remains visible across the interval, and both internal borders survive.
        screenshot = window.grabWindow()
        def pixel(time,y):
            point = timeline.mapToScene(QPointF(timeline.property('inset')+time/timeline.property('secondsPerPixel'),y)).toPoint()
            return screenshot.pixelColor(point)
        inside,outside = pixel(1.8,85),pixel(2.2,85)
        assert inside.red()>outside.red()+40 and inside.green()>outside.green()+40
        for boundary_time in (1.,2.-3*timeline.property('secondsPerPixel')):
            boundary = pixel(boundary_time,80)
            assert boundary.blue()<230,(selected,boundary_time,boundary.name())
        screenshot.save(str(run/f'overlap-selected-{selected}.png'))
    preview.selectClip(1)
    passed('qml_overlap_tint_and_both_outlines_persist_for_either_or_no_selection')
    def drag_at(time, y, delta, expected_index, resizing=False):
        begin = timeline.mapToScene(QPointF(timeline.property('inset')+(time-timeline.property('viewStart'))/timeline.property('secondsPerPixel'),y)).toPoint()
        end = QPoint(begin.x()+round(delta/timeline.property('secondsPerPixel')),begin.y())
        QTest.mousePress(window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.AltModifier,begin)
        active = 'resizeIndex' if resizing else 'dragIndex'
        if resizing: assert timeline.property(active)==expected_index,(active,timeline.property(active),expected_index)
        event = QMouseEvent(QEvent.Type.MouseMove,QPointF(end),QPointF(end),QPointF(window.mapToGlobal(end)),Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.AltModifier)
        QCoreApplication.sendEvent(window,event); QTest.qWait(50)
        assert timeline.property(active)==expected_index,(active,timeline.property(active),expected_index)
        QTest.mouseRelease(window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.AltModifier,end)
        wait(lambda:not preview.busy)

    for linked in (True,False):
        if not linked: preview.unlinkAudio()
        for lane,y,offset in (('video',64,0),('audio',118,1000000)):
            for selected,delta in ((0,.2),(1,-.2)):
                preview.selectClip(offset+selected); QTest.qWait(50)
                before = preview._clips.snapshot()
                clips = getattr(preview._clips,lane).clips.copy()
                other = 'audio' if lane=='video' else 'video'
                other_before = getattr(preview._clips,other).snapshot()
                drag_at(1.5,y,delta,offset+selected)
                changed = getattr(preview._clips,lane).clips
                assert changed[selected].start!=clips[selected].start
                assert changed[1-selected]==clips[1-selected]
                if not linked:
                    assert getattr(preview._clips,other).snapshot()==other_before
                preview.undoCut(); wait(lambda:not preview.busy)
                assert preview._clips.snapshot()==before
            # Trim either internal edge even while the other clip is selected.
            for index,side,delta in ((0,'right',-.2),(1,'left',.2)):
                preview.selectClip(offset+1-index); QTest.qWait(50)
                clips = getattr(preview._clips,lane).clips.copy()
                edge = visual_item(f'trim-{side}-{offset+index}')
                point = edge.mapToItem(timeline,QPointF(edge.width()/2,edge.height()/2))
                edge_time = timeline.property('viewStart')+(point.x()-timeline.property('inset'))*timeline.property('secondsPerPixel')
                drag_at(edge_time,point.y(),delta,offset+index,True)
                changed = getattr(preview._clips,lane).clips
                assert changed[index].pieces!=clips[index].pieces
                assert changed[1-index]==clips[1-index]
                preview.undoCut(); wait(lambda:not preview.busy)
                assert getattr(preview._clips,lane).clips==clips
        if not linked:
            preview.undoCut(); wait(lambda:not preview.busy)
            assert preview.lanesLinked
    preview.selectClip(1)
    window.grabWindow().save(str(run/'overlap-interaction.png'))
    passed('qml_selected_overlap_body_and_both_internal_trim_edges_linked_and_unlinked_lanes')
    preview._position=1.5
    assert abs(preview.moveTarget(1,.02,.01,False))<1e-6
    assert abs(preview.moveTarget(1,.1,.01,True)-.1)<.001
    preview.setFade('video_in','0.5'); wait(lambda:not preview.busy)
    assert preview._clips.video.clips[1].fades.video_in==.5
    preview.undoCut(); wait(lambda:not preview.busy); preview.undoCut(); wait(lambda:not preview.busy)
    assert not preview._clips.video.has_overlaps
    preview.redoCut(); wait(lambda:not preview.busy); preview.unlinkAudio()
    video = preview._clips.video.clips.copy()
    preview.moveClip(1000001,2); wait(lambda:not preview.busy)
    assert preview._clips.video.clips==video and not preview._clips.audio.has_overlaps
    assert visual_item('overlap-1000000-1000001') is None and visual_item('overlap-0-1') is not None
    passed('actual_qml_overlap_drag_snap_alt_baked_fade_refresh_undo_and_unlinked_lane')
finally:
    preview.close(); window.close(); engine.deleteLater(); app.processEvents()
assert hashlib.sha256(source.read_bytes()).hexdigest()==digest
passed('original_source_unchanged')
(OUT/'report.json').write_text(json.dumps({'checks':checks,'run':str(run)},indent=2),encoding='utf-8')
print('Report:',OUT/'report.json')
