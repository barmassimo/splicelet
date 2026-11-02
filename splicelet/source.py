"""Native decoding on cancellable workers. No Qt objects touch the GUI here."""
from collections import deque
from dataclasses import dataclass,replace
import math
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import threading

import av
import numpy as np
from PySide6.QtGui import QImage
from .effects import audio_fades, video_gain, cross_gain
from .composition import intervals, interval_frames
from .runtime import ARTIFACTS
from .sources import source_for, fit_geometry

INDEX_DIR = ARTIFACTS/'index'


@dataclass(frozen=True)
class Job:
    generation: int
    path: str
    position: float
    origin: float
    duration: float
    playing: bool
    audio_timeline: dict | None = None
    effects: tuple = ()
    parts: tuple | None = None
    fps: float = 30.
    width: int = 640
    height: int = 360
    source_times: tuple = ()
    sources: tuple = ()


def part_job(job,part):
    if not job.sources: return job
    source = source_for(job.sources,part.first_frame)
    return replace(job,path=source.path,origin=source.virtual_origin,audio_timeline=source.audio_timeline)


def source_rgb(frame,job,part):
    rgb = frame.to_ndarray(format='rgb24')
    if not job.sources: return rgb
    source = source_for(job.sources,part.first_frame)
    if source.rotation: rgb = np.ascontiguousarray(np.rot90(rgb,-source.rotation//90))
    w,h,x,y = fit_geometry(source,job.width,job.height)
    if rgb.shape[:2]!=(h,w):
        rgb = av.VideoFrame.from_ndarray(rgb,format='rgb24').reformat(width=w,height=h,interpolation='BILINEAR').to_ndarray(format='rgb24')
    if (w,h)==(job.width,job.height): return rgb
    canvas = np.zeros((job.height,job.width,3),dtype=np.uint8)
    canvas[y:y+h,x:x+w] = rgb
    return canvas


def audio_sample_timeline(path, cancelled=lambda: False):
    """Recover exact sample anchors; container PTS may be rounded to milliseconds.

    Snap only errors inside one source time-base tick. Preserve larger gaps.
    Indexing from the start also makes a later seek use the same sample anchor.
    """
    pts, positions = [], []
    cursor = None
    snapped = 0
    with av.open(path) as container:
        if not container.streams.audio:
            return None
        stream = container.streams.audio[0]
        rate = stream.codec_context.sample_rate
        for frame in container.decode(stream):
            if cancelled():
                return None
            if frame.sample_rate != rate or frame.pts is None:
                raise ValueError('Audio without timestamps or with a variable sample rate is not supported.')
            raw = frame.pts * frame.time_base * rate
            tolerance = frame.time_base * rate + 1
            begin = round(raw)
            if cursor is not None and abs(raw-cursor) <= tolerance:
                begin = cursor
                snapped += int(raw != cursor)
            pts.append(frame.pts)
            positions.append(begin)
            cursor = begin + frame.samples
        return {'rate':rate, 'pts':pts, 'sample_positions':positions, 'end_sample':cursor,
                'rounded_timestamps_corrected':snapped}


def configure(stream):
    stream.thread_type = 'AUTO'
    stream.codec_context.thread_count = 4


class Decoder:
    """One pending job, bounded output, cancellation at each decoded frame."""
    def __init__(self, kind, rate=48000, sample_format='flt', bytes_per_sample=4):
        self.kind = kind
        self.rate = rate
        self.sample_format = sample_format
        self.sample_bytes = bytes_per_sample * 2
        self.condition = threading.Condition()
        self.generation = 0
        self.pending = None
        self.queue = deque()
        self.queued_bytes = 0
        self.eof = False
        self.error = None
        self.closed = False
        self.thread = threading.Thread(target=self._run, name=f'{kind}-decoder', daemon=True)
        self.thread.start()

    def request(self, generation, job=None):
        with self.condition:
            self.generation = generation
            self.pending = job
            self.queue.clear()
            self.queued_bytes = 0
            self.eof = False
            self.error = None
            self.condition.notify_all()

    def stale(self, job):
        with self.condition:
            return self.closed or job.generation != self.generation

    def put(self, job, item):
        with self.condition:
            while not self.closed and job.generation == self.generation:
                full = len(self.queue) >= 6 if self.kind == 'video' else self.queued_bytes >= int(self.rate * self.sample_bytes * .5)
                if not full:
                    self.queue.append(item)
                    if self.kind == 'audio':
                        self.queued_bytes += len(item)
                    self.condition.notify_all()
                    return True
                self.condition.wait(.05)
            return False

    def take_video(self):
        with self.condition:
            item = self.queue.popleft() if self.queue else None
            self.condition.notify_all()
            return item

    def take_audio(self, size):
        with self.condition:
            if not self.queue:
                return b''
            chunk = self.queue[0]
            size = min(size, len(chunk))
            result = chunk[:size]
            if size == len(chunk):
                self.queue.popleft()
            else:
                self.queue[0] = chunk[size:]
            self.queued_bytes -= size
            self.condition.notify_all()
            return result

    def status(self):
        with self.condition:
            return len(self.queue), self.queued_bytes, self.eof, self.error

    def close(self):
        with self.condition:
            self.closed = True
            self.condition.notify_all()

    def _run(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.closed or self.pending is not None)
                if self.closed:
                    return
                job, self.pending = self.pending, None
            try:
                if self.kind == 'video':
                    self._video(job)
                else:
                    self._audio(job)
            except Exception as exc:
                with self.condition:
                    if job.generation == self.generation:
                        self.error = str(exc)
            finally:
                with self.condition:
                    if job.generation == self.generation:
                        self.eof = True

    def _video(self, job):
        if job.parts is not None:
            self._project_video(job)
            return
        with av.open(job.path) as container:
            stream = container.streams.video[0]
            configure(stream)
            target = Fraction(str(job.origin)) + Fraction(str(job.position))
            container.seek(max(0, int(target / stream.time_base)), stream=stream, backward=True, any_frame=False)
            emitted = 0
            for frame in container.decode(stream):
                if self.stale(job):
                    return
                stamp = float(frame.pts * frame.time_base) - job.origin
                if stamp < job.position - .000001:
                    continue
                rgb = frame.to_ndarray(format='rgb24')
                image = QImage(rgb.data, frame.width, frame.height, rgb.strides[0], QImage.Format.Format_RGB888).copy()
                if not self.put(job, (job.generation, stamp, image)):
                    return
                emitted += 1
                if not job.playing and emitted >= 5:
                    return

    def _intervals(self,job):
        cursor = 0.
        for part in job.parts:
            if part.start>cursor+.000001: yield cursor,part.start,None
            yield part.start,part.end,part
            cursor = part.end
        if cursor<job.duration-.000001: yield cursor,job.duration,None

    def _project_video(self,job):
        if any(s.cross_in or s.cross_out for s in job.effects):
            self._composite_video(job)
            return
        emitted = 0
        black = QImage(job.width,job.height,QImage.Format.Format_RGB888)
        black.fill(0xff000000)
        def gap(start,end):
            frame = max(0,math.ceil((max(start,job.position)-start)*job.fps-.00001))
            while start+frame/job.fps<end-.000001:
                yield start+frame/job.fps,black
                frame += 1
        def source(part):
            target = max(part.source_start,part.source_start+job.position-part.start)
            local = part_job(job,part)
            if job.sources and not source_for(job.sources,part.first_frame).has_video:
                for stamp in interval_frames((part,),job.source_times,max(part.start,job.position),part.end,job.fps):
                    yield stamp,black
                return
            with av.open(local.path) as container:
                stream = container.streams.video[0]
                configure(stream)
                container.seek(max(0,int(Fraction(str(target+local.origin))/stream.time_base)),stream=stream,backward=True)
                for frame in container.decode(stream):
                    if self.stale(job): return
                    stamp = float(frame.pts*frame.time_base)-local.origin
                    if stamp>=part.source_end-.000001: return
                    if stamp<target-.000001: continue
                    rgb = source_rgb(frame,job,part)
                    image = QImage(rgb.data,rgb.shape[1],rgb.shape[0],rgb.strides[0],QImage.Format.Format_RGB888).copy()
                    yield part.start+stamp-part.source_start,image
        for start,end,part in self._intervals(job):
            if end<=job.position+.000001: continue
            for stamp,image in (source(part) if part else gap(start,end)):
                if self.stale(job) or not self.put(job,(job.generation,stamp,image)): return
                emitted += 1
                if not job.playing and emitted>=5: return

    def _audio(self, job):
        if job.parts is not None:
            self._project_audio(job)
            return
        rate = self.rate
        cursor = round((job.origin + job.position) * rate)
        end = round((job.origin + job.duration) * rate)

        def silence(until):
            nonlocal cursor
            while cursor < until:
                count = min(until-cursor, 4096)
                if not self.put(job, bytes(count * self.sample_bytes)):
                    return False
                cursor += count
            return True

        def samples(frame):
            nonlocal cursor
            if self.stale(job):
                return False
            begin = round(frame.pts * frame.time_base * rate) if frame.pts is not None else cursor
            finish = min(begin + frame.samples, end)
            if finish <= cursor:
                return True
            if begin > cursor and not silence(min(begin, end)):
                return False
            skip = max(0, cursor-begin)
            count = max(0, finish-max(cursor, begin))
            if not count:
                return True
            data = frame.to_ndarray().tobytes()
            data = data[skip*self.sample_bytes:(skip+count)*self.sample_bytes]
            data = audio_fades(data,cursor-round(job.origin*rate),rate,self.sample_format,job.effects)
            if not self.put(job, data):
                return False
            cursor = finish
            return True

        with av.open(job.path) as container:
            if not container.streams.audio:
                silence(end)
                return
            stream = container.streams.audio[0]
            timeline = job.audio_timeline or audio_sample_timeline(job.path,lambda:self.stale(job))
            if self.stale(job):
                return
            anchors = dict(zip(timeline['pts'],timeline['sample_positions']))
            target = Fraction(str(job.origin + job.position))
            container.seek(max(0, int(target / stream.time_base)), stream=stream, backward=True)
            resampler = av.AudioResampler(format=self.sample_format, layout='stereo', rate=rate)
            for frame in container.decode(stream):
                if self.stale(job):
                    return
                # Normalize before resampling, so the output clock advances by
                # samples rather than the rounded packet timestamps.
                if frame.pts not in anchors:
                    raise ValueError('Audio timestamp not found in the sample index.')
                frame.pts = anchors[frame.pts]
                frame.time_base = Fraction(1,timeline['rate'])
                for converted in resampler.resample(frame):
                    if not samples(converted):
                        return
                if cursor >= end:
                    return
            for frame in resampler.resample(None):
                if not samples(frame):
                    return
            silence(end)

    def _project_audio(self,job):
        if any(s.cross_in or s.cross_out for s in job.effects):
            self._mix_audio(job)
            return
        rate = self.rate
        cursor = round(job.position*rate)
        limit = round(job.duration*rate)
        def push(data):
            nonlocal cursor
            data = data[:max(0,limit-cursor)*self.sample_bytes]
            if not data: return True
            rendered = audio_fades(data,cursor,rate,self.sample_format,job.effects)
            if not self.put(job,rendered): return False
            cursor += len(data)//self.sample_bytes
            return True
        for start,end,part in self._intervals(job):
            finish = min(limit,round(end*rate))
            if finish<=cursor: continue
            if part is None:
                while cursor<finish:
                    if not push(bytes(min(4096,finish-cursor)*self.sample_bytes)): return
                continue
            source_start = part.source_start+(cursor-round(part.start*rate))/rate
            count = finish-cursor
            child = Decoder('audio',rate,self.sample_format,self.sample_bytes//2)
            child.request(1,replace(part_job(job,part),generation=1,position=source_start,duration=source_start+count/rate,effects=(),parts=None))
            try:
                while cursor<finish and not self.stale(job):
                    data = child.take_audio(min(65536,(finish-cursor)*self.sample_bytes))
                    if data:
                        if not push(data): return
                    queued,_,eof,error = child.status()
                    if error: raise RuntimeError(error)
                    if eof and not queued: break
                    if not data:
                        with self.condition: self.condition.wait(.003)
                while cursor<finish and not self.stale(job):
                    if not push(bytes(min(4096,finish-cursor)*self.sample_bytes)): return
            finally:
                child.close()
                child.thread.join(timeout=2)
            if self.stale(job): return

    def _composite_video(self,job):
        """At most two live source readers and one lookahead frame per reader."""
        spans = {s.clip_id:s for s in job.effects}
        emitted = 0
        for start,end,active in intervals(job.parts,job.duration):
            if end<=job.position+1e-9: continue
            readers = []
            try:
                for part in active:
                    if job.sources and not source_for(job.sources,part.first_frame).has_video: continue
                    local = part_job(job,part)
                    container = av.open(local.path)
                    readers.append([part,container,None,None,None,local.origin])
                    stream = container.streams.video[0]; configure(stream)
                    target = part.source_start+max(start,job.position)-part.start+local.origin
                    container.seek(max(0,int(Fraction(str(target))/stream.time_base)),stream=stream,backward=True)
                    readers[-1][2] = iter(container.decode(stream))
                for stamp in interval_frames(active,job.source_times,max(start,job.position),end,job.fps):
                    if stamp<job.position-1e-9: continue
                    if self.stale(job): return
                    rgb = None
                    for reader in readers:
                        part,container,frames,current,following,origin = reader
                        target = part.source_start+stamp-part.start
                        while following is None or following[0]<=target+1e-9:
                            if following is not None: current = following
                            if self.stale(job): return
                            frame = next(frames,None)
                            if frame is None:
                                following = (float('inf'),None)
                                break
                            following = (float(frame.pts*frame.time_base)-origin,source_rgb(frame,job,part))
                        reader[3],reader[4] = current,following
                        if current is None: continue
                        span = spans[part.clip_id]
                        gain = video_gain(stamp,span)*cross_gain(stamp,span)
                        contribution = current[1] if len(readers)==1 and gain==1. else current[1].astype(np.float32)*gain
                        rgb = contribution if rgb is None else rgb+contribution
                    if rgb is None: rgb = np.zeros((job.height,job.width,3),dtype=np.uint8)
                    elif rgb.dtype!=np.uint8: rgb = np.clip(np.rint(rgb),0,255).astype(np.uint8)
                    image = QImage(rgb.data,rgb.shape[1],rgb.shape[0],rgb.strides[0],QImage.Format.Format_RGB888).copy()
                    if not self.put(job,(job.generation,stamp,image)): return
                    emitted += 1
                    if not job.playing and emitted>=5: return
            finally:
                for reader in readers: reader[1].close()

    def _mix_audio(self,job):
        """Mix bounded float PCM blocks; quantize int16 once after summing."""
        rate = self.rate
        spans = {s.clip_id:s for s in job.effects}
        cursor,limit = round(job.position*rate),round(job.duration*rate)
        for start,end,active in intervals(job.parts,job.duration):
            finish = min(limit,round(end*rate))
            if finish<=cursor: continue
            children = []
            try:
                for part in active:
                    source = part.source_start+(cursor-round(part.start*rate))/rate
                    child = Decoder('audio',rate,'flt',4)
                    children.append((part,child))
                    child.request(1,replace(part_job(job,part),generation=1,position=source,duration=source+(finish-cursor)/rate,effects=(),parts=None))
                while cursor<finish and not self.stale(job):
                    count = min(4096,finish-cursor)
                    mixed = np.zeros((count,2),dtype=np.float64)
                    for part,child in children:
                        data = bytearray()
                        while len(data)<count*8 and not self.stale(job):
                            chunk = child.take_audio(count*8-len(data))
                            data.extend(chunk)
                            queued,_,eof,error = child.status()
                            if error: raise RuntimeError(error)
                            if eof and not queued: break
                            if not chunk:
                                with self.condition: self.condition.wait(.003)
                        if self.stale(job): return
                        data.extend(bytes(count*8-len(data)))
                        span = spans[part.clip_id]
                        faded = audio_fades(data,cursor,rate,'flt',(span,))
                        positions = np.arange(cursor,cursor+count,dtype=np.int64)
                        gains = np.ones(count,dtype=np.float64)
                        if span.cross_in:
                            gains *= np.clip((positions-round(span.start*rate))/max(1,round((span.start+span.cross_in)*rate)-round(span.start*rate)),0,1)
                        if span.cross_out:
                            gains *= np.clip((round(span.end*rate)-positions)/max(1,round(span.end*rate)-round((span.end-span.cross_out)*rate)),0,1)
                        mixed += np.frombuffer(faded,dtype='<f4').reshape(-1,2)*gains[:,None]
                    if self.sample_format=='s16':
                        data = np.clip(np.rint(mixed*32768),-32768,32767).astype('<i2').tobytes()
                    else: data = mixed.astype('<f4').tobytes()
                    if not self.put(job,data): return
                    cursor += count
            finally:
                for _,child in children: child.close()
                for _,child in children: child.thread.join(timeout=2)
            if self.stale(job): return


def inspect_and_index(path, cancelled, publish):
    """Metadata first; exact PTS index later. Cached by path, size and mtime."""
    try:
        source = Path(path)
        stat = source.stat()
        key = hashlib.sha256(f'{source.resolve()}:{stat.st_size}:{stat.st_mtime_ns}'.encode()).hexdigest()
        cache = INDEX_DIR / f'{key}.json'
        cached = None
        if cache.exists():
            try:
                cached = json.loads(cache.read_text(encoding='utf-8'))
            except (ValueError,OSError):
                pass
        with av.open(str(source)) as container:
            if not container.streams.video:
                if not container.streams.audio: raise ValueError('The file has no video or audio stream.')
                audio = audio_sample_timeline(str(source),cancelled.is_set)
                if cancelled.is_set(): return
                if not audio or not audio['pts']: raise ValueError('No decodable audio samples found.')
                if any(b<=a for a,b in zip(audio['sample_positions'],audio['sample_positions'][1:])):
                    raise ValueError('Audio sample anchors are not increasing: this source is not supported.')
                rate = audio['rate']
                origin = audio['sample_positions'][0]/rate
                metadata = {'path':str(source),'name':source.name,'origin':origin,
                            'duration':audio['end_sample']/rate,'fps':30.,'width':640,'height':360,
                            'has_video':False,'has_audio':True,'audio_timeline':audio,'time_base':str(Fraction(1,rate))}
                publish('metadata',metadata)
                publish('index',{'time_base':str(Fraction(1,rate)),'pts':audio['sample_positions'],'audio':audio})
                return
            video = container.streams.video[0]
            origin = float(video.start_time * video.time_base) if video.start_time is not None else 0.
            duration = float(container.duration / av.time_base) if container.duration else 0.
            rate = float(video.average_rate or 30)
            metadata = {'path':str(source), 'name':source.name, 'origin':origin,
                        'duration':duration, 'fps':rate, 'width':video.width, 'height':video.height,
                        'has_video':True,'aspect':str(video.sample_aspect_ratio or Fraction(1)),
                        'has_audio':bool(container.streams.audio), 'time_base':str(video.time_base)}
            audio = cached.get('audio') if isinstance(cached,dict) else None
            if metadata['has_audio'] and audio is None:
                audio = audio_sample_timeline(str(source),cancelled.is_set)
            if cancelled.is_set():
                return
            metadata['audio_timeline'] = audio
            publish('metadata', metadata)
            if cancelled.is_set():
                return
            if cached:
                try:
                    index = cached
                    if index['time_base'] == str(video.time_base) and index['pts']:
                        index['audio'] = audio
                        temporary = cache.with_suffix('.tmp')
                        temporary.write_text(json.dumps(index),encoding='utf-8')
                        temporary.replace(cache)
                        publish('index', index)
                        return
                except (ValueError, KeyError, OSError):
                    pass
            configure(video)
            pts = []
            for frame in container.decode(video):
                if cancelled.is_set():
                    return
                if frame.pts is not None:
                    pts.append(frame.pts)
            if not pts:
                raise ValueError('No decodable frames found.')
            if any(b <= a for a,b in zip(pts,pts[1:])):
                raise ValueError('Video timestamps are not increasing: this source is not supported by the prototype.')
            index = {'time_base':str(video.time_base), 'pts':pts, 'audio':audio}
            INDEX_DIR.mkdir(parents=True, exist_ok=True)
            temporary = cache.with_suffix('.tmp')
            temporary.write_text(json.dumps(index),encoding='utf-8')
            temporary.replace(cache)
            publish('index', index)
    except Exception as exc:
        if not cancelled.is_set():
            publish('error', str(exc))
