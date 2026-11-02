"""Immutable linear fade envelopes shared by preview and export."""
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class Fades:
    audio_in: float = 0.
    audio_out: float = 0.
    video_in: float = 0.
    video_out: float = 0.


@dataclass(frozen=True)
class EffectSpan:
    start: float
    end: float
    fades: Fades
    cross_in: float = 0.
    cross_out: float = 0.
    clip_id: int = -1


def cross_gain(position,span):
    gain = 1.
    if span.cross_in: gain *= min(1.,max(0.,(position-span.start)/span.cross_in))
    if span.cross_out: gain *= min(1.,max(0.,(span.end-position)/span.cross_out))
    return gain


def effective_fades(fade_in,fade_out,duration):
    return min(fade_in,max(0.,duration)),min(fade_out,max(0.,duration))


def video_gain(position,span):
    duration = span.end-span.start
    fade_in,fade_out = effective_fades(span.fades.video_in,span.fades.video_out,duration)
    relative = position-span.start
    gain = 1.
    if fade_in: gain *= min(1.,max(0.,relative/fade_in))
    if fade_out: gain *= min(1.,max(0.,(duration-relative)/fade_out))
    return gain


def audio_fades(data,first_sample,rate,sample_format,spans):
    """first_sample is on the project clock, independent of a playback seek."""
    if not spans or not any(s.fades.audio_in or s.fades.audio_out for s in spans):
        return data
    dtype = np.dtype('<f4' if sample_format=='flt' else '<i2')
    samples = np.frombuffer(data,dtype=dtype).reshape(-1,2)
    last_sample = first_sample+len(samples)
    gains = np.ones(len(samples),dtype=np.float64)
    changed = False
    for span in spans:
        start,end = round(span.start*rate),round(span.end*rate)
        a,b = max(start,first_sample),min(end,last_sample)
        if a>=b: continue
        fade_in,fade_out = effective_fades(span.fades.audio_in,span.fades.audio_out,span.end-span.start)
        if not fade_in and not fade_out: continue
        indices = np.arange(a,b,dtype=np.int64)
        gain = np.ones(b-a,dtype=np.float64)
        if fade_in: gain *= np.clip((indices-start)/max(1,round(fade_in*rate)),0,1)
        if fade_out: gain *= np.clip((end-indices)/max(1,round(fade_out*rate)),0,1)
        gains[a-first_sample:b-first_sample] = gain
        changed = True
    if not changed: return data
    result = samples.astype(np.float64)*gains[:,None]
    if sample_format=='s16': result = np.rint(result)
    return result.astype(dtype).tobytes()
