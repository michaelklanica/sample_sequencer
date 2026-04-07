# Sample Sequencer — Phase 1a Core MVP

Phase 1a is an **offline-render-first** Python MVP for a recursive bar subdivision sample sequencer.

## What this phase implements

- One-bar `Pattern` architecture (prepared for future multi-bar expansion)
- Recursive equal subdivision rhythm tree
- Leaf-node sample assignment (`sample_slot`) and `velocity`
- Flattening leaf nodes into ordered playback events
- 16-slot WAV sample library
- Auto-load WAV files from `assets/samples/`
- Offline render into a NumPy float32 audio buffer
- One-shot playback via `sounddevice`
- Useful console debug output for tree, events, sample state, and render stats

## Current limitations (intentional for Phase 1a)

- No GUI/TUI
- No real-time scheduler/transport
- No loop playback
- No JSON/project serialization
- No resampling (all loaded WAVs must share the same sample rate)

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

At least 3 WAV files are recommended for the included demo pattern.

> Note: all WAV files must use the same sample rate in this phase.

## Run

```bash
python main.py
```

The demo builds a nontrivial rhythm tree (quarters + nested triplets + nested quintuplets), renders one bar offline, prints debug details, then plays it once.
