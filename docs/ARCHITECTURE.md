# Architecture

Splicelet is a Windows-only local editor built with Python, PySide6/QML, PyAV,
NumPy and FFmpeg. It prioritizes responsive timeline editing, source-timestamp
accuracy and unchanged originals. It has one video lane and one audio lane,
globally linked by default, rather than a general multitrack compositor.

This document describes the current design and its constraints. Usage belongs
in the [manual](MANUAL.md), build/check instructions in the
[development guide](DEVELOPMENT.md), and version history in the
[changelog](CHANGELOG.md). Development rules are in [AGENTS.md](../AGENTS.md).

## Components and data flow

Paths in this table are relative to `splicelet/` unless stated otherwise.

| Component | Responsibility |
|---|---|
| `__main__.py` | Qt/QML startup, locale, image provider, keyboard filter and shutdown |
| `Main.qml`, `PanelMenu.qml`, `Theme.qml` | Workspace, inline menus, shared actions, dialogs, transport and persisted appearance |
| `Timeline.qml` | Ruler, selection, drag/trim, snapping, gaps, zoom/pan and timeline visuals |
| `ClipProperties.qml`, `FadeControl.qml`, `SpliceletButton.qml` | Properties and reusable controls |
| `controller.py` | `Preview` QObject coordinates models, workers, audio sink, frame cache and export; `FrameProvider` supplies QImages |
| `editing.py` | Qt-independent `Clip`/`Part`, `Clips`, exact source mapping, reserves, selection and edit snapshots |
| `tracks.py` | Two-lane coordinator, global link mode, active lane and atomic history |
| `sources.py` | Immutable source catalog, virtual coordinates and common fit geometry |
| `source.py` | PyAV metadata/indexing, cancellable video/audio decoder workers and index cache |
| `effects.py`, `composition.py` | Shared linear envelopes, sample gain, interval sweep and source-PTS overlap composition |
| `visuals.py` | Background waveform peaks, sparse thumbnails, disk caches and visible-range aggregation |
| `project.py` | Validated versioned JSON, source identity and atomic project saves |
| `exporting.py`, `normalization.py` | Immutable export specification, background rendering, sample-peak gain, cancellation and safe publication |
| `runtime.py` | Development/frozen FFmpeg location and writable artifacts root |
| `smoke.py`, root `scripts/probe_*.py` | Actual-window and focused model/decoder/export checks |
| Root `scripts/test_fixture.py`, `scripts/run_tests.py` | Validated generated integration media and sequential suite runner with per-process logs |

QML sends actions to `Preview`; the independent edit model produces source/project
parts and effects. Decoder jobs and export specifications snapshot these values,
including the source catalog. Preview and export interpret the same ranges and
fade definitions. Qt Multimedia supplies `QAudioSink`; `QMediaPlayer` is not the
preview engine. Live imports use PyAV, rather than an FFprobe subprocess.

## Time and source model

- Decoded PTS and rational time bases define source frame edges. Never infer
  exact frames or cuts from `duration * fps`. Source audio has PTS-to-sample
  anchors; supported timestamp-rounding corrections precede resampling while
  larger discontinuities remain meaningful. Output is stereo 48 kHz.
- `Clips` uses `Fraction` for source edges and clip starts. Pieces are half-open
  source-index ranges `[first, end)`. An append-only virtual grid joins metadata
  indexes, not media. Each immutable `Source` retains its file, offset, PTS/time
  base, timestamp origin and audio index. `parts()` splits at source boundaries.
- `Clip.start` is an absolute project coordinate. `Clips.origin` can be negative
  after prepending a duplicate. Displayed time is absolute time minus origin;
  project duration is `extent - origin`. Neither is the container timestamp origin.
- Joins retain non-contiguous/reordered pieces and edited trim reserves.
  Re-extending a joined clip must not restore deliberately deleted source ranges.
  Video-derived edits use actual video edges; audio-only edits use decoded
  audio-block/sample-anchor boundaries, not individual samples.
- `Tracks` owns a `Clips` per lane. Linked changes copy the edited lane to its
  partner atomically; unlinked edits remain local. Frame schedules include black
  gaps. QML/worker float seconds and FFmpeg AVTB boundaries mean the complete
  pipeline is not rational end to end or submicrosecond-exact.
- Stable IDs track clips/selection. History snapshots include both lanes, link
  mode, active lane and ID counters. New edits invalidate redo. Imported library
  entries remain outside timeline Undo. Selected length is the union of selected
  intervals; export selection uses their outer bounds instead.

The first imported video fixes the canvas even if unused. Audio-only projects
provisionally use 640×360. Later videos fit by display aspect with bilinear scaling,
square output pixels and black padding. Shared geometry serves preview/export.
Each source retains its cadence; the export encoder uses a common time base,
falling back to microseconds if its denominator exceeds FFmpeg's integer limit.

## Editing invariants

Delete leaves space; only explicit gap removal shifts later clips. Unlinked gap
closure affects its lane without truncating the other lane. Moves and duplication
never ripple outsiders. Group movement requires consecutive selected timeline
indices and preserves internal gaps. Trims respect source reserves and retain at
least one frame. Added edge space affects the shared project bounds.

Partial overlaps of two consecutive clips derive linear crossfades from positions,
without storing separate transition durations. Nesting, triple overlaps and cuts
inside transitions are rejected atomically. `Part.clip_id` and `EffectSpan.clip_id`
associate contributions with their own fades. Manual linear fade-in/out envelopes
multiply and are applied before crossfade weights. Linked lanes transition
together; unlinked lanes independently. There is no automatic audio declicking.

Timeline input layers keep both overlap trim edges reachable and selected bodies
draggable. Use `WheelHandler` for wheel input: a full-area no-button `MouseArea`
previously overrode trim cursor shapes. Snapping is pixel-based with Alt bypass.

## Background work and playback

Indexing, decoding, visual preparation and export run off the GUI thread using
native/vectorized PyAV/FFmpeg/NumPy work. Imports are sequential cancellable jobs.
Generation IDs discard stale results; failed imports preserve the current montage.
Each decoder has one pending job, video output is bounded to six frames, audio
backpressure begins around 0.5 seconds of PCM, and the image cache targets 64 MiB
while retaining at least one image. Indexes persist in `artifacts/index`, keyed
by source path, size and modification time.

Video converts on CPU to RGB/QImage and displays through a Qt Quick image provider.
There is no implemented hardware decoding, zero-copy texture or GPU compositor.
Overlap composition merges actual PTS from both sources, including a held frame
at an off-grid boundary; it uses at most two readers with one lookahead each.
Audio mixes bounded 4096-sample float blocks from at most two child decoders;
int16 fallback is quantized after mixing. Manual video fades apply within overlap
composition; QML opacity is unity there. Fade edits invalidate cached composites.

After buffering, playback follows `QAudioSink.processedUSecs()`, with wall-clock
fallback when audio is unavailable. The playhead/time display follows this clock
each tick independently of video arrival. Displayed-frame position is separate
for frame count and video envelopes; delayed decoding can still cause video lag.
Paused seeks stay on the source-PTS grid.

The sink prefers float PCM with int16 fallback. Listening gain is preview-only:
up to 100% uses sink attenuation; above 100% applies NumPy gain/saturation to
bounded device-bound chunks. Pending bytes remain unscaled to avoid double gain
on partial writes. Listening gain never enters jobs, projects or `ExportSpec`.

## Timeline visual caches

Separate read-only, cancellable jobs build waveform peaks and sparse keyframe
thumbnails. Waveforms combine signed min/max from both channels before effects.
Base bins are normally 1 ms, coarsened to at most two million bins per source;
a min/max pyramid supports zoom, with a shared 128 MiB resident peak budget.
Visible aggregation is capped at 4096 columns and clips to retained source ranges.
Thumbnail caches retain at most 600 images per source fitting 160×90, spaced at
least two seconds apart; long GOPs make them coarser. QML creates visible tiles.

Caches under `artifacts/visuals` include source identity/cache version and publish
atomically. Failures are nonfatal. Drawing gain is QML-only and not serialized.
Disk caches have no eviction; full indexes, project frame maps and undo history
are not bounded by the decoded queue/cache budgets.

## Export and source protection

`ExportSpec` freezes separate lane mappings, effects, sources, canvas, window and
normalization options. Later UI edits cannot alter a running export. Shared sample
mapping/envelopes prepare temporary float PCM. Non-overlap video uses source PTS;
overlap intervals use the shared compositor and temporary lossless RGB FFV1/NUT.
FFmpeg interleaves these with black gaps on the project clock and preserves fade
phase when exporting a partial window.

One final lossy encode produces H.264 CRF 18 / veryfast / yuv420p and stereo 48 kHz
AAC 320 kbit/s. Optional export-only sample-peak normalization measures bounded
post-mix PCM, rounds peak dB/gain to six decimals, caps the target at -0.0001 dBFS
and uses double-precision FFmpeg volume. Linked channels share their larger peak;
independent mode applies separate gains. Silence has zero gain; non-finite input
is rejected when normalization is enabled. Disabled normalization leaves PCM
unchanged and adds no filter. There is no limiter, compression, DC removal,
extra resampling or true-peak/decoded-AAC peak guarantee.

Every source is read-only. Export rejects existing destinations and source aliases.
A `.video-export-*` directory on the destination volume contains temporary data.
Final Windows publication must not overwrite a file created during rendering.
Cancellation is cooperative with terminate/kill fallback; recursive cleanup first
validates the resolved temporary path. Temporary disk use grows with audio duration
and transition frames. Preserve this lifecycle when changing export behavior.

## Persistence and runtime

`.splicelet` JSON versions are independent of application versions. Version 2
stores single-video two-lane projects; version 3 adds multi-source/audio-only and
the canvas. Versions 1–3 load; version 1 opens linked and upgrades on save.
Source IDs reference local piece/reserve indexes, translated into the virtual grid
on load. Times serialize as numerator/denominator pairs. Source identity checks
absolute path, size and `mtime_ns`, not full hashes. Loading stages/indexes sources
and validates ranges before replacing a valid session. No relinking or autosave.

Project saves use a sibling temporary file, flush/fsync and atomic replacement.
Existing project saves may be updated, but source paths/aliases are protected.
Dirty state compares content to the saved snapshot, excluding selection. Undoing
to the saved state clears dirty state. History/playhead/viewport are not persisted.
QSettings stores recent projects and appearance per user.

`splicelet/__init__.py` is the application version source for CLI, About, Qt and
Windows executable metadata. Development launchers use the repository-local
Conda prefix. Frozen builds bundle QML, runtime dependencies and external FFmpeg;
their writable artifacts directory is beside the executable. Windows startup sets
the taskbar identity `Splicelet.Splicelet` before constructing the application.

## Limits and evidence

There is no general multitrack composition, individual-sample UI editing, integrated
proxy workflow or validated HDR/color-management pipeline. Broad codec/rotation/
multichannel behavior, sustained high-resolution transitions, long-run device sync
and clean-machine portable distribution remain unverified. Muted/offscreen checks
do not establish physical-device listening quality. PCM equality does not imply
sample-exact AAC playback across players. There is no installer or updater;
distribution license/notice/source packaging, MKL/Microsoft redistribution
questions and release signing remain unresolved.

See [development checks](DEVELOPMENT.md#verification) for reproducible commands
and fixture limits. The maintained suite generates its own PTS/sample-validated
synthetic media under `artifacts/test-fixtures`; no private recording is required.
Initial [synthetic](history/TECHNICAL_RESULTS.md) and
[real-source](history/REAL_SOURCE_RESULTS.md) reports explain early engine
decisions; their measurements and proposed next steps are historical evidence,
not the current feature list or a requirement to implement future work.
