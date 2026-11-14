"""Read-only, bounded sample-peak monitoring of device-bound preview PCM."""
from collections import deque
import math

import numpy as np


class AudioMeter:
    def __init__(self):
        self.reset()

    def reset(self):
        self.blocks = deque(maxlen=256)
        self.frames = 0
        self.tail = b''
        self.last_time = 0.
        self.levels = [-60.,-60.]
        self.peaks = [-60.,-60.]
        self.hold_until = [0.,0.]

    def append(self,data,sample_format):
        # Partial device writes may end within a sample or stereo frame.
        dtype = np.dtype('<f4' if sample_format=='flt' else '<i2')
        frame_bytes = 2*dtype.itemsize
        data = self.tail+data
        end = len(data)-len(data)%frame_bytes
        self.tail = data[end:]
        samples = np.frombuffer(data[:end],dtype=dtype).reshape(-1,2)
        for start in range(0,len(samples),1024):
            chunk = samples[start:start+1024]
            peaks = np.max(np.abs(chunk.astype(np.float32)),axis=0)
            if sample_format!='flt': peaks /= 32768.
            levels = tuple(max(-60.,min(0.,20*math.log10(float(v)))) if math.isfinite(float(v)) and v>0 else -60. for v in peaks)
            self.frames += len(chunk)
            self.blocks.append((self.frames/48000.,levels))

    def update(self,seconds):
        elapsed = max(0.,seconds-self.last_time)
        self.last_time = seconds
        incoming = [-60.,-60.]
        while self.blocks and self.blocks[0][0]<=seconds:
            _,values = self.blocks.popleft()
            incoming = [max(a,b) for a,b in zip(incoming,values)]
        for channel in range(2):
            self.levels[channel] = max(incoming[channel],self.levels[channel]-36*elapsed,-60.)
            if incoming[channel]>=self.peaks[channel] and incoming[channel]>-60.:
                self.peaks[channel] = incoming[channel]
                self.hold_until[channel] = seconds+.6
            elif seconds>self.hold_until[channel]:
                self.peaks[channel] = max(self.levels[channel],self.peaks[channel]-24*elapsed,-60.)
