# Architecture

Splicelet has one video lane and one audio lane, globally linked by default.
The core priorities are responsive editing, source-timestamp accuracy and
unchanged originals. Usage belongs in the [manual](MANUAL.md), commands in
[Development](DEVELOPMENT.md), and contribution rules in [AGENTS](../AGENTS.md).

## Components and data flow

Paths are relative to `splicelet/` unless stated otherwise.

| Component | Responsibility |
|---|---|
| `__main__.py`, `window_frame.py` | Qt startup/shutdown, locale, keyboard routing and native Windows caption input |
| `Main.qml`, `Theme.qml` | Workspace, menus, shared actions, dialogs and appearance |
| `Timeline.qml`, `ClipProperties.qml`, `FadeControl.qml` | Timeline gestures/visuals, properties and fades |
| `controller.py` | `Preview` QObject coordinates models, workers, sink, cache and export; `FrameProvider` supplies QImages |
| `editing.py`, `tracks.py` | Qt-independent clips, source mapping, reserves, two-lane transactions and history |
| `sources.py`, `source.py` | Immutable source catalog, virtual grid, fit geometry, PyAV indexing and decoder workers |
| `effects.py`, `composition.py` | Shared linear envelopes, sample gain and source-PTS overlap composition |
| `visuals.py` | Background waveform/thumbnail generation and caches |
| `project.py` | Validated versioned JSON, source identity and atomic saves |
| `exporting.py`, `normalization.py` | Frozen export specification, rendering, gain, cancellation and safe publication |
| `audio_meter.py` | Preview-only sample-peak monitoring before listening gain |
| `runtime.py`, `build_info.py` | Runtime/artifact paths and optional Git identity |
| `smoke.py`, root `scripts/probe_*.py` | Window and focused model/decoder/export checks |
| Root `scripts/test_fixture.py`, `scripts/run_tests.py` | Validated synthetic media and sequential test runner |

QML sends actions to `Preview`. Decoder jobs and export specifications snapshot
the independent model's ranges, effects and source catalog. Preview/export share
range and fade definitions. Imports use PyAV; preview audio uses `QAudioSink`,
not `QMediaPlayer`.

## Time and source model

- Actual decoded PTS/rational time bases define video edges; never use
  `duration * fps` for exact cuts/counts. Audio uses PTS-to-sample anchors:
  supported timestamp-rounding corrections precede resampling, while larger
  discontinuities remain meaningful. Output is stereo 48 kHz.
- `Clips` uses `Fraction` for starts/edges and half-open source-index pieces
  `[first, end)`. An append-only virtual grid joins metadata, not media.
  Each immutable `Source` retains its path, offset, PTS/time base, timestamp
  origin and audio index; `parts()` splits at source boundaries.
- `Clip.start` is absolute project time. `Clips.origin` may become negative
  after prepending a duplicate. Displayed time is absolute time minus origin;
  duration is `extent - origin`. Neither origin is the container timestamp origin.
- Joins preserve reordered pieces and edited trim reserves; extension must not
  resurrect deleted source ranges. Video-derived edits use video edges;
  audio-only edits use decoded audio-block/sample-anchor boundaries.
- Overlap joins store flat `Clip.components` with relative starts. Duration is
  their outer extent. Rendering flattens the original contributions with distinct
  IDs for duplicated constituents, preserving internal fades/crossfade clocks.
  Outer trims delegate to edge constituents; splits outside transitions partition
  the group; properties edit outer envelopes. QML draws one clip without internal
  transition highlighting.
- `Tracks` owns one `Clips` per lane. Linked edits copy the edited lane to its
  partner atomically. Mixed-lane moves apply one exact offset; temporary models
  validate both lanes before commit. Source placement always edits both lanes,
  even when unlinked. Schedules include black gaps. QML/worker floats and FFmpeg
  AVTB boundaries prevent an end-to-end rational or submicrosecond-exact claim.
- Stable IDs track selection. Snapshots retain both lanes, link mode, active lane
  and ID counters. Selected length is the union of occupied selected intervals;
  selection export uses their outer bounds. Selections are not saved; project
  opening initially selects the first video clip. Import is outside timeline Undo;
  unused-source removal participates in session history.

The first imported video locks the canvas even if unused. Audio-only projects
provisionally use 640×360. Later video fits by display aspect with bilinear
scaling, square pixels and black padding, using shared preview/export geometry.
Sources retain their cadence. The encoder uses a common time base, falling back
to microseconds if its denominator exceeds FFmpeg's integer limit.

## Editing invariants

Delete leaves gaps while any clip remains; deleting the last clip clears timeline
bounds in the same edit. Only explicit gap removal shifts later clips. Unlinked
gap closure must not truncate the other lane. Moves/copies never ripple outsiders;
group selection must be consecutive in each lane and preserve internal gaps.
Trims retain at least one frame and respect reserves. Edge space affects shared bounds.

Partial overlaps between consecutive clips derive linear crossfades from their
positions. Reject nesting, triple overlaps and cuts inside transitions atomically.
`Part.clip_id`/`EffectSpan.clip_id` associate contributions with their envelopes;
manual fades multiply before crossfade weights. Linked lanes transition together,
unlinked lanes independently. There is no automatic audio declicking.

Timeline layers keep both overlap trim edges reachable. Body/trim gestures start
after four horizontal pixels; temporary edge space and autoscroll wait for that
threshold. Use `WheelHandler`: a full-area no-button `MouseArea` previously
masked trim cursors. Snapping is pixel-based with Alt bypass. Ctrl+drag uses the
native copy cursor; `Tracks.duplicate_selection` validates both lanes before
committing new IDs, selection and one history entry. Copies retain pieces,
reserves and effects, and snap to original clip edges too.

## Background work and playback

Indexing, decoding, visuals and export run off the GUI thread with native/vectorized
PyAV/FFmpeg/NumPy work. Imports are sequential and cancellable; generation IDs
discard stale results and failed imports preserve the montage. Bounds:

| Resource | Limit/location |
|---|---|
| Decoder requests | One pending job per decoder |
| Video queue | Six frames |
| Audio backpressure | About 0.5 s of PCM |
| Image cache | Target 64 MiB, retaining at least one image |
| Index cache | `artifacts/index`, keyed by source path/size/mtime |

Video converts on CPU to RGB/QImage through a Qt Quick image provider; no hardware
decoding, zero-copy texture or GPU compositor is implemented. Overlaps merge
actual source PTS, including held frames at off-grid boundaries, using at most
two readers with one lookahead each. Int16 audio fallback is quantized after
mixing. Video envelopes apply inside composition (QML opacity stays at unity);
fade edits invalidate composite caches.

Audio mixes bounded 4096-sample float blocks from at most two child decoders.
Preview readers span retained source parts continuously across overlap edges;
a spare slot prebuffers the next contribution. Queues remain bounded and readers
close on stale jobs/cancellation/errors. Offline audio keeps per-interval reader
lifecycles to preserve accepted resampler initialization/exported PCM. Shared
ranges, sample anchors and fade clocks agree, but preview resampler history may
differ at internal boundaries for compressed/resampled sources.

After buffering, transport follows `QAudioSink.processedUSecs()`, falling back
to wall time without audio. Playhead/time updates are independent of video arrival;
displayed-frame time controls frame count/video envelopes. Only the GUI decoder
opts into clock-based recovery: expired overlap frames can be skipped while the
frame covering the clock remains, including sparse/VFR holds. Reference frames
still decode; RGB conversion waits for presentation, caching one held image per
reader. New requests clear the clock. Paused seeks/offline/export retain complete
source-PTS schedules. Slow sources can still stutter or lag.

The sink prefers float PCM with int16 fallback. Listening gain up to 100% uses
sink attenuation; above 100% applies NumPy gain/saturation to bounded device-bound
chunks. Pending bytes stay unscaled for partial writes. The setting is saved in
projects but never enters decoder jobs or `ExportSpec`.

`audio_meter.py` observes accepted device writes from original PCM before listening
gain, without changing bytes. Stereo sample peaks use blocks of at most 1024
frames and a bounded queue following the sink clock. Notifications are limited
to about 30 Hz, with decay/peak hold; transport resets clear the meter. No output
means no activity. It is not true-peak or export-normalization measurement.

## Visual caches

Read-only cancellable jobs build source peaks before effects and sparse keyframe
thumbnails. Waveform bins are normally 1 ms, coarsened to at most two million per
source; a min/max pyramid has a shared 128 MiB resident budget. Visible aggregation
is limited to 4096 columns and retained ranges. Thumbnails fit 160×90, at most 600
per source and at least two seconds apart (coarser with long GOPs).

`artifacts/visuals` caches include source identity/version and publish atomically;
failures are nonfatal. QML handles drawing gain; project settings persist it.
Disk caches have no eviction. Full indexes, project frame maps and Undo history
are not bounded by decoded queue/cache budgets.

## Export and source protection

`ExportSpec` freezes lane mappings, effects, sources, canvas, window and normalization;
later UI edits cannot affect an export. Shared mapping/envelopes prepare temporary
float PCM. Non-overlap video uses source PTS; overlaps use the shared compositor
and lossless RGB FFV1/NUT. The intermediate nominal rate is a bounded rational
approximation; explicit microsecond PTS retain transition cadence. FFmpeg interleaves
black gaps on project time and preserves fade phase for partial windows.

Original video inputs seek before the first required indexed PTS (including held
left-edge frames) and bound demuxing with outward-rounded slack. Input offsets are
container-relative; `copyts` preserves absolute timestamps. FFmpeg decodes keyframe
preroll; existing trim/timestamp filters choose exact output. Ranges before the
reported container origin retain unbounded reads.

One final lossy encode produces H.264 CRF 18 / veryfast / yuv420p and stereo 48 kHz
AAC 320 kbit/s. Optional sample-peak normalization measures bounded post-mix PCM,
rounds peak dB/gain to six decimals, caps target at -0.0001 dBFS and uses
FFmpeg double-precision volume. Linked channels share the larger peak; independent
mode uses separate gains. Silence has zero gain; enabled normalization rejects
non-finite input. Disabled normalization leaves PCM/filtering unchanged. There is
no limiter, DC removal, extra resampling or true-peak/decoded-AAC peak guarantee.

Sources are read-only; exports reject existing destinations and source aliases.
Temporary `.video-export-*` directories live on the destination volume; final
Windows publication cannot overwrite a file created during rendering. Cancellation
is cooperative with terminate/kill fallback. Recursive cleanup validates resolved
paths first. Disk use grows with audio duration/transition frames.

## Window and persistence

The expanded-client-area title bar reserves workspace height. Hamburger/Ctrl+M
reveals a horizontal MenuBar with zero safe-area padding and cascading submenus,
without adding a layout row. Opening/closing clears the active category.
`WindowFrame` routes native hits: menu regions receive client input, the icon
receives the system-menu target, and remaining caption space supports native
move/double-click. Qt/Windows retain caption buttons/resize borders; offscreen
QML events use a drag-threshold/double-click fallback. Full screen hides the bar.

`.splicelet` JSON versions are independent of application versions. Versions 1–4
load: v1 opens linked and upgrades on save; v2 stores single-video two-lane
projects; v3 adds multi-source/audio-only and canvas; v4 adds compounds and is
written only when needed. Source-local pieces/reserves translate to the virtual
grid on load. Times serialize as rational pairs. Identity uses absolute path,
size and `mtime_ns`, not hashes. Loading stages/indexes/validates before replacing
a valid session. No relinking or autosave.

Optional settings save listening volume, waveform gain and source display order.
Removing unused sources retains virtual coordinates/indexes for session Undo,
which verifies source identity before restoration. Saving omits removed sources,
remaps IDs and retains canvas lock, nominal rate, time base and audio availability.
Projects without clips reopen at zero duration; export requires a clip.

Saves use a sibling temporary file, flush/fsync and atomic replacement. Existing
project saves may update, but source aliases are protected. Dirty state compares
content against the saved snapshot, excluding selection; Undo can clear it.
History/playhead/viewport are not saved. QSettings holds recent projects/appearance.

`__init__.py` owns the application version. `build_info.py` adds Git provenance;
source startup probes only the project repository with bounded timeouts. Frozen
startup reads bundled `_build_info.json`, never Git. Invalid/missing identity
falls back to version alone. See [Development](DEVELOPMENT.md#release-procedure)
for release rules/current automation limits. Launchers configure local Conda;
frozen builds bundle QML/dependencies/FFmpeg and write artifacts beside the executable.
Windows sets taskbar identity `Splicelet.Splicelet` before Qt construction.

## Limits and evidence

There is no general multitrack compositor, individual-sample UI editing, integrated
proxy workflow, installer or updater. HDR/color management, broad codec/rotation/
multichannel behavior, sustained high-resolution transitions, long-run device sync
and clean-machine portability remain unverified. Muted tests do not establish
listening quality; PCM equality does not imply sample-exact AAC playback in players.
Licensing and redistribution blockers are in Development.

[Maintained checks](DEVELOPMENT.md#verification) generate their own validated media.
Early [synthetic](history/TECHNICAL_RESULTS.md) and
[real-source](history/REAL_SOURCE_RESULTS.md) reports are historical evidence,
not current requirements or performance claims.
