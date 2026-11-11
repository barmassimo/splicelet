"""Project-edge black/silent space: rational metadata, history and real QML controls."""
from fractions import Fraction
import json
import os
from pathlib import Path
from test_fixture import ensure_fixture
import sys
import time
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ.setdefault('QT_QUICK_BACKEND','software')
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
OUT=ROOT/'artifacts/edge-space-tests'; OUT.mkdir(parents=True,exist_ok=True)
from splicelet.editing import Clips
from splicelet import project
checks=[]
def passed(name):
    checks.append(name); print('PASS',name,flush=True)
model=Clips(4,[Fraction(0),Fraction(1,10),Fraction(3,10),Fraction(3,4)],Fraction(1))
model.rename('Opening'); model.undo_stack.clear()
before=model.snapshot(); clips=model.clips.copy(); selected=model.selected_ids.copy()
assert model.add_space('start','1.25') and model.origin==Fraction(-5,4)
assert model.clips==clips and model.selected_ids==selected
assert model.gaps()==((Fraction(0),Fraction(5,4)),) and model.duration==Fraction(9,4)
prefixed=model.snapshot()
assert model.add_space('end','0.5') and model.duration==Fraction(11,4)
assert model.gaps()==((0,Fraction(5,4)),(Fraction(9,4),Fraction(11,4)))
assert model.clips==clips
after=model.snapshot(); model.undo(); assert model.snapshot()==prefixed
model.undo(); assert model.snapshot()==before
model.redo(); model.redo(); assert model.snapshot()==after
passed('exact_decimal_edge_space_preserves_clips_names_selection_and_atomic_history')
for side,value in (('middle','1'),('start','0'),('end','-1'),('start','nan'),('end','inf'),('end','1,5')):
    before=model.snapshot(); history=len(model.undo_stack)
    try: model.add_space(side,value)
    except ValueError: pass
    else: raise AssertionError((side,value))
    assert model.snapshot()==before and len(model.undo_stack)==history
passed('invalid_space_has_no_side_effects')
state=project.timeline(model)
restored=project.restore({'timeline':state},model.times,model.source_duration)
assert project.timeline(restored)==state
assert restored.remove_gap(0) and restored.remove_gap(0)
assert restored.duration==1 and restored.parts()[0].start==0
empty=Clips(4,model.times,model.source_duration); empty.delete_selected(); empty.remove_gap(0)
assert empty.duration==0
assert empty.add_space('start','.125') and empty.add_space('end','.25')
assert not empty.clips and empty.duration==Fraction(3,8) and all(frame is None for _,frame in empty.frames())
passed('space_persists_remains_removable_and_works_with_empty_timeline')

from PySide6.QtCore import QObject,QSettings,QUrl,Qt,QPointF,QMetaObject,QLocale
from PySide6.QtGui import QGuiApplication,QFontDatabase
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from splicelet.controller import FrameProvider,Preview,FrameKeys
QLocale.setDefault(QLocale('en_US'))
app=QGuiApplication([]); QQuickStyle.setStyle('Basic')
if not QFontDatabase.families():
    for name in ('segoeui.ttf','segoeuib.ttf','consola.ttf'):
        QFontDatabase.addApplicationFont(str(Path(os.environ.get('SystemRoot','C:/Windows'))/'Fonts'/name))
QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat,QSettings.Scope.UserScope,str(OUT/'settings'))
provider=FrameProvider(); preview=Preview(provider,muted=True)
engine=QQmlApplicationEngine(); engine.addImageProvider('frames',provider); engine.setInitialProperties({'preview':preview})
engine.load(QUrl.fromLocalFile(str(ROOT/'splicelet/Main.qml')))
assert engine.rootObjects()
window=engine.rootObjects()[0]; keys=FrameKeys(window,preview); app.installEventFilter(keys)
def wait(predicate):
    deadline=time.monotonic()+30
    while not predicate():
        assert time.monotonic()<deadline,preview.status
        app.processEvents(); QTest.qWait(10)
def click(item):
    QTest.mouseClick(window,Qt.MouseButton.LeftButton,pos=item.mapToScene(QPointF(item.width()/2,item.height()/2)).toPoint())
    QTest.qWait(50)
def black():
    return not any(bytes(provider.image.constBits()))
try:
    start=window.findChild(QObject,'addStartSpaceAction'); end=window.findChild(QObject,'addEndSpaceAction')
    assert not start.property('enabled') and not end.property('enabled')
    preview.open_path(str(ensure_fixture()))
    wait(lambda:preview.indexedReady and not preview.busy); QTest.qWait(50); window.requestActivate()
    timeline=window.findChild(QQuickItem,'editTimeline')
    assert timeline.property('inset')==12
    assert window.findChild(QQuickItem,'addStartSpaceButton') is None and window.findChild(QQuickItem,'addEndSpaceButton') is None
    assert not start.property('shortcut') and not end.property('shortcut')
    menu=window.findChild(QObject,'editMenu')
    assert menu.property('count')==10
    QMetaObject.invokeMethod(menu,'open'); QTest.qWait(100)
    window.grabWindow().save(str(OUT/'edit-space-menu.png'))
    QMetaObject.invokeMethod(menu,'close'); QTest.qWait(100)
    def trigger(action):
        QMetaObject.invokeMethod(action,'trigger'); QTest.qWait(50)
    window.grabWindow().save(str(OUT/'plain-timeline.png'))
    original=preview._clips.snapshot(); duration=preview.duration; position=preview.position
    dialog=window.findChild(QObject,'addSpaceDialog'); field=window.findChild(QQuickItem,'spaceSeconds')
    confirm=window.findChild(QQuickItem,'confirmSpaceButton')
    trigger(start)
    assert dialog.property('visible') and not window.property('transportKeysEnabled')
    assert preview.position==position
    window.grabWindow().save(str(OUT/'start-dialog.png'))
    for bad in ('0','-1','nan','1,5'):
        field.setProperty('text',bad); click(confirm)
        assert dialog.property('visible') and dialog.property('error') and preview._clips.snapshot()==original
    field.forceActiveFocus(); QTest.keyClick(window,Qt.Key.Key_A,Qt.KeyboardModifier.ControlModifier)
    for char in '1.25': QTest.keyClick(window,Qt.Key(ord(char)))
    QTest.keyClick(window,Qt.Key.Key_Return)
    wait(lambda:not preview.busy); QTest.qWait(50)
    assert not dialog.property('visible') and abs(preview.duration-duration-1.25)<1e-6
    assert abs(preview.position-position-1.25)<1e-6 and preview.projectDirty
    assert preview._clips.clips==original[0][0] and preview.selectionCount==1
    prefixed=preview._clips.snapshot()
    passed('qml_menu_opens_modal_without_shortcuts_validates_seconds_and_adds_prefix')
    trigger(end); assert dialog.property('side')=='end'
    QMetaObject.invokeMethod(dialog,'reject'); QTest.qWait(50)
    assert preview._clips.snapshot()==prefixed
    trigger(end); field.setProperty('text','2.5'); click(confirm)
    wait(lambda:not preview.busy)
    assert abs(preview.duration-duration-3.75)<1e-6
    after=preview._clips.snapshot()
    preview.seek(0); wait(lambda:not preview.busy); assert black()
    preview.seek(preview.duration-1); wait(lambda:not preview.busy); assert black()
    window.grabWindow().save(str(OUT/'leading-trailing-black.png'))
    passed('qml_cancel_is_noop_and_both_added_edges_preview_as_black')
    preview.undoCut(); wait(lambda:not preview.busy); assert preview._clips.snapshot()==prefixed
    preview.undoCut(); wait(lambda:not preview.busy); assert preview._clips.snapshot()==original
    preview.redoCut(); wait(lambda:not preview.busy); preview.redoCut(); wait(lambda:not preview.busy)
    assert preview._clips.snapshot()==after
    assert preview.saveProjectAs(QUrl.fromLocalFile(str(OUT/'space.splicelet')))
    preview.openProject(QUrl.fromLocalFile(str(OUT/'space.splicelet')))
    wait(lambda:preview.canSaveProject and not preview.busy)
    assert preview._clips.clips==after[0][0] and preview._clips.origin==after[0][3] and preview._clips.extent==after[0][2]
    assert not preview.projectDirty
    preview.removeGap(0); wait(lambda:not preview.busy)
    preview.removeGap(len(preview._clips.gaps())-1); wait(lambda:not preview.busy)
    assert abs(preview.duration-duration)<1e-6
    timeline=window.findChild(QQuickItem,'editTimeline'); timeline.setProperty('viewDuration',duration/4); timeline.setProperty('viewStart',20)
    assert start.property('enabled') and end.property('enabled')
    window.setWidth(760); window.setHeight(560); QTest.qWait(100)
    window.grabWindow().save(str(OUT/'minimum-zoomed.png'))
    trigger(end); assert dialog.property('visible')
    QMetaObject.invokeMethod(dialog,'reject'); QTest.qWait(50)
    timeline.setProperty('viewDuration',0); timeline.setProperty('viewStart',0); QTest.qWait(50)
    window.grabWindow().save(str(OUT/'plain-timeline-minimum.png'))
    passed('edge_space_history_persistence_removal_and_menu_available_while_zoomed')
    preview.selectClip(0); preview.deleteSelected(); wait(lambda:not preview.busy)
    preview.removeGap(0); wait(lambda:not preview.busy)
    assert preview.duration==0 and start.property('enabled') and end.property('enabled')
    assert preview.addSpace('end','.5'); wait(lambda:not preview.busy)
    assert preview.duration==.5 and not preview._clips.clips and black()
    passed('qml_can_add_black_space_after_the_entire_timeline_is_empty')
finally:
    preview.close(); engine.deleteLater()
(OUT/'report.json').write_text(json.dumps({'status':'pass','checks':checks},indent=2),encoding='utf-8')
