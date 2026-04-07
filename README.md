# Sample Sequencer — Phase 2 Textual TUI (One-Bar Interactive Editing)

Phase 2 adds a **Textual terminal UI** for interactive subdivision editing while keeping engine/audio layers UI-agnostic.

## What this phase implements

- Existing architecture remains intact (`Pattern -> Bar -> RhythmNode`)
- Existing CLI demos still available:
  - hardcoded demo: `python main.py`
  - JSON demo: `python main.py assets/patterns/demo_pattern.json`
- New Textual TUI mode:
  - `python main.py --tui`
  - `python main.py --tui assets/patterns/demo_pattern.json`
- Tree inspection and node navigation for current bar
- Leaf-only equal split editing (`2..6`)
- Leaf sample-slot assignment / clear
- Leaf velocity editing (`0.0..1.0`)
- Offline render + one-shot playback from the TUI
- JSON initialization when a JSON path is provided at startup

## Current limitations (intentional)

- Playback is still offline render + one-shot playback
- Practical workflow is still one-bar editing
- No real-time transport/scheduler
- No loop playback
- No song arrangement mode
- No save-back to JSON in this phase (edit/play only)

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

## TUI key bindings

- `Up/Down` (tree-native): navigate nodes
- `2` / `3` / `4` / `5` / `6`: split selected **leaf** into equal parts
- `s`: set/clear sample slot on selected leaf (`0..15`, blank or `x` clears)
- `v`: set velocity on selected leaf (`0.0..1.0`)
- `p`: render + play once
- `r`: refresh tree/panels
- `q`: quit

## Validation behavior

- Split is leaf-only in Phase 2; splitting internal nodes shows a status message.
- Slot assignment is leaf-only and validates `0..15`.
- Velocity edit is leaf-only and validates range `0.0..1.0`.
- Playback shows a status message when no samples are loaded.

## JSON workflow notes

- JSON loading keeps engine decoupled from raw JSON dictionaries.
- If `--tui` is used with a JSON file, the pattern/bpm/sample slot mappings are loaded from that file.
- Save-back JSON writing is deferred in this phase to keep scope focused on interactive edit + playback.
