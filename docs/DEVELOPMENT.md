# Development

See [AGENTS.md](../AGENTS.md) for development rules,
[ARCHITECTURE.md](ARCHITECTURE.md) for the design, and the
[manual](MANUAL.md) for user behavior. Commands below run in PowerShell from
the repository root. Generated files belong under `artifacts/`; source media is
never disposable.

## Environment and launch

Requirements for source development are **64-bit Windows**, PowerShell and a
working Anaconda/Miniconda installation whose Python can run `python -m conda`.
Bootstrap needs network access to the conda-forge package URLs in the lock file.
No globally installed PySide6, FFmpeg, NumPy or Python packages are required.

```powershell
powershell -NoProfile -File scripts/bootstrap.ps1
& '.\Launch Splicelet.cmd'
```

Bootstrap looks for Conda using `CONDA_PYTHON_EXE`, `CONDA_EXE`, Conda executables
on PATH, then `miniconda3`/`anaconda3` folders under the current user profile,
Local AppData and ProgramData. It checks that the selected Python can run
`python -m conda` before creating the environment. An explicit `-CondaPython`
overrides detection; use it for custom installations, for example:

```powershell
powershell -NoProfile -File scripts/bootstrap.ps1 -CondaPython (Join-Path $env:USERPROFILE 'miniconda3\python.exe')
```

It creates `.envs/video-tech` **inside this repository**, using `.conda-pkgs` as
its package cache. The name is a project convention shared by the scripts, not
a pre-existing named environment that users must create or activate globally.
Do not rename the prefix without updating its consumers. Base Conda is unchanged.
Bootstrap is needed only when creating/recreating the environment.

`environment.yml` declares dependencies, including the required `qt6-multimedia`
package in addition to `pyside6`. `environment-win-64.lock` pins the Windows
packages and takes precedence during bootstrap. It is not a cross-platform lock.
Launchers configure the local runtime's DLL paths and `CONDA_PREFIX` themselves.
Development FFmpeg is resolved from that runtime's `Library/bin`, not system PATH.

To open an existing source/project directly, substitute your own file path:

```powershell
powershell -NoProfile -File scripts/launch-splicelet.ps1 -Source '.\media\example.mkv'
```

No media is bundled or required to open the empty editor. Restart after code
changes. The source launcher accepts `-Muted` and `-SmokeTest` as well.

## Portable build

The experimental PyInstaller folder build is for local use and testing. This
repository distributes source code only, with no prebuilt binary releases.
The build bundles Python, Qt/QML, PyAV, NumPy and FFmpeg, so it runs without a
separate Python/Conda installation. Install its pinned build dependencies into
the existing project environment:

```powershell
.\.envs\video-tech\python.exe -m pip install -r scripts/requirements-build.txt
& '.\Build portable.cmd'
```

Close the portable app first. The build command stays open for error review;
`& '.\Build portable.cmd' -NoPause` skips that pause. The build regenerates PNG/ICO
assets from `splicelet/assets/splicelet.svg` using Qt under `artifacts/icon`.
`scripts/Splicelet.spec` derives Windows version metadata from the application
version source; there is no separate manual version field to maintain.

Output is `artifacts/portable/Splicelet/Splicelet.exe`. Keep the **entire Splicelet
folder** together, with `_internal` beside the executable. Run from a writable location, since cache,
logs and smoke outputs go into `artifacts` beside the executable. Source media
is not included; projects retain original paths. QSettings remains per user.
Rebuild after changes; an existing binary does not automatically follow source.

The build is unsigned, with no installer/updater. Clean-machine compatibility
and distribution licensing work remain pending. A same-machine
isolated probe exists and defaults to the generated integration fixture:

```powershell
.\.envs\video-tech\python.exe scripts/probe_portable.py
```

It removes Conda/Python/Qt environment settings and uses another working directory.
Reports: `artifacts/portable-tests/report.json` and the executable's own
`artifacts/smoke-tests` subfolder. This is not a clean-machine Windows test.

### Distribution licensing

Generated executables, DLLs and environments stay out of Git and public downloads.
Before distributing a portable build, prepare the required license/attribution
texts and exact corresponding-source materials, including recipe patches and
applicable GPL/LGPL replacement/rebuild instructions. Resolve the current
Intel MKL/GPL compatibility and Microsoft VC/UCRT redistribution questions.
The pinned Qt Multimedia package declares GPL-3.0-only; Qt main/PySide declare
LGPL-3.0-only. PyInstaller's exception does not waive dependency requirements;
codec patent rights remain a separate, unassessed issue. A passing smoke test
does not establish licensing compliance. Local review evidence is under
`artifacts/portable-license-review/` and is not legal clearance.

## Verification

After bootstrap, run the maintained suite with one command:

```powershell
powershell -NoProfile -File scripts/run-tests.ps1
```

This runs 18 isolated processes sequentially, including source feasibility,
application smoke, all maintained focused probes and source/proxy checks. No
private recordings or media downloads are required. Each process has a timeout;
failures are recorded without skipping later checks. Logs and an aggregate report
are written to a unique directory under `artifacts/test-suite/`. The command
returns nonzero if any included check fails.

`scripts/run-tests.ps1` is the single test launcher. For focused checks, invoke
the individual Python probe after configuring the runtime paths below.

Build the portable folder first, then add `-Portable` to include its isolated
smoke probe. The retired QMediaPlayer feasibility experiment is preserved only
in the [historical report](history/TECHNICAL_RESULTS.md#qtqml-probe); its executable
probe and runner options have been removed. Qt Multimedia remains a runtime
dependency for `QAudioSink`.


Run checks appropriate to a change. Documentation changes require link/command
review; QML changes require visual inspection, and audio changes require listening.
Numerical PCM tests and muted/offscreen UI checks do not establish perceived sync,
device latency or listening quality. Report the checks actually run; do not
append routine pass counts or screenshots to permanent design documentation.

For direct Python probes, configure the project DLL paths in the current session:

```powershell
$SpliceletRuntime = Join-Path $PWD '.envs\video-tech'
$env:PATH = "$SpliceletRuntime;$SpliceletRuntime\Library\bin;$SpliceletRuntime\Scripts;$env:PATH"
$env:CONDA_PREFIX = $SpliceletRuntime
& "$SpliceletRuntime\python.exe" scripts/probe_timeline_edits.py
```

### Focused checks

These create their own synthetic sources, use test doubles or share the generated
integration fixture. Report paths are relative to `artifacts/`.

| Script under `scripts/` | Coverage | Report |
|---|---|---|
| `probe_timeline_edits.py` | Gaps, mapping, joins, reserves, duplication and history | `timeline-tests/report.json` |
| `probe_clip_effects.py` | PCM/video fades, seeks, joins and preservation | `effects-tests/report.json` |
| `probe_audio_tracks.py` | Independent lanes, mapping, gestures and persistence | `audio-track-tests/report.json` |
| `probe_crossfades.py` | Mixed PCM/video, PTS schedules, preview clock-jump recovery and VFR frame holds, exact paused/offline frames, export window phase, overlap interaction and cancellation | `crossfade-tests/report.json` |
| `probe_multi_source.py` | Mixed sources/canvases/cadences, PCM, projects, library gestures and safety | `multi-source-tests/report.json` |
| `probe_timeline_visuals.py` | Peaks, thumbnails, retained ranges, caches and QML zoom/pan | `timeline-visual-tests/report.json` |
| `probe_export_options.py` | Export scope/defaults, normalization, AAC references and cancellation | `export-option-tests/report.json` |
| `probe_playhead_clock.py` | Delayed/absent video, transport clock, displayed-frame fades and paused seeks | `playhead-clock-tests/report.json` |

The synthetic source checks are included in the full suite and can also run alone:

```powershell
& "$SpliceletRuntime\python.exe" scripts/probe_source.py
```

It generates CFR/VFR H.264 and deterministic stereo PCM, checking seeks, cuts,
transitions and encoding; report: `artifacts/report.json`.

### Generated integration fixture

`scripts/test_fixture.py` creates `artifacts/test-fixtures/v1/integration.mkv`
on first use. It uses the project FFmpeg to generate a moving 640×360 test pattern,
H.264 with B-frames and GOPs up to 240 frames, plus distinct stereo tones in
24-bit PCM at 48 kHz. It contains 8910 video frames over approximately 297.1 s,
an irregular final frame interval of approximately 134 ms, and 14253056 samples
per audio channel, ending about 162 ms before video. The duration preserves
smoke operations at 180/240 s; this is low-resolution correctness coverage,
not an HD performance benchmark or a reconstruction of the deleted recording.

Generation validates actual decoded PTS, frame count and sample count. A manifest
stores the generator version, size and SHA-256. Later calls verify and reuse it;
changed/incomplete fixtures cause an error instead of being silently overwritten.
Move the generated version folder aside to regenerate it. Generated media stays
out of Git; the fixture uses about 121 MiB locally, plus test outputs. Encoding
bytes may differ across FFmpeg builds; the manifest checks
local integrity, not a universal cross-machine byte hash.

Generate it explicitly with the configured project environment:

```powershell
& "$SpliceletRuntime\python.exe" scripts/test_fixture.py
```

Smoke can now run without a source argument:

```powershell
powershell -NoProfile -File scripts/launch-splicelet.ps1 -SmokeTest
```

It uses the actual Qt window offscreen, software rendering and muted audio.
Report/screenshots are under `artifacts/smoke-tests`. Appearance, edge-space,
layout, project and group-edit probes default to the same generated source;
reports are under `appearance-tests`, `edge-space-tests`, `layout-tests`,
`project-tests` and `group-edit-tests`, each with `report.json`.

`probe_clip_export.py`, `probe_splicelet_audio.py`, `probe_group_edits.py`,
`probe_real_source.py` and `probe_portable.py` accept an optional source argument.
Without it they use the generated fixture. Custom files must still meet each
probe's assumptions; a short arbitrary recording is not a universal substitute.
Audio probes include late seeks and source-tail checks. Export safety/project
checks require a filesystem supporting hardlinks (such as NTFS); execution
sandboxes may restrict their creation even on a supported filesystem.
Reports are `artifacts/export-tests/report.json`,
`artifacts/splicelet-audio-report.json` and the other probe directories above.

### Optional real-media checks

The source/proxy suite also runs on generated media by default:

```powershell
& "$SpliceletRuntime\python.exe" scripts/probe_real_source.py
```

Pass a source as the first positional argument to inspect your own compatible
video/audio recording, for example:

```powershell
& "$SpliceletRuntime\python.exe" scripts/probe_real_source.py '.\media\example.mkv'
```

The probe
includes a 15-second proxy comparison starting at minute 2, so that input must
be sufficiently long. Its generated references and report are written under
`artifacts/real`; this does not implement an editor proxy workflow. Measurements
from the synthetic fixture are not real-recording performance measurements.
The original private recording is no longer required by any maintained check;
its early measurements remain only in the historical reports.

### Known validation limits

The layout probe has shown intermittent wheel-event failures, including a failure
reproduced with pre-change QML. This does not establish physical trackpad behavior;
inspect current warnings and reproduce against a baseline before attributing regressions.
Muted tests do not replace listening; high-resolution/GPU/device and clean-machine
distribution claims require their own evidence.

Initial measurements are archived in [history](history/TECHNICAL_RESULTS.md) and
the [real-source report](history/REAL_SOURCE_RESULTS.md). They are not maintained
as current test results. Generated reports/captures may contain absolute source
paths: `artifacts/`, `media/` and runtime/cache directories are excluded from Git. Review generated files before sharing them separately.
