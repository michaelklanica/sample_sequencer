# Sample Sequencer — Phase 10 Live-Safe Editing During Real-Time Playback

Phase 10 adds an explicit **live-safe editing policy** for the Textual TUI during realtime playback, so you can clearly tell which edits continue playback and which edits intentionally stop transport.

## What this phase implements

- Pattern model supports:
  - multiple bars
  - per-bar time signatures
  - optional `playback_order` bar-chain indices
- Leaf event model supports:
  - `sample_slot`
  - `velocity`
  - `pitch_offset` (integer semitone metadata)
- Rhythm tree editing now supports:
  - rest/mute toggle for leaves
  - subtree copy + paste-over replacement
  - subtree reset to blank leaf
- TUI now supports:
  - playback order prompt editing
  - leaf pitch offset editing
  - current-bar real-time loop playback toggle (`space`)
  - full-pattern real-time loop playback toggle (`P`)
  - chain real-time loop playback toggle (`C`)
  - a dedicated transport panel showing:
    - playback state (`PLAYING` / `STOPPED`)
    - active mode (`BAR LOOP` / `PATTERN LOOP` / `CHAIN LOOP`)
    - loop progress (ASCII progress bar + percentage)
    - active bar during pattern loop
    - active chain step + source bar during chain loop
    - most recent stop reason
- Offline rendering supports:
  - rendering all bars in natural order
  - rendering explicit chained order (e.g. `[0, 1, 0, 2]`)
  - bar-duration-aware timeline assembly across mixed time signatures
- Real-time playback supports:
  - callback-driven output via `sounddevice`
  - looping the currently selected bar
  - looping the full pattern in natural bar order (`bar 0 -> 1 -> ... -> last -> 0`)
  - looping the full pattern using explicit `playback_order` chain mode (`C`)
  - repeated bars in the chain are scheduled as distinct timeline segments
  - mixed time signatures across chain segments are handled by per-segment frame lengths
  - overlapping sample voices
  - safe wraparound trigger scheduling at loop boundaries
  - centralized edit classification (`live_safe` vs `transport_invalidating`)
  - live-safe leaf parameter edits during playback (`velocity`, `sample_slot`, `pitch_offset`, rest toggle)
  - applying leaf parameters at trigger time so future triggers use updated values
  - already-started voices continue unchanged after live-safe edits
  - stopping playback automatically for transport-invalidating edits
  - read-only transport snapshots for UI polling
  - segment-aware position reporting for pattern and chain loops
- JSON format now supports:
  - `bars` as a non-empty list
  - optional `playback_order` with validation
  - optional leaf `pitch_offset` in range `-24..24`
- CLI JSON mode now prints:
  - pattern-level info
  - per-bar duration + leaf event counts
  - timeline events with chain position, absolute times, and pitch offset
  - final render details

## Current limitations (intentional)

- Transport playhead/progress is high-level and approximate (not a sample-accurate visual editor)
- No event-level highlighting in the rhythm tree during playback
- No hot rebuild of timeline for structural edits while playing
- No arranger/song timeline yet
- Structural and timing edits still stop realtime playback automatically
- `pitch_offset` is metadata-only in this phase:
  - stored on leaf events
  - loaded from JSON and editable in TUI
  - printed in debug output
  - **not yet sonically applied during rendering**
- Save-back JSON writing is not implemented in this phase

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

Hardcoded demo:

```bash
python main.py
```

JSON demo:

```bash
python main.py assets/patterns/demo_pattern.json
```

Textual TUI with built-in demo pattern:

```bash
python main.py --tui
```

Textual TUI with JSON pattern:

```bash
python main.py --tui assets/patterns/demo_pattern.json
```

CLI WAV export (optional):

```bash
python main.py --export assets/patterns/demo_pattern.json
python main.py --export-bars assets/patterns/demo_pattern.json
```

## Multi-bar JSON structure

```json
{
  "name": "Pattern Name",
  "bpm": 120,
  "sample_folder": "assets/samples",
  "sample_slots": { "0": "kick.wav", "1": "snare.wav" },
  "playback_order": [0, 1, 0],
  "bars": [
    {
      "time_signature": { "numerator": 4, "denominator": 4 },
      "tree": {
        "split": 4,
        "children": [
          { "sample_slot": 0, "velocity": 1.0, "pitch_offset": 0 },
          { "sample_slot": 1, "velocity": 0.8, "pitch_offset": -2 }
        ]
      }
    }
  ]
}
```

Validation rules:

- `bars` must be non-empty
- `playback_order`, if present, must be non-empty and contain only valid bar indices
- leaf `pitch_offset`, if present, must be an integer in `-24..24`
- each bar keeps existing tree/time-signature validation rules

## TUI key bindings

- `Up/Down` (tree-native): navigate nodes
- `2` / `3` / `4` / `5` / `6`: split selected **leaf** into equal parts
- `s`: set/clear sample slot on selected leaf (`0..15`, blank or `x` clears)
- `v`: set velocity on selected leaf (`0.0..1.0`)
- `t`: set pitch offset on selected leaf (`-24..24`)
- `m`: toggle selected leaf rest/active
- `y`: copy selected subtree into clipboard
- `u`: paste clipboard subtree over selected node
- `r`: reset selected node/subtree to blank leaf
- `o`: edit playback order (`0,1,0,2`; blank clears custom order)
- `[` / `]`: previous/next bar
- `a`: add a new bar after current bar
- `d`: duplicate current bar
- `x`: delete current bar (blocked if it is the last remaining bar)
- `b`: render + play current bar once
- `p`: render + play full pattern/chain once
- `space`: toggle real-time loop playback for current bar
- `P`: toggle real-time loop playback for full pattern (natural bar order)
- `C`: toggle real-time loop playback for explicit playback chain (`playback_order`)
- `e`: export full pattern WAV to `exports/`
- `E`: export each bar WAV to `exports/`
- `R`: refresh tree/panels
- `q`: quit

## Transport panel semantics

When stopped:

- `State: STOPPED`
- `Mode: —`
- `Position: —`

When bar loop is active:

- mode is `BAR LOOP`
- progress shows position through the currently selected bar loop

When natural pattern loop is active:

- mode is `PATTERN LOOP`
- progress shows position through the full pattern loop
- `Bar: X of N` shows which bar segment is currently active

When chain loop is active:

- mode is `CHAIN LOOP`
- progress shows position through the full chain loop
- `Chain Step: X of N` shows active playback-order position
- `Bar Ref: Y` shows the source bar index for that chain segment

The panel also shows:

- `Live-safe edits: ON (velocity/slot/pitch/rest)`

## Editing During Real-Time Playback

### Live-safe edits (playback continues)

These edits do **not** stop realtime playback:

- leaf velocity (`v`)
- leaf sample slot reassignment / clear (`s`)
- leaf pitch offset metadata (`t`)
- leaf rest toggle (`m`, implemented as `sample_slot=None`)
- node selection and other non-transport UI interactions

Behavior: the next trigger reads current leaf values (slot/velocity/pitch metadata). Already-triggered voices are not retroactively modified.

### Transport-invalidating edits (playback auto-stops)

These edits stop realtime playback with a reason message before applying:

- split selected node (`2..6`)
- reset subtree (`r`)
- paste subtree (`u`)
- playback order changes (`o`)
- add / duplicate / delete bar (`a`, `d`, `x`)
- changing selected bar while **bar-loop mode** is active (`[`, `]`)

These edits can change structure/timing/loop length/bar count/chain structure, so transport is invalidated conservatively.

## Exporting Audio

From the TUI:

- `e` → export full pattern (chain-aware)
- `E` → export all bars (natural bar order)

By default, files are written to:

```text
exports/
```

Naming format:

- Full pattern: `{prefix}_bpm{BPM}.wav` (example: `my_pattern_bpm120.wav`)
- Per-bar: `{prefix}_bar{index:02d}_{numerator}-{denominator}.wav`
  (example: `my_pattern_bar01_4-4.wav`)

## Chain-loop behavior

- Chain loop uses `playback_order` exactly as defined (including repeated bar indices).
- If `playback_order` is missing or empty, realtime chain loop refuses to start with a status message.
- If `playback_order` is invalid, realtime chain loop refuses to start with a status message.
- The realtime callback remains timeline-based; chain/pattern/bar differences are resolved during transport preparation.
- Editing pattern structure or playback order while realtime playback is active stops playback immediately.

## Validation behavior

- Split is leaf-only.
- Slot/velocity/pitch editing and rest toggle are leaf-only.
- Copy works on any node; paste requires clipboard content.
- Paste replaces the target subtree and rebinds timing to the target span.
- Reset works on any selected node and creates a blank leaf for that span.
- Playback order prompt validates integer indices and bar bounds.
- Blank playback-order input clears custom order and uses natural bar order.
- Deleting last remaining bar is rejected with status message.
- Missing sample-slot audio does not crash rendering (events are skipped).
- Invalid JSON chain indices fail validation.
