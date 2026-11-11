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

- Use `MAJOR.MINOR.PATCH` for the application version, adding a suffix only when
  explicitly requested by the user. Never change the version automatically,
  whether changes are committed or uncommitted. Change `__version__` in
  `splicelet/__init__.py` only when the user asks to create a new version or release.
- An unqualified request to create a release targets the main branch and uses
  the latest reachable stable tag `vMAJOR.MINOR.PATCH` as the comparison baseline;
  ignore all suffixed tags. For a request with a suffix such as `-rc`, use the
  latest reachable tag that is either stable or has that exact suffix, ignoring
  other suffixes. Do not invent suffixes or suffix counters.
- When creating a release, inspect the existing tags, the version in HEAD and
  the working tree, and all commits and the cumulative diff since the applicable
  baseline tag. Choose the increment from the combined changes since that tag,
  not from the current version string or the latest commit alone. Increment
  MINOR (the second number) for new functionality and reset PATCH to 0; increment
  PATCH (the third number) for compatible fixes without new functionality.
  If changes include both features and fixes, use a MINOR increment. For an
  explicitly requested release containing only documentation, tests or development
  tooling changes, use PATCH. If no applicable baseline tag exists, clarify the
  initial version with the user instead of inventing release history.
- Propose a MAJOR increment (the first number) for incompatible changes,
  explaining why, but obtain the user's explicit agreement before applying it;
  reset MINOR and PATCH to 0 when approved.
- Assess incompatibility from the user's perspective. Changes to existing default
  behavior (for example, the default export resolution) or new mandatory user
  requirements warrant a MAJOR proposal. Requirements include external tools,
  even when automatically installed: requiring network access to install them is
  itself a new requirement. An optional capability does not introduce a mandatory
  requirement if existing use remains available with the same defaults and
  requirements. Adding a configuration parameter preserves compatibility only
  when it is optional and leaving it unset preserves existing default behavior.
  Internal implementation changes alone do not warrant MAJOR when user behavior
  and requirements remain compatible. Apply these criteria before the MINOR/PATCH
  rules; retain the existing approval requirements for changes affecting export.
- As part of the requested release, update the version and CHANGELOG, commit
  the release metadata and create the matching `vMAJOR.MINOR.PATCH` tag, including
  exactly the suffix requested by the user, on the release commit. Never overwrite
  an existing tag or rewrite existing commits to create a release.
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
- Keep pending release notes under Unreleased without changing the application
  version. When the user requests a release, consolidate the relevant notes into
  a concise entry for that version, grouped by Added/Changed/Fixed as applicable.
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
