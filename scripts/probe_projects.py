"""Project round trips, source protection and actual QML project controls."""
import copy
from dataclasses import replace
from fractions import Fraction
import json
import os
from pathlib import Path
from test_fixture import ensure_fixture
import sys
import time
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ.setdefault('QT_QUICK_BACKEND','software')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from splicelet import project
from splicelet.editing import Clip, Clips
from splicelet.effects import Fades

OUT = ROOT/'artifacts'/'project-tests'
OUT.mkdir(parents=True,exist_ok=True)
(OUT/'report.json').unlink(missing_ok=True)
checks = []
def passed(name):
    checks.append(name)
    print('PASS',name,flush=True)
def rejected(fn):
    try: fn()
    except (ValueError,KeyError,TypeError,OSError): return
    raise AssertionError('Expected rejection')

source = OUT/'source.bin'
source.write_bytes(b'project source protection fixture')
times = [Fraction(i,30) for i in range(120)]
model = Clips(120,times,Fraction(4))
model.clips = [Clip(7,Fraction(-1),((60,90),(0,15)),Fades(.3,.4,.5,.6),((30,60),),((15,30),)),
               Clip(9,Fraction(2),((90,120),))]
model.origin,model.extent = Fraction(-1),Fraction(5)
data = project.document(model,source)
path = OUT/'roundtrip.splicelet'
project.write(path,data)
restored = project.restore(project.read(path),times,Fraction(4))
assert project.timeline(restored)==project.timeline(model)
assert restored.parts()==model.parts() and restored.frames()==model.frames()
assert restored.next_id==10
assert not restored.undo_stack
passed('exact_reordered_ranges_fades_reserves_negative_origin_and_gaps')
named = Clips(120,times,Fraction(4))
assert named.rename('  Opening shot  ') and named.selected_clip.name=='Opening shot'
named.undo(); assert named.selected_clip.name==''
named.redo(); assert named.selected_clip.name=='Opening shot'
assert named.split(60) and all(c.name=='Opening shot' for c in named.clips)
assert named.duplicate(named.selected) and named.selected_clip.name=='Opening shot'
named.select(0); named.select(1,True); assert named.join()
assert named.selected_clip.name=='Opening shot'
assert project.timeline(project.restore(project.document(named,source),times,Fraction(4)))==project.timeline(named)
legacy = copy.deepcopy(project.document(named,source))
for clip in legacy['timeline']['clips']: clip.pop('name')
assert all(c.name=='' for c in project.restore(legacy,times,Fraction(4)).clips)
for bad in (None,42,'a'*121,'two\nlines'):
    invalid = copy.deepcopy(project.document(named,source)); invalid['timeline']['clips'][0]['name']=bad
    rejected(lambda:project.restore(invalid,times,Fraction(4)))
assert named.rename('') and named.selected_clip.name==''
passed('clip_names_history_split_duplicate_join_persistence_legacy_and_validation')

model.clips = []
for end in (Fraction(5),model.origin):
    model.extent = end
    empty = project.restore(project.document(model,source),times,Fraction(4))
    assert empty.clips==[] and empty.duration==model.duration
passed('empty_timeline_and_zero_duration')
for mutate in (lambda d:d['timeline']['clips'][0].update(start=[1,0]),
               lambda d:d['timeline']['clips'][0]['pieces'][0].update(end=1000),
               lambda d:d['timeline']['clips'][0]['pieces'][0].update(source='unknown'),
               lambda d:d['timeline']['clips'][0]['fades'].update(audio_in=float('nan')),
               lambda d:d['timeline']['clips'][1].update(id=7),
               lambda d:d['timeline']['clips'][1].update(start=[-1,1])):
    invalid = copy.deepcopy(data); mutate(invalid)
    rejected(lambda:project.restore(invalid,times,Fraction(4)))
passed('invalid_times_ranges_sources_fades_ids_and_overlaps')
rejected(lambda:project.write(source,data))
assert source.read_bytes()==b'project source protection fixture'
alias = OUT/'source-alias.bin'
if alias.exists(): alias.unlink()
os.link(source,alias)
rejected(lambda:project.write(alias,data))
assert source.read_bytes()==b'project source protection fixture'
passed('source_and_hardlink_alias_cannot_be_overwritten')
missing = copy.deepcopy(data); missing['sources'][0]['path'] = str(OUT/'missing-video.mkv')
(OUT/'missing.splicelet').write_text(json.dumps(missing),encoding='utf-8')
try: project.read(OUT/'missing.splicelet')
except ValueError as exc: assert str(OUT/'missing-video.mkv') in str(exc)
else: raise AssertionError('Missing source accepted')
source.write_bytes(b'changed fixture')
rejected(lambda:project.read(path))
passed('missing_source_full_path_and_changed_source_rejected')
previous = path.read_bytes()
with patch.object(project.os,'replace',side_effect=OSError('Simulated publication failure')):
    rejected(lambda:project.write(path,data))
assert path.read_bytes()==previous
assert not list(OUT.glob('.splicelet-*.tmp'))
passed('failed_atomic_save_preserves_previous_project_and_cleans_temporary_file')

from PySide6.QtCore import QSettings, QUrl, Qt, QObject, QMetaObject
from PySide6.QtGui import QGuiApplication, QFontDatabase
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from splicelet.controller import FrameProvider, Preview
app = QGuiApplication([])
QQuickStyle.setStyle('Basic')
if not QFontDatabase.families():
    for name in ('segoeui.ttf','segoeuib.ttf','consola.ttf'):
        QFontDatabase.addApplicationFont(str(Path(os.environ.get('SystemRoot','C:/Windows'))/'Fonts'/name))
QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat,QSettings.Scope.UserScope,str(OUT/'settings'))
provider = FrameProvider(); preview = Preview(provider,muted=True)
preview._settings.clear(); preview._recent = []
engine = QQmlApplicationEngine(); engine.addImageProvider('frames',provider)
engine.setInitialProperties({'preview':preview})
engine.load(QUrl.fromLocalFile(str(ROOT/'splicelet/Main.qml')))
assert engine.rootObjects()
window = engine.rootObjects()[0]
errors = []; preview.projectError.connect(errors.append)
def wait(predicate):
    deadline = time.monotonic()+30
    while not predicate():
        assert time.monotonic()<deadline, preview.status
        app.processEvents(); QTest.qWait(10)
try:
    source_file = ensure_fixture()
    preview.open_path(str(source_file))
    wait(lambda:preview.canSaveProject and not preview.busy)
    preview.seek(2); wait(lambda:not preview.busy)
    preview.cut()
    preview.setFade('audio_in','0.45')
    expected = project.timeline(preview._clips)
    target = OUT/'gui.splicelet'
    assert preview.saveProjectAs(QUrl.fromLocalFile(str(target)))
    assert not preview.projectDirty
    preview.setFade('video_out','1.25')
    assert preview.projectDirty
    preview.undoCut(); assert not preview.projectDirty
    preview.openProject(QUrl.fromLocalFile(str(target)))
    wait(lambda:preview.canSaveProject and not preview.busy)
    assert project.timeline(preview._clips)==expected and not preview.projectDirty
    assert preview.projectName=='gui'
    passed('controller_save_open_dirty_and_undo')
    before = preview._clips
    preview.openProject(QUrl.fromLocalFile(str(OUT/'missing.splicelet')))
    assert errors and str(OUT/'missing-video.mkv') in errors[-1]
    assert preview._clips is before
    passed('missing_source_aborts_without_replacing_current_project')
    for dialog in window.findChildren(QObject):
        if dialog.metaObject().indexOfSignal('accepted()')>=0 and dialog.property('title')=='Project error':
            QMetaObject.invokeMethod(dialog,'accept')
    for i in range(12):
        assert preview.saveProjectAs(QUrl.fromLocalFile(str(OUT/f'recent-{i}.splicelet')))
    assert len(preview.recentProjects)==10 and preview.recentProjects[0].endswith('recent-11.splicelet')
    assert len(set(preview.recentProjects))==10
    assert preview.saveProject()
    assert len(preview.recentProjects)==10
    assert QSettings('Splicelet','Splicelet').value('recentProjects',[],type=list)==preview.recentProjects
    passed('recent_projects_persist_order_deduplicate_and_limit_ten')
    menu = window.findChild(QObject,'fileMenu')
    QMetaObject.invokeMethod(menu,'open')
    QTest.qWait(100)
    window.grabWindow().save(str(OUT/'file-menu.png'))
    assert menu.property('count')==7
    QMetaObject.invokeMethod(menu,'close')
    recent = window.findChild(QObject,'recentMenu')
    assert recent.property('count')==10
    preview.setFade('video_out','1.5')
    QTest.keyClick(window,Qt.Key.Key_S,Qt.KeyboardModifier.ControlModifier)
    QTest.qWait(100)
    assert not preview.projectDirty
    QTest.keyClick(window,Qt.Key.Key_S,Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.ShiftModifier)
    QTest.qWait(100)
    dialog = window.findChild(QObject,'saveProjectDialog')
    assert dialog.property('visible')
    QMetaObject.invokeMethod(dialog,'reject')
    passed('file_menu_recent_submenu_and_save_shortcuts')
    preview.setFade('video_out','2')
    window.close(); QTest.qWait(100)
    dialog = window.findChild(QObject,'unsavedProjectDialog')
    assert dialog.property('visible') and window.isVisible()
    QMetaObject.invokeMethod(dialog,'reject')
    assert window.isVisible() and preview.projectDirty
    passed('close_prompts_and_cancel_preserves_project')
    window.close(); QTest.qWait(50)
    QMetaObject.invokeMethod(dialog,'accept')
    QTest.qWait(50)
    assert not preview.projectDirty and not window.isVisible()
    passed('close_save_commits_changes_before_closing')
finally:
    preview.close()
    engine.deleteLater()
(OUT/'report.json').write_text(json.dumps({'status':'pass','checks':checks},indent=2),encoding='utf-8')
