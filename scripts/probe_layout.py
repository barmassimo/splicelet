"""Verify compact QML transport, menu shortcuts and preview-only listening gain."""
import json
import os
from pathlib import Path
from test_fixture import ensure_fixture
import sys
import time
from types import SimpleNamespace

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ.setdefault('QT_QUICK_BACKEND','software')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
OUT = ROOT/'artifacts/layout-tests'
OUT.mkdir(parents=True,exist_ok=True)
import numpy as np
from PySide6.QtCore import QObject, QMetaObject, QSettings, QUrl, Qt, QPointF, QLocale, QPoint, QCoreApplication
from PySide6.QtGui import QGuiApplication, QFontDatabase, QWheelEvent
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from splicelet.controller import FrameProvider, Preview

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
engine.setInitialProperties({'preview':preview})
engine.load(QUrl.fromLocalFile(str(ROOT/'splicelet/Main.qml')))
assert engine.rootObjects()
window = engine.rootObjects()[0]
checks = []
def passed(name):
    checks.append(name)
    print('PASS',name,flush=True)
def wait(predicate):
    deadline = time.monotonic()+30
    while not predicate():
        assert time.monotonic()<deadline,preview.status
        app.processEvents(); QTest.qWait(10)
try:
    preview.open_path(str(ensure_fixture()))
    wait(lambda:preview.indexedReady and not preview.busy)
    assert preview.volume==1.
    before = preview.export_spec()
    generation = preview._generation
    for value,expected in ((-1,0),(0.5,.5),(2.,2.),(3.,2.)):
        preview.setVolume(value)
        assert preview.volume==expected and preview.muted
    preview.setVolume(float('nan')); assert preview.volume==2.
    preview.toggleMute(); assert not preview.muted
    if preview.sink: assert preview.sink.volume()==1.
    preview.setVolume(.4)
    preview.toggleMute(); assert preview.muted and preview.volume==.4
    if preview.sink: assert preview.sink.volume()==0.
    preview.toggleMute()
    if preview.sink: assert abs(preview.sink.volume()-.4)<1e-6
    assert preview.export_spec()==before and preview._generation==generation
    passed('volume_clamps_mute_restores_level_and_export_snapshot_is_unchanged')
    preview.setVolume(2.)
    original_format = preview.audio.sample_format
    for fmt,dtype,values,expected in (
        ('flt','<f4',[-1.,-.25,0.,.25,1.],[-1.,-.5,0.,.5,1.]),
        ('s16','<i2',[-32768,-10000,0,10000,32767],[-32768,-20000,0,20000,32767])):
        preview.audio.sample_format=fmt
        data=np.array(values,dtype=dtype).tobytes()
        np.testing.assert_allclose(np.frombuffer(preview._listening_pcm(data),dtype=dtype),expected,atol=1e-7)
        preview.setVolume(.75); assert preview._listening_pcm(data) is data
        preview.setVolume(2.)
    preview.audio.sample_format=original_format
    passed('float_and_int16_boost_preserves_headroom_and_saturates_without_wraparound')
    original_sink,original_io,original_audio=preview.sink,preview._io,preview.audio
    raw=np.array([.1,-.2]*16,dtype='<f4').tobytes()
    written=[]
    def write(data):
        count=min(8,len(data)); written.append(data[:count]); return count
    try:
        preview.sink=SimpleNamespace(bytesFree=lambda:len(raw))
        preview._io=SimpleNamespace(write=write)
        preview.audio=SimpleNamespace(sample_format='flt',sample_bytes=8,take_audio=lambda available:b'')
        preview._audio_pending=raw
        preview._pump_audio()
        np.testing.assert_allclose(np.frombuffer(b''.join(written),dtype='<f4'),np.frombuffer(raw,dtype='<f4')*2.)
        assert not preview._audio_pending
    finally:
        preview.sink,preview._io,preview.audio=original_sink,original_io,original_audio
    passed('partial_device_writes_do_not_amplify_pending_pcm_twice')
    preview.toggleMute()
    QTest.keyClick(window,Qt.Key.Key_E,Qt.KeyboardModifier.ControlModifier)
    QTest.qWait(100)
    dialog=window.findChild(QObject,'exportOptionsDialog')
    assert dialog.property('visible')
    QMetaObject.invokeMethod(dialog,'reject')
    passed('ctrl_e_opens_export_options')
    assert preview.saveProjectAs(QUrl.fromLocalFile(str(OUT/'import-check.splicelet')))
    QTest.keyClick(window,Qt.Key.Key_I,Qt.KeyboardModifier.ControlModifier)
    QTest.qWait(100)
    import_dialog=window.findChild(QObject,'importVideoDialog')
    assert import_dialog.property('visible')
    QMetaObject.invokeMethod(import_dialog,'reject')
    passed('ctrl_i_opens_import_dialog')
    timeline=window.findChild(QQuickItem,'editTimeline')
    old=timeline.property('visibleDuration')
    QTest.keyClick(window,Qt.Key.Key_Plus,Qt.KeyboardModifier.ControlModifier)
    QTest.qWait(50)
    assert abs(timeline.property('visibleDuration')-old/2)<.001
    QTest.keyClick(window,Qt.Key.Key_Minus,Qt.KeyboardModifier.ControlModifier)
    QTest.qWait(50)
    assert abs(timeline.property('visibleDuration')-old)<.001
    QTest.keyClick(window,Qt.Key.Key_Equal,Qt.KeyboardModifier.ControlModifier)
    QTest.qWait(50)
    assert abs(timeline.property('visibleDuration')-old/2)<.001
    QTest.keyClick(window,Qt.Key.Key_Minus,Qt.KeyboardModifier.ControlModifier)
    passed('ctrl_plus_minus_and_equal_alias_zoom_viewport')
    # Compare clip double-click with the ruler at exactly the same scene x.
    point=timeline.mapToScene(QPointF(timeline.width()*.35,20)).toPoint()
    QTest.mouseClick(window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.AltModifier,point)
    wait(lambda:not preview.busy)
    expected_position=preview.position
    preview.seek(0); wait(lambda:not preview.busy)
    clip_point=QPoint(point.x(),int(timeline.mapToScene(QPointF(0,65)).y()))
    original_clips=preview._clips.snapshot()
    QTest.mouseDClick(window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.AltModifier,clip_point)
    QTest.mouseRelease(window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.AltModifier,clip_point)
    wait(lambda:not preview.busy)
    assert abs(preview.position-expected_position)<.000001,(preview.position,expected_position)
    assert not preview.playing and preview._clips.snapshot()==original_clips
    preview.toggle(); wait(lambda:preview.playing and not preview.busy)
    QTest.mouseDClick(window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.AltModifier,clip_point)
    QTest.mouseRelease(window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.AltModifier,clip_point)
    wait(lambda:not preview.busy)
    assert preview.playing and abs(preview.position-expected_position)<.5
    preview.pause(); wait(lambda:not preview.busy)
    passed('clip_double_click_matches_ruler_seek_and_preserves_transport')
    duration=preview.duration/4
    timeline.setProperty('viewDuration',duration)
    timeline.setProperty('viewStart',duration)
    original_clips=preview._clips.snapshot()
    def wheel_at(y,pixels,angles):
        point=timeline.mapToScene(QPointF(timeline.width()/2,y))
        event=QWheelEvent(point,QPointF(window.mapToGlobal(point.toPoint())),pixels,angles,
                          Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier,Qt.ScrollPhase.ScrollUpdate,False,
                          Qt.MouseEventSource.MouseEventSynthesizedBySystem)
        QCoreApplication.sendEvent(window,event)
        QTest.qWait(30)
    for y in (20,65):
        for pixels,angles in ((QPoint(-45,0),QPoint()),(QPoint(0,-45),QPoint()),(QPoint(-20,-15),QPoint(-60,-30)),(QPoint(),QPoint(-120,0)),(QPoint(),QPoint(0,-120))):
            old_start=timeline.property('viewStart')
            wheel_at(y,pixels,angles)
            assert timeline.property('viewStart')>old_start,(y,pixels,angles,old_start,timeline.property('viewStart'))
            delta=-(pixels.x() or pixels.y())*timeline.property('secondsPerPixel') if not pixels.isNull() else -(angles.x() or angles.y())/120*duration*.15
            assert abs(timeline.property('viewStart')-min(preview.duration-duration,old_start+delta))<1e-6,(y,pixels,angles,old_start,delta,timeline.property('viewStart'))
            assert timeline.property('visibleDuration')==duration
            scroll=window.findChild(QQuickItem,'timelineScrollBar')
            assert abs(scroll.property('position')-timeline.property('viewStart')/preview.duration)<1e-6
    wheel_at(65,QPoint(100000,0),QPoint()); assert timeline.property('viewStart')==0
    wheel_at(20,QPoint(-100000,0),QPoint()); assert abs(timeline.property('viewStart')-(preview.duration-duration))<1e-6
    assert preview._clips.snapshot()==original_clips
    timeline.setProperty('viewDuration',0); timeline.setProperty('viewStart',0)
    passed('trackpad_pixel_and_angle_scroll_over_ruler_and_clips_updates_scrollbar_with_bounds')
    follow=window.findChild(QObject,'followAction')
    playhead=window.findChild(QQuickItem,'timelinePlayhead')
    def toggle_follow():
        QTest.keyClick(window,Qt.Key.Key_F); QTest.qWait(30)
    def assert_centered():
        assert abs(playhead.x()-timeline.width()/2)<1e-5,(playhead.x(),timeline.width())
        assert follow.property('checked') and timeline.property('followEnabled')
    assert not follow.property('checked')
    toggle_follow()
    assert follow.property('checked') and not window.property('fullScreen')
    assert timeline.property('viewStart')==0  # Fit view stays unchanged.
    timeline.setProperty('viewDuration',preview.duration/20)
    for target in (0,preview.duration/2,preview.duration):
        preview.seek(target); wait(lambda:not preview.busy); QTest.qWait(30)
        assert_centered()
    preview.seek(preview.duration/2); wait(lambda:not preview.busy)
    QTest.keyClick(window,Qt.Key.Key_Plus,Qt.KeyboardModifier.ControlModifier)
    QTest.qWait(30); assert_centered()
    preview.toggle(); wait(lambda:preview.playing and not preview.busy)
    old_position=preview.position
    wait(lambda:preview.position>old_position); assert_centered()
    preview.pause()
    start=timeline.property('viewStart')
    toggle_follow()
    assert not follow.property('checked') and timeline.property('viewStart')==start
    preview.seek(preview.position+2); wait(lambda:not preview.busy)
    assert timeline.property('viewStart')==start
    view=window.findChild(QObject,'viewMenu')
    QMetaObject.invokeMethod(view,'open'); QTest.qWait(50)
    QMetaObject.invokeMethod(follow,'trigger'); QTest.qWait(30)
    assert_centered()
    QMetaObject.invokeMethod(view,'open'); QTest.qWait(50)
    window.grabWindow().save(str(OUT/'follow-menu.png'))
    QMetaObject.invokeMethod(view,'close'); QTest.qWait(30)
    # A horizontal ruler drag releases tracking; a press alone may start a box selection.
    preview.seek(0); wait(lambda:not preview.busy)
    point=timeline.mapToScene(QPointF(timeline.width()*.65,20)).toPoint()
    expected=(timeline.width()*.65-timeline.property('inset'))*timeline.property('secondsPerPixel')+timeline.property('viewStart')
    QTest.mousePress(window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.AltModifier,point)
    QTest.mouseMove(window,point+QPoint(25,0)); QTest.qWait(30)
    assert not follow.property('checked')
    QTest.mouseRelease(window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.AltModifier,point+QPoint(25,0))
    wait(lambda:not preview.busy)
    assert preview.position>expected
    toggle_follow(); wheel_at(20,QPoint(-45,0),QPoint())
    assert not follow.property('checked')
    toggle_follow()
    scroll=window.findChild(QQuickItem,'timelineScrollBar')
    point=scroll.mapToScene(QPointF(scroll.width()/2,scroll.height()/2)).toPoint()
    QTest.mouseClick(window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,point)
    assert not follow.property('checked')
    toggle_follow(); QTest.keyClick(window,Qt.Key.Key_Z); QTest.qWait(30)
    assert not follow.property('checked')
    QTest.keyClick(window,Qt.Key.Key_F11); QTest.qWait(30)
    assert window.property('fullScreen')
    QTest.keyClick(window,Qt.Key.Key_F11); QTest.qWait(30)
    assert not window.property('fullScreen')
    assert preview._clips.snapshot()==original_clips
    timeline.setProperty('viewDuration',0); timeline.setProperty('viewStart',0)
    passed('follow_shortcut_menu_centered_playback_seek_edges_zoom_and_manual_release')
    undo=window.findChild(QObject,'undoAction'); redo=window.findChild(QObject,'redoAction')
    assert not preview.canUndo and not preview.canRedo
    preview.seek(2); wait(lambda:not preview.busy); preview.cut(); wait(lambda:not preview.busy)
    assert preview.canUndo and not preview.canRedo and undo.property('enabled')
    edit=window.findChild(QObject,'editMenu')
    QMetaObject.invokeMethod(edit,'open'); QTest.qWait(100)
    window.grabWindow().save(str(OUT/'edit-menu.png'))
    QMetaObject.invokeMethod(undo,'trigger'); QMetaObject.invokeMethod(edit,'close')
    wait(lambda:not preview.busy)
    assert len(preview._clips.clips)==1 and preview.canRedo and not preview.canUndo
    QMetaObject.invokeMethod(edit,'open'); QTest.qWait(50)
    QMetaObject.invokeMethod(redo,'trigger'); QMetaObject.invokeMethod(edit,'close')
    wait(lambda:not preview.busy)
    assert len(preview._clips.clips)==2 and preview.canUndo and not preview.canRedo
    QTest.keyClick(window,Qt.Key.Key_Z,Qt.KeyboardModifier.ControlModifier); wait(lambda:not preview.busy)
    assert len(preview._clips.clips)==1
    QTest.keyClick(window,Qt.Key.Key_Y,Qt.KeyboardModifier.ControlModifier); wait(lambda:not preview.busy)
    assert len(preview._clips.clips)==2
    QTest.keyClick(window,Qt.Key.Key_Z,Qt.KeyboardModifier.ControlModifier); wait(lambda:not preview.busy)
    QTest.keyClick(window,Qt.Key.Key_Z,Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.ShiftModifier); wait(lambda:not preview.busy)
    assert len(preview._clips.clips)==2
    QTest.keyClick(window,Qt.Key.Key_Z,Qt.KeyboardModifier.ControlModifier); wait(lambda:not preview.busy)
    passed('edit_menu_undo_redo_enabled_state_and_all_shortcuts_share_history')
    def click_item(item):
        QTest.mouseClick(window,Qt.MouseButton.LeftButton,pos=item.mapToScene(QPointF(item.width()/2,item.height()/2)).toPoint())
    preview.selectClip(0); QTest.qWait(250)
    window.requestActivate(); QTest.qWait(50)
    field=window.findChild(QQuickItem,'clipName')
    click_item(field); QTest.qWait(50)
    assert not window.property('transportKeysEnabled'),(field.isVisible(),field.property('activeFocus'),field.mapToScene(QPointF()),preview.selectionCount)
    QTest.keyClick(window,Qt.Key.Key_A,Qt.KeyboardModifier.ControlModifier)
    for char in 'opening shot': QTest.keyClick(window,Qt.Key(ord(char.upper())),Qt.KeyboardModifier.ShiftModifier if char.isupper() else Qt.KeyboardModifier.NoModifier)
    generation=preview._generation
    spec=preview.export_spec()
    QTest.keyClick(window,Qt.Key.Key_Return); QTest.qWait(50)
    assert preview.selectedClipName=='opening shot' and preview.projectDirty,(preview.selectedClipName,field.property('text'),field.property('modified'),preview.status)
    assert preview._generation==generation and preview.export_spec()==spec
    assert preview.clips[0]['durationText']==preview.selectedDurationText==preview.durationText
    assert preview.clips[0]['label'].endswith('opening shot')
    QTest.keyClick(window,Qt.Key.Key_Z,Qt.KeyboardModifier.ControlModifier); wait(lambda:not preview.busy)
    assert preview.selectedClipName=='Clip 1'
    QTest.keyClick(window,Qt.Key.Key_Y,Qt.KeyboardModifier.ControlModifier); wait(lambda:not preview.busy)
    assert preview.selectedClipName=='opening shot'
    assert preview.saveProjectAs(QUrl.fromLocalFile(str(OUT/'named-clip.splicelet')))
    preview.openProject(QUrl.fromLocalFile(str(OUT/'named-clip.splicelet')))
    wait(lambda:preview.canSaveProject and not preview.busy)
    assert preview.selectedClipName=='opening shot' and not preview.projectDirty
    # Leaving the field by clicking a zoom button must commit to the same clip.
    click_item(field); QTest.keyClick(window,Qt.Key.Key_A,Qt.KeyboardModifier.ControlModifier)
    for char in 'main scene': QTest.keyClick(window,Qt.Key(ord(char.upper())),Qt.KeyboardModifier.ShiftModifier if char.isupper() else Qt.KeyboardModifier.NoModifier)
    old=timeline.property('visibleDuration')
    click_item(window.findChild(QQuickItem,'zoomInButton')); QTest.qWait(50)
    assert preview.selectedClipName=='main scene' and timeline.property('visibleDuration')<old
    click_item(window.findChild(QQuickItem,'zoomOutButton')); QTest.qWait(50)
    assert abs(timeline.property('visibleDuration')-old)<.001
    click_item(field); QTest.keyClick(window,Qt.Key.Key_A,Qt.KeyboardModifier.ControlModifier)
    for char in 'scene after tab': QTest.keyClick(window,Qt.Key(ord(char.upper())))
    QTest.keyClick(window,Qt.Key.Key_Tab); QTest.qWait(50)
    assert preview.selectedClipName=='scene after tab'
    # A non-name edit target can retain focus; finish it before later shortcuts.
    QTest.keyClick(window,Qt.Key.Key_Return); QTest.qWait(30)
    window.grabWindow().save(str(OUT/'clip-name-and-zoom.png'))
    passed('editable_clip_name_history_persistence_duration_and_zoom_buttons_commit_focus')


    help_menu=window.findChild(QObject,'helpMenu')
    assert help_menu.property('count')==2
    for name in ('about','shortcuts'):
        QMetaObject.invokeMethod(window.findChild(QObject,name+'Action'),'trigger')
        QTest.qWait(100)
        help_dialog=window.findChild(QObject,name+'Dialog')
        assert help_dialog.property('visible') and not window.property('transportKeysEnabled')
        position=preview.position
        QTest.keyClick(window,Qt.Key.Key_Right)
        QTest.qWait(50)
        assert preview.position==position
        window.grabWindow().save(str(OUT/(name+'.png')))
        QMetaObject.invokeMethod(help_dialog,'accept')
    passed('help_actions_open_readable_modal_dialogs_and_block_transport_keys')
    volume_button=window.findChild(QQuickItem,'volumeButton')
    point=volume_button.mapToScene(QPointF()).toPoint()
    def icon_pixels():
        image=window.grabWindow().copy(point.x(),point.y(),int(volume_button.width()),int(volume_button.height()))
        return bytes(image.constBits())
    preview.setVolume(1.)
    if preview.muted: preview.toggleMute()
    QTest.qWait(100)
    assert volume_button.property('symbol')=='speaker'
    audible_pixels=icon_pixels()
    window.grabWindow().save(str(OUT/'speaker.png'))
    preview.toggleMute(); QTest.qWait(100)
    assert volume_button.property('symbol')=='muted' and icon_pixels()!=audible_pixels
    window.grabWindow().save(str(OUT/'muted.png'))
    passed('mute_repaints_speaker_waves_as_cross')

    view=window.findChild(QObject,'viewMenu')
    QMetaObject.invokeMethod(view,'open'); QTest.qWait(100)
    window.grabWindow().save(str(OUT/'view-menu.png'))
    assert view.property('count')==7
    QMetaObject.invokeMethod(view,'close')
    timeline=window.findChild(QQuickItem,'editTimeline')
    old=timeline.property('visibleDuration')
    QTest.keyClick(window,Qt.Key.Key_Z); QTest.qWait(50)
    assert timeline.property('visibleDuration')<=old
    play=window.findChild(QQuickItem,'playButton')
    previous=window.findChild(QQuickItem,'previousFrameButton')
    next_frame=window.findChild(QQuickItem,'nextFrameButton')
    field=window.findChild(QQuickItem,'timeInput')
    assert field.mapToScene(QPointF(0,field.height()/2)).y()==play.mapToScene(QPointF(0,play.height()/2)).y()
    frame_label=window.findChild(QQuickItem,'frameLabel')
    assert 0<frame_label.mapToScene(QPointF()).x()-next_frame.mapToScene(QPointF(next_frame.width(),0)).x()<12
    assert previous.mapToScene(QPointF()).y()==next_frame.mapToScene(QPointF()).y()
    assert preview.status not in ('Playing','Paused')
    window.grabWindow().save(str(OUT/'layout.png'))
    window.setWidth(760); window.setHeight(560); QTest.qWait(100)
    QMetaObject.invokeMethod(window.findChild(QObject,'shortcutsDialog'),'open'); QTest.qWait(100)
    window.grabWindow().save(str(OUT/'shortcuts-minimum.png'))
    scroll=window.findChild(QQuickItem,'shortcutsScroll')
    assert scroll.property('contentHeight')>scroll.property('availableHeight')
    flickable=scroll.property('contentItem')
    flickable.setProperty('contentY',scroll.property('contentHeight')-scroll.property('availableHeight'))
    QTest.qWait(100)
    window.grabWindow().save(str(OUT/'shortcuts-bottom.png'))
    QMetaObject.invokeMethod(window.findChild(QObject,'shortcutsDialog'),'accept')
    slider=window.findChild(QQuickItem,'volumeSlider')
    assert slider.mapToScene(QPointF(slider.width(),0)).x()<=window.width()
    window.grabWindow().save(str(OUT/'layout-minimum.png'))
    preview._exporting=True; preview._export_progress=.42; preview._export_status='Exporting video…'
    preview._status='Clip duplicated into the adjacent space.'; preview.exportChanged.emit(); preview.changed.emit()
    QTest.qWait(100)
    window.grabWindow().save(str(OUT/'status-export.png'))
    assert window.findChild(QQuickItem,'statusText').property('text').startswith('Exporting video…')
    preview._exporting=False
    passed('view_menu_transport_alignment_minimum_width_and_unified_export_status')
finally:
    preview.close()
    engine.deleteLater()
(OUT/'report.json').write_text(json.dumps({'status':'pass','checks':checks},indent=2),encoding='utf-8')
