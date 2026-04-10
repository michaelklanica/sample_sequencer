# Sample Sequencer — Phase 8 Chain-Aware Real-Time Transport

Phase 8 extends callback-driven **real-time transport** with explicit chain playback so realtime behavior can match offline chain export semantics when desired.

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
  - stopping playback automatically when the active bar changes (bar-loop mode)
  - stopping playback automatically when pattern structure changes
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

- No live playhead visualization in the TUI
- No realtime hot-reload while editing
- No arranger/song timeline yet
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
