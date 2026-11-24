# Development guide

Splicelet is a local Windows video editor using Python, PySide6/QML, PyAV,
NumPy and FFmpeg in a repository-local Conda environment.

## Documentation

Write for humans: reading time is precious. Keep only project-specific facts,
commands, constraints and design decisions. Remove repetition and generic
explanations; link to the document that owns a topic.

- [README](README.md): short introduction, screenshot, quick start and links.
- [Manual](docs/MANUAL.md): current interactions, shortcuts, defaults and limits.
- [Architecture](docs/ARCHITECTURE.md): components, timing, data flow and decisions.
  Read it when resuming work or planning changes across components.
- [Development](docs/DEVELOPMENT.md): environment, builds, release procedure,
  checks, fixtures and validation limits.
- [Changelog](docs/CHANGELOG.md): verifiable history and pending release notes.
- `docs/history/`: historical evidence, not current requirements or test results.
  Do not routinely update it.

Update affected documentation in the same task. Describe current behavior;
distinguish policy and planned work from implemented checks. Keep documentation
under `docs/`, except root README and AGENTS. Keep detailed test evidence under
`artifacts/`, not in design documents. Review links and commands after editing;
use portable paths and never publish personal paths or private fixture requirements.
Keep pending notes under Unreleased; preserve historical records.

## Environment and assets

- Keep source, comments, identifiers, filenames, UI and documentation in English.
  Use `.` for decimals regardless of Windows locale.
- Keep development reproducible and self-contained: use `.envs/video-tech`,
  pinned dependencies and project-local tools/caches. Any additional runtime,
  such as Node.js, must also be project-local and justified by the task.
  Do not alter base Conda or install globally. Existing Conda is the bootstrap
  prerequisite; the Visual Studio C++ runtime may be installed system-wide.
- Always warn before any system-level installation or update, including the
  C++ runtime. Do not silently install missing prerequisites.
- Verify downloads against expected SHA-256 hashes from official sources before
  using/extracting/executing them. Record source and expected hash; fail on mismatch.
- Always maintain an application icon for the window and distributions.
- Prefer bundled, appropriately licensed fonts. If bundling is impractical or
  inadvisable, notify the user and document the dependency. Currently the UI
  uses Windows Segoe UI/Consolas; see Development for this exception.
- Keep generated outputs under `artifacts/`; do not treat `media/` as disposable.
  Follow existing Python/QML conventions; no formatter or package pipeline is configured.

## Editing and media constraints

- Keep the interface light and responsive. Selection and editing belong on the
  timeline; do not add a separate clip toolbar.
- Warn before implementing changes expected to significantly affect performance;
  explain the impact and distinguish estimates from measurements.
- Originals are always read-only. Never overwrite export destinations or source
  aliases. Preserve cancellation, destination race protection and validated
  temporary-directory cleanup.
- Export quality has been tested and accepted. Before changing rendering or
  encoding for the same timeline, range and settings, notify the user, explain
  the impact and agree on scope. This includes shared decoding, timing, source
  mapping, fades, resampling and encoding, even for preview features. Automating
  equivalent existing edits needs no separate export-quality approval when the
  resulting timeline and export processing are unchanged.
- Keep editing/time logic independent of Qt/QML and playback. Preview and export
  share source ranges and fade definitions. Respect PTS/time bases and audio
  sample positions; never infer exact cuts/counts from `duration * fps`.
- Keep decoding, indexing and export off the GUI thread. Preserve stale-job
  cancellation, bounded queues/caches and native/vectorized processing.
- Preserve the Manual's interaction rules, especially deletion with gaps,
  explicit gap removal, source trim reserves and duplication without ripple.
- No cloud, AI features, creative presets or live recording. Automatic audio
  declicking requires a new request.

## Versions and releases

- Change `splicelet/__init__.py::__version__` only on an explicit version/release
  request. Use `MAJOR.MINOR.PATCH` with exactly the requested suffix; never invent
  suffixes or counters. Qt, About, CLI and executable metadata derive from it.
  Numeric executable fields exclude suffixes; project format versions are independent.
- A release request includes reviewing changes, committing the release and
  creating its matching tag; it does not authorize GitHub publication or binaries.
  Default to the main branch. Inspect tags, HEAD, working tree, all commits and
  cumulative changes since the applicable previous tag before choosing a version.
- Without a suffix, compare with the latest reachable stable `vMAJOR.MINOR.PATCH`
  tag. With a suffix, compare with the latest reachable tag with that exact
  suffix; ignore other suffixes and stable tags. If no applicable tag exists,
  clarify the baseline/initial version rather than inventing release history.
- Use MINOR for new functionality, PATCH for compatible fixes or a release
  containing only documentation/tests/tooling. Features plus fixes use MINOR.
  Reset lower components when incrementing MINOR or MAJOR.
- Propose MAJOR and obtain explicit agreement before applying incompatible
  changes: unsupported existing projects/media, changed established defaults or
  new mandatory requirements, including external tools/network installation.
  Optional additions preserve compatibility only if existing defaults and
  requirements remain available. Interaction/internal changes follow these same criteria.
- Consolidate Unreleased notes, update the version, run appropriate checks,
  commit all intended release changes and create `v<version>` on that commit.
  Never overwrite tags or rewrite commits. A tag/version mismatch is an error:
  stop release/publication rather than silently relabeling the code.
- Build releases after commit/tag with a clean tree. If GitHub publication is
  requested, use a manual workflow or one triggered by publishing a version tag,
  never by arbitrary pushes. Source-only distribution remains the default;
  portable publication requires a new request and resolution of Development's
  licensing issues. Keep generated binaries, DLLs and environments out of Git.

## Build identity

- Include the short Git hash and `modified` state in About, CLI, startup logs
  and textual executable metadata; retain the full hash in build metadata.
  Release artifact labels should follow `v<version>-<hash>[-modified]`, for example
  `v1.2.3-test-abcdef0-modified`. See Development for the current app display format.
- `modified` covers staged/unstaged tracked changes and non-ignored untracked
  files. It is provenance, not an application-version suffix or exact content ID.
  Ignored tools/environments/outputs do not dirty builds. Capture identity before
  generating metadata and regenerate the snapshot for every portable build.
- Source launches inspect only the project repository. Portable startup reads
  only its bundled snapshot, without Git, network or a nearby repository. Missing
  or invalid identity falls back to the application version; never reuse a stale
  snapshot or invent a clean state. Verify retention outside the checkout before
  claiming portable identity support.
- Ask before making the version clickable or bundling a repository URL: a remote
  may be private. If authorized, capture the verified repository root URL at
  build time; never invent one. Opening it must remain optional and offline use
  available. This rule does not itself authorize implementing a link.

## Validation

Run from the project root in PowerShell:

```powershell
powershell -NoProfile -File scripts/bootstrap.ps1
powershell -NoProfile -File scripts/launch-splicelet.ps1
powershell -NoProfile -File scripts/run-tests.ps1
```

Bootstrap is needed only to create/recreate the environment. The maintained
suite generates synthetic fixtures under `artifacts/`; smoke alone uses
`scripts/launch-splicelet.ps1 -SmokeTest`. See Development for focused checks.
Run checks appropriate to the change: visually inspect QML, listen for audio
changes, and review links/commands for documentation-only work. Report checks
actually run and material limitations; muted tests do not establish listening quality.
