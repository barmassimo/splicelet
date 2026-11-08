from bisect import bisect_right
from dataclasses import asdict, replace
import math
import numpy as np
from collections import OrderedDict
from fractions import Fraction
from pathlib import Path
import threading
import time

from PySide6.QtCore import QObject, Property, Signal, Slot, QTimer, Qt, QUrl, QEvent, QSettings
from PySide6.QtGui import QImage
from PySide6.QtMultimedia import QAudioFormat, QAudioSink, QMediaDevices
from PySide6.QtQuick import QQuickImageProvider

from .source import Decoder, Job, inspect_and_index
from .editing import Clips
from .tracks import Tracks
from .exporting import ExportTask, ExportSpec
from .effects import Fades, video_gain
from . import project
from .visuals import build_visuals, waveform_columns, source_at
from .sources import catalog_entry, source_for


class FrameKeys(QObject):
    """Use the typed symbol: Italian and US keyboards map < and > differently."""
    def __init__(self,window,preview):
        super().__init__(window)
        self.window,self.preview = window,preview

    def eventFilter(self,receiver,event):
        if receiver is self.window and event.type()==QEvent.Type.KeyPress:
            if not self.window.property('transportKeysEnabled'):
                return False
            if event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.MetaModifier):
                return False
            symbol = event.text()
            if symbol not in ('<','>'):
                symbol = {Qt.Key.Key_Less:'<',Qt.Key.Key_Greater:'>'}.get(event.key())
            if symbol in ('<','>'):
                self.preview.step(-1 if symbol=='<' else 1)
                event.accept()
                return True
        return False


class FrameProvider(QQuickImageProvider):
    def __init__(self):
        super().__init__(QQuickImageProvider.ImageType.Image)
        self.lock = threading.Lock()
        self.image = QImage(16, 9, QImage.Format.Format_RGB888)
        self.image.fill(Qt.GlobalColor.black)

    def put(self, image):
        with self.lock:
            self.image = image

    def clear(self,width=16,height=9):
        image = QImage(width,height,QImage.Format.Format_RGB888)
        image.fill(Qt.GlobalColor.black)
        self.put(image)

    def requestImage(self, identifier, size, requested_size):
        with self.lock:
            image = self.image
        size.setWidth(image.width())
        size.setHeight(image.height())
        return image


class Preview(QObject):
    changed = Signal()
    frameChanged = Signal()
    indexed = Signal(int, str, object)
    editChanged = Signal()
    exportChanged = Signal()
    projectChanged = Signal()
    projectError = Signal(str)
    visualsChanged = Signal()
    appearanceChanged = Signal()
    sourceChanged = Signal()
    sourceIndexed = Signal(int,str,object)

    def __init__(self, provider, muted=False):
        super().__init__()
        self.provider = provider
        self._visual_revision = 0
        self._waveform = None
        self._thumbnails = ([], [])
        self._visual_status = ''
        self._project_path = ''
        self._saved_timeline = None
        self._pending_project = None
        self._sources = ()
        self._source_identities = {}
        self._source_visuals = {}
        self._saved_catalog = None
        self._import_queue = []
        self._importing = False
        self._import_cancel = threading.Event()
        self._canvas_locked = False
        self._initial_metadata = None
        self._source_identity = None
        self._settings = QSettings(QSettings.defaultFormat(),QSettings.Scope.UserScope,'Splicelet','Splicelet')
        self._dark_theme = self._settings.value('darkTheme',False,type=bool)
        self._recent = self._settings.value('recentProjects',[],type=list)[:10]
        self._path = ''
        self._name = 'No sources imported'
        self._detail = 'Import video or audio, or drop files into the window'
        self._duration = 0.
        self._position = 0.
        self._frame_position = 0.
        self._origin = 0.
        self._playing = False
        self._status = 'Ready'
        self._index = []
        self._source_index = []
        self._source_duration = 0.
        self._timeline_origin = 0.
        self._render_frames = ()
        self._fps = 30.
        self._width,self._height = 640,360
        self._video_pts = []
        self._video_time_base = Fraction(1,1000)
        self._clips = None
        self._exporting = False
        self._export_progress = 0.
        self._export_status = ''
        self.export_task = ExportTask(self)
        self.export_task.updated.connect(self._export_updated,Qt.ConnectionType.QueuedConnection)
        self.export_task.finished.connect(self._export_finished,Qt.ConnectionType.QueuedConnection)
        self._generation = 0
        self._source_generation = 0
        self._revision = 0
        self._has_audio = False
        self._audio_timeline = None
        self._opening = False
        self._busy = False
        self._scrub_resume = False
        self._audio_started = False
        self._base = 0.
        self._wall_start = 0.
        self._audio_pending = b''
        self._next_frame = None
        self._cache = OrderedDict()
        self._cache_bytes = 0
        self._cache_limit = 64 * 1024 * 1024
        self._index_cancel = threading.Event()
        self._closed = False
        self._displayed_generation = -1
        self._max_clock_frame_gap = 0.
        self._device = QMediaDevices.defaultAudioOutput()
        self._format = QAudioFormat()
        self._format.setSampleRate(48000)
        self._format.setChannelCount(2)
        self._format.setSampleFormat(QAudioFormat.SampleFormat.Float)
        if not self._device.isNull() and not self._device.isFormatSupported(self._format):
            self._format.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        self._audio_available = not self._device.isNull() and self._device.isFormatSupported(self._format)
        self.sink = QAudioSink(self._device,self._format,self) if self._audio_available else None
        self._volume = 1.
        self._muted = muted
        if self.sink:
            self.sink.setBufferSize(round(48000 * 2 * self._format.bytesPerSample() * .12))
            self.sink.setVolume(0. if muted else self._volume)
        self._io = None
        self.video = Decoder('video',realtime=True)
        self.audio = Decoder('audio', sample_format='flt' if self._format.sampleFormat()==QAudioFormat.SampleFormat.Float else 's16', bytes_per_sample=self._format.bytesPerSample())
        self.indexed.connect(self._receive_index,Qt.ConnectionType.QueuedConnection)
        self.sourceIndexed.connect(self._receive_source,Qt.ConnectionType.QueuedConnection)
        self.timer = QTimer(self)
        self.timer.setInterval(8)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self._tick)
        self.timer.start()

    @Property(bool,notify=appearanceChanged)
    def darkTheme(self): return self._dark_theme

    @Slot(bool)
    def setDarkTheme(self,enabled):
        if self._dark_theme==enabled: return
        self._dark_theme = enabled
        self._settings.setValue('darkTheme',enabled)
        self._settings.sync()
        self.appearanceChanged.emit()

    @Property(str,notify=projectChanged)
    def projectName(self): return Path(self._project_path).stem if self._project_path else 'Untitled'
    @Property(bool,notify=projectChanged)
    def projectDirty(self):
        return self._clips is not None and (project.timeline(self._clips)!=self._saved_timeline or self._catalog_state()!=self._saved_catalog)
    @Property(bool,notify=projectChanged)
    def hasProjectPath(self): return bool(self._project_path)
    @Property(bool,notify=projectChanged)
    def openingProject(self): return self._pending_project is not None
    @Property('QVariantList',notify=projectChanged)
    def recentProjects(self): return self._recent
    @Property(bool,notify=projectChanged)
    def canSaveProject(self): return self._clips is not None and self._pending_project is None and not self._importing

    def _catalog_state(self): return ([s.path for s in self._sources],self._width,self._height)

    @Property(bool,notify=sourceChanged)
    def importing(self): return self._importing

    @Property('QVariantList',notify=sourceChanged)
    def importedSources(self):
        return [{'index':i,'name':Path(s.path).name,'path':s.path,'duration':float(s.duration)-float(self._source_index[s.first]-s.offset),'durationText':self.format_time(float(s.duration)),
                 'kind':'Video' if s.has_video else 'Audio','detail':f'{s.width} × {s.height}' if s.has_video else 'Audio · black video'}
                for i,s in enumerate(self._sources)]

    def _source_sources(self):
        return self._sources if len(self._sources)>1 or (self._sources and not self._sources[0].has_video) else ()

    def _store_source_visual(self,path,event,value):
        if all(s.path!=path for s in self._sources): return
        self._source_visuals.setdefault(path,{})[event] = value
        self._bound_waveforms()

    def _bound_waveforms(self):
        # Keep every source visible while coarsening very large libraries to a
        # shared 128 MiB peak-pyramid budget. Disk caches retain full detail.
        budget = max(16,128*1024*1024//max(1,len(self._sources)))
        for values in self._source_visuals.values():
            wave = values.get('waveform')
            if wave is None: continue
            step,levels = wave
            while len(levels)>1 and sum(level.nbytes for level in levels)>budget:
                step *= 2; levels = levels[1:]
            values['waveform'] = (step,levels)
        if self._sources and self._waveform is not None:
            self._waveform = self._source_visuals.get(self._sources[0].path,{}).get('waveform',self._waveform)

    def _remember_project(self,path):
        self._recent = [path]+[item for item in self._recent if item.casefold()!=path.casefold()]
        self._recent = self._recent[:10]
        self._settings.setValue('recentProjects',self._recent)
        self.projectChanged.emit()

    @Slot(QUrl)
    def openProject(self,url):
        if not url.isLocalFile() or self._exporting: return
        path = str(Path(url.toLocalFile()).resolve())
        try:
            data = project.read(path)
        except (OSError,ValueError,KeyError,TypeError) as exc:
            self.projectError.emit(f'Cannot open project:\n{path}\n\n{exc}')
            return
        if data['version']==3 or 'canvas' in data:
            self._load_multi_project(path,data)
            return
        self.open_path(data['sources'][0]['path'])
        self._pending_project = (path,data)
        self._status = 'Opening project…'
        self.changed.emit()
        self.projectChanged.emit()

    @Slot(str)
    def openRecentProject(self,path): self.openProject(QUrl.fromLocalFile(path))

    @Slot(result=bool)
    def saveProject(self):
        return self.saveProjectAs(QUrl.fromLocalFile(self._project_path)) if self._project_path else False

    @Slot(QUrl,result=bool)
    def saveProjectAs(self,url):
        if not self.canSaveProject or not url.isLocalFile(): return False
        path = str(Path(url.toLocalFile()).resolve())
        try:
            for source,identity in self._source_identities.items():
                if project.source_info(source)!=identity: raise ValueError(f'Imported source has changed:\n{source}')
            data = project.document(self._clips,self._path,{'width':self._width,'height':self._height})
            project.write(path,data)
        except (OSError,ValueError) as exc:
            self.projectError.emit(f'Cannot save project:\n{path}\n\n{exc}')
            return False
        self._project_path = path
        self._saved_timeline = data['timeline']
        self._saved_catalog = self._catalog_state()
        self._remember_project(path)
        return True

    @Property(str, notify=changed)
    def fileName(self): return self._name
    @Property(str, notify=changed)
    def detail(self): return self._detail
    @Property(str, notify=changed)
    def status(self): return self._status
    @Property(float, notify=changed)
    def duration(self): return self._duration
    @Property(float, notify=changed)
    def workspaceDuration(self): return self._duration
    @Property(float, notify=changed)
    def position(self): return self._position
    @Property(bool, notify=changed)
    def playing(self): return self._playing
    @Property(bool, notify=changed)
    def loaded(self): return bool(self._path) and not self._opening
    @Property(bool, notify=changed)
    def indexedReady(self): return bool(self._index)
    @Property(bool, notify=changed)
    def busy(self): return self._busy or self._opening or self._pending_project is not None
    @Property(bool, notify=changed)
    def muted(self): return self._muted
    @Property(float, notify=changed)
    def volume(self): return self._volume
    @Property(bool, notify=changed)
    def audioEnabled(self): return self._has_audio and self._audio_available
    @Property(bool, notify=changed)
    def hasAudio(self): return self._has_audio
    @Property(float, notify=changed)
    def videoGain(self):
        if self._clips is None: return 1.
        model = self._clips.video if isinstance(self._clips,Tracks) else self._clips
        if model.has_overlaps: return 1.
        for span in self.effect_spans():
            if span.start-.000001<=self._frame_position<span.end-.000001:
                return video_gain(self._frame_position,span)
        return 1.
    @Property(str, notify=frameChanged)
    def frameSource(self): return f'image://frames/current?revision={self._revision}'
    @Property(str, notify=changed)
    def positionText(self): return self.format_time(self._position)
    @Property(str, notify=changed)
    def durationText(self): return self.format_time(self._duration)
    @Property(str, notify=changed)
    def frameLabel(self):
        if not self._index: return 'Indexing frames…' if self._path else ''
        return f'Frame {max(0,bisect_right(self._index,self._frame_position+.000001)-1)+1} / {len(self._index)}'

    def _boundary_time(self,frame):
        return self._index[frame] if frame<len(self._index) else self._duration

    def _clip_start(self,clip): return float(self._clips.project_start(clip))
    def _clip_end(self,clip): return float(self._clips.project_end(clip))

    def _lanes(self):
        if isinstance(self._clips,Tracks): return [('video',self._clips.video),('audio',self._clips.audio)]
        return [('video',self._clips)] if self._clips else []

    def _activate_index(self,index):
        if isinstance(self._clips,Tracks): self._clips.activate('audio' if index>=1000000 else 'video')
        return index%1000000

    @Property('QVariantList',notify=editChanged)
    def clips(self):
        if self._clips is None or not self._duration: return []
        result = []
        for lane,model in self._lanes():
            if lane=='audio' and not self._has_audio: continue
            for i,clip in enumerate(model.clips):
                linked = isinstance(self._clips,Tracks) and self._clips.linked
                selected = clip.uid in self._clips.selected_ids and (linked or self._clips.active is model) if isinstance(self._clips,Tracks) else i in model.selected_indices
                result.append({'index':i+(1000000 if lane=='audio' else 0),'lane':lane,'linked':linked,
                    'start':self._clip_start(clip),'end':self._clip_end(clip),'selected':selected,
                    'startRatio':self._clip_start(clip)/self._duration,'endRatio':self._clip_end(clip)/self._duration,
                    'label':f'{i+1} \u00b7 {clip.name or (Path(source_for(self._sources,clip.pieces[0][0]).path).name if self._sources else self._name)}',
                    'durationText':self.format_time(float(model.length(clip))),
                    'rangeText':f'{self.format_time(self._clip_start(clip))} \u2192 {self.format_time(self._clip_end(clip))}'})
        return result

    @Property(int, notify=visualsChanged)
    def visualRevision(self): return self._visual_revision

    @Property(str, notify=visualsChanged)
    def visualsStatus(self): return self._visual_status

    def _visual_pieces(self, index):
        lane = 'audio' if index >= 1000000 else 'video'
        model = next((model for name, model in self._lanes() if name == lane), None)
        local = index % 1000000
        if model is None or not 0 <= local < len(model.clips): return []
        return [(p.start, p.end, p.source_start) for p in model.parts(model.clips[local])]

    @Slot(int, float, float, int, result='QVariantList')
    def waveformColumns(self, index, start, end, columns):
        if self._source_sources():
            columns = min(4096,max(0,columns))
            result = np.zeros((columns,2),np.float32)
            for part,source in self._visual_source_parts(index):
                wave = self._source_visuals.get(source.path,{}).get('waveform')
                if wave is None: continue
                step,levels = wave
                values = waveform_columns(levels,step,[(part.start,part.end,part.source_start-float(source.offset))],start,end,columns)
                if values:
                    result[:,0] = np.minimum(result[:,0],np.asarray(values)[:,0])
                    result[:,1] = np.maximum(result[:,1],np.asarray(values)[:,1])
            return result.tolist()
        if self._waveform is None: return []
        step, levels = self._waveform
        return waveform_columns(levels, step, self._visual_pieces(index), start, end, columns)

    @Slot(int, float, float, float, result='QVariantList')
    def timelineThumbnails(self, index, start, end, spacing):
        if self._source_sources():
            if spacing<=0 or end<=start: return []
            parts = self._visual_source_parts(index)
            if not parts: return []
            first = parts[0][0].start+math.floor((start-parts[0][0].start)/spacing)*spacing
            result = []
            for i in range(min(512,math.ceil((end-first)/spacing))):
                position = first+i*spacing
                sample = max(start,position)+min(spacing/2,(end-max(start,position))/2)
                for part,source in parts:
                    if not part.start<=sample<part.end: continue
                    times,files = self._source_visuals.get(source.path,{}).get('thumbnails',([],[]))
                    if not times: break
                    stamp = part.source_start+sample-part.start-float(source.offset)
                    at = max(0,min(len(times)-1,bisect_right(times,stamp)-1))
                    result.append({'start':max(position,part.start),'end':min(part.end,end,position+spacing),'url':QUrl.fromLocalFile(files[at]).toString()})
                    break
            return result
        times, files = self._thumbnails
        if not times or spacing <= 0 or end <= start: return []
        pieces = self._visual_pieces(index)
        result = []
        # Anchor tiles to the clip, rather than the viewport, for stable panning.
        if not pieces: return []
        first = pieces[0][0]+math.floor((start-pieces[0][0])/spacing)*spacing
        for i in range(min(512, math.ceil((end-first)/spacing))):
            position = first+i*spacing
            source = source_at(pieces, max(start, position)+min(spacing/2, (end-max(start, position))/2))
            if source is None: continue
            at = max(0, min(len(times)-1, bisect_right(times, source)-1))
            result.append({'start':position, 'end':min(pieces[-1][1], position+spacing),
                           'url':QUrl.fromLocalFile(files[at]).toString()})
        return result

    def _visual_source_parts(self,index):
        model = next((m for lane,m in self._lanes() if lane==('audio' if index>=1000000 else 'video')),None)
        local = index%1000000
        if model is None or not 0<=local<len(model.clips): return []
        return [(p,source_for(self._sources,p.first_frame)) for p in model.parts(model.clips[local])]

    @Property('QVariantList',notify=editChanged)
    def gaps(self):
        return [{'index':i+(1000000 if lane=='audio' else 0),'lane':lane,'start':float(a),'end':float(b)}
                for lane,model in self._lanes() if lane!='audio' or self._has_audio
                for i,(a,b) in enumerate(model.gaps())]

    @Property(bool,notify=editChanged)
    def lanesLinked(self): return isinstance(self._clips,Tracks) and self._clips.linked

    @Property(str,notify=editChanged)
    def selectionLane(self): return self._clips.lane if isinstance(self._clips,Tracks) else 'video'

    @Property(bool,notify=editChanged)
    def canUnlink(self):
        return self._has_audio and self.lanesLinked

    @Property(bool,notify=editChanged)
    def showAudioFades(self):
        return self._has_audio and (self.canUnlink or isinstance(self._clips,Tracks) and self._clips.lane=='audio')

    @Property(bool,notify=editChanged)
    def showVideoFades(self):
        return self.canUnlink or not isinstance(self._clips,Tracks) or self._clips.lane=='video'

    @Slot()
    def unlinkAudio(self):
        if self.canUnlink and self._clips.unlink():
            self._status = 'Audio unlinked. Audio and video can now be edited independently.'
            self._editing_changed(False)

    @Property(int,notify=editChanged)
    def selectedClip(self): return self._clips.selected if self._clips else -1
    @Property(int,notify=editChanged)
    def selectionCount(self): return len(self._clips.selected_indices) if self._clips else 0
    @Property(str,notify=editChanged)
    def selectedClipName(self):
        return (self._clips.selected_clip.name or f'Clip {self.selectedClip+1}') if self.selectionCount==1 else ''
    @Property(str,notify=editChanged)
    def selectedDurationText(self):
        return self.format_time(float(self._clips.length(self._clips.selected_clip))) if self.selectionCount==1 else ''
    @Property(str,notify=editChanged)
    def selectedLengthText(self):
        return self.format_time(float(self._clips.selected_length)) if self.selectionCount else ''
    @Property(bool,notify=editChanged)
    def canUndo(self): return bool(self._clips and self._clips.undo_stack) and self._pending_project is None
    @Property(bool,notify=editChanged)
    def canRedo(self): return bool(self._clips and self._clips.redo_stack) and self._pending_project is None
    @Property(bool,notify=editChanged)
    def canJoin(self): return self._clips.can_join if self._clips else False
    @Property('QVariantMap',notify=editChanged)
    def selectionRange(self):
        clips = [clip for clip in self._clips.clips if clip.uid in self._clips.selected_ids] if self._clips else []
        return {'start':min(self._clip_start(c) for c in clips),'end':max(self._clip_end(c) for c in clips)} if clips else {'start':0.,'end':self._duration}
    @Property('QVariantMap',notify=editChanged)
    def fadeValues(self):
        if self._clips is None or self._clips.selected<0: return asdict(Fades())
        return asdict(self._clips.effects[self._clips.selected])
    @Property(str,notify=editChanged)
    def selectionText(self):
        if self._clips is None: return ''
        if not self.selectionCount: return 'No clip selected'
        if self.selectionCount>1: return f'{self.selectionCount} clips selected'
        clip = self._clips.selected_clip
        return f'Clip {self._clips.selected+1} · {self.format_time(self._clip_start(clip))} → {self.format_time(self._clip_end(clip))}'
    @Property(QUrl,notify=editChanged)
    def suggestedExportUrl(self):
        return self.exportFileUrl(bool(self.selectionCount))

    @Slot(bool,result=QUrl)
    def exportFileUrl(self,selected):
        if self._clips is None: return QUrl()
        source = Path(self._path)
        suffix = f'_clip-{self._clips.selected+1}' if selected and self.selectionCount else '_export'
        return QUrl.fromLocalFile(str(source.with_name(f'{source.stem}{suffix}.mp4')))
    @Property(bool,notify=exportChanged)
    def exporting(self): return self._exporting
    @Property(float,notify=exportChanged)
    def exportProgress(self): return self._export_progress
    @Property(str,notify=exportChanged)
    def exportStatus(self): return self._export_status

    @Slot()
    def cut(self):
        if not self._clips or self.busy: return
        if self._clips.split_at(self._position):
            self._status = 'Split added. Select a clip on the timeline to export it.'
            self._editing_changed()
        else:
            self._status = 'Cannot split at a boundary, in an empty gap or through a crossfade.'
        self.changed.emit()
    @Slot(int)
    @Slot(int,bool)
    @Slot(int,bool,bool)
    def selectClip(self,index,toggle=False,extend_range=False):
        index = self._activate_index(index)
        if self._clips:
            self._clips.select(index,toggle,extend_range)
            self.editChanged.emit()

    @Slot('QVariantList',str,'QVariantList',bool)
    def selectClips(self,indices,lane,baseline,toggle):
        if not self._clips or self._pending_project is not None: return
        if isinstance(self._clips,Tracks): self._clips.activate(lane)
        model = self._clips.active if isinstance(self._clips,Tracks) else self._clips
        selected = {model.clips[int(i)%1000000].uid for i in indices if 0<=int(i)%1000000<len(model.clips)}
        previous = {model.clips[int(i)%1000000].uid for i in baseline if 0<=int(i)%1000000<len(model.clips)}
        model.selected_ids = previous ^ selected if toggle else selected
        model.selection_anchor = next((c.uid for c in model.clips if c.uid in model.selected_ids),None)
        self.editChanged.emit()

    def effect_spans(self,lane='video'):
        if self._clips is None: return ()
        model = getattr(self._clips,lane) if isinstance(self._clips,Tracks) else self._clips
        return model.effect_spans()

    def _editing_changed(self,structure=True):
        if not structure and any(model.has_overlaps for _,model in self._lanes()): structure = True
        if structure:
            new_origin = float(self._clips.origin)
            self._position += self._timeline_origin-new_origin
            self._timeline_origin = new_origin
            self._render_frames = self._clips.frames(self._fps)
            self._index = [stamp for stamp,_ in self._render_frames]
            self._duration = float(self._clips.duration)
            self._cache.clear(); self._cache_bytes = 0
        self.editChanged.emit()
        self.changed.emit()
        self.projectChanged.emit()
        if structure or self._playing: self._request(self._position,self._playing)

    @Slot(str)
    def renameSelected(self,text):
        if self.selectionCount!=1: return
        try:
            if self._clips.rename(text):
                self.editChanged.emit()
                self.projectChanged.emit()
        except ValueError as exc:
            self._status = str(exc)
            self.changed.emit()
            self.editChanged.emit()

    @Slot(str,str)
    def setFade(self,key,text):
        if self.selectionCount!=1: return
        try:
            value = float(text.strip())
            if not math.isfinite(value) or value<0: raise ValueError()
            if self._clips.set_fade(key,value): self._editing_changed(False)
        except ValueError:
            self._status = 'Invalid duration: enter a nonnegative number of seconds using a decimal point.'
            self.changed.emit()
            self.editChanged.emit()

    @Slot()
    def joinSelected(self):
        if self._clips and self._clips.join():
            self._status = 'Clips joined. Existing crossfades and outer fades were preserved.'
            self._editing_changed()
        else:
            self._status = 'Select exactly two touching or overlapping consecutive clips to join them.'
            self.changed.emit()

    @Slot(float,float,result=float)
    def snapPosition(self,position,pixel_span):
        if self._clips is None or pixel_span<=0: return position
        edges = [0.,self._duration,*[edge for _,model in self._lanes() for clip in model.clips for edge in (self._clip_start(clip),self._clip_end(clip))]]
        closest = min(edges,key=lambda edge:abs(edge-position))
        return closest if abs(closest-position)<=self._duration*8/pixel_span else position

    @Slot()
    def deleteSelected(self):
        if self._clips and self._clips.delete_selected():
            self._status = 'Clips removed from the timeline. Empty gaps were preserved.'
            self._editing_changed()

    @Slot(str,str,result=bool)
    def addSpace(self,side,text):
        if self._clips is None or self.busy: return False
        try:
            value = float(text.strip())
            if not math.isfinite(value) or value<=0: raise ValueError('Enter a positive number of seconds using a decimal point.')
            self._clips.add_space(side,text.strip())
        except (ValueError,OverflowError) as exc:
            self._status = str(exc)
            self.changed.emit()
            return False
        self._status = 'Empty space added at project '+side+'.'
        self._editing_changed()
        return True

    @Slot(int)
    def removeGap(self,index):
        index = self._activate_index(index)
        if not self._clips or not 0<=index<len(self._clips.gaps()): return
        start,end = map(float,self._clips.gaps()[index])
        if self._clips.remove_gap(index):
            if self._position>=start: self._position = max(start,self._position-(end-start))
            self._status = 'Empty gap removed.'
            self._editing_changed()

    @Slot(int,result='QVariantList')
    def movingClips(self,index):
        index = self._activate_index(index)
        if self._clips is None: return []
        lane = self._clips.lane if isinstance(self._clips,Tracks) else 'video'
        lanes = ['video','audio'] if self.lanesLinked and self._has_audio else [lane]
        return [{'index':i+(1000000 if lane=='audio' else 0),'lane':lane,
                 'start':self._clip_start(self._clips.clips[i]),'end':self._clip_end(self._clips.clips[i])}
                for lane in lanes for i in self._clips.moving_indices(index)]

    @Slot(int,float,float,bool,result=float)
    def moveTarget(self,index,target,seconds_per_pixel,disable_snap):
        index = self._activate_index(index)
        if not self._clips or not 0<=index<len(self._clips.clips): return target
        clip = self._clips.clips[index]
        indices = self._clips.moving_indices(index)
        if not indices: return self._clip_start(clip)
        moving = [self._clips.clips[i] for i in indices]
        minimum = float(clip.start-moving[0].start)
        target = max(minimum,target)
        if not disable_snap:
            ids = {c.uid for c in moving}
            anchors = [0.,self._position]
            for _,model in self._lanes():
                for other in model.clips:
                    same_lane = not isinstance(self._clips,Tracks) or model is self._clips.active
                    linked_partner = isinstance(self._clips,Tracks) and self._clips.linked
                    if other.uid not in ids or not (same_lane or linked_partner): anchors += [self._clip_start(other),self._clip_end(other)]
            offsets = {edge-self._clip_start(clip) for c in moving for edge in (self._clip_start(c),self._clip_end(c))}
            candidates = [edge-offset for edge in anchors for offset in offsets if edge-offset>=minimum]
            closest = min(candidates,key=lambda start:abs(start-target))
            if abs(closest-target)<=seconds_per_pixel*8: return closest
        return max(minimum,round(target*self._fps)/self._fps)

    @Slot(int,float)
    def moveClip(self,index,target):
        index = self._activate_index(index)
        if self._clips:
            if self._clips.move_selection(index,target):
                self._status = 'Clips moved.' if self.selectionCount>1 else 'Clip moved.'
                self._editing_changed()
            else:
                self._status = 'Cannot move: select consecutive clips; nested and triple overlaps are not supported.'
                self.changed.emit()

    @Slot(int,str,float,float,bool,result='QVariantMap')
    def resizeTarget(self,index,side,target,seconds_per_pixel,disable_snap):
        index = self._activate_index(index)
        if not self._clips: return {'start':0.,'end':0.}
        if not disable_snap:
            anchors = [0.,self._duration,self._position]
            for _,model in self._lanes():
                for clip in model.clips: anchors += [self._clip_start(clip),self._clip_end(clip)]
            limit = self._clips.resize_candidate(index,side,1e12 if side=='right' else -1e12)
            if limit: anchors.append(self._clip_end(limit) if side=='right' else self._clip_start(limit))
            closest = min(anchors,key=lambda edge:abs(edge-target))
            if abs(closest-target)<=8*seconds_per_pixel: target = closest
        candidate = self._clips.resize_candidate(index,side,target)
        return {'start':self._clip_start(candidate),'end':self._clip_end(candidate)} if candidate else {'start':0.,'end':0.}

    @Slot(int,str,float)
    def resizeClip(self,index,side,target):
        index = self._activate_index(index)
        if self._clips and self._clips.resize(index,side,target):
            self._status = 'Edge updated. The original file is unchanged.'
            self._editing_changed()

    @Slot()
    def duplicateSelected(self):
        if self._clips is None: return
        index = self._clips.selected
        if not self.selectionCount:
            index = next((i for i,clip in enumerate(self._clips.clips) if self._clip_start(clip)<=self._position<self._clip_end(clip)),-1)
        if index>=0 and self._clips.duplicate(index):
            self._status = 'Clip duplicated into the adjacent space.'
            self._editing_changed()
        else:
            self._status = 'Cannot duplicate: select one clip with enough adjacent space.'
            self.changed.emit()
    @Slot()
    def undoCut(self):
        if self._clips:
            self._clips.undo()
            self._editing_changed()
    @Slot()
    def redoCut(self):
        if self._clips:
            self._clips.redo()
            self._editing_changed()

    def export_spec(self,selected=True,normalize_audio=False,level=-1.,independent=False):
        if self._clips is None: raise ValueError('Wait for video indexing to finish.')
        if selected and not self.selectionCount: raise ValueError('Select a timeline interval to export.')
        if not math.isfinite(level) or level>0: raise ValueError('Normalization level must be a finite number less than or equal to 0 dBFS.')
        clip = next((c for c in self._clips.clips if c.uid in self._clips.selected_ids),None) if selected else None
        a,b = (clip.pieces[0][0],clip.pieces[-1][1]) if clip else (0,len(self._video_pts))
        window = self.selectionRange if selected else {'start':0.,'end':self._duration}
        if window['end']<=window['start']: raise ValueError('The export interval is empty.')
        end_pts = self._video_pts[b] if b<len(self._video_pts) else max(self._video_pts[-1]+1,round(Fraction(str(self._origin+self._source_duration))/self._video_time_base))
        return ExportSpec(self._path,a,b,self._video_pts[a],end_pts,self._video_time_base,self._origin,self._audio_timeline,
                          clip.fades if clip else Fades(),(self._clips.video if isinstance(self._clips,Tracks) else self._clips).parts(),window['start'],window['end'],
                          self._clips.audio.parts() if isinstance(self._clips,Tracks) else self._clips.parts(),
                          self.effect_spans('audio'),self.effect_spans(),self._fps,self._width,self._height,tuple(self._video_pts),
                          normalize_audio,level,independent,self._source_sources())

    @Slot(QUrl)
    @Slot(QUrl,bool,bool,float,bool)
    def exportClip(self,url,selected=True,normalize_audio=False,level=-1.,independent=False):
        if self._exporting or not url.isLocalFile(): return
        try:
            spec = self.export_spec(selected,normalize_audio,level,independent)
            self._export_progress = 0.
            self._export_status = 'Preparing export…'
            self._exporting = True
            self.export_task.start(spec,url.toLocalFile())
        except Exception as exc:
            self._exporting = False
            self._export_status = str(exc)
        self.exportChanged.emit()

    @Slot()
    def cancelExport(self):
        if self._exporting:
            self._export_status = 'Cancelling…'
            self.export_task.cancel()
            self.exportChanged.emit()

    @Slot(float,str)
    def _export_updated(self,fraction,text):
        self._export_progress = fraction
        self._export_status = text
        self.exportChanged.emit()

    @Slot(str,str)
    def _export_finished(self,result,message):
        self._exporting = False
        self._export_status = message
        self.exportChanged.emit()

    @staticmethod
    def format_time(seconds):
        ms = max(0,round(seconds*1000))
        return f'{ms//3600000:02d}:{ms//60000%60:02d}:{ms//1000%60:02d}.{ms%1000:03d}'

    @Slot(QUrl)
    def openUrl(self,url):
        if url.isLocalFile(): self.open_path(url.toLocalFile())

    @Slot('QVariantList')
    def importUrls(self,urls):
        if self._exporting or self._pending_project: return
        paths = []
        for value in urls:
            url = value if isinstance(value,QUrl) else QUrl(str(value))
            if url.isLocalFile():
                path = str(Path(url.toLocalFile()).resolve())
                if path not in paths and path not in self._import_queue and all(s.path!=path for s in self._sources): paths.append(path)
        if not paths: return
        if not self._path:
            first = paths.pop(0)
            self.open_path(first)
        self._import_queue.extend(paths)
        self._start_import_next()

    def _start_import_next(self):
        if self._importing or not self._sources or not self._import_queue or self._closed: return
        path = self._import_queue.pop(0)
        self._importing = True
        self.sourceChanged.emit(); self.projectChanged.emit()
        generation,cancelled = self._source_generation,self._import_cancel
        def run():
            try:
                values = {}
                inspect_and_index(path,cancelled,lambda kind,data:values.__setitem__(kind,data))
                if cancelled.is_set(): return
                if 'error' in values or 'index' not in values: raise ValueError(values.get('error','Import cancelled.'))
                identity = project.source_info(path)
                self.sourceIndexed.emit(generation,'entry',(path,values['metadata'],values['index'],identity))
                metadata = values['metadata']
                build_visuals(path,metadata['origin'],metadata['duration']-metadata['origin'],metadata['audio_timeline'],cancelled,
                              lambda kind,data:self.sourceIndexed.emit(generation,'visual',(path,kind,data)) if not self._closed else None)
            except (OSError,ValueError,KeyError,TypeError) as exc:
                if not cancelled.is_set() and not self._closed: self.sourceIndexed.emit(generation,'import-error',(path,str(exc)))
            finally:
                if not cancelled.is_set() and not self._closed: self.sourceIndexed.emit(generation,'done',None)
        threading.Thread(target=run,name='source-import',daemon=True).start()

    @Slot(int,float,str)
    def insertSource(self,index,position,lane='video'):
        if self._clips is None or not 0<=index<len(self._sources) or not math.isfinite(position) or self._exporting or self._pending_project: return
        before = self._clips.snapshot()
        self._clips.activate('audio' if lane=='audio' else 'video')
        if self._clips.insert_source(self._sources[index],position): self._editing_changed()
        else:
            self._clips.restore_snapshot(before)
            self._status = 'Cannot place source here. Use free space or a partial overlap of two clips.'
            self.changed.emit()

    @Slot(int)
    def appendSource(self,index):
        if 0<=index<len(self._sources): self.insertSource(index,self._duration,'video' if self._sources[index].has_video else 'audio')

    def _extend_catalog(self,path,metadata,index,identity):
        source,times = catalog_entry(path,metadata,index,self._sources)
        self._sources = (*self._sources,source)
        self._bound_waveforms()
        self._source_identities[path] = identity
        exact = tuple(self._clips.video.times)+times
        self._source_index = [float(t) for t in exact]
        self._source_duration = float(source.offset+source.duration)
        for _,model in self._lanes():
            model.sources = self._sources
            model.times = exact
            model.edges = (*exact,source.offset+source.duration)
            model.frame_count = len(exact)
            model.source_duration = source.offset+source.duration
        if source.has_video and not self._canvas_locked:
            self._width,self._height,self._fps = source.width,source.height,source.fps
            self._canvas_locked = True
        # The project clock represents every source PTS; it is independent of output cadence.
        denominator = math.lcm(*(s.time_base.denominator for s in self._sources),*(s.offset.denominator for s in self._sources))
        if denominator>2147483647: denominator = 1000000
        self._video_time_base = Fraction(1,denominator)
        self._video_pts = [round((t+Fraction(str(self._origin)))/self._video_time_base) for t in exact]
        self._has_audio = any(s.audio_timeline for s in self._sources)
        self._audio_timeline = next((s.audio_timeline for s in self._sources if s.audio_timeline),None)
        self._editing_changed()
        self.sourceChanged.emit()

    def _load_multi_project(self,path,document):
        if self._importing: return
        self._pending_project = (path,document)
        self._importing = True
        self._stop_transport()
        self.sourceChanged.emit(); self.projectChanged.emit(); self.changed.emit()
        generation,cancelled = self._source_generation,self._import_cancel
        def run():
            entries = []
            try:
                for item in document['sources']:
                    values = {}
                    inspect_and_index(item['path'],cancelled,lambda kind,data:values.__setitem__(kind,data))
                    if cancelled.is_set(): return
                    if 'error' in values: raise ValueError(values['error'])
                    entries.append((item['path'],values['metadata'],values['index'],project.source_info(item['path'])))
                project.validate_sources(document)
                self.sourceIndexed.emit(generation,'project',(path,document,entries))
            except (OSError,ValueError,KeyError,TypeError) as exc:
                if not cancelled.is_set(): self.sourceIndexed.emit(generation,'project-error',str(exc))
        threading.Thread(target=run,name='project-source-index',daemon=True).start()

    @Slot(int,str,object)
    def _receive_source(self,generation,kind,data):
        if self._closed or generation!=self._source_generation: return
        if kind=='entry':
            try: self._extend_catalog(*data)
            except (ValueError,KeyError,OverflowError) as exc: self.projectError.emit(f'Cannot import source:\n{exc}')
        elif kind=='visual':
            path,event,value = data
            self._store_source_visual(path,event,value)
            self._visual_revision += 1; self.visualsChanged.emit()
        elif kind=='import-error': self.projectError.emit(f'Cannot import source:\n{data[0]}\n\n{data[1]}')
        elif kind=='done':
            self._importing = False
            self.sourceChanged.emit(); self.projectChanged.emit()
            self._start_import_next()
        elif kind=='project-error':
            self._pending_project = None; self._importing = False
            self.projectError.emit(f'Cannot open project:\n{data}')
            self.sourceChanged.emit(); self.projectChanged.emit(); self.changed.emit()
        elif kind=='project':
            path,document,entries = data
            try:
                sources,times = (),()
                for source_file,metadata,index,identity in entries:
                    source,local = catalog_entry(source_file,metadata,index,sources)
                    sources = (*sources,source); times += local
                duration = sources[-1].offset+sources[-1].duration
                tracks = project.restore(document,times,duration,sources)
            except (OSError,ValueError,KeyError,TypeError,OverflowError) as exc:
                self._receive_source(generation,'project-error',str(exc)); return
            self._index_cancel.set(); self._import_cancel.set()
            self._index_cancel = threading.Event(); self._import_cancel = threading.Event()
            self._source_generation += 1
            self._sources = sources; self._clips = tracks
            self._source_identities = {entry[0]:entry[3] for entry in entries}
            self._source_identity = entries[0][3]
            self._path = sources[0].path; self._name = Path(self._path).name
            self._origin = sources[0].origin
            self._source_index = [float(t) for t in times]
            self._source_duration = float(duration)
            denominator = math.lcm(*(s.time_base.denominator for s in sources),*(s.offset.denominator for s in sources))
            self._video_time_base = Fraction(1,denominator if denominator<=2147483647 else 1000000)
            self._video_pts = [round((t+Fraction(str(self._origin)))/self._video_time_base) for t in times]
            self._has_audio = any(s.audio_timeline for s in sources)
            self._audio_timeline = next((s.audio_timeline for s in sources if s.audio_timeline),None)
            self._width,self._height = document['canvas']['width'],document['canvas']['height']
            self._canvas_locked = any(s.has_video for s in sources)
            self._fps = next((s.fps for s in sources if s.has_video),30.)
            self._project_path = path; self._pending_project = None
            self._importing = self._opening = False
            self._source_visuals = {}; self._waveform = None; self._thumbnails = ([],[])
            self._position = 0.; self._timeline_origin = float(tracks.origin)
            self._saved_timeline = project.timeline(tracks); self._saved_catalog = self._catalog_state()
            self._editing_changed(); self._remember_project(path)
            self.sourceChanged.emit()
            # Reuse the bounded sequential import worker to populate visual caches.
            cancelled,generation = self._import_cancel,self._source_generation
            def visuals():
                for source in sources:
                    if cancelled.is_set(): return
                    build_visuals(source.path,source.origin,float(source.duration),source.audio_timeline,cancelled,
                                  lambda event,value,s=source:self.sourceIndexed.emit(generation,'visual',(s.path,event,value)) if not self._closed else None)
            threading.Thread(target=visuals,name='project-visuals',daemon=True).start()

    def open_path(self,path):
        if self._exporting: return
        path = str(Path(path).resolve())
        self._project_path = ''
        self._saved_timeline = None
        self._pending_project = None
        self._import_cancel.set()
        self._import_cancel = threading.Event()
        self._import_queue = []
        self._importing = False
        self._sources = ()
        self._source_identities = {}
        self._source_visuals = {}
        self._saved_catalog = None
        self._canvas_locked = False
        self._initial_metadata = None
        self.sourceChanged.emit()
        self._source_identity = None
        self._stop_transport()
        self._index_cancel.set()
        self._index_cancel = threading.Event()
        self._source_generation += 1
        source_generation = self._source_generation
        self._generation += 1
        self.video.request(self._generation)
        self.audio.request(self._generation)
        self._path = path
        self._index = []
        self._source_index = []
        self._render_frames = ()
        self._video_pts = []
        self._clips = None
        self._waveform = None
        self._thumbnails = ([], [])
        self._visual_status = 'Preparing timeline previews…'
        self._visual_revision += 1
        self.visualsChanged.emit()
        self.projectChanged.emit()
        self._timeline_origin = 0.
        self.editChanged.emit()
        self._export_status = ''
        self.exportChanged.emit()
        self._cache.clear()
        self._cache_bytes = 0
        self._next_frame = None
        self._position = self._duration = 0.
        self._name = Path(path).name
        self._opening = True
        self._busy = False
        self._status = 'Importing source…'
        self.provider.clear()
        self._revision += 1
        self.frameChanged.emit()
        self.changed.emit()
        cancelled = self._index_cancel
        threading.Thread(target=inspect_and_index,args=(path,cancelled,lambda kind,data:self.indexed.emit(source_generation,kind,data) if not self._closed else None),name='source-index',daemon=True).start()

    @Slot(int,str,object)
    def _receive_index(self,generation,kind,data):
        if generation != self._source_generation or self._closed: return
        if kind in ('waveform', 'thumbnails', 'visuals-error'):
            if kind == 'waveform': self._waveform = data
            elif kind == 'thumbnails': self._thumbnails = data
            if self._sources: self._store_source_visual(self._sources[0].path,kind,data)
            self._visual_status = f'Timeline previews: {data}' if kind == 'visuals-error' else ('' if kind == 'thumbnails' else 'Preparing video thumbnails…')
            self._visual_revision += 1
            self.visualsChanged.emit()
        elif kind=='error':
            self._opening = False
            self._status = f'Error: {data}'
            if self._pending_project:
                self._pending_project = None
                self.projectError.emit(self._status)
                self.projectChanged.emit()
            if self._clips is None:
                self._path = ''; self._duration = 0.; self._index = []; self._has_audio = False
                remaining = self._import_queue.copy()
                if remaining:
                    self._import_queue = []
                    self.projectError.emit(f'Cannot import source:\n{data}')
                    self.importUrls([QUrl.fromLocalFile(path) for path in remaining])
            self.changed.emit()
        elif kind=='metadata':
            self._initial_metadata = data
            self._canvas_locked = data.get('has_video',True)
            self._duration = max(0.,data['duration']-data['origin'])
            self._source_duration = self._duration
            self._fps = data['fps']
            self._width,self._height = data['width'],data['height']
            self._origin = data['origin']
            self._has_audio = data['has_audio']
            self._audio_timeline = data['audio_timeline']
            self._detail = f"{data['width']} × {data['height']}  ·  {data['fps']:.3f} fps".replace('.000 fps',' fps')
            self._opening = not data.get('has_video',True)
            if data.get('has_video',True): self._request(0.,False)
        elif kind=='index':
            self._opening = False
            base = Fraction(data['time_base'])
            self._video_time_base = base
            self._video_pts = data['pts']
            self._index = [float(pts*base)-self._origin for pts in data['pts']]
            self._source_index = self._index.copy()
            if not self._duration: self._duration = self._index[-1] + 1/30
            exact_times = [pts*base-Fraction(str(self._origin)) for pts in data['pts']]
            try:
                source,_ = catalog_entry(self._path,{**self._initial_metadata,'duration':self._duration+self._origin},data)
            except (ValueError,KeyError,OverflowError) as exc:
                self._receive_index(generation,'error',str(exc)); return
            self._sources = (source,)
            self._clips = Tracks(Clips(len(self._index),exact_times,Fraction(str(self._duration))))
            if self._pending_project:
                path,document = self._pending_project
                self._pending_project = None
                try:
                    project.validate_sources(document)
                    self._clips = project.restore(document,exact_times,Fraction(str(self._duration)))
                    if not isinstance(self._clips,Tracks): self._clips = Tracks(self._clips)
                except (OSError,ValueError,KeyError,TypeError,OverflowError) as exc:
                    self._clips = None
                    self._path = ''
                    self._index = []
                    self._duration = 0.
                    self._stop_transport()
                    self.projectError.emit(f'Cannot open project:\n{path}\n\n{exc}')
                    self.editChanged.emit()
                    self.changed.emit()
                    self.projectChanged.emit()
                    return
                self._project_path = path
                self._saved_timeline = project.timeline(self._clips)
                self._timeline_origin = float(self._clips.origin)
                self._remember_project(path)
            self._source_identity = project.source_info(self._path)
            self._source_identities = {self._path:self._source_identity}
            for _,model in self._lanes(): model.sources = self._sources
            if self._project_path: self._saved_catalog = self._catalog_state()
            self._render_frames = self._clips.frames(self._fps)
            if self._project_path or not source.has_video:
                self._index = [stamp for stamp,_ in self._render_frames]
                self._duration = float(self._clips.duration)
                self._request(0.,False)
            self.projectChanged.emit()
            self.editChanged.emit()
            if not self._busy and not self._playing: self._status = ''
            self.changed.emit()
            self.sourceChanged.emit()
            self._start_import_next()

            cancelled = self._index_cancel
            threading.Thread(target=build_visuals,
                args=(self._path, self._origin, self._source_duration or self._duration,
                      self._audio_timeline, cancelled,
                      lambda kind, data: self.indexed.emit(generation, kind, data) if not self._closed else None),
                name='timeline-visuals', daemon=True).start()

    def _stop_transport(self):
        if self.sink: self.sink.stop()
        self._io = None
        self._playing = False
        self._audio_started = False
        self._audio_pending = b''

    def _request(self,position,play,endpoint=False):
        if not self._path or self._opening: return
        self._seek_endpoint = endpoint
        position = max(0.,min(position,self._index[-1] if self._index else max(0.,self._duration-.001)))
        if self._index:
            position = self._index[max(0,bisect_right(self._index,position+.000001)-1)]
        self._stop_transport()
        self._generation += 1
        if self._clips is not None and self._duration<=0:
            self.video.request(self._generation,None)
            self.audio.request(self._generation,None)
            self._next_frame = None
            self._position = 0.
            self._busy = False
            self.provider.clear(self._width,self._height)
            self._revision += 1
            self.frameChanged.emit()
            self._status = 'Empty timeline'
            self.changed.emit()
            return
        job = Job(self._generation,self._path,position,self._origin,self._duration,play,self._audio_timeline,self.effect_spans(),
                  (self._clips.video if isinstance(self._clips,Tracks) else self._clips).parts() if self._clips is not None else None,self._fps,self._width,self._height,tuple(self._source_index),self._source_sources())
        self._next_frame = None
        self._position = position
        self._base = position
        self._playing = play
        self._busy = True
        cached = self._cache.get(round(position*1000000))
        self.video.request(self._generation,job if play or cached is None else None)
        audio_job = replace(job,parts=self._clips.audio.parts(),effects=self.effect_spans('audio')) if isinstance(self._clips,Tracks) else job
        self.audio.request(self._generation,audio_job if play and self.audioEnabled else None)
        if cached is not None:
            self._show(self._generation,position,cached)
        self._status = 'Preparing…' if play else 'Seeking…' if cached is None else ''
        self.changed.emit()

    @Slot(float)
    def seek(self,position): self._request(position,False)
    @Slot(float)
    def jump(self,seconds):
        if self.loaded:
            self._request(self._position+seconds,self._playing)
    @Slot(int)
    def jumpBoundary(self,direction):
        if self._clips is None: return
        boundaries = sorted({0.,self._duration,*[edge for clip in self._clips.clips
                             for edge in (self._clip_start(clip),self._clip_end(clip))]})
        candidates = [edge for edge in boundaries if (edge-self._position)*direction>.000001]
        if candidates:
            target = min(candidates) if direction>0 else max(candidates)
            endpoint = target==self._duration
            self._request(target,self._playing and not endpoint,endpoint=endpoint)
    @Slot(str)
    def seekText(self,text):
        try:
            parts = text.strip().split(':')
            if not 1<=len(parts)<=3: raise ValueError()
            seconds = 0.
            for part in parts: seconds = seconds*60+float(part)
            if not 0<=seconds<=self._duration: raise ValueError()
            self.seek(seconds)
        except ValueError:
            self._status = 'Invalid time. Use hh:mm:ss.mmm or seconds with a decimal point.'
            self.changed.emit()
    @Slot()
    def toggle(self):
        if not self.loaded: return
        if self._playing: self.pause()
        else: self._request(0. if self._position>=self._duration-.04 else self._position,True)
    @Slot()
    def pause(self):
        if self.loaded: self._request(self._position,False)
    @Slot(int)
    def step(self,direction):
        if not self._index: return
        if direction<0 and self._position>=self._duration:
            self._request(self._index[-1],False)
            return
        index = max(0,bisect_right(self._index,self._position+.000001)-1)
        self._request(self._index[min(len(self._index)-1,max(0,index+direction))],False)
    @Slot()
    def beginScrub(self):
        self._scrub_resume = self._playing
        if self._playing: self.pause()
    @Slot(float)
    def endScrub(self,position): self._request(position,self._scrub_resume)
    @Slot()
    def toggleMute(self):
        self._muted = not self._muted
        self._update_volume()
        self.changed.emit()

    @Slot(float)
    def setVolume(self,value):
        if not math.isfinite(value): return
        self._volume = max(0.,min(2.,value))
        self._update_volume()
        self.changed.emit()

    def _update_volume(self):
        if self.sink: self.sink.setVolume(0. if self._muted else min(1.,self._volume))

    def _listening_pcm(self,data):
        """Boost only device-bound PCM; retain raw pending bytes after partial writes."""
        if self._volume<=1.: return data
        dtype = np.dtype('<f4' if self.audio.sample_format=='flt' else '<i2')
        samples = np.frombuffer(data,dtype=dtype).astype(np.float32)*self._volume
        if self.audio.sample_format=='s16':
            samples = np.clip(np.rint(samples),-32768,32767)
        else:
            samples = np.clip(samples,-1.,1.)
        return samples.astype(dtype).tobytes()

    def _remember(self,stamp,image):
        key = round(stamp*1000000)
        if key in self._cache:
            self._cache.move_to_end(key)
            return
        self._cache[key] = image
        self._cache_bytes += image.sizeInBytes()
        while self._cache_bytes>self._cache_limit and len(self._cache)>1:
            _,old = self._cache.popitem(last=False)
            self._cache_bytes -= old.sizeInBytes()

    def _show(self,generation,stamp,image):
        if generation!=self._generation: return
        if self._index:
            i = max(0,bisect_right(self._index,stamp+.000001)-1)
            if abs(self._index[i]-stamp)<.000001: stamp = self._index[i]
        self._remember(stamp,image)
        self.provider.put(image)
        self._position = self._duration if self._seek_endpoint else stamp
        self._frame_position = self._position
        self._revision += 1
        self._displayed_generation = generation
        self._busy = False
        self.frameChanged.emit()

    def _pump_audio(self):
        if not self._io: return
        available = self.sink.bytesFree()
        available -= available % self.audio.sample_bytes
        while available>0:
            if not self._audio_pending:
                self._audio_pending = self.audio.take_audio(available)
            if not self._audio_pending: break
            count = self._io.write(self._listening_pcm(self._audio_pending[:available]))
            if count<0:
                raise RuntimeError('Cannot write to the audio device.')
            if not count: break
            self._audio_pending = self._audio_pending[count:]
            available -= count

    def _clock(self):
        if self.audioEnabled and self._audio_started:
            return self._base + self.sink.processedUSecs()/1000000.
        return self._base + time.perf_counter()-self._wall_start

    @Slot()
    def _tick(self):
        if self._closed: return
        try:
            self._advance()
        except Exception as exc:
            self._stop_transport()
            self._busy = False
            self._status = f'Error: {exc}'
            self.changed.emit()

    def _advance(self):
        vcount,_,veof,verror = self.video.status()
        acount,abytes,aeof,aerror = self.audio.status()
        if verror or (self._playing and aerror):
            raise RuntimeError(verror or aerror)
        if not self.loaded: return
        if not self._playing:
            received = False
            while True:
                item = self.video.take_video()
                if item is None: break
                generation,stamp,image = item
                self._remember(stamp,image)
                if generation==self._generation and self._displayed_generation!=generation:
                    self._show(generation,stamp,image)
                    received = True
            if received:
                self._status = ''
                self.changed.emit()
            return
        if not self._audio_started:
            if not vcount: return
            if self.audioEnabled and abytes<round(.08*48000*self.audio.sample_bytes) and not aeof: return
            if self.audioEnabled:
                self._io = self.sink.start()
                if self._io is None: raise RuntimeError('Audio device unavailable.')
                self._pump_audio()
            self._wall_start = time.perf_counter()
            self._audio_started = True
            self._busy = False
            self._status = '' if self.audioEnabled else 'No audio output'
        if self.audioEnabled:
            self._pump_audio()
            if self.sink.error().value:
                # Underrun resumes automatically when decoded samples arrive.
                if 'Underrun' not in str(self.sink.error()):
                    raise RuntimeError(f'Audio output: {self.sink.error()}')
        clock = min(self._duration,self._clock())
        self.video.set_preview_position(self._generation,clock)
        latest = None
        while True:
            if self._next_frame is None:
                self._next_frame = self.video.take_video()
            if self._next_frame is None: break
            generation,stamp,image = self._next_frame
            if stamp>clock+.0005: break
            latest,self._next_frame = self._next_frame,None
        if latest:
            self._show(*latest)
            self._max_clock_frame_gap = max(self._max_clock_frame_gap,clock-latest[1])
        # The transport must advance even when the video worker falls behind.
        # Keep frame-dependent display metadata tied to the presented image.
        self._position = clock
        if clock>=self._duration-.002:
            self.pause()
        self.changed.emit()

    def diagnostics(self):
        return {'source':self._path,'position':self._position,'playing':self._playing,
                'displayed_frame_position':self._frame_position,
                'generation':self._generation,'displayed_generation':self._displayed_generation,
                'index_frames':len(self._index),'cache_bytes':self._cache_bytes,
                'video_queue_frames':self.video.status()[0],'audio_queue_bytes':self.audio.status()[1],
                'audio_device':self._device.description(),'audio_available':self._audio_available,
                'audio_clock_started':self._audio_started,'audio_processed_us':self.sink.processedUSecs() if self.sink else None,
                'max_clock_to_displayed_frame_gap_seconds':self._max_clock_frame_gap}

    def close(self):
        self._closed = True
        self.export_task.close()
        self.timer.stop()
        self._index_cancel.set()
        self._import_cancel.set()
        self._stop_transport()
        self.video.close()
        self.audio.close()
        self.video.thread.join(timeout=2)
        self.audio.thread.join(timeout=2)
