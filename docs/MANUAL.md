# User manual

Splicelet is a local Windows video editor. Imported files are **sources**;
editable timeline items are **clips**. Editing never modifies the originals.
For installation, see the [README](../README.md).

## Workspace and projects

Open `Launch Splicelet.cmd`. The left panel switches between **Properties** and
**Sources**. The three-line button in the window title bar, or **Ctrl+M**,
reveals **File / Edit / View / Help** horizontally beside it, temporarily hiding
the window title until the menu closes. Every opening starts with no category
selected. Click a category to open its commands. Commands open
below their category; second-level menus open to the side. The side panel stays
available and opening the menu does not resize the workspace. Esc, the three-line
button, or clicking the preview/timeline dismisses it. Drag the title bar to move
the window; double-click it to maximize/restore. Windows window controls remain
available on the right. The Splicelet icon to the left of the three-line button
opens the Windows system menu; double-clicking the icon closes the application,
with the usual save/discard/cancel prompt for unsaved changes.
**View > Night theme** saves a per-user appearance preference.
Authored UI text is English; native file dialogs follow Windows language settings.
Numeric fields require a decimal point, such as `6.25`.

| Command | Shortcut |
|---|---|
| Open project | Ctrl+O |
| Save project / Save project as | Ctrl+S / Ctrl+Shift+S |
| Import sources | Ctrl+I |
| Export video | Ctrl+E |
| Undo / Redo | Ctrl+Z / Ctrl+Shift+Z or Ctrl+Y |

The window title marks unsaved changes with `*`. Opening another project or
closing prompts to save, discard or cancel. File also lists up to ten recent
projects. Undo/redo applies to timeline edits; importing a library entry is not
undone by Undo.

Projects use `.splicelet` files. They save sources, clips, names, gaps, trim
reserves, fades, lane link mode and canvas, but do not embed media. Keep sources
at their original paths: missing files or changed size/modification time prevent
opening; relinking is not available. Reopening starts paused at the beginning;
selection, playhead, zoom and undo history are not saved. There is no autosave.

## Import and place sources

Use **File > Import sources...**, the Sources **Import** button, or drop files
onto the preview. Multiple video/audio files are indexed in the background in
the supplied order. The first source is placed automatically; later sources
enter the library without replacing the montage. Unsupported imports report an
error while preserving existing clips.

Drag a library row onto the timeline to place it. The insertion marker snaps to
boundaries; **Alt** bypasses snapping. Its **+** button or double-click appends
it to the project. Reusing a source creates an independent clip. Placement never
moves existing clips automatically; free space and partial two-clip overlaps
are allowed, nesting and triple overlaps are rejected.

The **first imported video fixes the project resolution**, even if not placed.
Later videos fit with preserved display proportions and black padding. Each
source retains its frame cadence, including variable frame rate. Audio output
is stereo at 48 kHz. Audio-only projects use a 640×360 black canvas until the
first video is imported. Video without audio contributes silence; audio-only
sources contribute black video. Import does not transcode sources.

## Playback and navigation

| Action | Control |
|---|---|
| Play/pause | Space |
| Seek backward/forward 5 seconds | Left / Right |
| Previous/next clip boundary, including gaps | Ctrl+Left / Ctrl+Right |
| Previous/next frame; pause | `<` / `>` or transport buttons |
| Seek to time | Enter seconds or `hh:mm:ss.mmm` in the time field |
| Seek/scrub | Click/drag horizontally on the ruler |
| Seek inside a clip, retaining play/pause | Double-click its body |
| Full screen | F11 or double-click video; Esc exits |

Frame stepping becomes available after indexing. Playback stops at project end.
Full screen shows only video; keyboard controls remain available.
Ruler and clip double-click seeks snap to boundaries within 8 pixels; hold
**Alt** to bypass snapping. Numeric and keyboard seeks do not snap.

During crossfades, preview drops expired video frames to follow the playback
clock instead of accumulating slow motion and then catching up. Demanding media
can still stutter; export retains all scheduled frames.

The speaker mutes without forgetting its level. Listening volume ranges from
**0–200%**, initially **100%**, marked by a red tick. Above 100% can distort
loud material. Listening volume and mute do not affect exports or project data.

## Selection and editing

Click a clip to select without seeking. **Ctrl+click** toggles individual clips.
**Shift+click** selects an inclusive range from the last clicked clip; repeated
Shift clicks keep that anchor. **Ctrl+Shift+click** adds the range.
Drag **down from the ruler** to select clips touched by a rectangle; **Ctrl**
toggles them against the starting selection. With unlinked lanes the rectangle
acts on the active lane: click a clip in that lane first.

**Selected length** sums occupied selected time, excluding gaps and counting
overlaps and linked pairs once. This differs from the export selection window,
which includes everything between its outer boundaries.

| Action | Control and behavior |
|---|---|
| Split | **C** or scissors: split before the displayed frame; it becomes the right clip's first frame. Empty clips are prevented. |
| Delete | **Delete** removes selected clips and leaves gaps. Other clips stay in place. |
| Close a gap | Hover the gap and click its trash icon. Later clips in that lane move left and the project shortens where possible. Undo restores it. |
| Join | **J** joins exactly two selected, adjacent clips, retaining edited source pieces and outer fades. |
| Move | Drag a clip body. Dragging an unselected clip selects and moves it alone. |
| Trim | Drag a clip edge to hide/reveal source material without changing speed or the opposite edge. |
| Duplicate | **D** copies the selected clip, or the clip under the playhead without a selection. |

A selected group moves together only when consecutive in timeline order.
Internal gaps remain; an unselected clip between selected clips blocks movement.
Moves never ripple other clips and produce one undo entry. Edges snap to other
boundaries and the playhead; **Alt** bypasses snapping. Dragging near a viewport
edge scrolls. Partial outer overlaps can create crossfades, but another clip
cannot occupy an internal group gap.

Trimming retains at least one frame and respects available source material.
Joined clips retain their edited trim reserves: re-extending a join restores
retained pieces without resurrecting deliberately deleted material.
Video-derived cuts/trims follow actual source frame edges. Audio-only sources
use decoded audio-block boundaries; individual-sample editing is not provided.

Duplication copies source pieces, names and fades. It uses adjacent space on the
right, otherwise the left; an interior clip needs a sufficiently large gap.
The last clip can extend the project right, and the first can extend it left
when its right side is occupied. Existing clips do not move automatically.

**Edit > Add space at start... / Add space at end...** accepts positive seconds
and adds project-wide black/silent space, including on empty timelines. These
spaces save with the project and can be removed with gap trash buttons.

## Linked and independent lanes

Video and audio start **globally linked**. Selection, cuts, movement, trimming,
duplication, joins, deletion and gap closure affect both partners.
**Edit > Unlink audio** separates the whole project without requiring selection.
There is no relink command; Undo can undo unlinking.

After unlinking, click a clip to choose the active lane. Editing and gap closure
affect only that lane, so close matching gaps separately to preserve alignment.
Library drops affect the destination lane; **+** appends video files to video
and audio files to audio. Seeking, movement and trimming snap across lanes.
Add-space commands still affect both lanes. Additional mixing/overlay lanes
are not available.

## Names, fades and crossfades

With exactly one clip selected, **Properties** shows its name, duration and fades.
Names accept up to 120 characters; Enter or leaving the field commits, and
clearing restores the automatic name. Splits/duplicates inherit names; joins
retain the left clip's name. Hover a clip for its name, range and duration.

Audio and video fade-in/out are independent; video fades to/from black.
Linked mode shows both groups; unlinked mode shows the selected lane's controls.
Sliders cover **0–4 s** in **0.01 s** steps; text fields accept other nonnegative
durations. **0** disables a fade. Enter/leaving a field commits; sliders commit
on release. Fades are linear, clamped to clip duration, and overlapping envelopes
multiply. Splitting keeps outer fades and creates unfaded internal edges.
There is no automatic audio declicking at hard cuts.

Partially overlap two consecutive clips by moving or trimming to create an
automatic **linear crossfade**, shown in lilac. Its duration is the overlap;
separate the clips to remove it. Audio mixes and video dissolves, with manual
fades applied first. Linked lanes transition together; unlinked lanes separately.
Both trim edges remain reachable; dragging within the overlap moves the selected
clip. Nested clips, triple overlaps and splits through a transition are blocked.
Separate the clips before cutting inside that interval.

## Timeline view

| Action | Control |
|---|---|
| Zoom around pointer | Ctrl+wheel |
| Zoom around viewport center | Ctrl++ / Ctrl+-; Ctrl+= also zooms in; magnifying-glass buttons |
| Fit selection, or project with no selection | Z |
| Pan | Wheel or two-finger trackpad scrolling; either gesture axis |
| Pan outside the audio lane | Shift+wheel |
| Enlarge waveform drawing, 1×–256× | Shift+wheel over audio lane |
| Center playhead while zoomed | F or View > Follow |

Follow allows empty space beyond project edges to keep the playhead centered.
The playhead head and line turn orange while Follow is active, in both themes.
Zoom (including trackpad zoom and Z) preserves Follow. Pressing the ruler or a
clip (including its trim edges), rectangle selection, manual panning or scrollbar
use releases it. Import/open resets Follow; it is not saved with projects.

Thumbnails use sparse keyframes and can repeat at high zoom; they are approximate.
The waveform combines both channels' source peaks before fades/listening gain.
Vertical waveform zoom changes only the drawing and resets on import/open.
Background previews are cached under `artifacts/visuals`; hover a clip for
preparation status/errors. They never affect export. Zoomed views have a scrollbar;
narrow windows place scissors, zoom and listening controls in a second row.

## Export

**File > Export video...** opens options, then the native save dialog.
**All** is the default on every opening, even with clips selected. It exports
the full project including edge/internal gaps. **Selected** must be chosen
explicitly: it exports from the first selected start to the last selected end
in the active lane, including gaps and intervening clips. Both lanes render;
missing video/audio becomes black/silence.

**Normalize audio** defaults off. When enabled, **Level** defaults to `-1` dBFS
and accepts finite values at or below `0`. Constant sample-peak gain is measured
after fades/crossfades. **Normalize stereo channels independently**, off by
default, adjusts each channel separately and can change stereo balance. Silence
remains silent. This adds no limiter/compression and does not guarantee true-peak
or decoded AAC peak levels. Normalization does not affect preview or project data.

**Continue** opens the save dialog. Cancelling either dialog creates no export.
Export produces a new H.264/AAC MP4: CRF 18, veryfast, yuv420p, stereo 48 kHz AAC
320 kbit/s, with one final lossy encode. Progress and **Cancel** appear below the
timeline. Existing destinations and source aliases are rejected, including files
created while export runs. Original media remains read-only.
Temporary PCM and transition files require disk space beside the destination;
cancellation or closing stops export and cleans up its temporary directory.

## Current limits

There is no autosave, source relinking, integrated proxy workflow, cut/copy/paste,
installer or automatic updater. Codec support depends on the supplied PyAV/FFmpeg
builds. SDR mono/stereo is the tested scope; HDR/color management, rotation
metadata and multichannel downmix are not broadly validated. High-resolution
transition performance and physical audio-device latency/sync need dedicated
validation. The portable build is experimental; see the
[development guide](DEVELOPMENT.md#portable-build).
