# Development guide

This is a local, Windows-only video editor using Python, PySide6/QML,
PyAV, NumPy and FFmpeg in a project-local Conda environment.

## Where to look

- Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) when understanding the architecture,
  resuming earlier work, or planning changes across components. Reading it is
  not required for every small, self-contained edit.
- [README.md](README.md) is the short public introduction and quick start.
- [docs/MANUAL.md](docs/MANUAL.md) describes current user interactions and limitations.
- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) covers setup, builds, probes, report
  locations and generated fixture requirements.
- [docs/CHANGELOG.md](docs/CHANGELOG.md) records user-visible version history.
- Reports under `docs/history/` are historical measurements, not the current
  feature list or proof of untested capabilities. Do not routinely update them.

## Conventions and constraints

- Keep UI text, dialogs, messages, comments, identifiers and documentation in
  English. Use `.` for decimals regardless of Windows locale.
- Keep the interface light, minimal and responsive. The timeline itself holds
  selection and editing interactions; do not add a separate clip toolbar.
- Original sources must remain untouched under every operation. Never overwrite
  existing export destinations or source aliases. Preserve export cancellation,
  destination race protection and validated temporary-directory cleanup.
- Public distribution currently consists of source code and local build scripts.
  Keep generated executables, DLLs and environments out of Git/public downloads;
  portable redistribution requires resolving the licensing issues in
  docs/DEVELOPMENT and a new user request to publish binaries.
- The user has thoroughly tested and accepted exported audio/video quality.
  Before making any change that could affect exported audio or video, notify
  the user, explain the potential impact, and agree on the scope before proceeding.
  This includes shared decoding, timing, source-range mapping, fades, resampling,
  rendering and encoding settings, even when the requested feature is for preview.
- Keep editing/time logic independent of Qt/QML and the playback backend.
  Preview and export must interpret the same source ranges and fade definitions.
- Respect source PTS/time bases and audio sample positions; do not derive exact
  frame counts or cuts from `duration * fps`. See the time model in ARCHITECTURE.
- Keep decoding, indexing and export off the GUI thread. Preserve stale-job
  cancellation and bounded queues/caches. Use native/vectorized source processing.
- Preserve the interaction rules in MANUAL, especially delete-with-gaps versus
  explicit gap removal, trimming source reserves, and duplication without ripple.
- No cloud, AI features, creative presets or live recording. Do not add automatic
  audio declicking without a new request; the current audio behavior was accepted.
- Use the existing Conda environment and prebuilt dependencies; do not alter base
  Anaconda, install globally, or introduce another runtime without a task need.
  Keep generated outputs under `artifacts/`; do not treat `media/` as disposable.
- Match existing Python/QML conventions. No formatter, package build or standalone
  distribution pipeline is currently configured. Keep changes focused.

## Versioning

- Use `MAJOR.MINOR.PATCH` for the application version. Increment once per pending
  set of application changes, not once per request or follow-up. Before changing
  `__version__` in `splicelet/__init__.py`, inspect the version in HEAD, the working
  tree and existing tags. If a pending version increment has neither been
  committed nor tagged, keep that version for further changes and fixes, and
  consolidate their CHANGELOG notes under the same version. A commit containing
  the increment or a tag for that version establishes a new versioning baseline;
  do not rewrite existing commits or tags to consolidate earlier increments.
  Apply this rule to all three version components. Choose the increment from
  the baseline according to the combined scope of the pending changes:
  increment MINOR (the second number) for new functionality and reset PATCH to 0;
  increment PATCH (the third number) for fixes without new functionality.
  If a change includes both features and fixes, use a MINOR increment.
  If the pending scope grows from fixes to new functionality, replace the pending
  PATCH increment with a MINOR increment from the baseline, rather than adding
  another increment. For example, from committed `1.3.0`, pending features use
  `1.4.0`; follow-up fixes retain `1.4.0` until it is committed or tagged.
- Propose a MAJOR increment (the first number) when warranted, explaining why,
  but never apply it automatically; obtain the user's explicit agreement first.
- Documentation-only, test-only and development-tooling-only changes do not
  require an application version increment unless they change shipped behavior.
- Avoid duplicating the current version in introductory/design documentation.
  Keep any current-version references consistent with the application version;
  preserve clearly identified historical release records.
  Qt, About, CLI and executable metadata must continue to derive their version
  from `splicelet/__init__.py`. Project file format versions are independent:
  do not increment them merely because the application version changes.

## Documentation maintenance

- Keep project documentation under `docs/`, with README and the repository-wide
  AGENTS instructions in the root. AGENTS must remain at the root so its scope
  includes application code and scripts.

- Update affected documentation as part of the same task, without waiting for
  a separate request. This is an agent responsibility, not an installed background
  synchronizer. Update only documents whose content actually changes.
- Keep README concise: introduction, repository screenshot, quick start and links.
  Update it when presentation, major scope, requirements or initial setup changes.
- Update MANUAL for changes to interactions, shortcuts, defaults, user-visible
  limitations or setup relevant to users. Describe current behavior, not its history.
- Update ARCHITECTURE for changes to components, data flow, timing, design decisions
  or material technical constraints. Organize by topic; replace outdated descriptions
  rather than appending dated implementation reports or routine fix narratives.
- Update docs/DEVELOPMENT for environment, build or verification changes, including
  commands, fixture requirements and known validation limitations. Distinguish
  maintained synthetic checks from optional real-media and historical probes.
- For each application version increment, add a concise CHANGELOG entry grouped
  by Added/Changed/Fixed as applicable. Consolidate changes within the same version.
  Record only verifiable history; do not infer missing versions or label untagged
  work as a published release. Use Unreleased for relevant pending release notes,
  including documentation-only changes that do not increment the application.
- Keep test implementation in probes and detailed evidence in artifacts. Report
  checks actually run in the task response; do not transcribe every pass count,
  capture or intermediate attempt into permanent documentation. Preserve material
  limitations that affect interpreting results.
- Review relative links when moving/renaming documents. Keep commands portable
  across repository locations, use explicit placeholders for user media and paths,
  and document installation assumptions. Never publish personal absolute paths or
  present ignored local fixtures as bundled prerequisites.

## Launch and validation

Run from the project root in PowerShell:

```powershell
powershell -NoProfile -File scripts/bootstrap.ps1
powershell -NoProfile -File scripts/launch-splicelet.ps1
```

Bootstrap is needed only when creating/recreating the environment. Run
`powershell -NoProfile -File scripts/run-tests.ps1` for the maintained suite;
it generates its own synthetic integration fixture under artifacts. For smoke
alone, use `scripts/launch-splicelet.ps1 -SmokeTest`. See docs/DEVELOPMENT for
focused commands, report paths and optional portable checks.
Run checks appropriate to the change; visually inspect QML changes and listen
when audio changes. Documentation-only changes need link/command review, not
source playback/export reruns. Follow the documentation maintenance rules above.
