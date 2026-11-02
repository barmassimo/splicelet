# Real screen-recording probe

> Historical feasibility report. Measurements and proposed next steps describe
> the initial probes, not the current application. Paths below are relative to
> the repository root; generated reports and local media are not bundled.

Input: `media/2026-10-24_16-12-37.mkv`, approximately 104.5 MB, duration 4:57.1.
Progressive Full HD H.264, nominally 30 fps, SDR BT.709. Stereo 24-bit PCM audio
at 48 kHz. The environment matches the synthetic probes, with four CPU threads
for video decoding. This report describes the initial real-source probes before
the interactive preview was built.

## Results

All six checks in the final report passed. The original was opened read-only;
its size and modification time remained unchanged.

| Check | Result |
|---|---|
| Full sequential decoding | 8910 frames in approximately 11.1 s, including selected hashes; approximately 802 fps |
| PyAV seeking across the recording | 40/40 requests exactly matching sequential decoding in PTS and pixels |
| Seek/decode latency | Sourcen 152 ms; 95th percentile approximately 284 ms; maximum 310 ms |
| CPU frame conversion to RGB | Sourcen 1.6 ms; excludes GPU upload and screen presentation |
| Video cut from source | 150 frames verified by hash after lossless export |
| 24-bit audio cut | 240000 identical samples per channel, starting at sample 59217 |
| 5-second H.264/AAC MP4 | 150 frames; approximately 2.2 s to encode from the lossless reference |

Exact sample comparison applies to the PCM reference, not MP4 AAC audio.
The MP4 was checked for decodability and frame count; pixel checks apply to
the lossless output.

Sequential decoding is much faster than the source's 30 fps. This does not
establish future UI fluidity: the complete rendering, audio, clock and cache
path was not included. Timings are local measurements with uncontrolled
filesystem caching.

## Seeking and proxy comparison

The largest observed keyframe distance was 240 frames, approximately 8 s.
Verified seeks decoded up to 221 frames to reach their target. This is the
main seeking cost; converting a single frame is relatively inexpensive.

Comparison at ten matching positions between 2:00 and 2:15, including CPU
RGB conversion:

| Input | Sourcen | 95th percentile |
|---|---:|---:|
| Original 1920x1080 | 162 ms | 250 ms |
| Proxy 960x540, 15-frame GOP | 27 ms | 36 ms |

The proxy made seeking approximately six times faster in this probe.
Generating 15 seconds of proxy took approximately 2.3 s and produced 5.5 MB.
Both lower resolution and shorter GOP contribute; this is not an equal-quality
comparison. A shorter GOP can increase disk use: a proxy improves responsiveness
but is not guaranteed to be smaller than the original.

Recommendation from these measurements: optional background proxy generation
and a frame cache for nearby movements. Direct decoding is promising for normal
playback; proxies are particularly useful for scrubbing. Editing must reference
original timestamps and export must use originals. Proxy time mapping requires
explicit verification.

## Two timing characteristics

1. The last two frames are separated by 134 ms, from 296.933 to 297.067 s.
   Other intervals are 33/34 ms, consistent with 30 fps and a millisecond time
   base. The final gap adds approximately 100 ms. `duration × fps` suggests
   8913 frames, whereas 8910 were decoded. Actual timestamps must remain
   authoritative.
2. Audio has 14253056 samples per channel, lasting approximately 296.939 s;
   it ends approximately 162 ms before video. Audio timestamp/sample-count
   differences stay within 0.334 ms, compatible with container time resolution.
   This does not demonstrate progressive drift.

The proposed editor behavior was to hold the previous video frame until a new
one arrives and insert silence where audio is absent, without stretching the
source. These were rules to implement and compare between preview and export,
not corrections already applied to the original.

## Interpretation at the time of the probe

The data supported continuing with PyAV and FFmpeg without yet validating a
complete editing engine. The next prototype was to test a real A/V window,
audio clock, asynchronous seeking with cancellation of stale requests, bounded
caches and transitions between two clips. Device latency, A/V drift, GPU
rendering and playback transitions still required tests. Current usage is described in the [manual](../MANUAL.md).

Probe: `scripts/probe_real_source.py`; current commands are in the
[development guide](../DEVELOPMENT.md#optional-real-media-checks). Historical machine report:
`artifacts/real/report.json`. Extracts are in `artifacts/real`.
