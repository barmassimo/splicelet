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
Use project-local environments and tools for any future runtime additions.
Existing Conda is a bootstrap prerequisite; the Visual Studio C++ runtime may
be system-wide. Always warn before installing or updating anything at system
level, including that runtime; bootstrap does not install these prerequisites.

```powershell
powershell -NoProfile -File scripts/bootstrap.ps1
& '.\Launch Splicelet.cmd'
```

Conda detection checks `CONDA_PYTHON_EXE`, `CONDA_EXE`, PATH, then
`miniconda3`/`anaconda3` under the user profile, Local AppData and ProgramData.
Override detection for a custom installation:

```powershell
powershell -NoProfile -File scripts/bootstrap.ps1 -CondaPython (Join-Path $env:USERPROFILE 'miniconda3\python.exe')
```

Bootstrap creates `.envs/video-tech` with cache `.conda-pkgs`, leaving base Conda
unchanged. Scripts share this prefix; do not rename it without updating consumers.
Rerun bootstrap only to create/recreate the environment.

`environment.yml` declares dependencies; `qt6-multimedia` is required alongside
`pyside6` for `QAudioSink`. The Windows-only `environment-win-64.lock` takes precedence.
Launchers configure the local runtime's DLL paths and `CONDA_PREFIX` themselves.
Development FFmpeg is resolved from that runtime's `Library/bin`, not system PATH.

Reproducibility limits: the explicit lock pins package URLs but does not contain
expected SHA-256 hashes; build-tool requirements pin versions without hashes.
Neither provides the official-source SHA-256 verification required for new
downloads by AGENTS. A hash-verified dependency manifest remains future work.

To open an existing source/project directly, substitute your own file path:

```powershell
powershell -NoProfile -File scripts/launch-splicelet.ps1 -Source '.\media\example.mkv'
```

The source launcher also accepts `-Muted` and `-SmokeTest`. No media is bundled.

### Icon and fonts

The application icon source is `splicelet/assets/splicelet.svg`; portable builds
generate PNG/ICO assets from it. Keep the icon in the window and distributions.

Fonts are currently a system dependency: QML requests Windows **Segoe UI** and
**Consolas**, and offscreen startup registers them from the Windows Fonts folder
when Qt finds no fonts. Fonts are not explicitly bundled by the application.
Prefer licensed bundled fonts for future UI work; replacing these fonts requires
layout verification and license/packaging review. Do not copy Windows font files
into distributions without redistribution rights.

## Release procedure

A version/release request authorizes the release commit and tag, not GitHub
publication. Follow [AGENTS](../AGENTS.md#versions-and-releases):

1. Work on main unless another branch is requested. Inspect status, tags, commits
   and the cumulative diff since the latest reachable stable version tag, or the
   latest tag with exactly the requested suffix. If none exists, clarify the baseline.
2. Choose the increment from all those changes. Obtain agreement before a MAJOR
   increase; preserve the exact requested suffix.
3. Update `__version__` and consolidate Unreleased notes. Run relevant checks,
   commit the intended changes and tag that release commit as `v<version>`.
4. Verify the tag resolves to the intended commit, its version matches that
   commit's `__version__`, and the build tree is clean. Any mismatch is an error;
   stop rather than moving a tag or silently changing the version. Build afterward.

Release artifact identity uses `v<version>-<short-hash>[-modified]`, for example
`v1.2.3-test-abcdef0-modified` for a local modified build. Tagged release builds
must be clean. Hash/state are provenance, separate from the semantic version.
The current app displays `1.2.3 (abcdef0, modified)` instead; artifact naming and
tag/version rejection are release-procedure rules, not automated build checks.
The current portable spec parses only a numeric version, so suffixed portable
builds need a spec update before use.

No GitHub release workflow is configured. If publication is requested, use manual
dispatch or a version-tag push trigger. Do not publish on ordinary branch pushes.
Binary publication additionally requires resolving the licensing section below.

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

Builds also capture the current Git commit and whether tracked or untracked
non-ignored files differ from it. About, `python -m splicelet --version`, startup
logs and textual Windows version fields show this identity; the application
version and numeric executable version fields remain unchanged. Portable builds
bundle the snapshot and need no Git installation at runtime. Missing Git or
repository metadata falls back to the application version alone. The `modified`
marker identifies a local change state, not the exact content of those changes.

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

This runs isolated processes sequentially, including build identity, source feasibility,
application smoke, all maintained focused probes and source/proxy checks. No
private recordings or media downloads are required. Each process has a timeout;
failures are recorded without skipping later checks. Logs and an aggregate report
are written to a unique directory under `artifacts/test-suite/`. The command
returns nonzero if any included check fails.

Build the portable folder first, then add `-Portable` to include its isolated
smoke probe.


Review links/commands for documentation changes, visually inspect QML and listen
for audio changes. Muted/offscreen/PCM checks do not establish perceived sync or
device latency/quality. Crossfade, multi-source and project probes isolate INI settings.

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
| `probe_build_info.py` | Clean/modified Git identity, missing Git/repository fallback and portable snapshot loading without Git | `build-info-tests/report.json` |
| `probe_timeline_edits.py` | Gaps, mapping, joins, reserves, duplication and history | `timeline-tests/report.json` |
| `probe_clip_effects.py` | PCM/video fades, seeks, joins and preservation | `effects-tests/report.json` |
| `probe_audio_tracks.py` | Independent lanes, mapping, gestures and persistence | `audio-track-tests/report.json` |
| `probe_group_edits.py` | Mixed-lane selection/moves/copies, copy cursor, collisions and atomic history | `group-edit-tests/report.json` |
| `probe_crossfades.py` | PCM/video transitions, PTS/VFR, preview recovery, compound equivalence, persistence and cancellation | `crossfade-tests/report.json` |
| `probe_multi_source.py` | Mixed sources/canvases/cadences, PCM, projects, external file drops across the workspace, library gestures and safety | `multi-source-tests/report.json` |
| `probe_timeline_visuals.py` | Peaks, thumbnails, retained ranges, caches and QML zoom/pan | `timeline-visual-tests/report.json` |
| `probe_export_options.py` | Export scope/defaults, normalization, AAC references and cancellation | `export-option-tests/report.json` |
| `probe_export_seeks.py` | Bounded seeks versus unbounded reads: exact decoded A/V, cuts, overlaps, VFR/tails and container origins | `export-seek-tests/report.json` |
| `probe_playhead_clock.py` | Delayed/absent video, transport clock, displayed-frame fades and paused seeks | `playhead-clock-tests/report.json` |
| `probe_audio_meter.py` | Peaks, partial writes, unchanged device bytes, mute, bounded queue and layouts | `audio-meter-tests/report.json` |

The synthetic source checks are included in the full suite and can also run alone:

```powershell
& "$SpliceletRuntime\python.exe" scripts/probe_source.py
```

It generates CFR/VFR H.264 and deterministic stereo PCM, checking seeks, cuts,
transitions and encoding; report: `artifacts/report.json`.

### Generated integration fixture

`scripts/test_fixture.py` creates `artifacts/test-fixtures/v1/integration.mkv`
on first use: a moving 640×360 H.264 pattern with B-frames/long GOPs and distinct
48 kHz stereo PCM tones. Approximately 297 s supports late-seek checks at
180/240 s; an irregular final frame and shorter audio exercise tail handling.
Exact generator parameters live in that script. This tests correctness, not
HD performance or equivalence to a private recording.

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

The appearance probe checks title-bar double-click maximize/restore and menu
alignment with the hamburger. Offscreen rendering has no Windows safe-area
margins; also run this probe on the Windows platform after title-bar changes,
using the configured runtime paths above:

```powershell
$env:QT_QPA_PLATFORM = 'windows'
& "$SpliceletRuntime\python.exe" scripts/probe_appearance.py
Remove-Item Env:QT_QPA_PLATFORM
```

The probe uses startup's native frame filter, but QTest bypasses OS hit testing.
After it finishes, verify menus/reopen reset, caption maximize/restore, icon
system-menu/close and dragging with real mouse input.

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

The probe includes a 15-second proxy comparison starting at minute 2, so input must
be sufficiently long. Its generated references and report are written under
`artifacts/real`; this does not implement an editor proxy workflow. Measurements
from the synthetic fixture are not real-recording performance measurements.

### Known validation limits

The layout probe has shown intermittent wheel-event failures, including a failure
reproduced with pre-change QML. This does not establish physical trackpad behavior;
inspect current warnings and reproduce against a baseline before attributing regressions.
Muted tests do not replace listening; high-resolution/GPU/device and clean-machine
distribution claims require their own evidence.

Initial [synthetic](history/TECHNICAL_RESULTS.md) and
[real-source](history/REAL_SOURCE_RESULTS.md) measurements are historical.
Generated reports may contain absolute source paths; review before sharing.
Artifacts, media and runtime/cache directories are excluded from Git.
