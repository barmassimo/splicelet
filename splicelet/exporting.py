"""Export a frozen clip to a NEW path. Source files are read-only inputs."""
from dataclasses import dataclass, field, replace
from bisect import bisect_right
from fractions import Fraction
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
import av
import numpy as np

from PySide6.QtCore import QObject, Signal
from .source import Decoder, Job
from .effects import Fades, EffectSpan, effective_fades
from .runtime import ffmpeg_executable
from .composition import intervals
from .normalization import sample_peaks, normalization_gains, normalization_filter
from .sources import source_for, fit_geometry


@dataclass(frozen=True)
class ExportSpec:
    source: str
    start_frame: int
    end_frame: int
    start_pts: int
    end_pts: int
    time_base: Fraction
    origin: float
    audio_timeline: dict | None
    fades: Fades = field(default_factory=Fades)
    parts: tuple | None = None
    timeline_start: float | None = None
    timeline_end: float | None = None
    audio_parts: tuple | None = None
    audio_effects: tuple | None = None
    video_effects: tuple | None = None
    fps: float = 30.
    width: int = 640
    height: int = 360
    source_pts: tuple = ()
    normalize_audio: bool = False
    normalization_level: float = -1.
    normalize_channels_independently: bool = False
    sources: tuple = ()

    @property
    def start(self): return self.timeline_start if self.timeline_start is not None else float(self.start_pts*self.time_base)-self.origin
    @property
    def end(self): return self.timeline_end if self.timeline_end is not None else float(self.end_pts*self.time_base)-self.origin
    @property
    def duration(self): return self.end-self.start


def validate_destination(source,destination):
    if isinstance(source,(tuple,list)):
        results = [validate_destination(item,destination) for item in source]
        return results[0]
    source = Path(source).resolve(strict=True)
    destination = Path(destination).absolute()
    resolved = destination.resolve(strict=False)
    if os.path.normcase(str(source))==os.path.normcase(str(resolved)):
        raise ValueError('The original file cannot be used as the destination.')
    if os.path.lexists(destination):
        try:
            if os.path.samefile(source,destination):
                raise ValueError('The destination refers to the original file.')
        except OSError:
            pass
        raise ValueError('The destination file already exists. Choose a new name.')
    parent = destination.parent.resolve(strict=True)
    if not parent.is_dir(): raise ValueError('The destination folder does not exist.')
    if destination.suffix.lower()!='.mp4':
        raise ValueError('Choose a file name with the .mp4 extension.')
    return parent/destination.name


def piece_context(spec,part):
    if not spec.sources: return spec,part
    source = source_for(spec.sources,part.first_frame)
    return replace(spec,source=source.path,origin=source.virtual_origin,time_base=source.time_base,source_pts=source.pts),replace(part,first_frame=part.first_frame-source.first,end_frame=part.end_frame-source.first)


def fit_filter(spec,part):
    if not spec.sources: return ''
    source = source_for(spec.sources,part.first_frame)
    w,h,x,y = fit_geometry(source,spec.width,spec.height)
    rotation = {90:',transpose=clock',180:',hflip,vflip',270:',transpose=cclock'}.get(source.rotation,'')
    return rotation+f',scale={w}:{h}:flags=bilinear,setsar=1,pad={spec.width}:{spec.height}:{x}:{y}:black'


def input_paths(spec,parts):
    return [source_for(spec.sources,p.first_frame).path for p in parts] if spec.sources else [spec.source]*max(1,len(parts))


def source_paths(spec): return tuple(s.path for s in spec.sources) or (spec.source,)


def track_video_graph(spec):
    """Compose source PTS and black gaps on the project clock before windowing."""
    if any(s.cross_in or s.cross_out for s in spec.video_effects):
        return crossfade_video_graph(spec)
    parts = [p for p in spec.parts if p.end>spec.start+.000001 and p.start<spec.end-.000001]
    chains,labels = [],[]
    cursor = spec.start
    def black(start,end):
        label = f'g{len(labels)}'
        chains.append(f'color=c=black:s={spec.width}x{spec.height}:r={spec.fps:.12f}:d={end-start:.12f},settb=AVTB,setpts=PTS+{start:.12f}/TB[{label}]')
        labels.append(f'[{label}]')
    for i,part in enumerate(parts):
        if part.start>cursor+.000001: black(cursor,min(part.start,spec.end))
        if spec.sources and not source_for(spec.sources,part.first_frame).has_video:
            black(max(part.start,spec.start),min(part.end,spec.end)); cursor = part.end
            continue
        local,p = piece_context(spec,part)
        first = round(Fraction(str(part.source_start+local.origin))/local.time_base)
        last = round(Fraction(str(part.source_end+local.origin))/local.time_base)
        if local.source_pts:
            target = Fraction(str(part.source_start+local.origin+max(0.,spec.start-part.start)))/local.time_base
            frame = max(p.first_frame,bisect_right(local.source_pts,target)-1)
            first = local.source_pts[min(p.end_frame-1,frame)]
            limit = Fraction(str(part.source_start+local.origin+spec.end-part.start))/local.time_base
            last = min(last,math.ceil(limit-Fraction(1,1000000)))
        # Keep the frame covering the left edge even when independent lanes have
        # different PTS grids. Hold its remaining interval from output time zero.
        stamp = f'max(PTS-{part.source_start+local.origin:.12f}/TB+{part.start:.12f}/TB,{spec.start:.12f}/TB)'
        chains.append(f"[{i}:v:0]trim=start_pts={first}:end_pts={last},settb=AVTB,setpts='{stamp}'"+fit_filter(spec,part)+f'[p{i}]')
        labels.append(f'[p{i}]')
        cursor = part.end
    if cursor<spec.end-.000001: black(cursor,spec.end)
    if len(labels)==1:
        graph = ';'.join(chains)+';'+labels[0]+'null'
    else:
        graph = ';'.join(chains)+';'+''.join(labels)+f'interleave=nb_inputs={len(labels)}:duration=longest'
    for span in spec.video_effects:
        fade_in,fade_out = effective_fades(span.fades.video_in,span.fades.video_out,span.end-span.start)
        enable = f"enable='gte(t,{span.start:.12f})*lt(t,{span.end:.12f})'"
        if fade_in: graph += f',fade=t=in:st={span.start:.12f}:d={fade_in:.12f}:color=black:{enable}'
        if fade_out: graph += f',fade=t=out:st={span.end-fade_out:.12f}:d={fade_out:.12f}:color=black:{enable}'
    graph += f',trim=start={spec.start:.12f}:end={spec.end:.12f},setpts=PTS-{spec.start:.12f}/TB'
    return max(1,len(parts)),graph


def crossfade_video_graph(spec):
    """Original source frames outside transitions; lossless RGB mixes inside them."""
    parts = [p for p in spec.parts if p.end>spec.start+1e-9 and p.start<spec.end-1e-9]
    spans = {s.clip_id:s for s in spec.video_effects}
    if not spec.source_pts: raise ValueError('Crossfade export requires the source PTS index.')
    with av.open(spec.source) as source:
        aspect = Fraction(1) if spec.sources else source.streams.video[0].sample_aspect_ratio or Fraction(1)
    sar = f'setsar={aspect.numerator}/{aspect.denominator}'
    chains,labels = [],[]
    for start,end,active in intervals(spec.parts,spec.end):
        start,end = max(start,spec.start),min(end,spec.end)
        if end<=start+1e-9 or len(active)==2: continue
        label = f'r{len(labels)}'
        if not active or (spec.sources and not source_for(spec.sources,active[0].first_frame).has_video):
            chain = f'color=c=black:s={spec.width}x{spec.height}:r={spec.fps:.12f}:d={end-start:.12f},settb=AVTB,setpts=PTS+{start:.12f}/TB'
        else:
            part = active[0]
            index = parts.index(part)
            local,p = piece_context(spec,part)
            target = Fraction(str(part.source_start+local.origin+start-part.start))/local.time_base
            first = local.source_pts[max(p.first_frame,min(p.end_frame-1,bisect_right(local.source_pts,target)-1))]
            last = min(round(Fraction(str(part.source_end+local.origin))/local.time_base),
                       math.ceil(Fraction(str(part.source_start+local.origin+end-part.start))/local.time_base-Fraction(1,1000000)))
            stamp = f'max(PTS-{part.source_start+local.origin:.12f}/TB+{part.start:.12f}/TB,{start:.12f}/TB)'
            chain = f"[{index}:v:0]trim=start_pts={first}:end_pts={last},settb=AVTB,setpts='{stamp}'"+fit_filter(spec,part)
            span = spans[part.clip_id]
            fade_in,fade_out = effective_fades(span.fades.video_in,span.fades.video_out,span.end-span.start)
            if fade_in: chain += f',fade=t=in:st={span.start:.12f}:d={fade_in:.12f}:color=black'
            if fade_out: chain += f',fade=t=out:st={span.end-fade_out:.12f}:d={fade_out:.12f}:color=black'
        chains.append(chain+f',{sar}[{label}]'); labels.append(f'[{label}]')
    chains.append(f'[{max(1,len(parts))}:v:0]settb=AVTB,{sar},format=yuv420p[mix]'); labels.append('[mix]')
    graph = ';'.join(chains)+';'+''.join(labels)+f'interleave=nb_inputs={len(labels)}:duration=longest'
    graph += f',trim=start={spec.start:.12f}:end={spec.end:.12f},setpts=PTS-{spec.start:.12f}/TB'
    return max(1,len(parts)),graph


class ExportTask(QObject):
    updated = Signal(float,str)
    finished = Signal(str,str)

    def __init__(self,parent=None):
        super().__init__(parent)
        self.cancelled = threading.Event()
        self.finalize_lock = threading.Lock()
        self.thread = None

    def start(self,spec,destination):
        if self.thread and self.thread.is_alive(): raise RuntimeError('An export is already in progress.')
        destination = validate_destination(source_paths(spec),destination)
        self.cancelled.clear()
        self.thread = threading.Thread(target=self._run,args=(spec,destination),name='clip-export',daemon=True)
        self.thread.start()

    def cancel(self):
        with self.finalize_lock:
            self.cancelled.set()

    def _audio(self,spec,path):
        worker = Decoder('audio')
        worker.request(1,Job(1,spec.source,spec.start,spec.origin,spec.end,True,spec.audio_timeline,
                             spec.audio_effects if spec.audio_effects is not None else (EffectSpan(spec.start,spec.end,spec.fades),),
                             spec.audio_parts if spec.audio_parts is not None else spec.parts,sources=spec.sources))
        written = 0
        peaks = np.zeros(2,dtype=np.float64)
        last_update = 0.
        total = max(1,round(spec.end*48000)-round(spec.start*48000)) * 8
        try:
            with path.open('xb') as output:
                while not self.cancelled.is_set():
                    chunk = worker.take_audio(65536)
                    if chunk:
                        if spec.normalize_audio:
                            peaks = np.maximum(peaks,sample_peaks(chunk))
                        output.write(chunk)
                        written += len(chunk)
                        now = time.monotonic()
                        if now-last_update>=.1 or written>=total:
                            self.updated.emit(min(.1,.1*written/total),'Preparing audio…')
                            last_update = now
                    count,_,eof,error = worker.status()
                    if error: raise RuntimeError(error)
                    if eof and not count: break
                    if not chunk: self.cancelled.wait(.005)
        finally:
            worker.close()
            worker.thread.join(timeout=3)
        return peaks

    def _run(self,spec,destination):
        try:
            result,message = self._execute(spec,destination)
        except Exception as exc:
            result,message = 'error',str(exc)
        self.finished.emit(result,message)

    def _transition_video(self,spec,path):
        """Only overlapping frames take this lossless intermediate path."""
        worker = Decoder('video')
        times = tuple(float(p*spec.time_base)-spec.origin for p in spec.source_pts)
        try:
            with av.open(str(path),'w',format='nut') as output:
                stream = output.add_stream('ffv1',rate=Fraction(str(spec.fps)))
                stream.width,stream.height = spec.width,spec.height
                stream.pix_fmt = 'bgr0'
                stream.time_base = Fraction(1,1000000)
                stream.codec_context.time_base = stream.time_base
                generation = 0
                for start,end,active in intervals(spec.parts,spec.end):
                    start,end = max(start,spec.start),min(end,spec.end)
                    if len(active)!=2 or end<=start+1e-9: continue
                    generation += 1
                    worker.request(generation,Job(generation,spec.source,start,spec.origin,end,True,
                                   effects=spec.video_effects,parts=spec.parts,fps=spec.fps,width=spec.width,height=spec.height,source_times=times,sources=spec.sources))
                    while not self.cancelled.is_set():
                        item = worker.take_video()
                        if item:
                            _,stamp,image = item
                            rgb = np.frombuffer(image.constBits(),dtype=np.uint8).reshape(image.height(),image.bytesPerLine())[:,:image.width()*3].reshape(image.height(),image.width(),3)
                            frame = av.VideoFrame.from_ndarray(rgb,format='rgb24')
                            frame.pts,frame.time_base = round(stamp*1000000),stream.time_base
                            for packet in stream.encode(frame): output.mux(packet)
                        count,_,eof,error = worker.status()
                        if error: raise RuntimeError(error)
                        if eof and not count: break
                        if not item: self.cancelled.wait(.003)
                    if self.cancelled.is_set(): return
                for packet in stream.encode(): output.mux(packet)
        finally:
            worker.close(); worker.thread.join(timeout=3)

    def _execute(self,spec,destination):
        directory = None
        process = None
        reader = None
        try:
            if (spec.parts is None and spec.end_frame<=spec.start_frame) or spec.duration<=0:
                raise ValueError('The clip is empty.')
            destination = validate_destination(source_paths(spec),destination)
            directory = Path(tempfile.mkdtemp(prefix='.video-export-',dir=destination.parent))
            rendered = directory/'render.mp4'
            audio_path = directory/'audio.f32le'
            transition_path = directory/'transitions.nut'
            crossfades = spec.video_effects is not None and any(s.cross_in or s.cross_out for s in spec.video_effects)
            # A window may be far from every transition in the project.
            crossfades = crossfades and any(len(active)==2 and end>spec.start and start<spec.end for start,end,active in intervals(spec.parts,spec.end))
            if not crossfades and spec.video_effects is not None:
                spec = replace(spec,video_effects=tuple(replace(s,cross_in=0.,cross_out=0.) for s in spec.video_effects))
            if crossfades:
                self.updated.emit(0.,'Preparing transitions…')
                self._transition_video(spec,transition_path)
            if spec.audio_timeline:
                peaks = self._audio(spec,audio_path)
            if self.cancelled.is_set():
                return 'cancelled','Export cancelled.'
            executable = ffmpeg_executable()
            command = [str(executable),'-hide_banner','-v','error','-nostats','-n','-copyts']
            input_count = len(spec.parts) if spec.parts is not None else 1
            if spec.video_effects is not None: input_count,track_filter = track_video_graph(spec)
            visible = [p for p in spec.parts if p.end>spec.start+.000001 and p.start<spec.end-.000001] if spec.parts is not None else []
            paths = input_paths(spec,visible) if spec.video_effects is not None else [spec.source]*input_count
            if not paths: paths = [spec.source]
            for path in paths:
                command += ['-threads','1']
                if spec.sources: command += ['-noautorotate']
                command += ['-i',path]
            if crossfades:
                command += ['-threads','1','-i',str(transition_path)]
                input_count += 1
            if spec.audio_timeline:
                command += ['-f','f32le','-ar','48000','-ac','2','-i',str(audio_path)]
            fade_in,fade_out = effective_fades(spec.fades.video_in,spec.fades.video_out,spec.duration)
            if spec.video_effects is not None:
                video_filter = track_filter
                fade_in,fade_out = 0.,0.
            elif spec.parts is not None:
                chains = []
                for i,part in enumerate(spec.parts):
                    first = round(Fraction(str(part.source_start+spec.origin))/spec.time_base)
                    last = round(Fraction(str(part.source_end+spec.origin))/spec.time_base)
                    offset = part.start-spec.start
                    chains.append(f'[{i}:v:0]trim=start_pts={first}:end_pts={last},settb=AVTB,setpts=PTS-{part.source_start+spec.origin:.12f}/TB+{offset:.12f}/TB[p{i}]')
                labels = ''.join(f'[p{i}]' for i in range(input_count))
                video_filter = ';'.join(chains)+';'+labels+f'interleave=nb_inputs={input_count}:duration=longest'
            else:
                video_filter = f'[0:v:0]trim=start_pts={spec.start_pts}:end_pts={spec.end_pts},setpts=PTS-{spec.start_pts}'
            if fade_in: video_filter += f',fade=t=in:st=0:d={fade_in:.9f}:color=black'
            if fade_out: video_filter += f',fade=t=out:st={max(0.,spec.duration-fade_out):.9f}:d={fade_out:.9f}:color=black'
            command += ['-filter_complex',video_filter+'[v]',
                        '-map','[v]']
            if spec.audio_timeline:
                command += ['-map',f'{input_count}:a:0','-c:a','aac','-b:a','320k']
                if spec.normalize_audio:
                    gains = normalization_gains(peaks,spec.normalization_level,spec.normalize_channels_independently)
                    command += ['-af',normalization_filter(gains)]
            else:
                command += ['-an']
            command += ['-c:v','libx264','-preset','veryfast','-crf','18','-pix_fmt','yuv420p','-threads','4',
                        '-fps_mode','vfr','-enc_time_base:v',f'{spec.time_base.numerator}:{spec.time_base.denominator}',
                        '-t',f'{spec.duration:.9f}','-movflags','+faststart','-stats_period','0.2','-progress','pipe:1',str(rendered)]
            self.updated.emit(.1,'Exporting MP4…')
            with (directory/'ffmpeg.log').open('wb') as errors:
                process = subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=errors,
                                           text=True,encoding='utf-8',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))

                def progress():
                    for line in process.stdout:
                        if line.startswith('out_time_us='):
                            try:
                                fraction = int(line.partition('=')[2])/1000000/spec.duration
                                self.updated.emit(min(.99,.1+.89*max(0.,fraction)),'Exporting MP4…')
                            except ValueError:
                                pass
                reader = threading.Thread(target=progress,name='export-progress',daemon=True)
                reader.start()
                cancel_time = None
                while process.poll() is None:
                    if self.cancelled.is_set():
                        if cancel_time is None:
                            cancel_time = time.monotonic()
                            try:
                                process.stdin.write('q\n')
                                process.stdin.flush()
                            except (OSError,ValueError): pass
                        elif time.monotonic()-cancel_time>4:
                            process.kill()
                        elif time.monotonic()-cancel_time>2:
                            process.terminate()
                    time.sleep(.025)
                reader.join(timeout=2)
            if self.cancelled.is_set():
                return 'cancelled','Export cancelled.'
            if process.returncode:
                raise RuntimeError((directory/'ffmpeg.log').read_text(errors='replace')[-4000:] or 'FFmpeg did not complete the export.')
            # Windows rename never replaces an existing destination, including
            # one created while rendering. Keep the temp file on the same volume.
            with self.finalize_lock:
                if self.cancelled.is_set():
                    return 'cancelled','Export cancelled.'
                if os.name=='nt':
                    os.rename(rendered,destination)
                else:
                    os.link(rendered,destination)
                    rendered.unlink()
            self.updated.emit(1.,'Completed')
            return 'success',f'Exported: {destination}'
        except Exception as exc:
            return 'error',str(exc)
        finally:
            if process is not None:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=3)
                for stream in (process.stdin,process.stdout):
                    if stream: stream.close()
            if directory is not None:
                resolved = directory.resolve(strict=True)
                if directory.is_symlink() or resolved.parent!=destination.parent.resolve(strict=True) or not resolved.name.startswith('.video-export-'):
                    raise RuntimeError('Unexpected temporary path: cleanup stopped.')
                shutil.rmtree(directory)

    def close(self):
        self.cancel()
        if self.thread: self.thread.join(timeout=6)
