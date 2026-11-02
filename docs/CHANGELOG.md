# Changelog

The first public source snapshot is version 1.2.1. Earlier local development is
summarized below; application versions and project file format versions are
independent of each other and of the public Git history.

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
