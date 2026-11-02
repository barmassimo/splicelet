"""Export options, constant sample-peak normalization and actual QML controls."""
from dataclasses import replace
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ.setdefault('QT_QUICK_BACKEND','software')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
OUT = ROOT/'artifacts/export-option-tests'
OUT.mkdir(parents=True,exist_ok=True)
run = OUT/str(time.time_ns()); run.mkdir()

import av
import numpy as np
from PySide6.QtCore import QObject,QUrl,QMetaObject,Qt,QPointF,QLocale
from PySide6.QtGui import QGuiApplication,QFontDatabase
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from splicelet.controller import Preview,FrameProvider
from splicelet.exporting import ExportTask
from splicelet.normalization import sample_peaks,normalization_gains,normalization_filter
from splicelet.runtime import ffmpeg_executable

checks = []
def passed(name):
    checks.append(name); print('PASS',name,flush=True)
ffmpeg = str(ffmpeg_executable())
def ff(*args):
    return subprocess.run([ffmpeg,'-hide_banner','-nostdin',*map(str,args)],capture_output=True,check=True)
source = run/'source.mkv'
ff('-f','lavfi','-i','testsrc2=size=160x90:rate=10:duration=2','-f','lavfi','-i',
   'aevalsrc=0.317*sin(2*PI*440*t)|0.1*sin(2*PI*700*t):s=48000:d=2',
   '-c:v','libx264','-c:a','pcm_f32le',source)
source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
QLocale.setDefault(QLocale('en_US'))
app = QGuiApplication([]); QQuickStyle.setStyle('Basic')
if not QFontDatabase.families():
    for name in ('segoeui.ttf','segoeuib.ttf','consola.ttf'):
        QFontDatabase.addApplicationFont(str(Path(os.environ.get('SystemRoot','C:/Windows'))/'Fonts'/name))
provider = FrameProvider(); preview = Preview(provider,muted=True)
engine = QQmlApplicationEngine(); engine.addImageProvider('frames',provider)
engine.setInitialProperties({'preview':preview}); engine.load(QUrl.fromLocalFile(str(ROOT/'splicelet/Main.qml')))
assert engine.rootObjects()
window = engine.rootObjects()[0]
def wait(predicate):
    deadline = time.monotonic()+30
    while not predicate():
        assert time.monotonic()<deadline,preview.status
        app.processEvents(); QTest.qWait(10)
def obj(name): return window.findChild(QObject,name)
def invoke(item,method):
    QMetaObject.invokeMethod(item,method); QTest.qWait(50)
def click(name):
    item = window.findChild(QQuickItem,name)
    QTest.mouseClick(window,Qt.MouseButton.LeftButton,pos=item.mapToScene(QPointF(item.width()/2,item.height()/2)).toPoint())
    QTest.qWait(50)
try:
    preview.open_path(str(source)); wait(lambda:preview.indexedReady and not preview.busy)
    spec = preview.export_spec()
    spec = replace(spec,audio_effects=tuple(replace(span,fades=replace(span.fades,audio_in=.3,audio_out=.4)) for span in spec.audio_effects))
    plain = run/'plain.f32le'; ExportTask()._audio(spec,plain)
    raw = plain.read_bytes(); peaks = sample_peaks(raw)
    analysis = ff('-f','f32le','-ar','48000','-ac','2','-i',plain,'-af',
                  'aformat=sample_fmts=dbl,astats=reset=0:measure_perchannel=none:measure_overall=Peak_level',
                  '-f','null','-').stderr.decode(errors='replace')
    measured = float(re.findall(r'Peak level dB:\s*(\S+)',analysis)[-1])
    gain = round(-1-measured,6)
    assert normalization_gains(peaks,-1)==(gain,)
    passed('peak_and_gain_match_reference_astats_six_decimal_algorithm')
    for independent in (False,True):
        normalized = replace(spec,normalize_audio=True,normalize_channels_independently=independent)
        pcm = run/f'normalized-{independent}.f32le'
        found = ExportTask()._audio(normalized,pcm)
        assert pcm.read_bytes()==raw and np.array_equal(found,peaks)
        gains = normalization_gains(found,-1,independent)
        result = ff('-v','error','-f','f32le','-ar','48000','-ac','2','-i',pcm,
                    '-af',normalization_filter(gains),'-f','f64le','-').stdout
        samples = np.frombuffer(result,dtype='<f8').reshape(-1,2)
        expected = np.frombuffer(raw,dtype='<f4').reshape(-1,2).astype(np.float64)*10**(np.array(gains)/20)
        np.testing.assert_allclose(samples,expected,rtol=1e-12,atol=1e-14)
        if independent: np.testing.assert_allclose(np.max(abs(samples),axis=0),10**(-1/20),atol=2e-7)
        else: assert abs(np.max(abs(samples[:,0]))/np.max(abs(samples[:,1]))-peaks[0]/peaks[1])<1e-12
        target = run/f'normalized-{independent}.mp4'
        status,message = ExportTask()._execute(normalized,target); assert status=='success',message
        # Compare actual AAC packets to an independent reference encode of the same PCM.
        reference = run/f'reference-{independent}.m4a'
        ff('-v','error','-f','f32le','-ar','48000','-ac','2','-i',pcm,'-af',normalization_filter(gains),'-c:a','aac','-b:a','320k',reference)
        with av.open(str(target)) as a,av.open(str(reference)) as b:
            assert [bytes(p) for p in a.demux(audio=0) if p.size]==[bytes(p) for p in b.demux(audio=0) if p.size]
    passed('both_gain_modes_match_float64_reference_and_single_aac_encode')
    assert normalization_gains((0,0),-1,True)==(0,0)
    assert normalization_gains((0,.1),-1,True)[0]==0
    assert normalization_gains((1,1),0)==(-.0001,)
    for bad in (math.nan,math.inf,1):
        try: normalization_gains(peaks,bad)
        except ValueError: pass
        else: raise AssertionError(bad)
    for bad in (math.nan,math.inf):
        try: sample_peaks(np.array([bad,0],dtype='<f4').tobytes())
        except ValueError: pass
        else: raise AssertionError(bad)
    passed('silence_silent_channel_zero_target_margin_and_invalid_values')
    preview._clips.split_at(.5); preview._clips.split_at(1)
    preview._clips.select(1); preview._clips.delete_selected()
    preview._clips.add_space('start','.5'); preview._clips.add_space('end','.5'); preview._editing_changed()
    wait(lambda:not preview.busy)
    preview._clips.select(0); preview._editing_changed()
    selected = preview.export_spec(); all_spec = preview.export_spec(False)
    assert (selected.start,selected.end)==(.5,1) and (all_spec.start,all_spec.end)==(0,3)
    all_pcm = run/'all.f32le'; ExportTask()._audio(all_spec,all_pcm)
    samples = np.fromfile(all_pcm,dtype='<f4').reshape(-1,2)
    assert len(samples)==144000 and not np.any(samples[:24000]) and not np.any(samples[48000:72000]) and not np.any(samples[120000:])
    target = run/'all.mp4'; status,message = ExportTask()._execute(all_spec,target)
    assert status=='success',message
    with av.open(str(target)) as rendered:
        frames = list(rendered.decode(video=0))
        assert len(frames)==30
        assert np.max(frames[0].to_ndarray(format='rgb24'))<=3 and np.max(frames[-1].to_ndarray(format='rgb24'))<=3
        assert all(np.max(frame.to_ndarray(format='rgb24'))<=3 for frame in frames[10:15])
    passed('all_includes_leading_trailing_space_and_deleted_gap_with_exact_pcm_and_video')
    options = obj('exportOptionsDialog'); action = obj('exportAction')
    wait(lambda:not preview.busy and action.property('enabled'))
    invoke(action,'trigger')
    assert options.property('visible') and obj('exportAllRadio').property('checked')
    assert obj('exportSelectedRadio').property('enabled') and not obj('exportSelectedRadio').property('checked')
    assert obj('exportAllRadio').mapToScene(QPointF()).x()<obj('exportSelectedRadio').mapToScene(QPointF()).x()
    assert not obj('normalizeAudioCheck').property('checked') and not obj('normalizationLevel').property('enabled')
    assert obj('normalizationOptions').property('opacity')==0.4
    window.grabWindow().save(str(OUT/'normalization-disabled.png'))
    click('exportSelectedRadio'); assert obj('exportSelectedRadio').property('checked')
    assert not obj('normalizeChannelsCheck').property('checked')
    assert not window.property('transportKeysEnabled')
    click('normalizeAudioCheck'); assert obj('normalizationLevel').property('enabled')
    assert obj('normalizationOptions').property('opacity')==1
    assert not obj('normalizeChannelsCheck').property('checked')
    obj('normalizationLevel').setProperty('text','-1,5'); click('continueExportButton')
    assert options.property('visible') and options.property('error')
    obj('normalizationLevel').setProperty('text','-1.5')
    window.grabWindow().save(str(OUT/'selected-normalize.png'))
    click('normalizeChannelsCheck'); click('continueExportButton')
    assert not options.property('visible') and obj('exportVideoDialog').property('visible')
    assert options.property('normalize') and options.property('independent') and options.property('level')==-1.5
    qml_target = Path(preview.exportFileUrl(True).toLocalFile())
    invoke(obj('exportVideoDialog'),'accept')
    wait(lambda:not preview.exporting)
    assert qml_target.exists() and preview.exportStatus.startswith('Exported:'),preview.exportStatus
    invoke(action,'trigger')
    assert obj('exportAllRadio').property('checked') and not obj('exportSelectedRadio').property('checked')
    click('continueExportButton')
    invoke(obj('exportVideoDialog'),'reject'); assert not preview.exporting
    preview._clips.selected_ids.clear(); preview._editing_changed(); wait(lambda:not preview.busy)
    assert action.property('enabled')
    invoke(action,'trigger')
    assert obj('exportAllRadio').property('checked') and not obj('exportSelectedRadio').property('enabled')
    assert not obj('normalizeAudioCheck').property('checked') and not obj('normalizeChannelsCheck').property('checked')
    window.setWidth(760); window.setHeight(560); QTest.qWait(100)
    window.grabWindow().save(str(OUT/'all-minimum.png'))
    original_theme = preview.darkTheme
    preview.setDarkTheme(True); QTest.qWait(100)
    window.grabWindow().save(str(OUT/'all-dark.png'))
    preview.setDarkTheme(original_theme)
    invoke(options,'reject')
    passed('qml_defaults_validation_enabling_save_dialog_order_cancellation_and_minimum_layout')
    for normalized in (False,True):
        task = ExportTask()
        task.updated.connect(lambda fraction,message:task.cancel(),Qt.ConnectionType.DirectConnection)
        target = run/f'cancel-{normalized}.mp4'
        status,message = task._execute(replace(all_spec,normalize_audio=normalized),target)
        assert status=='cancelled' and not target.exists() and not list(run.glob('.video-export-*'))
    assert hashlib.sha256(source.read_bytes()).hexdigest()==source_hash
    passed('cancellation_with_both_modes_cleans_temporary_files_and_preserves_source')
finally:
    preview.close(); window.setProperty('closingApproved',True); window.close(); app.processEvents()
(OUT/'report.json').write_text(json.dumps({'checks':checks,'run':str(run)},indent=2),encoding='utf-8')
print('PASS',len(checks),'checks',flush=True)
