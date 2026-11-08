# Changelog

The first public source snapshot is version 1.2.1. Earlier local development is
summarized below; application versions and project file format versions are
independent of each other and of the public Git history.

## Unreleased

### Development

- Consolidate follow-up changes under the same pending application version until
  its increment is committed or tagged; select the increment from the combined
  scope of the pending changes.

## 1.6.0 — Unreleased

### Added

- Join touching or overlapping consecutive clips into one compound clip while
  retaining internal crossfades, manual fades, source timing and trim reserves,
  without intermediate rendering or re-encoding. Preserve compounds in project
  format 4, displayed as a single clip with atomic Undo/Redo.

## 1.5.1 — Unreleased

### Fixed

- Open first-level application menus on hover and switch categories without
  requiring an initial click, keeping the hamburger reopen selection reset.

## 1.5.0 — Unreleased

### Added

- Application icon beside the hamburger opens the native Windows system menu
  and supports double-click close with the existing unsaved-project protection.

## 1.4.2 — Unreleased

### Fixed

- Route Windows title-bar hit tests to native caption gestures and real QML menu
  input, restoring physical double-click maximize/restore and category clicks.
- Clear the active menu category and its highlight whenever the application menu
  closes or opens.

## 1.4.1 — Unreleased

### Fixed

- Restored title-bar double-click maximize/restore by starting window movement
  only after a drag begins.
- Aligned menu categories beside the hamburger on Windows by overriding inherited
  safe-area padding, and removed the hamburger tooltip that obscured the menu.

## 1.4.0 — Unreleased

### Changed

- Integrated the application menu into the window title bar: horizontal
  File/Edit/View/Help categories and cascading submenus replace the vertical
  side-panel accordion, preserving the workspace while navigating commands.
  The window title hides while the menu is open.

## 1.3.1 — Unreleased

### Fixed

- Overlap preview skips expired composition work using the transport clock and
  converts only the source frames needed for presentation, avoiding accumulated
  slow motion followed by catch-up. Paused seeks and export retain their complete
  source-PTS schedules; audio processing is unchanged.

## 1.3.0 — Unreleased

### Added

- Orange playhead head and line indicate active timeline Follow in both themes.

### Changed

- Pressing the ruler or a clip immediately releases Follow, including rectangle
  selection and trim edges. All zoom operations, including Z, preserve Follow.

## 1.2.1 — 2026-11-02

Source snapshot prepared for the first public publication, under GPL-3.0-or-later.
Prebuilt binaries are not distributed; experimental portable build scripts are
provided for local use and testing.

### Included

- Multi-source video/audio editing with linked or independent lanes, source
  waveforms and thumbnails, non-destructive editing and undo/redo.
- Project saves, manual fades, automatic two-clip crossfades and H.264/AAC export
  with optional sample-peak normalization.
- Rectangle selection, selected-length display, responsive transport controls,
  inline menus and light/night themes.

### Fixed

- Avoid undefined Action assignments for menu entries without actions, removing
  the three PanelMenu startup warnings without changing menu behavior.

### Development

- Project-local Conda setup with automatic installation detection and an override
  for custom Conda locations.
- A single test launcher and reproducible synthetic fixtures, without requiring
  private recordings or video downloads.
- Separate user manual, architecture and development documentation, with early
  measurements and handwritten notes preserved as historical material.

## Earlier local development

These milestones predate public publication and do not refer to commits or tags
in the public repository.

- **1.0.0 — 2026-11-01:** first stable local version, with multi-source editing,
  project persistence, fades/crossfades, export, themes and local portable builds.
- **1.2.0 — 2026-11-02:** rectangle selection, selected length and scissors button;
  narrow-window transport layout; export defaults to All; playback cursor follows
  the transport clock independently of delayed video decoding.
