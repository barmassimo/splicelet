"""Constant sample-peak gain, matching video_audio_tools' normalization."""
import math

import numpy as np


def sample_peaks(chunk):
    samples = np.frombuffer(chunk,dtype='<f4').reshape(-1,2)
    if not np.isfinite(samples).all():
        raise ValueError('Audio contains non-finite samples.')
    return np.max(np.abs(samples.astype(np.float64)),axis=0)


def normalization_gains(peaks,level,independent=False):
    if not math.isfinite(level) or level>0:
        raise ValueError('Normalization level must be a finite number less than or equal to 0 dBFS.')
    target = min(level,-.0001)
    if not independent: peaks = (max(peaks),)
    # The reference uses astats' six-decimal dB measurement and volume argument.
    return tuple(0. if peak==0 else round(target-round(20*math.log10(peak),6),6) for peak in peaks)


def normalization_filter(gains):
    if len(gains)==1:
        return f'volume={gains[0]:.6f}dB:precision=double'
    return ('aformat=sample_fmts=dbl,channelsplit=channel_layout=stereo[nl][nr];'
            f'[nl]volume={gains[0]:.6f}dB:precision=double[nlg];'
            f'[nr]volume={gains[1]:.6f}dB:precision=double[nrg];'
            '[nlg][nrg]join=inputs=2:channel_layout=stereo:map=0.0-FL|1.0-FR')
