# Sample Sequencer — Phase 1b JSON Pattern Loading

Phase 1b extends the offline-render-first MVP with **JSON project loading** while preserving the original hardcoded demo path.

## What this phase implements

- Existing Phase 1a core architecture remains intact (`Pattern -> Bar -> RhythmNode`)
- JSON-driven pattern definition
- JSON-driven sample-slot mapping (explicit slot assignment)
- Validation with specific, path-based error messages
- JSON-to-engine translation layer (engine remains decoupled from raw JSON dicts)
- Dual CLI behavior:
  - hardcoded demo: `python main.py`
  - JSON demo: `python main.py assets/patterns/demo_pattern.json`

## Current limitations (intentional)

- No GUI/TUI
- No real-time scheduler/transport
- No loop playback
- No save-back editing to JSON
- No resampling (all loaded WAVs must share the same sample rate)
- Equal subdivisions only (timing is derived from tree structure, not stored absolute timestamps)

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

> Note: all WAV files must use the same sample rate in this phase.

## Run demos

Hardcoded Phase 1a-compatible demo:

```bash
python main.py
```

JSON-driven demo:

```bash
python main.py assets/patterns/demo_pattern.json
```

## JSON workflow

- Put pattern files in `assets/patterns/`.
- Use explicit `sample_slots` mapping for slot IDs `0..15`.
- Set `sample_folder` to a folder containing those WAV files.
- Slot mappings are resolved as:
  - absolute path, if filename is absolute
  - otherwise `sample_folder / filename`
- Relative `sample_folder` values are resolved from the JSON file's directory.

### Example JSON shape

```json
{
  "name": "Demo Pattern",
  "bpm": 120,
  "sample_folder": "../samples",
  "sample_slots": {
    "0": "kick.wav",
    "1": "snare.wav",
    "2": "hat_closed.wav",
    "3": "hat_open.wav"
  },
  "bars": [
    {
      "time_signature": { "numerator": 4, "denominator": 4 },
      "tree": {
        "split": 4,
        "children": [
          { "sample_slot": 0, "velocity": 1.0 },
          {
            "split": 3,
            "children": [
              { "sample_slot": 2, "velocity": 0.7 },
              { "sample_slot": 2, "velocity": 0.55 },
              { "sample_slot": 1, "velocity": 0.9 }
            ]
          },
          {
            "split": 5,
            "children": [
              { "sample_slot": 2, "velocity": 0.5 },
              { "sample_slot": 2, "velocity": 0.5 },
              { "sample_slot": 2, "velocity": 0.5 },
              { "sample_slot": 2, "velocity": 0.5 },
              { "sample_slot": 3, "velocity": 0.8 }
            ]
          },
          { "sample_slot": 0, "velocity": 0.85 }
        ]
      }
    }
  ]
}
```

## JSON semantic rules

- Top-level required fields: `name`, `bpm`, `sample_folder`, `sample_slots`, `bars`
- `bpm` must be a positive number
- `sample_slots` keys must map to integer slot IDs in `0..15`
- `bars` must be a non-empty list
- Each bar must include:
  - `time_signature.numerator` (positive int)
  - `time_signature.denominator` (positive int; validated as power-of-two)
  - `tree`
- Tree node must be exactly one of:
  - Internal node: `split` + `children` and `len(children) == split`
  - Leaf node: optional `sample_slot`, optional `velocity`
- Leaf velocity defaults to `1.0`; if present it must be in `0.0..1.0`
- Leaf with no `sample_slot` is treated as rest

## Notes about included demo pattern

`assets/patterns/demo_pattern.json` includes:

- 4/4 bar
- nested triplet
- nested quintuplet
- multiple sample slots

If your sample filenames differ, edit the JSON `sample_slots` values to match your local WAV filenames.
