# Sample Sequencer — Phase 12 Sample Management and Sequencing Ergonomics

Phase 12 improves high-frequency composition workflows in the Textual editor: slot browsing is clearer, sample audition is faster, and repetitive leaf editing requires fewer manual steps.

## What this phase implements

- Startup flow now favors authoring:
  - `python main.py` opens the Textual editor
  - `python main.py path/to/pattern.json` opens that project in the editor
  - `python main.py --demo` runs the legacy CLI demo mode
- New project management actions inside TUI:
  - create new blank pattern with prompts (`n`)
  - load JSON project (`l`)
  - save (`w`) and save-as (`W`)
  - rename pattern (`N`)
  - edit BPM (`B`)
- Better bar authoring:
  - `a` adds a same-time-signature bar
  - `A` adds a bar with prompted custom time signature
- Clear project state visibility in status panel:
  - pattern name
  - BPM
  - current project file path (or `unsaved`)
  - saved/modified state
- Dirty-state tracking for authoring edits:
  - set when structure, metadata, playback-order, bar, or leaf edits occur
  - cleared after successful save and after successful project load
- Safer project replacement flows:
  - new/load prompts for confirmation before replacing unsaved work
- Dedicated sample-slot panel in TUI:
  - always-visible slot list (`00..15`) with filename or empty marker
  - currently selected leaf slot is highlighted
  - includes simple sample metadata (`channels`, `sample_rate`) when loaded
- Faster slot workflow:
  - slot assignment prompt now includes loaded-slot filename + metadata context
  - one-shot sample-slot audition from TUI (`z` for selected leaf slot, `Z` for prompted slot)
  - if realtime playback is active, audition stops transport first for safety
- Leaf event-value ergonomics:
  - copy/paste **event values only** (`sample_slot`, `velocity`, `pitch_offset`) without replacing tree structure
  - fill sibling leaves with copied event values for fast repeated rhythm content
- Quick bar initialization helper:
  - initialize current bar to a 4/8/16 equal-leaf grid
  - treated as structural edit; realtime playback is stopped before applying
- JSON save-back support for full project state:
  - pattern name, BPM, sample folder, sample slot mapping, bars, playback order, leaf event fields

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Add samples

Place WAV files in:

```text
assets/samples/
```

All WAV files should share one sample rate.

## Run modes

Default authoring mode (Textual TUI):

```bash
python main.py
```

Open a specific JSON project in the TUI:

```bash
python main.py assets/patterns/demo_pattern.json
```

Legacy CLI demo mode:

```bash
python main.py --demo
```

CLI WAV export:

```bash
python main.py --export assets/patterns/demo_pattern.json
python main.py --export-bars assets/patterns/demo_pattern.json
```

## TUI key bindings

Project management:

- `n`: new pattern (name, BPM, time signature prompts)
- `l`: load/open JSON pattern
- `w`: save (or save-as if unsaved project)
- `W`: save as
- `N`: rename pattern
- `B`: edit BPM

Bar and structure editing:

- `[` / `]`: previous/next bar
- `a`: add new bar using current bar time signature
- `A`: add new bar with custom time signature
- `d`: duplicate current bar
- `x`: delete current bar (blocked if last bar)
- `2` / `3` / `4` / `5` / `6`: split selected **leaf** into equal parts

Leaf editing:

- `s`: set/clear sample slot (prompt includes loaded slot list)
- `z`: audition currently selected leaf's assigned sample slot (one-shot)
- `Z`: audition prompted sample slot number (one-shot)
- `v`: set velocity (`0.0..1.0`)
- `t`: set pitch offset (`-24..24`)
- `m`: toggle selected leaf rest/active
- `c`: copy selected leaf event values only (`sample_slot`, `velocity`, `pitch_offset`)
- `j`: paste copied event values onto selected leaf (timing/structure unchanged)
- `f`: fill selected leaf's sibling leaves with copied event values
- `y`: copy selected subtree
- `u`: paste copied subtree over selected node
- `r`: reset selected node/subtree to blank leaf
- `o`: edit playback order (`0,1,0,2`; blank clears custom order)
- `g`: quick-initialize current bar to grid (`4`, `8`, or `16` leaves)

Playback and export:

- `b`: render + play current bar once
- `p`: render + play full pattern/chain once
- `space`: toggle real-time current-bar loop
- `P`: toggle real-time natural-order pattern loop
- `C`: toggle real-time chain-aware loop (`playback_order`)
- `e`: export full pattern WAV to `exports/`
- `E`: export per-bar WAV files to `exports/`
- `R`: refresh tree/panels
- `q`: quit

## Real-time safety behavior

The existing edit policy is preserved and extended:

- Live-safe edits (slot/velocity/pitch/rest + event-value paste/fill) can continue while realtime playback runs.
- Transport-invalidating actions stop realtime playback safely before applying edits.
- Project-level edits that stop playback include:
  - new pattern
  - load pattern
  - BPM changes
  - bar additions/deletions/duplication
  - structural tree edits
  - quick grid initialization (`g`)
- Sample audition one-shots (`z` / `Z`) stop realtime playback first when needed, then play the slot preview.

Save/save-as operations do not stop playback by themselves.

## JSON persistence notes

- Save writes complete project state back to JSON.
- `sample_slots` may be empty for blank projects.
- `sample_folder` is written as an absolute path.
- Sample slot paths are written relative to `sample_folder` when possible; otherwise absolute.

## Current limitations (intentional)

- No graphical file browser or drag-and-drop
- No waveform/sample browser widget
- No MIDI input
- No arranger/song redesign
- No plugin hosting or cloud/project-manager UX
