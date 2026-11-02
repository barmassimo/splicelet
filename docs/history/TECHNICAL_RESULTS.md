# Initial technical probes — October 30, 2026

> Historical feasibility report. Measurements and proposed next steps describe
> the initial probes, not the current application. Paths below are relative to
> the repository root; generated reports and local media are not bundled.

Subsequent real-recording probes: [REAL_SOURCE_RESULTS.md](REAL_SOURCE_RESULTS.md).
This report describes the initial feasibility tests, before the interactive
preview and timeline were implemented.

## Outcome and environment

An isolated Conda environment was created in `.envs/video-tech` using prebuilt
conda-forge packages. All eight source checks passed. The separate Qt probe did
not meet exact-seeking requirements and did not validate video rendering.
These were component feasibility results, not a final engine choice or a
usable editing prototype.

Versions: Python 3.12.16, PySide6/Qt Multimedia 6.11.2, PyAV 19.0.2,
NumPy 2.5.4, FFmpeg 9.0.2. Exact packages: `environment-win-64.lock`.
`pyside6` alone lacked the required Qt Multimedia runtime; `qt6-multimedia`
was added. The existing `conda.exe` launcher returned a Windows error, whereas
Anaconda's Python running `python -m conda` worked. The base environment and
other environments were not modified.

## Measured correctness

| Check | Result |
|---|---|
| Synthetic sources | 12 s, 640x360, H.264 with B-frames; CFR 360 frames, VFR 300 frames |
| PyAV CFR seeking | 40/40 frames identical to sequential decoding by RGB hash |
| PyAV VFR seeking | 40/40 identical frames; varying PTS intervals confirmed |
| Video cut | 150/150 identical decoded frames in lossless output |
| PCM audio cut | 240000 samples per channel exactly matching the source range |
| Stereo crossfade | 12000 overlapping samples; linear mix error below 1 int16 unit |
| Video dissolve | 15 overlapping frames; expected duration and luminance verified |
| H.264/AAC MP4 | 150 frames; minimum per-frame PSNR 44.6 dB against reference |
| FFmpeg cancellation | Stopped through `q` in approximately 104 ms in this run |

The audio cut begins at sample 59217 (1.2336875 s), outside the 30 fps video
grid. Exact verification applies to PCM. AAC edge behavior after decoding in
different players was not established.

Recorded median PyAV seeking times were approximately 66 ms for CFR and 46 ms
for VFR. These are indicative measurements on small files with other probes
running concurrently. Some seeks decode 90 frames. They do not establish
HD/4K performance.

## Qt/QML probe

The experimental QMediaPlayer probe and its launcher have been retired. The
measurements below remain as historical evidence for the engine choice; the
current application uses PyAV for video and Qt Multimedia's QAudioSink for audio.

QML loaded and QMediaPlayer decoded the source. Seeks were requested while
paused. Each request waited for 150 ms without further frame events before
evaluating the last received frame timestamp.

| Requested, ms | Expected PTS, ms | Returned PTS, ms |
|---:|---:|---:|
| 1233 | 1233 | 1200 |
| 10000 | 10000 | 9967 |
| 500 | 500 | 467 |
| 11000 | 11000 | 10967 |
| 1234 | 1233 | 1233 |
| 10001 | 10000 | 10000 |
| 501 | 500 | 500 |
| 11001 | 11000 | 11000 |

The four other boundary requests (0, 2967, 3000, 6000 ms) were correct.
Overall: 8/12 correct cases; 4/8 exact boundary requests failed. This compares
sink timestamps, not Qt pixel hashes. The 1 ms offset shows boundary behavior
for this particular file/runtime; it is not a general fix for VFR, other codecs
or high frame rates. QMediaPlayer was not accepted as the exact-seeking engine.

The offscreen QML capture with software rendering contained only the window
background, so video rendering was not validated. Timers also showed startup
delay, but this probe does not measure a real timeline's responsiveness. No
audio output was activated. The probe deliberately returns failure to preserve
the unmet requirement in its report.

## GES and MLT

The consulted conda-forge Windows/noarch metadata contained GStreamer and
PyGObject, but no packages named `gst-editing-services`, `ges`, `mlt` or `mlt7`.
Inventory: `artifacts/engine-package-inventory.json`.
GES/MLT were not installed or run. Evaluation would require checking another
local binary distribution, including bindings and plugins. Missing package
names do not prove that these engines cannot be used on Windows.

## Interpretation at the time of the probes

PyAV + FFmpeg was a viable basis for precise source access and offline
rendering. Audio clocks, playback mixing, A/V synchronization and real-time
composition had not been verified; PyAV alone was not a complete preview
engine. The proposed next test was a real window with two clips, clocked audio,
seeking and crossfades, followed by HD/4K sources, bounded queues and drift
measurements. GES remained an option if a local runtime outside Conda was
acceptable. Current usage is documented in the [manual](../MANUAL.md).

## Reproduction

Instructions: [development guide](../DEVELOPMENT.md). Machine reports: `artifacts/report.json`,
`artifacts/qt-report.json`, `artifacts/qt-launch-report.json`.
Demonstration MP4: `artifacts/cut.mp4`.
