"""Independent lanes: edits/history, projects, actual QML, PCM and padded exports."""
from dataclasses import replace
from fractions import Fraction
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ.setdefault('QT_QUICK_BACKEND','software')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from splicelet.editing import Clip,Clips
from splicelet.tracks import Tracks
from splicelet.effects import Fades
from splicelet import project

OUT = ROOT/'artifacts'/'audio-track-tests'
OUT.mkdir(parents=True,exist_ok=True)
run = Path(tempfile.mkdtemp(prefix='run-',dir=OUT))
checks = []
def passed(name):
    checks.append(name); print('PASS',name,flush=True)

def model(): return Tracks(Clips(180,[Fraction(i,30) for i in range(180)],Fraction(6)))
m = model()
assert m.split_at(Fraction(2)) and m.video.clips==m.audio.clips
assert m.resize(1,'right',4) and m.video.clips==m.audio.clips
m.select(1); assert m.move_selection(1,3) and m.video.clips==m.audio.clips
before = m.snapshot(); assert m.unlink()
assert m.move_selection(1,4) and m.video.clips!=m.audio.clips
m.undo(); m.undo(); assert m.snapshot()==before
m.redo(); m.redo(); assert m.video.clips!=m.audio.clips
passed('linked_split_trim_move_and_atomic_unlink_undo_redo')

m = model(); assert m.unlink(); original = m.video.clips.copy()
m.activate('audio'); m.select(0)
assert m.split_at(2) and m.video.clips==original and len(m.audio.clips)==2
assert m.resize(1,'right',4) and m.move_selection(1,3)
assert m.set_fade('audio_in',.5) and m.video.clips==original
assert m.duplicate(1) and m.video.clips==original
assert m.delete_selected() and m.video.clips==original
assert m.remove_gap(0) and m.video.clips==original
m.select(0); m.select(1,True); assert m.join() and m.video.clips==original
passed('audio_only_split_trim_move_duplicate_delete_gap_join_and_fade')

m = model(); m.split_at(2); m.split_at(4)
m.select(1); assert m.unlink() and not m.linked
video = m.video.clips.copy()
m.activate('audio'); m.select(1); assert m.delete_selected()
assert m.remove_gap(0) and m.video.clips==video
assert m.audio.clips[1].start==2 and m.video.clips[2].start==4
m.activate('video'); m.select(1); assert m.delete_selected() and m.remove_gap(0)
assert m.video.clips==m.audio.clips and not m.linked and not m.unlink()
m.undo(); m.undo(); assert not m.linked
m = model(); m.selected_ids.clear(); assert m.unlink() and not m.linked
m.undo(); assert m.linked
passed('global_unlink_without_selection_lane_only_gap_closure_and_no_implicit_relink')

from PySide6.QtCore import QObject,QUrl,Qt,QPointF,QPoint,QSettings,QMetaObject,QCoreApplication,QEvent,QLocale
from PySide6.QtGui import QGuiApplication,QFontDatabase,QMouseEvent
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
import av
import numpy as np
from splicelet.controller import Preview,FrameProvider
from splicelet.exporting import ExportTask

QLocale.setDefault(QLocale('en_US'))
app = QGuiApplication([]); QQuickStyle.setStyle('Basic')
if not QFontDatabase.families():
    for name in ('segoeui.ttf','segoeuib.ttf','consola.ttf'):
        QFontDatabase.addApplicationFont(str(Path(os.environ.get('SystemRoot','C:/Windows'))/'Fonts'/name))
QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat,QSettings.Scope.UserScope,str(run/'settings'))
ffmpeg = Path(sys.executable).parent/'Library/bin/ffmpeg.exe'
source = run/'white-tone.mkv'
subprocess.run([str(ffmpeg),'-v','error','-n','-f','lavfi','-i','color=white:size=320x180:rate=30:duration=6',
                '-f','lavfi','-i','aevalsrc=0.25*sin(2*PI*440*t)|0.125*sin(2*PI*880*t):s=48000:d=6',
                '-c:v','libx264','-crf','0','-threads','4','-c:a','pcm_s24le',str(source)],check=True,timeout=30)
original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
provider = FrameProvider(); preview = Preview(provider,muted=True)
engine = QQmlApplicationEngine(); engine.addImageProvider('frames',provider)
engine.setInitialProperties({'preview':preview})
engine.load(QUrl.fromLocalFile(str(ROOT/'splicelet/Main.qml')))
assert engine.rootObjects()
window = engine.rootObjects()[0]
def wait(predicate):
    deadline = time.monotonic()+30
    while not predicate():
        assert time.monotonic()<deadline,preview.status
        app.processEvents(); QTest.qWait(10)
def click(item):
    QTest.mouseClick(window,Qt.MouseButton.LeftButton,pos=item.mapToScene(QPointF(item.width()/2,item.height()/2)).toPoint())
    QTest.qWait(30)
def clip(index):
    return next(c for c in timeline.childItems() if c.objectName()==f'clip-{index}')
try:
    preview.open_path(str(source)); wait(lambda:preview.indexedReady and not preview.busy)
    timeline = window.findChild(QQuickItem,'editTimeline')
    assert clip(1000000).height()==44 and clip(1000000).height()<clip(0).height()
    assert {c['index'] for c in preview.movingClips(0)}=={0,1000000}
    start=clip(0).mapToScene(QPointF(clip(0).width()/2,26)).toPoint()
    target=QPoint(start.x()+round(.5/timeline.property('secondsPerPixel')),start.y())
    QTest.mousePress(window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.AltModifier,start)
    event=QMouseEvent(QEvent.Type.MouseMove,QPointF(target),QPointF(target),QPointF(window.mapToGlobal(target)),
                      Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.AltModifier)
    QCoreApplication.sendEvent(window,event); QTest.qWait(50)
    assert {'drag-preview-0','drag-preview-1000000'}.issubset({c.objectName() for c in timeline.childItems()})
    assert clip(0).opacity()==clip(1000000).opacity()==.4
    window.grabWindow().save(str(run/'linked-drag.png'))
    QTest.mouseRelease(window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.AltModifier,target)
    wait(lambda:not preview.busy)
    assert preview._clips.video.clips==preview._clips.audio.clips
    preview.undoCut(); wait(lambda:not preview.busy)
    passed('qml_linked_drag_moves_and_previews_both_lanes_as_one_edit')
    action = window.findChild(QObject,'unlinkAudioAction')
    assert action.property('enabled') and preview.showAudioFades and preview.showVideoFades
    menu = window.findChild(QObject,'editMenu'); QMetaObject.invokeMethod(menu,'open'); QTest.qWait(80)
    window.grabWindow().save(str(run/'linked-menu.png')); QMetaObject.invokeMethod(menu,'close')
    preview.selectClip(0,True)
    assert preview.selectionCount==0 and action.property('enabled')
    QMetaObject.invokeMethod(action,'trigger'); QTest.qWait(50)
    assert not preview.canUnlink and not preview.showAudioFades and preview.showVideoFades
    click(clip(1000000))
    assert preview._clips.lane=='audio' and preview.showAudioFades and not preview.showVideoFades
    preview.seek(2); wait(lambda:not preview.busy)
    QTest.keyClick(window,Qt.Key.Key_C); wait(lambda:not preview.busy)
    assert len(preview._clips.audio.clips)==2 and len(preview._clips.video.clips)==1
    assert window.findChild(QQuickItem,'audioFadeIn').isVisible()
    assert not window.findChild(QQuickItem,'videoFadeIn').isVisible()
    window.grabWindow().save(str(run/'audio-split.png'))
    passed('qml_audio_lane_height_menu_unlink_selection_fades_and_audio_keyboard_cut')

    # A real drag and trim in the short audio lane must leave video untouched.
    preview.resizeClip(1000001,'right',4); wait(lambda:not preview.busy)
    video = preview._clips.video.clips.copy()
    start = clip(1000001).mapToScene(QPointF(clip(1000001).width()/2,13)).toPoint()
    target = QPoint(start.x()+round(1/timeline.property('secondsPerPixel')),start.y())
    QTest.mousePress(window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.AltModifier,start)
    event = QMouseEvent(QEvent.Type.MouseMove,QPointF(target),QPointF(target),QPointF(window.mapToGlobal(target)),
                       Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.AltModifier)
    QCoreApplication.sendEvent(window,event); QTest.qWait(40)
    assert timeline.property('dragIndex')==1000001
    QTest.mouseRelease(window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.AltModifier,target)
    wait(lambda:not preview.busy)
    assert abs(float(preview._clips.audio.clips[1].start)-3)<.04 and preview._clips.video.clips==video
    layer = timeline.findChild(QQuickItem,'timelineTrimEdges')
    edges = next(c for c in layer.childItems() if c.objectName()=='clip-edges-1000001')
    edge = next(c for c in edges.childItems() if c.objectName()=='trim-right-1000001')
    start = edge.mapToScene(QPointF(edge.width()/2,13)).toPoint(); target = QPoint(start.x()-40,start.y())
    length = preview._clips.audio.length(preview._clips.audio.clips[1])
    QTest.mousePress(window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.AltModifier,start)
    event = QMouseEvent(QEvent.Type.MouseMove,QPointF(target),QPointF(target),QPointF(window.mapToGlobal(target)),
                       Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.AltModifier)
    QCoreApplication.sendEvent(window,event)
    QTest.mouseRelease(window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.AltModifier,target)
    wait(lambda:not preview.busy)
    assert preview._clips.audio.length(preview._clips.audio.clips[1])<length and preview._clips.video.clips==video
    passed('qml_audio_drag_and_trim_leave_video_unchanged')

    # Cross-lane junctions are snap targets for moving, either trim edge and seeking.
    previous = preview._clips
    video = Clips(180,[Fraction(i,30) for i in range(180)],Fraction(6))
    audio = Clips(180,[Fraction(i,30) for i in range(180)],Fraction(6))
    video.split_at(3); audio.split_at(2)
    preview._clips=Tracks(video,audio,False); preview._editing_changed(); wait(lambda:not preview.busy)
    for side in ('left','right'):
        assert preview.resizeTarget(1000001,side,3.06,.01,False)['start' if side=='left' else 'end']==3
        bypass = preview.resizeTarget(1000001,side,3.06,.01,True)
        assert abs(bypass['start' if side=='left' else 'end']-3)>.04
    assert preview.resizeTarget(0,'right',2.06,.01,False)['end']==2
    assert preview.resizeTarget(0,'right',2.06,.01,True)['end']>2.04
    assert preview.moveTarget(1000001,3.06,.01,False)==3
    assert preview.moveTarget(1000001,3.06,.01,True)>3.04
    assert preview.snapPosition(3.06,600)==3
    preview._clips=previous; preview._editing_changed(); wait(lambda:not preview.busy)
    passed('cross_lane_junction_snapping_for_audio_video_trim_move_and_ruler_with_alt_bypass')

    # Deliberately different windows: video 1..4, audio 3..6.
    times = [p*preview._video_time_base-Fraction(str(preview._origin)) for p in preview._video_pts]
    video = Clips(len(times),times,Fraction(6)); audio = Clips(len(times),times,Fraction(6))
    video.clips = [Clip(0,Fraction(1),((0,90),),Fades(video_in=1,video_out=1))]
    audio.clips = [Clip(1,Fraction(3),((90,180),),Fades(audio_in=.5,audio_out=.5))]
    video.next_id=audio.next_id=2
    video.selected_ids={0}; audio.selected_ids=set()
    preview._clips=Tracks(video,audio,False); preview._editing_changed(); wait(lambda:not preview.busy)
    saved = project.timeline(preview._clips)
    path = run/'independent.splicelet'
    assert preview.saveProjectAs(QUrl.fromLocalFile(str(path)))
    preview.openProject(QUrl.fromLocalFile(str(path))); wait(lambda:preview.canSaveProject and not preview.busy)
    assert project.timeline(preview._clips)==saved and not preview.projectDirty
    assert preview.selectionCount==1 and not preview._clips.audio.selected_ids
    for mutate in (lambda d:d['timeline'].update(linked=True),lambda d:d['timeline']['audio'].update(extent=[7,1])):
        bad=copy.deepcopy(project.document(preview._clips,source)); mutate(bad)
        try: project.restore(bad,times,Fraction(6))
        except ValueError: pass
        else: raise AssertionError('Invalid lane/link accepted')
    legacy = project.document(video,source)
    upgraded = Tracks(project.restore(legacy,times,Fraction(6)))
    assert upgraded.video.clips==upgraded.audio.clips and upgraded.linked
    passed('v2_independent_project_roundtrip_validation_and_v1_upgrade')

    for index,label in ((0,'video-window'),(1000000,'audio-window')):
        preview.selectClip(index); spec=preview.export_spec()
        pcm=run/f'{label}.f32le'; ExportTask()._audio(spec,pcm)
        samples=np.fromfile(pcm,dtype='<f4').reshape(-1,2)
        assert len(samples)==144000
        if index==0:
            assert np.max(abs(samples[:96000]))==0 and np.max(abs(samples[100800:]))>.1
        else:
            reference=subprocess.check_output([str(ffmpeg),'-v','error','-i',str(source),'-map','0:a:0','-af',
                'atrim=start_sample=144000:end_sample=288000,asetpts=PTS-STARTPTS,aformat=sample_fmts=flt,afade=t=in:ns=24000,afade=t=out:ss=120000:ns=24000',
                '-f','f32le','-'],timeout=30)
            assert np.max(abs(samples-np.frombuffer(reference,dtype='<f4').reshape(-1,2)))<1e-7
        target=run/f'{label}.mp4'
        result,message=ExportTask()._execute(spec,target); assert result=='success',message
        with av.open(str(target)) as rendered:
            frames=[(float(f.pts*f.time_base),float(f.to_ndarray(format='gray').mean())) for f in rendered.decode(video=0)]
        assert len(frames)==90,(label,len(frames))
        assert abs(frames[0][0])<.001
        def luma(t): return min(frames,key=lambda f:abs(f[0]-t))[1]
        if index==0:
            assert luma(0)<3 and 110<luma(.5)<145 and luma(1.5)>245 and 110<luma(2.5)<145
        else:
            assert luma(0)>245 and 110<luma(.5)<145 and luma(1.5)<3 and luma(2.5)<3
        with av.open(str(target)) as rendered:
            stream=rendered.streams.audio[0]
            assert abs(float(stream.duration*stream.time_base)-3)<.003
    passed('video_or_audio_export_window_exact_pcm_fades_black_silence_and_frame_timestamps')

    full_before=preview.export_spec(False)
    preview.selectClip(0,True)
    assert preview.selectionCount==2 and preview.selectionRange=={'start':1.,'end':6.}
    assert preview.selectedLengthText==preview.format_time(5)
    assert preview.export_spec(False)==full_before
    mixed=preview.export_spec()
    assert mixed.start==1 and mixed.end==6 and mixed.duration==5
    assert mixed.parts==spec.parts and mixed.audio_parts==spec.audio_parts
    assert mixed.video_effects==spec.video_effects and mixed.audio_effects==spec.audio_effects
    pcm=run/'mixed-selection.f32le'; ExportTask()._audio(mixed,pcm)
    samples=np.fromfile(pcm,dtype='<f4').reshape(-1,2)
    assert len(samples)==240000 and not np.any(samples[:96000])
    reference=np.fromfile(run/'audio-window.f32le',dtype='<f4').reshape(-1,2)
    np.testing.assert_array_equal(samples[96000:],reference)
    target=run/'mixed-selection.mp4'
    result,message=ExportTask()._execute(mixed,target); assert result=='success',message
    with av.open(str(target)) as rendered:
        frames=[(float(f.pts*f.time_base),float(f.to_ndarray(format='gray').mean())) for f in rendered.decode(video=0)]
    assert len(frames)==150 and abs(frames[0][0])<.001
    assert all(abs(stamp-i/30)<.001 for i,(stamp,_) in enumerate(frames))
    def luma(t): return min(frames,key=lambda f:abs(f[0]-t))[1]
    assert luma(0)<3 and 110<luma(.5)<145 and luma(1.5)>245
    assert 110<luma(2.5)<145 and luma(3.5)<3 and luma(4.5)<3
    with av.open(str(target)) as rendered:
        stream=rendered.streams.audio[0]
        assert abs(float(stream.duration*stream.time_base)-5)<.003
    passed('mixed_selection_exports_both_outer_bounds_exact_pcm_video_pts_and_unchanged_full_spec')

    shifted = replace(spec,timeline_start=float(Fraction(91,30)),timeline_end=float(Fraction(181,30)))
    target=run/'offset-pts-grids.mp4'
    result,message=ExportTask()._execute(shifted,target); assert result=='success',message
    with av.open(str(target)) as rendered:
        frames=list(rendered.decode(video=0))
        assert frames[0].pts==0 and frames[0].to_ndarray(format='gray').mean()>230
        assert frames[-1].to_ndarray(format='gray').max()<3
    passed('offset_audio_video_pts_grids_hold_the_covering_frame_at_export_start')

    # Reordered source pieces, an internal gap and a multi-clip export window.
    previous = preview._clips
    video = Clips(len(times),times,Fraction(6)); audio = Clips(len(times),times,Fraction(6))
    video.clips = [Clip(0,Fraction(0),((90,120),)),Clip(1,Fraction(2),((0,30),))]
    video.selected_ids={0,1}; audio.selected_ids=set()
    preview._clips=Tracks(video,audio,False); preview._editing_changed(); wait(lambda:not preview.busy)
    spec=preview.export_spec(); assert spec.start==0 and spec.end==3
    target=run/'reordered-with-gap.mp4'
    result,message=ExportTask()._execute(spec,target); assert result=='success',message
    with av.open(str(target)) as rendered:
        frames=list(rendered.decode(video=0))
        assert len(frames)==90
        assert frames[15].to_ndarray(format='gray').mean()>245
        assert frames[45].to_ndarray(format='gray').max()<3
        assert frames[75].to_ndarray(format='gray').mean()>245
    preview._clips=previous; preview._editing_changed(); wait(lambda:not preview.busy)
    passed('multi_selection_exports_reordered_video_and_internal_black_gap')

    preview.selectClip(1000000); preview.deleteSelected(); wait(lambda:not preview.busy)
    preview.selectClip(0); spec=preview.export_spec()
    target=run/'silent.mp4'; result,message=ExportTask()._execute(spec,target); assert result=='success',message
    pcm=run/'silent.f32le'; ExportTask()._audio(spec,pcm); assert not np.any(np.fromfile(pcm,dtype='<f4'))
    preview.undoCut(); wait(lambda:not preview.busy)
    preview.selectClip(0); preview.deleteSelected(); wait(lambda:not preview.busy)
    preview.selectClip(1000000); spec=preview.export_spec()
    target=run/'black.mp4'; result,message=ExportTask()._execute(spec,target); assert result=='success',message
    with av.open(str(target)) as rendered:
        frames=list(rendered.decode(video=0)); assert len(frames)==90 and all(f.to_ndarray(format='gray').max()<3 for f in frames)
    preview.seek(4); wait(lambda:not preview.busy)
    assert provider.image.pixelColor(10,10).red()==0
    window.setWidth(760); window.setHeight(560); QTest.qWait(80)
    window.grabWindow().save(str(run/'minimum-audio-only.png'))
    assert hashlib.sha256(source.read_bytes()).hexdigest()==original_hash
    passed('empty_opposite_lane_exports_padding_previews_black_and_preserves_source')
finally:
    preview.close(); engine.deleteLater()
(OUT/'report.json').write_text(json.dumps({'status':'pass','checks':checks,'run':str(run)},indent=2),encoding='utf-8')
