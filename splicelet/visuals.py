"""Source-only timeline previews. Workers never depend on the editing model."""
import hashlib
import math
from pathlib import Path
import uuid

import av
import numpy as np

from .runtime import ARTIFACTS


def peak_levels(peaks):
    levels = [peaks]
    while len(levels[-1]) > 1:
        previous = levels[-1]
        if len(previous) % 2:
            previous = np.concatenate((previous, np.zeros((1, 2), np.float32)))
        paired = previous.reshape(-1, 2, 2)
        levels.append(np.column_stack((paired[:, :, 0].min(axis=1), paired[:, :, 1].max(axis=1))))
    return levels


def build_visuals(path, origin, duration, audio_timeline, cancelled, publish):
    """Cancellable, bounded source cache; failure leaves editing/playback available."""
    try:
        source = Path(path)
        stat = source.stat()
        key = hashlib.sha256(f'v1:{source.resolve()}:{stat.st_size}:{stat.st_mtime_ns}'.encode()).hexdigest()
        folder = ARTIFACTS/'visuals'/key
        folder.mkdir(parents=True, exist_ok=True)
        if audio_timeline:
            rate = audio_timeline['rate']
            # Usually 1 ms; bound the base level to two million bins for long source.
            stride = max(1, math.ceil(rate*.001), math.ceil(duration*rate/2_000_000))
            count = max(1, math.ceil(duration*rate/stride))
            cache = folder/'peaks.npy'
            peaks = None
            if cache.exists():
                try:
                    candidate = np.load(cache, allow_pickle=False)
                    if candidate.shape == (count, 2) and candidate.dtype == np.float32:
                        peaks = candidate
                except (OSError, ValueError):
                    pass
            if peaks is None:
                peaks = np.zeros((count, 2), np.float32)
                anchors = dict(zip(audio_timeline['pts'], audio_timeline['sample_positions']))
                with av.open(path) as container:
                    resampler = av.AudioResampler(format='fltp', layout='stereo', rate=rate)
                    for frame in container.decode(audio=0):
                        if cancelled.is_set(): return
                        begin = anchors[frame.pts] - round(origin*rate)
                        for converted in resampler.resample(frame):
                            values = converted.to_ndarray()
                            left, right = max(0, -begin), min(converted.samples, count*stride-begin)
                            if right > left:
                                values = values[:, left:right]
                                indices = (np.arange(begin+left, begin+right)//stride).astype(np.intp)
                                boundaries = np.r_[0, np.flatnonzero(np.diff(indices))+1]
                                low = np.minimum.reduceat(values.min(axis=0), boundaries)
                                high = np.maximum.reduceat(values.max(axis=0), boundaries)
                                bins = indices[boundaries]
                                peaks[bins, 0] = np.minimum(peaks[bins, 0], low)
                                peaks[bins, 1] = np.maximum(peaks[bins, 1], high)
                            begin += converted.samples
                if cancelled.is_set(): return
                temporary = folder/f'peaks-{uuid.uuid4().hex}.npy'
                try:
                    np.save(temporary, peaks, allow_pickle=False)
                    temporary.replace(cache)
                finally:
                    temporary.unlink(missing_ok=True)
            if cancelled.is_set(): return
            publish('waveform', (stride/rate, peak_levels(peaks)))
        cache = folder/'thumbs.npz'
        times = files = None
        if cache.exists():
            try:
                with np.load(cache, allow_pickle=False) as data:
                    times = data['times'].tolist()
                    files = data['files'].tolist()
                if not times or len(times) != len(files) or not all((folder/f).is_file() for f in files):
                    times = files = None
            except (OSError, ValueError, KeyError):
                times = files = None
        if times is None:
            times, files = [], []
            interval = max(2., duration/599)
            with av.open(path) as container:
                if not container.streams.video:
                    if not cancelled.is_set(): publish('thumbnails',([],[]))
                    return
                stream = container.streams.video[0]
                stream.codec_context.thread_count = 1
                stream.codec_context.skip_frame = 'NONKEY'
                for frame in container.decode(stream):
                    if cancelled.is_set(): return
                    if frame.pts is None: continue
                    stamp = float(frame.pts*frame.time_base)-origin
                    if times and stamp < times[-1]+interval: continue
                    if len(times) >= 600: break
                    # QImage writes JPEG without introducing Pillow as a dependency.
                    from PySide6.QtGui import QImage
                    scale = min(160/frame.width, 90/frame.height)
                    scaled = frame.reformat(width=max(1, round(frame.width*scale)), height=max(1, round(frame.height*scale)), format='rgb24')
                    pixels = scaled.to_ndarray()
                    image = QImage(pixels.data, pixels.shape[1], pixels.shape[0], pixels.strides[0], QImage.Format.Format_RGB888)
                    name = f'thumb-{len(times):04d}.jpg'
                    temporary = folder/f'{uuid.uuid4().hex}.jpg'
                    try:
                        if not image.save(str(temporary), 'JPEG', 65):
                            raise OSError('Cannot save timeline thumbnail.')
                        temporary.replace(folder/name)
                    finally:
                        temporary.unlink(missing_ok=True)
                    times.append(stamp); files.append(name)
            if cancelled.is_set(): return
            temporary = folder/f'thumbs-{uuid.uuid4().hex}.npz'
            try:
                np.savez(temporary, times=times, files=files)
                temporary.replace(cache)
            finally:
                temporary.unlink(missing_ok=True)
        if not cancelled.is_set():
            publish('thumbnails', (times, [str(folder/f) for f in files]))
    except Exception as exc:
        if not cancelled.is_set(): publish('visuals-error', str(exc))


def waveform_columns(levels, step, pieces, start, end, columns):
    """Aggregate visible source ranges; never sample over a deleted join range."""
    columns = min(4096, max(0, columns))
    if not columns or end <= start: return []
    result = np.zeros((columns, 2), np.float32)
    width = (end-start)/columns
    for project_start, project_end, source_start in pieces:
        a, b = max(start, project_start), min(end, project_end)
        if b <= a: continue
        first, last = max(0, int((a-start)/width)), min(columns, math.ceil((b-start)/width))
        level = min(len(levels)-1, max(0, int(math.floor(math.log2(max(1, width/step))))))
        peaks, factor = levels[level], 2**level
        for i in range(first, last):
            lo = source_start+max(a, start+i*width)-project_start
            hi = source_start+min(b, start+(i+1)*width)-project_start
            x = max(0, math.floor(lo/step+1e-7))
            y = min(len(levels[0]), math.ceil(hi/step-1e-7))
            if y > x:
                # Only whole coarse bins belong to this range. Use base peaks
                # at either edge so an adjacent deleted transient cannot leak in.
                first_full, end_full = math.ceil(x/factor), y//factor
                ranges = [levels[0][x:min(y, first_full*factor)]]
                if end_full > first_full:
                    ranges.append(peaks[first_full:end_full])
                ranges.append(levels[0][max(x, end_full*factor):y])
                for values in ranges:
                    if len(values):
                        result[i, 0] = min(result[i, 0], float(values[:, 0].min()))
                        result[i, 1] = max(result[i, 1], float(values[:, 1].max()))
    return result.tolist()


def source_at(pieces, position):
    for start, end, source in pieces:
        if start <= position < end: return source+position-start
    return None
