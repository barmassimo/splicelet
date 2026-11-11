"""Range selection and atomic group moves, including actual QML mouse gestures."""
from dataclasses import replace
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
OUT=ROOT/'artifacts/group-edit-tests'
OUT.mkdir(parents=True,exist_ok=True)
from splicelet.editing import Clip, Clips
from splicelet.effects import Fades
from splicelet.tracks import Tracks
checks=[]
def passed(name):
    checks.append(name); print('PASS',name,flush=True)

def fixture():
    times=[Fraction(i*100+i%3,1000) for i in range(60)]
    model=Clips(len(times),times,Fraction(6))
    model.clips=[Clip(i,Fraction(i*3),((i*10,(i+1)*10),),Fades(.1,.2,.3,.4),name=f'Clip {i}') for i in range(5)]
    model.extent=Fraction(15)
    model.next_id=5
    model.select(0)
    return model
model=fixture()
model.selected_ids={0,2,4}
assert model.selected_length==sum((model.length(model.clips[i]) for i in (0,2,4)),Fraction(0))
model.clips[1]=replace(model.clips[1],start=Fraction(1,2))
model.selected_ids={0,1}
assert model.selected_length==model.end(model.clips[1])-model.clips[0].start
model.selected_ids.clear(); assert model.selected_length==0
passed('selected_length_uses_exact_union_excluding_gaps_and_duplicate_overlap')
model=fixture()
model.select(2); model.select(4,False,True); assert model.selected_indices=={2,3,4}
model.select(1,False,True); assert model.selected_indices=={1,2}
model.select(3,False,True); assert model.selected_indices=={2,3}
model.select(0,True); assert model.selected_indices=={0,2,3}
model.select(1,False,True); assert model.selected_indices=={0,1}
model.select(4,True); model.select(3,True,True); assert model.selected_indices=={0,1,3,4}
assert not model.undo_stack
passed('shift_range_forward_backward_fixed_anchor_ctrl_toggle_and_additive_range')
model=fixture(); model.select(1); model.select(3,False,True)
before=model.snapshot(); originals={c.uid:c for c in model.clips}
assert model.moving_indices(2)==(1,2,3)
assert model.move_selection(2,Fraction(19,3))
assert model.selected_ids=={1,2,3} and len(model.undo_stack)==1
for c in model.clips:
    delta=Fraction(1,3) if c.uid in {1,2,3} else Fraction(0)
    assert c==replace(originals[c.uid],start=originals[c.uid].start+delta)
assert model.clips[2].start-model.end(model.clips[1])==originals[2].start-model.end(originals[1])
after=model.snapshot(); model.undo(); assert model.snapshot()==before
model.redo(); assert model.snapshot()==after
passed('gapped_consecutive_group_moves_by_exact_delta_and_undo_redo_is_atomic')
model=fixture(); model.select(1); model.select(3,True)
before=model.snapshot(); history=len(model.undo_stack)
assert model.moving_indices(1)==() and not model.move_selection(1,4)
assert model.snapshot()==before and len(model.undo_stack)==history
model.select(1); model.select(3,False,True)
before=model.snapshot()
assert model.move_selection(2,8) and model.has_overlaps
model.undo(); assert model.snapshot()==before
# An unselected clip cannot be inserted into an internal gap of the moved block.
assert not model.move_selection(2,14) and model.snapshot()==before
assert not model.move_selection(2,-50) and model.snapshot()==before
model=fixture(); model.origin=Fraction(-3); model.select(0); model.select(2,False,True)
assert model.move_selection(2,-100) and model.clips[0].start==model.origin
assert model.clips[1].start==0 and model.clips[2].start==3
passed('sparse_selection_collisions_internal_gap_occupation_and_negative_origin_limits')
model=fixture(); model.select(1); model.select(2,False,True)
assert model.move_selection(4,14) and model.selected_indices=={4}
assert [c.start for c in model.clips[:4]]==[0,3,6,9]
passed('dragging_an_unselected_clip_moves_only_that_clip')

def mixed_fixture():
    tracks=Tracks(fixture()); tracks.unlink()
    tracks.video.select(1); tracks.video.select(2,True)
    tracks.activate('audio',True); tracks.select(0,True); tracks.select(1,True)
    return tracks

tracks=mixed_fixture()
before=tracks.snapshot(); history=len(tracks.undo_stack)
originals={lane:{c.uid:c for c in getattr(tracks,lane).clips} for lane in ('video','audio')}
assert tracks.move_selection(1,Fraction(10,3))
for lane in ('video','audio'):
    model=getattr(tracks,lane)
    for c in model.clips:
        original=originals[lane][c.uid]
        assert c==replace(original,start=original.start+(Fraction(1,3) if c.uid in model.selected_ids else 0))
assert len(tracks.undo_stack)==history+1 and not tracks.linked
after=tracks.snapshot(); tracks.undo(); assert tracks.snapshot()==before
tracks.redo(); assert tracks.snapshot()==after
passed('mixed_lane_move_preserves_exact_shared_delta_sources_fades_and_one_undo_redo')

tracks=mixed_fixture(); before=tracks.snapshot(); history=len(tracks.undo_stack)
# Video can move alone; audio would collide with its first unselected clip.
assert not tracks.move_selection(1,6) and tracks.snapshot()==before
assert len(tracks.undo_stack)==history
tracks.audio.select(3,True)
before=tracks.snapshot()
assert not tracks.moving_groups(1) and not tracks.move_selection(1,4)
assert tracks.snapshot()==before
passed('mixed_move_collision_or_sparse_group_in_either_lane_rejects_both_without_history')

tracks=mixed_fixture(); tracks.video.select(1); tracks.audio.select(1)
before=tracks.snapshot(); history=len(tracks.undo_stack)
assert tracks.move_selection(1,4)
tracks.undo(); assert tracks.snapshot()==before
tracks.video.clips.pop(2)
before=tracks.snapshot()
assert not tracks.move_selection(1,6) and tracks.snapshot()==before
assert len(tracks.undo_stack)==history
passed('single_clip_per_lane_candidates_do_not_mutate_live_models_before_validation')

tracks=mixed_fixture(); tracks.video.origin=tracks.audio.origin=Fraction(-3)
tracks.video.select(0,True)
before=tracks.snapshot()
assert tracks.move_selection(1,-100)
assert tracks.audio.clips[0].start==tracks.video.clips[0].start==-3
tracks.undo(); assert tracks.snapshot()==before
tracks=mixed_fixture(); before=tracks.snapshot()
assert tracks.selected_length==tracks.audio.length(tracks.audio.clips[0])+tracks.audio.length(tracks.audio.clips[1])+tracks.video.length(tracks.video.clips[2])
assert not tracks.can_join and not tracks.join()
assert tracks.delete_selected() and not tracks.video.selected_ids and not tracks.audio.selected_ids
assert len(tracks.video.clips)==3 and len(tracks.audio.clips)==3
tracks.undo(); assert tracks.snapshot()==before
tracks.activate('video',True)
assert tracks.move_selection(4,14) and tracks.video.selected_ids=={4} and not tracks.audio.selected_ids
tracks.select(0); tracks.activate('audio',True); tracks.select(0,True)
assert tracks.mixed_selection
tracks.select(0,True); assert tracks.lane=='video' and tracks.video.selected_ids=={0}
passed('mixed_selection_origin_clamp_union_delete_undo_and_unselected_drag_remain_consistent')

from PySide6.QtCore import QObject, QSettings, QUrl, Qt, QPointF, QPoint, QCoreApplication, QEvent, QLocale
from PySide6.QtGui import QGuiApplication, QFontDatabase, QMouseEvent
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from splicelet.controller import FrameProvider, Preview, FrameKeys
QLocale.setDefault(QLocale('en_US'))
app=QGuiApplication([]); QQuickStyle.setStyle('Basic')
if not QFontDatabase.families():
    for name in ('segoeui.ttf','segoeuib.ttf','consola.ttf'):
        QFontDatabase.addApplicationFont(str(Path(os.environ.get('SystemRoot','C:/Windows'))/'Fonts'/name))
QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat,QSettings.Scope.UserScope,str(OUT/'settings'))
provider=FrameProvider(); preview=Preview(provider,muted=True)
engine=QQmlApplicationEngine(); engine.addImageProvider('frames',provider)
engine.warnings.connect(lambda errors: print('\n'.join(e.toString() for e in errors),flush=True))
engine.setInitialProperties({'preview':preview})
engine.load(QUrl.fromLocalFile(str(ROOT/'splicelet/Main.qml')))
assert engine.rootObjects()
window=engine.rootObjects()[0]
keys=FrameKeys(window,preview); app.installEventFilter(keys)
def wait(predicate):
    deadline=time.monotonic()+30
    while not predicate():
        assert time.monotonic()<deadline,preview.status
        app.processEvents(); QTest.qWait(10)
try:
    preview.open_path(str(Path(sys.argv[1]) if len(sys.argv)>1 else ensure_fixture()))
    wait(lambda:preview.indexedReady and not preview.busy)
    times=[pts*preview._video_time_base-Fraction(str(preview._origin)) for pts in preview._video_pts]
    model=Clips(len(times),times,Fraction(str(preview._source_duration)))
    model.clips=[Clip(i,Fraction(i*20),((i*300,(i+1)*300),),name=f'Shot {i+1}') for i in range(5)]
    model.extent=Fraction(100); model.next_id=5; model.select(0)
    preview._clips=model; preview._editing_changed(); wait(lambda:not preview.busy)
    timeline=window.findChild(QQuickItem,'editTimeline')
    QTest.qWait(100)
    def item(index): return next((c for c in timeline.childItems() if c.objectName()==f'clip-{index}'),None)
    def center(index):
        clip=item(index)
        return clip.mapToScene(QPointF(clip.width()/2,clip.height()/2)).toPoint()
    def click(index,modifier=Qt.KeyboardModifier.NoModifier):
        QTest.mouseClick(window,Qt.MouseButton.LeftButton,modifier,center(index)); QTest.qWait(30)
    position=preview.position
    click(2); click(4,Qt.KeyboardModifier.ShiftModifier)
    assert model.selected_indices=={2,3,4} and preview.position==position
    click(1,Qt.KeyboardModifier.ShiftModifier); assert model.selected_indices=={1,2}
    click(3,Qt.KeyboardModifier.ShiftModifier); assert model.selected_indices=={2,3}
    click(0,Qt.KeyboardModifier.ControlModifier); assert model.selected_indices=={0,2,3}
    window.grabWindow().save(str(OUT/'shift-selection.png'))
    passed('qml_shift_click_selects_forward_backward_ranges_and_ctrl_keeps_toggling')
    def begin_drag(index,seconds):
        start=center(index); target=QPoint(start.x()+round(seconds/timeline.property('secondsPerPixel')),start.y())
        QTest.mousePress(window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.AltModifier,start)
        event=QMouseEvent(QEvent.Type.MouseMove,QPointF(target),QPointF(target),QPointF(window.mapToGlobal(target)),
                          Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.AltModifier)
        QCoreApplication.sendEvent(window,event); QTest.qWait(50)
        return target
    def end_drag(target):
        QTest.mouseRelease(window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.AltModifier,target)
        wait(lambda:not preview.busy); QTest.qWait(30)
    click(1); click(2,Qt.KeyboardModifier.ShiftModifier)
    before=model.snapshot(); original={c.uid:c for c in model.clips}
    target=begin_drag(2,5)
    assert timeline.property('dragIndex')==2
    assert {'drag-preview-1','drag-preview-2'}.issubset({c.objectName() for c in timeline.childItems()})
    assert abs(item(1).opacity()-.4)<1e-6 and abs(item(2).opacity()-.4)<1e-6 and item(0).opacity()==1
    window.grabWindow().save(str(OUT/'group-drag-preview.png'))
    end_drag(target)
    delta=model.clips[1].start-original[1].start
    assert abs(float(delta)-5)<.05 and delta==model.clips[2].start-original[2].start
    assert model.clips[0]==original[0] and model.clips[3]==original[3] and model.clips[4]==original[4]
    assert model.selected_ids=={1,2} and len(model.undo_stack)==1
    after=model.snapshot(); preview.undoCut(); wait(lambda:not preview.busy); assert model.snapshot()==before
    preview.redoCut(); wait(lambda:not preview.busy); assert model.snapshot()==after
    window.grabWindow().save(str(OUT/'group-moved.png'))
    preview.undoCut(); wait(lambda:not preview.busy)
    passed('qml_group_drag_from_any_member_shows_all_ghosts_preserves_gaps_and_is_one_undo')
    click(1); click(3,Qt.KeyboardModifier.ControlModifier)
    before=model.snapshot(); history=len(model.undo_stack)
    target=begin_drag(1,5)
    assert timeline.property('dragIndex')==-1
    end_drag(target)
    assert model.snapshot()==before and len(model.undo_stack)==history
    passed('qml_sparse_selection_drag_is_a_noop_without_collapsing_selection')
    click(1); click(2,Qt.KeyboardModifier.ShiftModifier)
    before=model.snapshot(); history=len(model.undo_stack)
    end_drag(begin_drag(2,15))
    assert model.has_overlaps and len(model.undo_stack)==history+1
    preview.undoCut(); wait(lambda:not preview.busy); assert model.snapshot()==before
    # Snap a member edge to the playhead; selected edges must not act as anchors.
    preview._position=55
    snapped=preview.moveTarget(2,44.9,.1,False)
    assert abs(snapped-45)<.002,(snapped,preview.movingClips(2))
    unsnapped=preview.moveTarget(2,44.9,.1,True)
    assert abs(unsnapped-44.9)<.001
    passed('qml_group_edge_overlap_creates_crossfade_and_group_edges_snap_with_alt_bypass')
    # Close the internal gap, then drag the same pair as a touching block.
    assert model.move(2,30)
    preview._editing_changed(); wait(lambda:not preview.busy)
    original={c.uid:c for c in model.clips}
    end_drag(begin_drag(1,5))
    assert abs(float(model.clips[1].start-original[1].start)-5)<.05
    assert model.end(model.clips[1])==model.clips[2].start
    passed('qml_touching_group_moves_without_creating_a_gap')
    # Start on the ruler, crossing partial clip bodies without moving the playhead.
    def box(x1,y1,x2,y2,modifier=Qt.KeyboardModifier.NoModifier):
        start=timeline.mapToScene(QPointF(x1,y1)).toPoint()
        end=timeline.mapToScene(QPointF(x2,y2)).toPoint()
        QTest.mousePress(window,Qt.MouseButton.LeftButton,modifier,start)
        event=QMouseEvent(QEvent.Type.MouseMove,QPointF(end),QPointF(end),QPointF(window.mapToGlobal(end)),
                          Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton,modifier)
        QCoreApplication.sendEvent(window,event); QTest.qWait(30)
        assert window.findChild(QQuickItem,'selectionRectangle').isVisible()
        window.grabWindow().save(str(OUT/'rectangle-active.png'))
        QTest.mouseRelease(window,Qt.MouseButton.LeftButton,modifier,end); QTest.qWait(30)
    def xat(seconds): return 12+seconds/timeline.property('secondsPerPixel')
    ruler_start=timeline.mapToScene(QPointF(xat(8),25)).toPoint()
    ruler_end=timeline.mapToScene(QPointF(xat(12),25)).toPoint()
    QTest.mouseClick(window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.AltModifier,ruler_start)
    wait(lambda:not preview.busy); assert abs(preview.position-8)<.1
    QTest.mousePress(window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.AltModifier,ruler_start)
    event=QMouseEvent(QEvent.Type.MouseMove,QPointF(ruler_end),QPointF(ruler_end),QPointF(window.mapToGlobal(ruler_end)),
                      Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.AltModifier)
    QCoreApplication.sendEvent(window,event); QTest.qWait(20)
    assert not window.findChild(QQuickItem,'selectionRectangle').isVisible()
    QTest.mouseRelease(window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.AltModifier,ruler_end)
    wait(lambda:not preview.busy); assert abs(preview.position-12)<.1
    history=len(model.undo_stack); position=preview.position
    box(xat(19),25,xat(41),55)
    assert model.selected_indices=={1,2},model.selected_indices
    box(xat(81),25,xat(89),55,Qt.KeyboardModifier.ControlModifier)
    assert model.selected_indices=={1,2,4},model.selected_indices
    box(xat(89),25,xat(81),55,Qt.KeyboardModifier.ControlModifier)
    assert model.selected_indices=={1,2}
    assert len(model.undo_stack)==history and preview.position==position
    label=window.findChild(QQuickItem,'selectedLengthLabel')
    assert label.isVisible() and label.property('text')=='Selected length: '+preview.selectedLengthText
    window.grabWindow().save(str(OUT/'selected-length.png'))
    box(xat(70),25,xat(75),55)
    assert preview.selectionCount==0 and not label.isVisible()
    # The scissors invoke the same existing split and undo path as C.
    preview.seek(5); wait(lambda:not preview.busy)
    button=window.findChild(QQuickItem,'cutButton')
    count=len(model.clips)
    QTest.mouseClick(window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,button.mapToScene(QPointF(button.width()/2,button.height()/2)).toPoint())
    wait(lambda:not preview.busy)
    assert len(model.clips)==count+1
    preview.undoCut(); wait(lambda:not preview.busy); assert len(model.clips)==count
    preview.selectClip(1)
    window.setWidth(760); window.setHeight(560); QTest.qWait(150)
    window.grabWindow().save(str(OUT/'selection-minimum.png'))
    for name in ('timeInput','selectedLengthLabel','cutButton','zoomInButton','volumeSlider'):
        control=window.findChild(QQuickItem,name)
        bounds=control.mapToScene(QPointF())
        assert bounds.x()>=0 and bounds.x()+control.width()<=window.width()+1,(name,bounds,control.width())
    assert label.width()>=label.implicitWidth(),(label.width(),label.implicitWidth())
    window.setWidth(1120); window.setHeight(790); QTest.qWait(50)
    preview._clips=Tracks(model); preview._editing_changed(); wait(lambda:not preview.busy)
    box(xat(19),25,xat(41),55)
    assert preview.selectionCount==2 and preview._clips.video.selected_ids==model.selected_ids
    assert preview.selectedLengthText==preview.format_time(float(model.selected_length))
    has_audio=preview._has_audio
    preview._has_audio=False
    assert abs(preview.moveTarget(3,60.2,.1,False)-60.2)<1e-6
    preview._has_audio=has_audio
    preview.unlinkAudio(); wait(lambda:not preview.busy)
    preview.selectClip(1000004)
    video_before=preview._clips.video.clips.copy(); audio_before=preview._clips.audio.clips.copy()
    box(xat(19),25,xat(41),120)
    assert preview.selectionLane=='audio' and preview._clips.audio.selected_indices=={1,2}
    assert preview._clips.video.selected_indices=={1,2}
    assert preview.selectionCount==4
    assert preview._clips.video.clips==video_before and preview._clips.audio.clips==audio_before
    preview.setDarkTheme(True); QTest.qWait(50)
    window.grabWindow().save(str(OUT/'selection-dark.png'))
    preview.setDarkTheme(False)
    passed('qml_rectangle_partial_hits_ctrl_toggle_reverse_clear_length_and_scissors')

    tracks=preview._clips
    click(1); click(1000002,Qt.KeyboardModifier.ControlModifier)
    assert tracks.video.selected_indices=={1} and tracks.audio.selected_indices=={2}
    assert preview.selectionCount==2 and not preview.canJoin
    assert {c['index'] for c in preview.clips if c['selected']}=={1,1000002}
    spec=preview.export_spec()
    assert spec.start==float(tracks.video.project_start(tracks.video.clips[1]))
    assert spec.end==float(tracks.audio.project_end(tracks.audio.clips[2]))
    assert preview.selectedLengthText==preview.format_time(20)
    start=float(tracks.video.project_start(tracks.video.clips[1]))
    assert abs(preview.moveTarget(1,start+.2,.1,False)-start)<1e-6
    # Clicking either selected lane for a drag must preserve the whole group.
    for anchor in (1,1000002):
        preview.movingClips(anchor)
        before=tracks.snapshot(); history=len(tracks.undo_stack)
        original={(lane,c.uid):c for lane,m in preview._lanes() for c in m.clips}
        target=begin_drag(anchor,5)
        assert timeline.property('dragIndex')==anchor
        assert {'drag-preview-1','drag-preview-1000002'}.issubset({c.objectName() for c in timeline.childItems()})
        assert item(1).opacity()==item(1000002).opacity()==.4
        window.grabWindow().save(str(OUT/f'mixed-drag-{anchor}.png'))
        end_drag(target)
        delta=tracks.video.clips[1].start-original['video',1].start
        assert abs(float(delta)-5)<.05
        assert tracks.audio.clips[2].start-original['audio',2].start==delta
        for lane,m in preview._lanes():
            for c in m.clips:
                assert c==replace(original[lane,c.uid],start=original[lane,c.uid].start+(delta if c.uid in m.selected_ids else 0))
        assert len(tracks.undo_stack)==history+1 and not tracks.linked
        after=tracks.snapshot(); preview.undoCut(); wait(lambda:not preview.busy)
        assert tracks.snapshot()==before,(anchor,before,tracks.snapshot())
        preview.redoCut(); wait(lambda:not preview.busy); assert tracks.snapshot()==after
        preview.undoCut(); wait(lambda:not preview.busy)
    click(1000002,Qt.KeyboardModifier.ControlModifier)
    assert preview.selectionCount==1 and preview.selectionLane=='video' and preview.selectedClipName=='Shot 2'
    click(1000002); assert not tracks.video.selected_ids and tracks.audio.selected_indices=={2}
    box(xat(19),25,xat(41),120)
    assert tracks.video.selected_indices==tracks.audio.selected_indices=={1,2}
    raw=float(tracks.video.project_start(tracks.video.clips[1]))+.2
    assert preview.moveTarget(1,raw,.1,False)==preview.moveTarget(1,raw,.1,True)
    click(1000003,Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
    assert tracks.video.selected_indices=={1,2} and tracks.audio.selected_indices=={1,2,3}
    click(1000002,Qt.KeyboardModifier.ShiftModifier)
    assert not tracks.video.selected_ids and tracks.audio.selected_indices=={1,2}
    box(xat(19),25,xat(41),120)
    box(xat(19),25,xat(29),120,Qt.KeyboardModifier.ControlModifier)
    assert tracks.video.selected_indices==tracks.audio.selected_indices=={2}
    box(xat(29),25,xat(19),120,Qt.KeyboardModifier.ControlModifier)
    assert tracks.video.selected_indices==tracks.audio.selected_indices=={1,2}
    assert preview.selectedLengthText==preview.format_time(20)
    before=tracks.snapshot(); history=len(tracks.undo_stack)
    preview.duplicateSelected(); preview.joinSelected()
    assert tracks.snapshot()==before and len(tracks.undo_stack)==history
    QTest.keyClick(window,Qt.Key.Key_Delete); wait(lambda:not preview.busy)
    assert len(tracks.video.clips)==len(tracks.audio.clips)==3
    assert len(tracks.undo_stack)==history+1
    preview.undoCut(); wait(lambda:not preview.busy); assert tracks.snapshot()==before
    window.grabWindow().save(str(OUT/'mixed-selection.png'))
    passed('qml_mixed_ctrl_rectangle_drag_each_lane_export_bounds_delete_and_atomic_history')
finally:
    preview.close(); engine.deleteLater(); QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
(OUT/'report.json').write_text(json.dumps({'status':'pass','checks':checks},indent=2),encoding='utf-8')
