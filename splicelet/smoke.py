"""Exercise the real Qt application, including QML rendering and audio clock."""
import hashlib
from bisect import bisect_right
import json
from pathlib import Path
import time
import traceback

import av
from PySide6.QtCore import QObject, QTimer, Qt, QPoint, QEvent, QCoreApplication, QPointF, QUrl
from PySide6.QtGui import QKeyEvent, QWheelEvent, QMouseEvent
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest
from .runtime import ARTIFACTS


class SmokeTest(QObject):
    def __init__(self, app, window, preview):
        super().__init__()
        self.app, self.window, self.preview = app, window, preview
        self.stage = 0
        self.started = time.perf_counter()
        self.stage_time = self.started
        self.report = {'checks':[], 'limitations':['Audio is muted during this test. Clock progression is measured; perceived lip-sync and physical device latency are not established.']}
        self.out = ARTIFACTS/'smoke-tests'
        self.out.mkdir(parents=True,exist_ok=True)
        self.timer = QTimer(self)
        self.timer.setInterval(25)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        self.extra = None
        self.wait_for = None

    def passed(self, name, **data):
        self.report['checks'].append({'name':name,'status':'pass',**data})
        print('PASS',name,data,flush=True)
        self.stage += 1
        self.stage_time = time.perf_counter()

    def finish(self, error=None):
        self.timer.stop()
        if error:
            self.report['checks'].append({'name':f'stage_{self.stage}','status':'fail','error':error})
        self.report['diagnostics'] = self.preview.diagnostics()
        self.report['status'] = 'fail' if error else 'pass'
        self.report['elapsed_seconds'] = time.perf_counter()-self.started
        (self.out/'smoke-report.json').write_text(json.dumps(self.report,indent=2),encoding='utf-8')
        print(json.dumps(self.report,indent=2),flush=True)
        self.app.exit(1 if error else 0)

    def tick(self):
        try:
            self.advance()
        except Exception:
            self.finish(traceback.format_exc())

    def advance(self):
        p = self.preview
        elapsed = time.perf_counter()-self.stage_time
        if time.perf_counter()-self.started>75:
            raise TimeoutError(f'Test timeout at stage {self.stage}; {p.status}; {p.diagnostics()}')
        if p.status.startswith('Error:'):
            raise AssertionError(p.status)
        if self.stage==0:
            if not p.indexedReady or p.busy or p._displayed_generation != p._generation:
                return
            assert p.provider.image.width()>16
            self.passed('open_and_index',frames=len(p._index))
            return
        if self.stage==1:
            capture = self.window.grabWindow()
            assert not capture.isNull()
            # Restrict to the video area, excluding UI text and controls.
            pixels={capture.pixelColor(x,y).rgba() for x in range(capture.width()//4,capture.width()*3//4,12)
                    for y in range(capture.height()//4,capture.height()//2,12)}
            assert len(pixels)>8, f'QML video area appears blank: {len(pixels)} colors'
            capture.save(str(self.out/'splicelet.png'))
            self.passed('qml_video_rendered',sampled_colors=len(pixels))
            p.seek(p.duration*.2)
            p.seek(p.duration*.8)
            p.seek(p.duration*.4)
            self.target = p.position
            self.generation = p._generation
            return
        if self.stage==2:
            if p.busy or p._displayed_generation != self.generation: return
            assert abs(p.position-self.target)<.000001
            with av.open(p._path) as c:
                stream=c.streams.video[0]
                c.seek(round((self.target+p._origin)/float(stream.time_base)),stream=stream,backward=True)
                for frame in c.decode(stream):
                    if float(frame.pts*frame.time_base)-p._origin>=self.target-.000001:
                        expected=frame.to_ndarray(format='rgb24')
                        actual=p.provider.image
                        # Compare active pixels, ignoring QImage row padding.
                        pixels=bytes(actual.constBits())
                        expected_rows=b''.join(pixels[y*actual.bytesPerLine():y*actual.bytesPerLine()+actual.width()*3] for y in range(actual.height()))
                        assert hashlib.sha256(expected_rows).digest()==hashlib.sha256(expected.tobytes()).digest()
                        break
                else: raise AssertionError('Reference frame not found')
            self.passed('latest_seek_wins_and_pixels_match',position=p.position)
            self.original=p.position
            self.frame_index=p._index.index(p.position)
            p.step(1)
            return
        if self.stage==3:
            if p.busy: return
            assert p.position==p._index[self.frame_index+1]
            self.passed('step_forward_exact',position=p.position)
            p.step(-1)
            return
        if self.stage==4:
            if p.busy: return
            assert p.position==self.original
            self.passed('step_backward_exact',position=p.position)
            p.toggle()
            return
        if self.stage==5:
            if not p._audio_started: return
            self.play_start=time.perf_counter()
            self.clock_start=p._clock()
            self.display_start=p.position
            self.passed('playback_started',audio_device=p._device.description(),using_audio_clock=p.audioEnabled)
            return
        if self.stage==6:
            if time.perf_counter()-self.play_start<2.2: return
            wall=time.perf_counter()-self.play_start
            clock=p._clock()-self.clock_start
            assert p.position-self.display_start>1.5, p.diagnostics()
            assert abs(wall-clock)<.35,(wall,clock)
            assert abs(p._clock()-p.position)<.25,p.diagnostics()
            assert p._cache_bytes<=p._cache_limit
            assert p.video.status()[0]<=6
            assert p.audio.status()[1]<=round(.6*48000*p.audio.sample_bytes)
            self.passed('clock_and_video_progress_and_bounded_buffers',wall_seconds=wall,clock_seconds=clock,
                        clock_to_frame_gap_ms=(p._clock()-p.position)*1000)
            p.pause()
            self.pause_position=p.position
            return
        if self.stage==7:
            if elapsed<.35 or p.busy: return
            assert not p.playing and p.position==self.pause_position
            self.passed('pause_holds_position',position=p.position)
            p.seek(p.duration-.5)
            p.toggle()
            return
        if self.stage==8:
            if p.playing: return
            assert p.position>=p._index[-2],p.diagnostics()
            self.passed('end_of_file_stops',position=p.position)
            return
        if self.extra is None:
            self.extra = self.transport_checks()
        if self.wait_for is not None and not self.wait_for(): return
        try:
            self.wait_for = next(self.extra)
        except StopIteration:
            self.finish()

    def transport_checks(self):
        p = self.preview
        self.window.requestActivate()
        self.window.contentItem().forceActiveFocus()
        p.seek(p.duration*.3)
        yield lambda:not p.busy

        for key,delta in ((Qt.Key.Key_Right,5),(Qt.Key.Key_Left,-5)):
            target=p._index[max(0,bisect_right(p._index,p.position+delta+.000001)-1)]
            QTest.keyClick(self.window,key)
            yield lambda:not p.busy
            assert not p.playing and p.position==target,(p.position,target,p.playing)
            self.passed('arrow_jump_preserves_pause',delta_seconds=delta,position=p.position)

        p.toggle()
        yield lambda:p._audio_started
        for key,delta in ((Qt.Key.Key_Right,5),(Qt.Key.Key_Left,-5)):
            target=p._index[max(0,bisect_right(p._index,p.position+delta+.000001)-1)]
            QTest.keyClick(self.window,key)
            assert p.playing
            yield lambda:p._audio_started and not p.busy
            assert p.playing and p._base==target,(p._base,target,p.playing)
            self.passed('arrow_jump_preserves_play',delta_seconds=delta,position=p.position)

        for key,modifier,direction in ((Qt.Key.Key_Less,Qt.KeyboardModifier.NoModifier,-1),
                                       (Qt.Key.Key_Greater,Qt.KeyboardModifier.ShiftModifier,1)):
            index=max(0,bisect_right(p._index,p.position+.000001)-1)
            target=p._index[index+direction]
            QTest.keyClick(self.window,key,modifier)
            yield lambda:not p.busy
            assert not p.playing and p.position==target,(key,p.position,target,p.playing)
            self.passed('angle_key_steps_exact_frame_and_pauses',direction=direction,position=p.position)

        # Same physical Italian key + Shift can retain Key_Less while typing >.
        for key,symbol,direction in ((Qt.Key.Key_Less,'>',1),(Qt.Key.Key_Comma,'<',-1),
                                     (Qt.Key.Key_Period,'>',1)):
            index=max(0,bisect_right(p._index,p.position+.000001)-1)
            target=p._index[index+direction]
            QCoreApplication.sendEvent(self.window,QKeyEvent(QEvent.Type.KeyPress,key,Qt.KeyboardModifier.ShiftModifier,symbol))
            yield lambda:not p.busy
            assert p.position==target and not p.playing
            self.passed('typed_angle_symbol_respects_keyboard_layout',symbol=symbol,key=int(key))

        QTest.keyClick(self.window,Qt.Key.Key_F11)
        yield lambda:self.window.property('fullScreen')
        video=self.window.findChild(QQuickItem,'previewImage')
        assert video.width()>=self.window.width()-4 and video.height()>=self.window.height()-4
        self.passed('f11_enters_video_fullscreen')
        QTest.keyClick(self.window,Qt.Key.Key_Escape)
        yield lambda:not self.window.property('fullScreen')
        self.passed('escape_exits_fullscreen')

        timeline=self.window.findChild(QQuickItem,'editTimeline')
        QTest.keyClick(self.window,Qt.Key.Key_F)
        yield lambda:timeline.property('followEnabled')
        assert not self.window.property('fullScreen')
        QTest.keyClick(self.window,Qt.Key.Key_F)
        yield lambda:not timeline.property('followEnabled')
        self.passed('f_toggles_timeline_follow')

        QTest.mouseDClick(self.window,Qt.MouseButton.LeftButton,pos=QPoint(self.window.width()//2,self.window.height()//3))
        yield lambda:self.window.property('fullScreen')
        self.window.grabWindow().save(str(self.out/'splicelet-fullscreen.png'))
        QTest.keyClick(self.window,Qt.Key.Key_Escape)
        yield lambda:not self.window.property('fullScreen')
        self.passed('video_double_click_enters_fullscreen')
        self.window.grabWindow().save(str(self.out/'splicelet-light.png'))
        yield from self.edit_checks()

    def edit_checks(self):
        p = self.preview
        for frame in (37,97):
            p.seek(p._index[frame])
            yield lambda:not p.busy
            QTest.keyClick(self.window,Qt.Key.Key_C)
            yield lambda:True
        assert p._clips.boundaries==[0,37,97,len(p._index)]
        self.passed('c_splits_at_exact_displayed_frame')
        QTest.keyClick(self.window,Qt.Key.Key_Z,Qt.KeyboardModifier.ControlModifier)
        yield lambda:True
        assert p._clips.boundaries==[0,37,len(p._index)]
        QTest.keyClick(self.window,Qt.Key.Key_Z,Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.ShiftModifier)
        yield lambda:True
        assert p._clips.boundaries==[0,37,97,len(p._index)]
        self.passed('cut_keyboard_undo_redo')

        timeline=self.window.findChild(QQuickItem,'editTimeline')
        clip=next((item for item in timeline.childItems() if item.objectName()=='clip-1'),None)
        assert clip is not None
        position=p.position
        point=clip.mapToScene(QPointF(clip.width()/2,clip.height()/2)).toPoint()
        QTest.mouseClick(self.window,Qt.MouseButton.LeftButton,pos=point)
        yield lambda:True
        assert p.selectedClip==1 and p.position==position
        self.passed('click_selects_clip_without_moving_playhead')

        p.exportClip(QUrl.fromLocalFile(p._path))
        assert not p.exporting and 'original file' in p.exportStatus
        self.passed('ui_rejects_original_as_export_destination')
        target=self.out/f'selected-clip-{time.time_ns()}.mp4'
        p.exportClip(QUrl.fromLocalFile(str(target)))
        assert p.exporting
        yield lambda:not p.exporting
        assert p.exportStatus.startswith('Exported:'),p.exportStatus
        with av.open(str(target)) as c:
            frames=sum(1 for _ in c.decode(video=0))
        assert frames==60,frames
        self.passed('selected_clip_exports_asynchronously',frames=frames,path=str(target))

        # Show representative, wider clips for visual review.
        p.undoCut();p.undoCut()
        for fraction in (.3,.7):
            p.seek(p.duration*fraction)
            yield lambda:not p.busy
            QTest.keyClick(self.window,Qt.Key.Key_C)
            yield lambda:True
        p.selectClip(1)
        yield lambda:True
        self.window.grabWindow().save(str(self.out/'splicelet-clips.png'))
        yield from self.property_checks()

    def property_checks(self):
        p=self.preview
        panel=self.window.findChild(QQuickItem,'clipProperties')
        timeline=self.window.findChild(QQuickItem,'editTimeline')
        def click_clip(index,ctrl=False):
            item=next(item for item in timeline.childItems() if item.objectName()==f'clip-{index}')
            point=item.mapToScene(QPointF(item.width()/2,item.height()/2)).toPoint()
            QTest.mouseClick(self.window,Qt.MouseButton.LeftButton,
                             Qt.KeyboardModifier.ControlModifier if ctrl else Qt.KeyboardModifier.NoModifier,point)
        assert p.selectionCount==1 and panel.isVisible()
        click_clip(0,True)
        yield lambda:True
        assert p.selectionCount==2 and not panel.isVisible()
        click_clip(1,True)
        yield lambda:True
        assert p.selectionCount==1 and panel.isVisible()
        click_clip(0,True)
        yield lambda:True
        assert p.selectionCount==0 and not panel.isVisible()
        assert self.window.findChild(QObject,'exportAction').property('enabled')
        self.passed('ctrl_click_allows_zero_one_and_multiple_selection')

        click_clip(1)
        yield lambda:True
        click_clip(0,True)
        yield lambda:True
        original_boundaries=p._clips.boundaries.copy()
        QTest.keyClick(self.window,Qt.Key.Key_J)
        yield lambda:True
        assert p._clips.boundaries==[original_boundaries[0],*original_boundaries[2:]]
        assert p.selectionCount==1 and panel.isVisible()
        QTest.keyClick(self.window,Qt.Key.Key_Z,Qt.KeyboardModifier.ControlModifier)
        yield lambda:True
        assert p._clips.boundaries==original_boundaries and p.selectionCount==2
        self.passed('j_joins_adjacent_clips_and_undo_restores_multi_selection')
        click_clip(1)
        yield lambda:True

        def type_value(name,text):
            field=self.window.findChild(QQuickItem,name)
            assert field is not None,name
            field.forceActiveFocus()
            QTest.keyClick(self.window,Qt.Key.Key_A,Qt.KeyboardModifier.ControlModifier)
            for character in text:
                QTest.keyClick(self.window,Qt.Key(ord(character.upper())))
            QTest.keyClick(self.window,Qt.Key.Key_Return)
        type_value('audioFadeIn','6.25')
        yield lambda:True
        assert p.fadeValues['audio_in']==6.25,p.fadeValues
        assert self.window.findChild(QQuickItem,'audioFadeIn').property('text')=='6.25'
        from PySide6.QtCore import QLocale
        assert QLocale().language()==QLocale.Language.English
        assert QLocale().decimalPoint()=='.'
        assert self.window.findChild(QQuickItem,'audioFadeInSlider').property('value')==4
        type_value('videoFadeIn','0.005')
        yield lambda:True
        assert p.fadeValues['video_in']==.005,p.fadeValues
        type_value('videoFadeIn','2')
        yield lambda:True
        assert p.fadeValues['video_in']==2
        self.passed('property_fields_accept_values_outside_slider_range')

        slider=self.window.findChild(QQuickItem,'audioFadeOutSlider')
        point=slider.mapToScene(QPointF(slider.width()/2,slider.height()/2)).toPoint()
        QTest.mouseClick(self.window,Qt.MouseButton.LeftButton,pos=point)
        yield lambda:True
        assert 1.8<p.fadeValues['audio_out']<2.2,p.fadeValues
        type_value('audioFadeOut','0')
        yield lambda:True
        assert p.fadeValues['audio_out']==0
        self.passed('fade_slider_commits_value_and_zero_disables')

        a,b=p._clips.selected_frames
        start=p._boundary_time(a)
        p.seek(start)
        yield lambda:not p.busy
        assert p.videoGain==0
        # Wait a tick for the QML opacity binding to be rendered.
        yield lambda:True
        image_item=self.window.findChild(QQuickItem,'previewImage')
        point=image_item.mapToScene(QPointF(image_item.width()/2,image_item.height()/2)).toPoint()
        color=self.window.grabWindow().pixelColor(point)
        assert max(color.red(),color.green(),color.blue())<3,(color.red(),color.green(),color.blue())
        p.seek(start+1)
        yield lambda:not p.busy
        assert .48<p.videoGain<.52,p.videoGain
        self.passed('preview_video_fade_renders_black_then_half_gain')

        x=float(timeline.property('inset'))+start/p.duration*float(timeline.property('span'))+5
        point=timeline.mapToScene(QPointF(x,12)).toPoint()
        QTest.mouseClick(self.window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,point)
        yield lambda:not p.busy
        assert p.position==start,(p.position,start)
        QTest.mouseClick(self.window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.AltModifier,point)
        yield lambda:not p.busy
        assert p.position>start+.3,(p.position,start)
        self.passed('playhead_snaps_to_cut_and_alt_bypasses_snap')
        self.window.grabWindow().save(str(self.out/'splicelet-properties.png'))
        yield from self.timeline_checks()

    def timeline_checks(self):
        p=self.preview
        timeline=self.window.findChild(QQuickItem,'editTimeline')
        p.selectClip(0)
        QTest.keyClick(self.window,Qt.Key.Key_Z)
        yield lambda:True
        assert timeline.property('visibleDuration')<p.duration
        p.selectClip(1,True)
        QTest.keyClick(self.window,Qt.Key.Key_Z)
        yield lambda:True
        bounds=p.selectionRange
        assert timeline.property('viewStart')<=bounds['start']+.000001
        assert timeline.property('viewStart')+timeline.property('visibleDuration')>=bounds['end']-.000001
        p.selectClip(0)
        QTest.keyClick(self.window,Qt.Key.Key_Z)
        yield lambda:True
        before=timeline.property('visibleDuration')
        point=timeline.mapToScene(QPointF(timeline.width()/2,20))
        def wheel(delta,modifier):
            event=QWheelEvent(point,QPointF(self.window.mapToGlobal(point.toPoint())),QPoint(),QPoint(0,delta),
                              Qt.MouseButton.NoButton,modifier,Qt.ScrollPhase.NoScrollPhase,False)
            QCoreApplication.sendEvent(self.window,event)
        wheel(120,Qt.KeyboardModifier.ControlModifier)
        yield lambda:True
        assert timeline.property('visibleDuration')<before
        assert self.window.findChild(QQuickItem,'timelineScrollBar').isVisible()
        before=timeline.property('viewStart')
        wheel(-120,Qt.KeyboardModifier.ShiftModifier)
        yield lambda:True
        assert timeline.property('viewStart')>before
        scroll=self.window.findChild(QQuickItem,'timelineScrollBar')
        before=timeline.property('viewStart')
        handle_x=(scroll.property('position')+scroll.property('size')/2)*scroll.width()
        handle=scroll.mapToScene(QPointF(handle_x,scroll.height()/2)).toPoint()
        moved=QPoint(handle.x()+80,handle.y())
        QTest.mousePress(self.window,Qt.MouseButton.LeftButton,pos=handle)
        QTest.mouseMove(self.window,moved,delay=30)
        QTest.mouseRelease(self.window,Qt.MouseButton.LeftButton,pos=moved)
        yield lambda:True
        assert timeline.property('viewStart')>before
        wheel(1440,Qt.KeyboardModifier.ControlModifier)
        yield lambda:True
        assert timeline.property('tickStep')<1
        self.window.grabWindow().save(str(self.out/'splicelet-timeline-zoom.png'))
        self.passed('ctrl_wheel_zoom_shift_wheel_pan_and_adaptive_ruler')
        p.selectClip(0,True)
        QTest.keyClick(self.window,Qt.Key.Key_Z)
        yield lambda:True
        assert timeline.property('viewStart')==0 and timeline.property('visibleDuration')==p.duration
        self.passed('z_fits_selection_or_entire_project_when_empty')

        p.selectClip(1)
        for key in ('audio_in','audio_out','video_in','video_out'):p.setFade(key,'0')
        before=[(float(c.start),float(p._clips.end(c))) for c in p._clips.clips]
        QTest.keyClick(self.window,Qt.Key.Key_Delete)
        yield lambda:not p.busy
        assert len(p._clips.clips)==2 and p.selectionCount==0
        after=[(float(c.start),float(p._clips.end(c))) for c in p._clips.clips]
        assert after==[before[0],before[2]]
        assert not any(bytes(p.provider.image.constBits()))
        self.passed('delete_preserves_gap_and_preview_is_black')
        self.window.grabWindow().save(str(self.out/'splicelet-gap.png'))

        item=next(item for item in timeline.childItems() if item.objectName()=='clip-1')
        start=item.mapToScene(QPointF(item.width()/2,item.height()/2)).toPoint()
        free_target=QPoint(start.x()+round((before[0][1]+2-before[2][0])/timeline.property('secondsPerPixel')),start.y())
        QTest.mousePress(self.window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.AltModifier,start)
        event=QMouseEvent(QEvent.Type.MouseMove,QPointF(free_target),QPointF(self.window.mapToGlobal(free_target)),
                          Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.AltModifier)
        QCoreApplication.sendEvent(self.window,event)
        QTest.mouseRelease(self.window,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.AltModifier,free_target)
        yield lambda:not p.busy
        assert abs(float(p._clips.clips[1].start)-(before[0][1]+2))<.2
        self.passed('alt_disables_clip_drag_snapping')
        item=next(item for item in timeline.childItems() if item.objectName()=='clip-1')
        current_start=float(p._clips.clips[1].start)
        start=item.mapToScene(QPointF(item.width()/2,item.height()/2)).toPoint()
        target=QPoint(start.x()+round((before[0][1]-current_start)/timeline.property('secondsPerPixel')),start.y())
        QTest.mousePress(self.window,Qt.MouseButton.LeftButton,pos=start)
        QTest.mouseMove(self.window,target,delay=30)
        QTest.mouseRelease(self.window,Qt.MouseButton.LeftButton,pos=target)
        yield lambda:not p.busy
        assert abs(float(p._clips.clips[1].start)-before[0][1])<.000001,[(float(c.start),float(p._clips.end(c))) for c in p._clips.clips]
        p.selectClip(0);p.selectClip(1,True)
        QTest.keyClick(self.window,Qt.Key.Key_J)
        yield lambda:not p.busy
        assert len(p._clips.clips)==1 and len(p._clips.clips[0].pieces)==2
        self.passed('drag_snaps_into_gap_then_j_joins_discontinuous_source_ranges')
        self.window.grabWindow().save(str(self.out/'splicelet-joined.png'))
        yield from self.trim_duplicate_checks()

    def trim_duplicate_checks(self):
        p=self.preview
        source=p._path
        p.open_path(source)
        yield lambda:p.indexedReady and not p.busy
        p.seek(180)
        yield lambda:not p.busy
        QTest.keyClick(self.window,Qt.Key.Key_C)
        QTest.keyClick(self.window,Qt.Key.Key_Delete)
        yield lambda:not p.busy
        assert len(p._clips.clips)==1
        assert abs(p._clip_end(p._clips.clips[0])-180)<.001
        timeline=self.window.findChild(QQuickItem,'editTimeline')
        def resize(side,target):
            layer=timeline.findChild(QQuickItem,'timelineTrimEdges')
            item=next(item for item in layer.childItems() if item.objectName()=='clip-edges-0')
            edge=next(item for item in item.childItems() if item.objectName()==f'trim-{side}-0')
            press=edge.mapToScene(QPointF(edge.width()/2,edge.height()/2)).toPoint()
            QTest.mouseMove(self.window,press)
            QCoreApplication.processEvents()
            assert self.window.cursor().shape()==Qt.CursorShape.SizeHorCursor,self.window.cursor().shape()
            clip=p._clips.clips[0]
            original=p._clip_start(clip) if side=='left' else p._clip_end(clip)
            release=QPoint(press.x()+round((target-original)/timeline.property('secondsPerPixel')),press.y())
            QTest.mousePress(self.window,Qt.MouseButton.LeftButton,pos=press)
            QTest.mouseMove(self.window,release,delay=20)
            QTest.mouseRelease(self.window,Qt.MouseButton.LeftButton,pos=release)
        p.seek(240)
        yield lambda:not p.busy
        resize('right',240)
        yield lambda:not p.busy
        assert abs(p._clip_end(p._clips.clips[0])-240)<.001,p.clips
        self.passed('right_handle_restores_deleted_source_tail_to_four_minutes')
        p.seek(30)
        yield lambda:not p.busy
        resize('left',30)
        yield lambda:not p.busy
        assert abs(p._clip_start(p._clips.clips[0])-30)<.001
        assert abs(p._clip_end(p._clips.clips[0])-240)<.001
        p.seek(0)
        yield lambda:not p.busy
        resize('left',0)
        yield lambda:not p.busy
        assert p._clips.clips[0].pieces[0][0]==0
        self.passed('left_handle_trims_and_reveals_head_without_moving_opposite_edge')

        point=timeline.mapToScene(QPointF(timeline.width()/2,20))
        wheel=QWheelEvent(point,QPointF(self.window.mapToGlobal(point.toPoint())),QPoint(),QPoint(0,-240),
                          Qt.MouseButton.NoButton,Qt.KeyboardModifier.ControlModifier,Qt.ScrollPhase.NoScrollPhase,False)
        QCoreApplication.sendEvent(self.window,wheel)
        yield lambda:True
        resize('right',p._source_duration)
        yield lambda:not p.busy
        assert p._clips.clips[0].pieces[-1][1]==len(p._video_pts)
        p.selectClip(0)
        original_duration=p.duration
        QTest.keyClick(self.window,Qt.Key.Key_D)
        yield lambda:not p.busy
        assert len(p._clips.clips)==2 and abs(p.duration-2*original_duration)<.001
        self.passed('d_duplicates_last_clip_and_extends_project')
        old_starts={clip.uid:clip.start for clip in p._clips.clips}
        p.selectClip(0)
        QTest.keyClick(self.window,Qt.Key.Key_D)
        yield lambda:not p.busy
        assert len(p._clips.clips)==3 and abs(p.duration-3*original_duration)<.001
        assert p._clips.origin<0
        assert all(c.start==old_starts[c.uid] for c in p._clips.clips if c.uid in old_starts)
        self.passed('d_duplicates_first_before_start_preserving_existing_positions')
        self.window.grabWindow().save(str(self.out/'splicelet-trim-duplicates.png'))
        p.selectClip(1)
        before=p._clips.snapshot()
        QTest.keyClick(self.window,Qt.Key.Key_D)
        yield lambda:True
        assert p._clips.snapshot()==before
        self.passed('d_refuses_internal_clip_when_both_adjacent_gaps_are_too_small')
        yield from self.gap_checks()

    def gap_checks(self):
        p=self.preview
        p.open_path(p._path)
        yield lambda:p.indexedReady and not p.busy
        p.seek(60)
        yield lambda:not p.busy
        p.cut()
        yield lambda:not p.busy
        p.seek(120)
        yield lambda:not p.busy
        p.cut()
        yield lambda:not p.busy
        p.selectClip(1); p.deleteSelected()
        yield lambda:not p.busy
        timeline=self.window.findChild(QQuickItem,'editTimeline')
        timeline.setProperty('viewDuration',0); timeline.setProperty('viewStart',0)
        yield lambda:True
        ruler=self.window.findChild(QQuickItem,'timelineRuler')
        QTest.mouseMove(self.window,ruler.mapToScene(QPointF(30,12)).toPoint())
        yield lambda:True
        assert self.window.cursor().shape()==Qt.CursorShape.ArrowCursor
        clip=next(i for i in timeline.childItems() if i.objectName()=='clip-0')
        QTest.mouseMove(self.window,clip.mapToScene(QPointF(clip.width()/2,26)).toPoint())
        yield lambda:True
        assert self.window.cursor().shape()==Qt.CursorShape.OpenHandCursor,self.window.cursor().shape()
        gap=next(i for i in timeline.childItems() if i.objectName()=='gap-0')
        trash=next(i for i in gap.childItems() if i.objectName()=='remove-gap-0')
        assert not trash.isVisible()
        QTest.mouseMove(self.window,gap.mapToScene(QPointF(10,26)).toPoint())
        yield lambda:trash.isVisible()
        assert self.window.cursor().shape()==Qt.CursorShape.ArrowCursor,self.window.cursor().shape()
        center=trash.mapToScene(QPointF(trash.width()/2,15)).toPoint()
        QTest.mouseMove(self.window,center)
        yield lambda:True
        assert self.window.cursor().shape()==Qt.CursorShape.PointingHandCursor,self.window.cursor().shape()
        self.window.grabWindow().save(str(self.out/'splicelet-gap-trash.png'))
        before=p._clips.snapshot(); duration=p.duration
        QTest.mouseClick(self.window,Qt.MouseButton.LeftButton,pos=center)
        yield lambda:not p.busy
        assert abs(p.duration-(duration-60))<.001
        assert abs(p.clips[1]['start']-60)<.001
        assert not p.gaps
        p.undoCut()
        yield lambda:not p.busy
        assert p._clips.snapshot()==before
        self.passed('gap_hover_trash_closes_gap_undo_and_distinct_cursors')

        p.seek(90)
        yield lambda:not p.busy
        for key,target in ((Qt.Key.Key_Left,60),(Qt.Key.Key_Left,0),(Qt.Key.Key_Right,60),(Qt.Key.Key_Right,120)):
            QTest.keyClick(self.window,key,Qt.KeyboardModifier.ControlModifier)
            yield lambda:not p.busy
            assert abs(p.position-target)<.001 and not p.playing,(p.position,target)
        p.seek(90)
        yield lambda:not p.busy
        p.toggle()
        yield lambda:p._audio_started
        for key,target in ((Qt.Key.Key_Left,60),(Qt.Key.Key_Right,120)):
            QTest.keyClick(self.window,key,Qt.KeyboardModifier.ControlModifier)
            assert p.playing
            yield lambda:p._audio_started and not p.busy
            assert abs(p._base-target)<.001 and p.playing,(p._base,target)
        p.pause()
        yield lambda:not p.busy
        QTest.keyClick(self.window,Qt.Key.Key_Right,Qt.KeyboardModifier.ControlModifier)
        yield lambda:not p.busy
        assert p.position==p.duration and not p.playing
        QTest.keyClick(self.window,Qt.Key.Key_Left,Qt.KeyboardModifier.ControlModifier)
        yield lambda:not p.busy
        assert abs(p.position-120)<.001
        self.passed('ctrl_arrows_skip_clip_and_gap_boundaries_preserving_transport')

        p.selectClip(1); p.deleteSelected()
        yield lambda:not p.busy
        # Reproduce after zooming out: the viewport must shrink with the project.
        timeline.setProperty('viewDuration',duration)
        yield lambda:True
        gap=next(i for i in timeline.childItems() if i.objectName()=='gap-0')
        trash=next(i for i in gap.childItems() if i.objectName()=='remove-gap-0')
        QTest.mouseMove(self.window,gap.mapToScene(QPointF(gap.width()/2,26)).toPoint())
        yield lambda:trash.isVisible()
        QTest.mouseClick(self.window,Qt.MouseButton.LeftButton,pos=trash.mapToScene(QPointF(trash.width()/2,15)).toPoint())
        yield lambda:not p.busy
        assert p.duration==60 and p.workspaceDuration==60 and not p.gaps
        assert abs(timeline.property('visibleDuration')-60)<.001
        assert abs(timeline.property('totalDuration')-60)<.001
        clip=next(i for i in timeline.childItems() if i.objectName()=='clip-0')
        assert abs(clip.width()-(timeline.property('span')-2))<2
        self.window.grabWindow().save(str(self.out/'splicelet-trailing-gap-closed.png'))
        p.undoCut()
        yield lambda:not p.busy
        assert p.duration==duration
        self.passed('trailing_gap_trash_shortens_duration_and_visible_timeline')
        p._clips.selected_ids={c.uid for c in p._clips.clips}
        p.deleteSelected()
        yield lambda:not p.busy
        p.removeGap(0)
        yield lambda:not p.busy
        assert p.duration==0 and not p.playing
        p.toggle()
        assert not p.playing
        p.undoCut()
        yield lambda:not p.busy
        assert p.duration==duration and p.indexedReady
        self.passed('removing_entire_empty_timeline_is_safe_and_undoable')
