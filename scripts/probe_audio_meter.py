"""Check read-only preview metering, partial writes, mute and compact QML layout."""
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ.setdefault('QT_QUICK_BACKEND','software')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
from PySide6.QtCore import QLocale, QPointF, QSettings, QUrl
from PySide6.QtGui import QGuiApplication, QFontDatabase
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from splicelet.audio_meter import AudioMeter
from splicelet.controller import FrameProvider, Preview
from test_fixture import ensure_fixture

OUT = ROOT/'artifacts/audio-meter-tests'
OUT.mkdir(parents=True,exist_ok=True)
checks = []
for fmt,dtype in (('flt','<f4'),('s16','<i2')):
    values = np.tile([.5,.125],(4800,1))
    raw = (values if fmt=='flt' else values*32768).astype(dtype).tobytes()
    meter = AudioMeter()
    for start in range(0,len(raw),117): meter.append(raw[start:start+117],fmt)
    meter.update(.1)
    assert np.allclose(meter.levels,[-6.0206,-18.0618],atol=.0001)
    assert not meter.tail
    meter.update(.4)
    assert meter.levels[0]<-6.1 and abs(meter.peaks[0]+6.0206)<.0001
    meter.update(1.)
    assert meter.peaks[0]<-6.1
    meter.reset()
    assert not meter.blocks and meter.levels==[-60.,-60.]
checks.append('stereo_float_int16_partial_frames_decay_hold_reset')
meter = AudioMeter()
meter.append(np.tile([1.,0.],(1024*300,1)).astype('<f4').tobytes(),'flt')
assert len(meter.blocks)==256
meter.update(10.)
assert meter.levels==[0.,-60.]
checks.append('bounded_queue_full_scale_and_silence')

QLocale.setDefault(QLocale('en_US'))
app = QGuiApplication([])
QQuickStyle.setStyle('Basic')
if not QFontDatabase.families():
    for name in ('segoeui.ttf','segoeuib.ttf','consola.ttf'):
        QFontDatabase.addApplicationFont(str(Path(os.environ.get('SystemRoot','C:/Windows'))/'Fonts'/name))
QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat,QSettings.Scope.UserScope,str(OUT/'settings'))
provider = FrameProvider(); preview = Preview(provider,muted=True)
engine = QQmlApplicationEngine(); engine.addImageProvider('frames',provider)
warnings = []
engine.warnings.connect(lambda items:warnings.extend(str(item) for item in items))
engine.setInitialProperties({'preview':preview})
engine.load(QUrl.fromLocalFile(str(ROOT/'splicelet/Main.qml')))
assert engine.rootObjects(),warnings
window = engine.rootObjects()[0]
try:
    # Exercise the actual pump with irregular accepted byte counts and boost.
    real_audio,real_sink = preview.audio,preview.sink
    preview.timer.stop()
    original = np.tile([.25,-.125],(4800,1)).astype('<f4').tobytes()
    for volume in (.4,1.,1.8):
        preview._meter.reset()
        preview._volume = volume
        preview.audio = SimpleNamespace(sample_bytes=8,sample_format='flt',take_audio=lambda n:b'')
        preview.sink = SimpleNamespace(bytesFree=lambda:len(original))
        class Device:
            def __init__(self): self.data = bytearray()
            def write(self,data):
                count = min(len(data),116)
                self.data.extend(data[:count])
                return count
        preview._io = Device()
        preview._audio_pending = original
        preview._pump_audio()
        expected = original if volume<=1 else preview._listening_pcm(original)
        assert bytes(preview._io.data)==expected
        preview._meter.update(.1)
        assert np.allclose(preview.audioLevels,[-12.0412,-18.0618],atol=.0001)
    preview.audio,preview.sink,preview._io = real_audio,real_sink,None
    preview._volume = 1.
    preview._update_volume()
    preview.timer.start()
    checks.append('pump_bytes_unchanged_across_volume_and_partial_writes')
    preview.open_path(str(ensure_fixture()))
    def wait(predicate):
        for _ in range(3000):
            app.processEvents(); QTest.qWait(10)
            if predicate(): return
        raise AssertionError(preview.status)
    wait(lambda:preview.indexedReady and not preview.busy)
    meter_item = window.findChild(QQuickItem,'audioMeter')
    slider = window.findChild(QQuickItem,'volumeSlider')
    assert meter_item is not None
    if preview.audioEnabled:
        preview.toggle()
        wait(lambda:max(preview.audioLevels)>-59)
        assert preview.muted and meter_item.property('quiet')
        first = preview.position
        QTest.qWait(150)
        assert preview.position>first and max(preview.audioLevels)>-59
        preview.setVolume(0.)
        QTest.qWait(100)
        assert max(preview.audioLevels)>-59
        checks.append('actual_muted_and_zero_volume_playback_keeps_meter_active')
    else:
        checks.append('no_device_meter_activity_unverified')
    # Freeze transport updates while inspecting a deterministic stereo level.
    preview.pause(); preview.timer.stop()
    preview._meter.levels = [-10.,-18.]
    preview._meter.peaks = [-6.,-12.]
    preview.meterChanged.emit()
    preview.setVolume(1.)
    for dark in (False,True):
        preview.setDarkTheme(dark)
        for width in (760,1000,1120,1440):
            window.setWidth(width)
            QTest.qWait(120)
            left = meter_item.mapToScene(QPointF())
            right = meter_item.mapToScene(QPointF(meter_item.width(),0))
            window.grabWindow().save(str(OUT/'latest-layout.png'))
            assert right.x()<=width and left.x()>=slider.mapToScene(QPointF(slider.width(),0)).x(),(width,left.x(),right.x(),slider.mapToScene(QPointF(slider.width(),0)).x())
            if preview.muted: preview.toggleMute()
            QTest.qWait(30)
            window.grabWindow().save(str(OUT/f'{"dark" if dark else "light"}-{width}.png'))
        preview.toggleMute()
        QTest.qWait(30)
        assert meter_item.property('quiet')
        window.grabWindow().save(str(OUT/f'{"dark" if dark else "light"}-muted.png'))
    preview._stop_transport()
    assert preview.audioLevels==[-60.,-60.]
    assert not warnings,warnings
    checks.append('qml_light_dark_mute_widths_and_reset_without_warnings')
finally:
    preview.audio,preview.sink = real_audio,real_sink
    preview._io = None
    preview.close()
    window.setVisible(False)
(OUT/'report.json').write_text(json.dumps({'checks':checks,'warnings':warnings},indent=2),encoding='utf-8')
print(json.dumps({'checks':checks,'warnings':warnings},indent=2))
