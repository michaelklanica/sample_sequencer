# Sample Sequencer — Phase 3 Multi-Bar Patterns + Pattern Chaining

Phase 3 extends the one-bar prototype into a true **multi-bar offline sequencer** while keeping engine, audio, and UI layers separated.

## What this phase implements

- Pattern model now supports:
  - multiple bars
  - per-bar time signatures
  - optional `playback_order` bar-chain indices
- Offline rendering now supports:
  - rendering all bars in natural order
  - rendering explicit chained order (e.g. `[0, 1, 0, 2]`)
  - bar-duration-aware timeline assembly across mixed time signatures
- JSON format now supports:
  - `bars` as a non-empty list
  - optional `playback_order` with validation
- CLI JSON mode now prints:
  - pattern-level info
  - per-bar duration + leaf event counts
  - timeline events with chain position and absolute times
  - final render details
- Textual TUI now supports:
  - viewing all bars and active bar
  - switching bars (`[` and `]`)
  - adding bar (`a`)
  - duplicating bar (`d`)
  - deleting bar safely (`x`, never allows zero bars)
  - playing current bar (`b`)
  - playing full pattern chain (`p`)

## Current limitations (intentional)

- Playback remains offline render + one-shot playback
- No real-time transport/scheduler yet
- No loop transport yet
- No arranger/song timeline yet
- TUI currently shows playback order (read-only in this phase)
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
      "tree": { "split": 4, "children": [ ... ] }
    }
  ]
}
```

Validation rules:

- `bars` must be non-empty
- `playback_order`, if present, must be non-empty and contain only valid bar indices
- each bar keeps existing tree/time-signature validation rules

## TUI key bindings

- `Up/Down` (tree-native): navigate nodes
- `2` / `3` / `4` / `5` / `6`: split selected **leaf** into equal parts
- `s`: set/clear sample slot on selected leaf (`0..15`, blank or `x` clears)
- `v`: set velocity on selected leaf (`0.0..1.0`)
- `[` / `]`: previous/next bar
- `a`: add a new bar after current bar
- `d`: duplicate current bar
- `x`: delete current bar (blocked if it is the last remaining bar)
- `b`: render + play current bar once
- `p`: render + play full pattern/chain once
- `r`: refresh tree/panels
- `q`: quit

## Validation behavior

- Split is leaf-only.
- Slot assignment and velocity editing are leaf-only.
- Deleting last remaining bar is rejected with status message.
- Missing sample-slot audio does not crash rendering (events are skipped).
- Invalid JSON chain indices fail validation.
