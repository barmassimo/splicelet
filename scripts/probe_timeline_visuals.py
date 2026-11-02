"""Real peaks, sparse thumbnails, source mapping, cache and rendered QML."""
import hashlib
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QT_QUICK_BACKEND', 'software')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from PySide6.QtCore import QUrl, QLocale, QPointF, QPoint, Qt, QCoreApplication
from PySide6.QtGui import QGuiApplication, QFontDatabase, QImage, QWheelEvent
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from splicelet.controller import Preview, FrameProvider
from splicelet.visuals import build_visuals, peak_levels, waveform_columns
from splicelet import project

OUT = ROOT/'artifacts'/'timeline-visual-tests'
OUT.mkdir(parents=True, exist_ok=True)
run = Path(tempfile.mkdtemp(prefix='run-', dir=OUT))
checks = []
def passed(name):
    checks.append(name)
    print('PASS', name, flush=True)

# Coarse display bins must not borrow a transient from deleted source material.
peaks = np.zeros((1000, 2), np.float32)
peaks[100] = [-.8, .9]
levels = peak_levels(peaks)
assert np.max(np.abs(waveform_columns(levels, .001, [(0, .1, .101)], 0, .1, 1))) == 0
assert np.allclose(waveform_columns(levels, .001, [(0, .001, .1)], 0, .001, 1), [[-.8, .9]])
passed('peak_aggregation_preserves_transients_and_excludes_deleted_ranges')

ffmpeg = Path(sys.executable).parent/'Library/bin/ffmpeg.exe'
source = run/'pattern.mkv'
subprocess.run([str(ffmpeg), '-v', 'error', '-n', '-f', 'lavfi', '-i',
    'testsrc2=size=320x180:rate=30:duration=6', '-f', 'lavfi', '-i',
    r'aevalsrc=if(between(t\,1\,2)\,0.008*sin(2*PI*440*t)\,0)|if(between(t\,4\,5)\,0.004*sin(2*PI*880*t)\,0):s=48000:d=6',
    '-c:v', 'libx264', '-g', '30', '-threads', '2', '-c:a', 'pcm_f32le', str(source)], check=True, timeout=30)
source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
QLocale.setDefault(QLocale('en_US'))
app = QGuiApplication([])
QQuickStyle.setStyle('Basic')
if not QFontDatabase.families():
    for name in ('segoeui.ttf', 'segoeuib.ttf', 'consola.ttf'):
        QFontDatabase.addApplicationFont(str(Path(os.environ.get('SystemRoot', 'C:/Windows'))/'Fonts'/name))
provider = FrameProvider()
preview = Preview(provider, muted=True)
engine = QQmlApplicationEngine()
warnings = []
engine.warnings.connect(lambda items: warnings.extend(str(item) for item in items))
engine.addImageProvider('frames', provider)
engine.setInitialProperties({'preview': preview})
engine.load(QUrl.fromLocalFile(str(ROOT/'splicelet/Main.qml')))
assert engine.rootObjects()
window = engine.rootObjects()[0]
def wait(predicate):
    deadline = time.monotonic()+45
    while not predicate():
        assert time.monotonic() < deadline, (preview.status, preview.visualsStatus)
        app.processEvents(); QTest.qWait(10)
def screenshot(name):
    QTest.qWait(150)
    assert window.grabWindow().save(str(run/name))
try:
    preview.open_path(str(source))
    wait(lambda: preview.indexedReady and preview._waveform is not None and bool(preview._thumbnails[0]))
    assert not preview.visualsStatus
    columns = np.array(preview.waveformColumns(1000000, 0, 6, 600))
    assert np.max(np.abs(columns[:90])) == 0
    assert columns[110:190, 1].max() > .0079
    assert .0039 < columns[410:490, 1].max() < .0041
    assert np.max(np.abs(columns[510:])) == 0
    passed('decoded_stereo_peaks_match_known_signal_and_silence')
    times, files = preview._thumbnails
    assert len(times) >= 3 and len(files) <= 600
    images = [QImage(path) for path in files]
    assert all(not image.isNull() and image.width() <= 160 and image.height() <= 90 for image in images)
    assert images[0] != images[-1]
    screenshot('overview.png')
    passed('real_distinct_small_thumbnails_and_qml_overview')

    timeline = window.findChild(QQuickItem, 'editTimeline')
    audio = next(item for item in timeline.childItems() if item.objectName() == 'clip-1000000')
    assert audio.height() == 44
    original_spec = preview.export_spec()
    original_project = project.timeline(preview._clips)
    original_volume = (preview.volume, preview.muted)
    def wheel(delta, y, modifier=Qt.KeyboardModifier.ShiftModifier):
        point = timeline.mapToScene(QPointF(timeline.width()/2, y))
        event = QWheelEvent(point, QPointF(window.mapToGlobal(point.toPoint())), QPoint(), QPoint(0, delta),
                            Qt.MouseButton.NoButton, modifier, Qt.ScrollPhase.NoScrollPhase, False)
        QCoreApplication.sendEvent(window, event)
        QTest.qWait(50)
    low = window.grabWindow()
    wheel(120*16, 115)
    assert 100 < timeline.property('waveformGain') < 256
    assert timeline.property('viewStart') == 0 and timeline.property('viewDuration') == 0
    screenshot('waveform-amplified.png')
    high = window.grabWindow()
    # Inspect an interior signal region, excluding borders, text and the playhead.
    point = audio.mapToScene(QPointF(audio.width()*.2, 4)).toPoint()
    low_crop = low.copy(point.x(), point.y(), 100, 35)
    high_crop = high.copy(point.x(), point.y(), 100, 35)
    assert low_crop != high_crop
    np.testing.assert_array_equal(preview.waveformColumns(1000000, 0, 6, 600), columns)
    assert preview.export_spec() == original_spec
    assert project.timeline(preview._clips) == original_project
    assert (preview.volume, preview.muted) == original_volume
    wheel(120*40, 115); assert timeline.property('waveformGain') == 256
    wheel(-120*80, 115); assert timeline.property('waveformGain') == 1
    wheel(120, 115, Qt.KeyboardModifier.ControlModifier)
    assert timeline.property('visibleDuration') < 6 and timeline.property('waveformGain') == 1
    wheel(-120, 20)
    assert timeline.property('viewStart') > 0 and timeline.property('waveformGain') == 1
    timeline.setProperty('viewStart', 0); timeline.setProperty('viewDuration', 0)
    passed('shift_wheel_amplifies_low_waveform_only_limits_and_other_wheel_gestures')

    model = preview._clips
    assert model.unlink()
    model.activate('audio')
    assert model.split_at(3)
    model.select(0)
    assert model.delete_selected() and model.remove_gap(0)
    preview._editing_changed()
    moved = np.array(preview.waveformColumns(1000000, 0, 3, 300))
    np.testing.assert_allclose(moved, columns[300:])
    # Video lane remains unchanged after audio edits.
    assert preview.timelineThumbnails(0, 0, 6, 1)[0]['url'] == QUrl.fromLocalFile(files[0]).toString()
    assert model.audio.duplicate(0)
    preview._editing_changed()
    np.testing.assert_allclose(preview.waveformColumns(1000001, 3, 6, 300), moved)
    passed('unlinked_audio_delete_close_gap_duplicate_and_source_mapping')
    saved = model.audio.clips.copy()
    # A joined clip can concatenate reordered source pieces without retaining
    # the deleted middle; the visual mapping must follow that same order.
    model.audio.clips = [replace(saved[0], pieces=((120, 150), (30, 60)))]
    preview._editing_changed()
    joined = np.array(preview.waveformColumns(1000000, 0, 2, 200))
    np.testing.assert_allclose(joined, np.concatenate((columns[400:500], columns[100:200])))
    assert model.audio.resize(0, 'left', .5)
    preview._editing_changed()
    np.testing.assert_allclose(preview.waveformColumns(1000000, .5, 2, 150), joined[50:])
    model.audio.clips = saved
    preview._editing_changed()
    passed('reordered_join_and_trim_follow_retained_source_pieces')
    timeline = window.findChild(QQuickItem, 'editTimeline')
    timeline.setProperty('viewDuration', 1.5)
    timeline.setProperty('viewStart', .75)
    screenshot('zoomed.png')
    assert len(preview.waveformColumns(1000000, .75, 2.25, 10000)) == 4096
    passed('qml_zoom_pan_and_bounded_visible_waveform')

    cached = {}
    build_visuals(str(source), preview._origin, 6, preview._audio_timeline, threading.Event(), lambda kind, value: cached.update({kind:value}))
    assert 'visuals-error' not in cached
    np.testing.assert_array_equal(cached['waveform'][1][0], preview._waveform[1][0])
    assert cached['thumbnails'] == preview._thumbnails
    cancel = threading.Event(); cancel.set()
    discarded = []
    build_visuals(str(source), 0, 6, preview._audio_timeline, cancel, lambda *value: discarded.append(value))
    assert discarded == []
    revision = preview.visualRevision
    preview._receive_index(preview._source_generation-1, 'waveform', None)
    assert preview.visualRevision == revision
    passed('cache_round_trip_cancellation_and_stale_source_results')
    # Existing main-window startup warnings are unrelated to timeline visuals.
    baseline = ('Main.qml:84:21: Unable to assign [undefined] to QString',
                'Main.qml:411:13: QML QQuickImage: Failed to get image from provider: image://frames/current?revision=1')
    unexpected = [warning for warning in warnings if not any(known in warning for known in baseline)]
    assert not unexpected, unexpected
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    passed('no_new_qml_warnings_and_original_source_unchanged')
    (OUT/'report.json').write_text(json.dumps({'status':'pass', 'checks':checks, 'run':str(run), 'existing_startup_warnings':warnings}, indent=2), encoding='utf-8')
finally:
    preview.close()
    window.close()
