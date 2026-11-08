"""Heterogeneous source, exact source mapping, real exports and library gestures."""
from dataclasses import replace
from fractions import Fraction
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
import av
import numpy as np
from PySide6.QtCore import QUrl,Qt,QPointF,QPoint,QCoreApplication,QEvent,QSettings,QLocale,QObject,QMetaObject
from PySide6.QtGui import QGuiApplication,QFontDatabase,QMouseEvent
from PySide6.QtQml import QQmlApplicationEngine,QQmlExpression
from PySide6.QtQuick import QQuickItem
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from splicelet.controller import Preview,FrameProvider
from splicelet.source import Decoder,Job
from splicelet.exporting import ExportTask,validate_destination,source_paths
from splicelet import project

OUT = ROOT/'artifacts/multi-source-tests'
OUT.mkdir(parents=True,exist_ok=True)
run = Path(tempfile.mkdtemp(prefix='run-',dir=OUT))
checks = []
def passed(name):
    checks.append(name); print('PASS',name,flush=True)

QLocale.setDefault(QLocale('en_US'))
app = QGuiApplication([]); QQuickStyle.setStyle('Basic')
QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat,QSettings.Scope.UserScope,str(run/'settings'))
if not QFontDatabase.families():
    for name in ('segoeui.ttf','segoeuib.ttf','consola.ttf'):
        QFontDatabase.addApplicationFont(str(Path(os.environ.get('SystemRoot','C:/Windows'))/'Fonts'/name))
ffmpeg = Path(sys.executable).parent/'Library/bin/ffmpeg.exe'
def generate(name,args):
    path = run/name
    subprocess.run([str(ffmpeg),'-v','error','-n',*args,str(path)],check=True,timeout=30)
    return path
red = generate('red.mkv',['-f','lavfi','-i','color=red:s=320x180:r=25:d=2',
                         '-f','lavfi','-i','aevalsrc=0.2|0.1:s=48000:d=2',
                         '-c:v','libx264','-crf','0','-threads','2','-c:a','pcm_s24le'])
blue = generate('blue.mov',['-f','lavfi','-i','color=blue:s=180x320:r=30:d=2',
                           '-f','lavfi','-i','aevalsrc=-0.1:s=44100:d=2',
                           '-c:v','mpeg4','-q:v','2','-c:a','pcm_s16le'])
audio = generate('audio.flac',['-f','lavfi','-i','aevalsrc=0.3|0.15:s=44100:d=1.5','-c:a','flac'])
silent = generate('silent.mkv',['-f','lavfi','-i','color=green:s=640x360:r=24:d=1','-c:v','ffv1','-threads','2'])
hashes = {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (red,blue,audio,silent)}
provider = FrameProvider(); preview = Preview(provider,muted=True)
engine = QQmlApplicationEngine(); engine.addImageProvider('frames',provider)
engine.setInitialProperties({'preview':preview})
warnings = []; engine.warnings.connect(lambda values:warnings.extend(v.toString() for v in values))
engine.load(QUrl.fromLocalFile(str(ROOT/'splicelet/Main.qml')))
assert engine.rootObjects(),warnings
window = engine.rootObjects()[0]
errors = []; preview.projectError.connect(errors.append)
def wait(predicate,timeout=40):
    deadline = time.monotonic()+timeout
    while not predicate():
        assert time.monotonic()<deadline,(preview.status,errors)
        app.processEvents(); QTest.qWait(10)
def idle(): wait(lambda:not preview.busy and not preview.importing and not preview._import_queue)
def click(item):
    QTest.mouseClick(window,Qt.MouseButton.LeftButton,pos=item.mapToScene(QPointF(item.width()/2,item.height()/2)).toPoint()); QTest.qWait(40)
def item_named(name,item=None):
    item = window.contentItem() if item is None else item
    if item.objectName()==name: return item
    for child in item.childItems():
        found = item_named(name,child)
        if found is not None: return found
    return None
def pixels(image):
    return np.frombuffer(image.constBits(),np.uint8).reshape(image.height(),image.bytesPerLine())[:,:image.width()*3].reshape(image.height(),image.width(),3)
def read(kind,spec,start=None,end=None):
    job = Job(1,spec.source,spec.start if start is None else start,spec.origin,spec.end if end is None else end,True,
              spec.audio_timeline,spec.audio_effects if kind=='audio' else spec.video_effects,
              spec.audio_parts if kind=='audio' else spec.parts,spec.fps,spec.width,spec.height,
              tuple(float(p*spec.time_base)-spec.origin for p in spec.source_pts),spec.sources)
    worker = Decoder(kind); worker.request(1,job)
    result = []; deadline = time.monotonic()+30
    try:
        while True:
            item = worker.take_video() if kind=='video' else worker.take_audio(32768)
            if item: result.append(item)
            count,_,eof,error = worker.status()
            assert not error,error
            if eof and not count: break
            assert time.monotonic()<deadline,'Decoder timeout'
            app.processEvents(); time.sleep(.001)
    finally: worker.close(); worker.thread.join(3)
    return result if kind=='video' else np.frombuffer(b''.join(result),'<f4').reshape(-1,2)
def export(spec,name):
    destination = run/name
    result,message = ExportTask()._execute(spec,destination)
    assert result=='success',message
    return destination

try:
    engine.rootContext().setContextProperty('testSourceUrls',[QUrl.fromLocalFile(str(p)) for p in (red,blue,audio,silent)])
    expression = QQmlExpression(engine.rootContext(),window,'preview.importUrls(testSourceUrls)')
    expression.evaluate(); assert not expression.hasError(),expression.error().toString()
    wait(lambda:len(preview._sources)==4); idle()
    assert not errors,errors
    assert preview.duration==2 and (preview._width,preview._height)==(320,180)
    assert len(preview.importedSources)==4
    assert preview._clips.linked
    preview.appendSource(1); idle()
    preview.appendSource(2); idle()
    preview.appendSource(3); idle()
    assert preview.duration==6.5 and len(preview._clips.video.clips)==4
    assert preview._clips.video.clips==preview._clips.audio.clips
    spec = preview.export_spec(False)
    assert len(spec.sources)==4 and spec.width==320 and spec.height==180
    passed('ordered_multi_import_library_only_additions_first_video_canvas_and_linked_append')

    pcm = read('audio',spec)
    assert pcm.shape==(312000,2),pcm.shape
    assert np.allclose(pcm[1000:95000],[.2,.1],atol=2e-6)
    # Mono is mixed to stereo using the existing FFmpeg resampler coefficients.
    reference = subprocess.run([str(ffmpeg),'-v','error','-i',str(blue),'-vn','-f','f32le','-ar','48000','-ac','2','-'],capture_output=True,check=True).stdout
    ref = np.frombuffer(reference,'<f4').reshape(-1,2)
    assert np.max(abs(pcm[96000:192000]-ref[:96000]))<2e-6
    assert np.allclose(pcm[193000:263000],[.3,.15],atol=2e-6)
    assert not np.any(pcm[264000:])
    sought = read('audio',spec,2.25,5.75)
    assert np.max(abs(sought-pcm[108000:276000]))<2e-6
    passed('exact_pcm_counts_mono_44100_resampling_audio_only_video_without_audio_and_seek')

    frames = read('video',spec)
    assert all(a[1]<b[1] for a,b in zip(frames,frames[1:]))
    for _,stamp,image in frames:
        rgb = pixels(image)
        assert rgb.shape==(180,320,3)
        if 2<=stamp<4:
            assert rgb[:,0:100].max()==0 and rgb[:,220:].max()==0
            assert rgb[90,160,2]>230
        if 4<=stamp<5.5: assert rgb.max()==0
    destination = export(spec,'heterogeneous.mp4')
    with av.open(str(destination)) as container:
        stream = container.streams.video[0]
        assert stream.codec_context.name=='h264' and (stream.width,stream.height)==(320,180)
        exported = list(container.decode(video=0))
    for frame in exported:
        stamp = float(frame.pts*frame.time_base); rgb = frame.to_ndarray(format='rgb24')
        if 2<=stamp<4: assert rgb[90,160,2]>225 and rgb[:,0:95].max()<8
        if 4<=stamp<5.5: assert rgb.max()<8
    assert abs(float(exported[-1].pts*exported[-1].time_base)-6.5)<.06
    export(replace(spec,timeline_start=2.25,timeline_end=5.75),'partial.mp4')
    passed('preview_export_fixed_canvas_letterbox_audio_black_vfr_and_partial_window')

    # Source reserves cannot extend an individual imported clip into its neighbor source.
    model = preview._clips
    original = model.video.clips.copy()
    assert not model.resize(0,'right',3)
    model.select(0); model.select(1,True); assert model.join()
    assert len(model.video.parts(model.video.clips[0]))==2
    assert model.resize(0,'right',3) and model.resize(0,'right',4)
    assert model.video.parts(model.video.clips[0])[-1].end==4
    assert model.split_at(2.5)
    preview._editing_changed(); idle()
    assert np.max(abs(read('audio',preview.export_spec(False))-pcm))<2e-6
    while model.video.clips!=original: model.undo()
    preview._editing_changed(); idle()
    passed('cross_source_join_split_trim_reserves_and_undo_preserve_samples')

    # A real cross-source dissolve at different resolutions and PTS grids.
    model.select(1)
    assert model.move_selection(1,1)
    preview._editing_changed(); idle()
    mixed = preview.export_spec(False)
    mixed_pcm = read('audio',mixed,1,2)
    alpha = np.arange(48000)/48000
    expected = np.array([.2,.1])*(1-alpha[:,None])+ref[:48000]*alpha[:,None]
    assert np.max(abs(mixed_pcm-expected))<2e-6
    mixed_frames = read('video',mixed,1.5,1.6)
    image = pixels(mixed_frames[0][2])
    assert 110<image[90,160,0]<145 and 110<image[90,160,2]<145
    export(replace(mixed,timeline_start=1.5,timeline_end=1.8),'transition.mp4')
    model.select(0); model.select(1,True); assert model.join()
    preview._editing_changed(); idle()
    compound = preview.export_spec(False)
    assert np.array_equal(read('audio',compound,1,2),mixed_pcm)
    compound_frames = read('video',compound,1.5,1.6)
    assert [f[1] for f in compound_frames]==[f[1] for f in mixed_frames]
    assert all(np.array_equal(pixels(a[2]),pixels(b[2])) for a,b in zip(compound_frames,mixed_frames))
    compound_path = run/'multi-compound.splicelet'
    assert preview.saveProjectAs(QUrl.fromLocalFile(str(compound_path)))
    assert project.read(compound_path)['version']==4
    compound_timeline = project.timeline(model)
    preview.openProject(QUrl.fromLocalFile(str(compound_path))); idle()
    assert not errors and project.timeline(preview._clips)==compound_timeline,errors
    assert np.array_equal(read('audio',preview.export_spec(False),1,2),mixed_pcm)
    # Return to the non-compound layout for the independent legacy-format checks.
    preview._clips = model
    model.undo()
    model.undo(); preview._editing_changed(); idle()
    passed('cross_source_dissolve_compound_join_version4_roundtrip_and_partial_export')

    path = run/'multi.splicelet'
    assert preview.saveProjectAs(QUrl.fromLocalFile(str(path)))
    saved = project.read(path); assert saved['version']==3 and len(saved['sources'])==4
    before = project.timeline(preview._clips)
    preview.openProject(QUrl.fromLocalFile(str(path))); idle()
    assert not errors and not preview.projectDirty and before==project.timeline(preview._clips),errors
    assert (preview._width,preview._height)==(320,180)
    assert np.max(abs(read('audio',preview.export_spec(False))-pcm))<2e-6
    # Invalid timeline data must fail after indexing without replacing this session.
    invalid = json.loads(path.read_text(encoding='utf-8'))
    invalid['timeline']['video']['clips'][0]['pieces'][0]['end'] = 999999
    bad_project = run/'invalid.splicelet'; bad_project.write_text(json.dumps(invalid),encoding='utf-8')
    previous = preview._clips
    preview.openProject(QUrl.fromLocalFile(str(bad_project))); idle()
    assert errors and preview._clips is previous and preview.canSaveProject
    errors.clear()
    error_dialog = window.findChild(QObject,'projectErrorDialog')
    QMetaObject.invokeMethod(error_dialog,'accept')
    wait(lambda:not error_dialog.property('visible')); QTest.qWait(200)
    for source_file in (red,blue,audio,silent):
        try: validate_destination(source_paths(spec),source_file)
        except ValueError: pass
        else: raise AssertionError('Source destination accepted')
    passed('version3_roundtrip_all_source_refs_exact_ranges_canvas_and_all_source_protection')

    # Actual library tab, append button, and drag into a free timeline gap.
    click(window.findChild(QQuickItem,'sourceTab'))
    assert window.findChild(QObject,'sidePanelTabs').property('currentIndex')==1
    window.grabWindow().save(str(run/'source-library.png'))
    click(item_named('appendSource2')); idle()
    assert preview.duration==8
    preview.undoCut(); idle(); assert preview.duration==6.5
    assert preview.addSpace('end','3'); idle()
    timeline = window.findChild(QQuickItem,'editTimeline')
    entry = item_named('sourceEntry2')
    assert entry and entry.isVisible()
    start = entry.mapToScene(QPointF(70,20)).toPoint()
    target = timeline.mapToScene(QPointF(timeline.property('inset')+7/timeline.property('secondsPerPixel'),55)).toPoint()
    QTest.mousePress(window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.AltModifier,start)
    for f in (.2,.5,.8,1.):
        point = QPoint(round(start.x()+(target.x()-start.x())*f),round(start.y()+(target.y()-start.y())*f))
        event = QMouseEvent(QEvent.Type.MouseMove,QPointF(point),QPointF(point),QPointF(window.mapToGlobal(point)),Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.AltModifier)
        QCoreApplication.sendEvent(window,event); QTest.qWait(40)
    window.grabWindow().save(str(run/'library-drag.png'))
    QTest.mouseRelease(window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.AltModifier,target)
    idle()
    assert any(abs(float(c.start)-7)<.08 for c in preview._clips.video.clips),preview.clips
    window.grabWindow().save(str(run/'library-drop.png'))
    window.setWidth(760); window.setHeight(560); QTest.qWait(100)
    window.grabWindow().save(str(run/'minimum.png'))
    preview.setDarkTheme(True); QTest.qWait(100); window.grabWindow().save(str(run/'dark.png'))
    passed('actual_qml_tabs_append_drag_drop_undo_light_dark_and_minimum_layout')

    # Audio-first projects remain black, and the first later video fixes the canvas.
    preview.open_path(str(audio)); idle()
    assert not preview._canvas_locked and preview._sources[0].has_video is False
    audio_spec = preview.export_spec(False)
    assert all(pixels(f[2]).max()==0 for f in read('video',audio_spec))
    export(audio_spec,'audio-only.mp4')
    audio_project = run/'audio-only.splicelet'
    assert preview.saveProjectAs(QUrl.fromLocalFile(str(audio_project)))
    preview.openProject(QUrl.fromLocalFile(str(audio_project))); idle()
    assert not preview.projectDirty and not preview._canvas_locked and preview.duration==1.5
    preview.importUrls([QUrl.fromLocalFile(str(blue))]); idle()
    assert (preview._width,preview._height)==(180,320)
    preview.appendSource(1); idle()
    assert preview.duration==3.5
    passed('audio_first_black_export_and_first_later_video_sets_resolution')

    # Uneven source PTS with a nonzero source origin after a different file.
    offset = generate('offset.mkv',['-f','lavfi','-i','testsrc2=s=320x180:r=25:d=2',
                      '-vf','select=not(eq(mod(n\\,3)\\,1)),setpts=PTS+2/TB','-fps_mode','vfr','-c:v','ffv1'])
    preview.importUrls([QUrl.fromLocalFile(str(offset))]); idle()
    source = preview._sources[-1]
    assert source.origin==2 and len(set(np.diff(source.pts)))>1
    start = preview.duration
    preview.appendSource(len(preview._sources)-1); idle()
    offset_spec = replace(preview.export_spec(False),timeline_start=start,timeline_end=preview.duration)
    actual = read('video',offset_spec)
    expected = [float(p*source.time_base)-source.origin+start for p in source.pts]
    assert np.allclose([f[1] for f in actual],expected,atol=1e-8)
    export(offset_spec,'vfr-offset.mp4')
    passed('heterogeneous_vfr_nonzero_source_origin_and_export_window')

    # Independent lanes retain their own content when importing/inserting.
    preview.unlinkAudio(); idle()
    before_video = preview._clips.video.clips.copy()
    preview.insertSource(0,preview.duration,'audio'); idle()
    assert preview._clips.video.clips==before_video
    assert preview._clips.audio.clips!=before_video
    preview.undoCut(); idle()
    task = ExportTask()
    task.updated.connect(lambda fraction,text:task.cancel() if fraction>0 else None)
    cancelled_path = run/'cancelled.mp4'
    outcome,message = task._execute(preview.export_spec(False),cancelled_path)
    assert outcome=='cancelled' and not cancelled_path.exists(),message
    assert not list(run.glob('.video-export-*'))
    passed('unlinked_insertion_is_lane_local_and_multi_source_cancel_cleans_temporaries')

    # A failed later import leaves the existing project and its history usable.
    bad = run/'bad.bin'; bad.write_bytes(b'not a source file')
    before = project.timeline(preview._clips)
    preview.importUrls([QUrl.fromLocalFile(str(bad))]); idle()
    assert errors and 'bad.bin' in errors[-1]
    errors.clear()
    assert project.timeline(preview._clips)==before
    preview.importUrls([QUrl.fromLocalFile(str(silent))])
    # Replacing the session invalidates every in-flight import/visual result.
    preview.open_path(str(red)); idle(); QTest.qWait(100)
    assert len(preview._sources)==1 and preview._sources[0].path==str(red)
    preview.open_path(str(bad)); idle()
    preview.importUrls([QUrl.fromLocalFile(str(bad)),QUrl.fromLocalFile(str(blue))])
    wait(lambda:len(preview._sources)==1 and preview._sources[0].path==str(blue)); idle()
    errors.clear()
    passed('failed_import_preserves_montage_and_replacement_discards_stale_source_jobs')

    assert all(hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest for path,digest in hashes.items())
    assert not errors,errors
    # Startup platform warnings are recorded separately from authored QML errors.
    assert not [w for w in warnings if 'ReferenceError' in w or 'TypeError' in w or 'Binding loop' in w],warnings
    passed('all_originals_unchanged_and_no_new_qml_runtime_errors')
finally:
    preview.close(); window.close(); app.processEvents()
    (OUT/'report.json').write_text(json.dumps({'checks':checks,'run':str(run),'warnings':warnings,'errors':errors},indent=2),encoding='utf-8')
print('Report:',OUT/'report.json')
