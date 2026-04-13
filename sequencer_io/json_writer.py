from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from engine.pattern import Pattern
from engine.rhythm_tree import RhythmNode


def _serialize_tree(node: RhythmNode) -> dict[str, Any]:
    if node.is_leaf():
        payload: dict[str, Any] = {
            "velocity": float(node.velocity),
            "pitch_offset": int(node.pitch_offset),
        }
        if node.sample_slot is not None:
            payload["sample_slot"] = int(node.sample_slot)
        return payload

    return {
        "split": len(node.children),
        "children": [_serialize_tree(child) for child in node.children],
    }


def _serialize_sample_slots(sample_library: Any, sample_folder: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for slot in sample_library.loaded_slots():
        sample = sample_library.slots[slot]
        if sample is None:
            continue
        sample_path = sample.path
        try:
            filename = sample_path.resolve().relative_to(sample_folder.resolve()).as_posix()
        except ValueError:
            filename = sample_path.resolve().as_posix()
        mapping[str(slot)] = filename
    return mapping


def save_pattern_project_to_json(
    output_path: Path | str,
    *,
    pattern_name: str,
    bpm: float,
    pattern: Pattern,
    sample_folder: Path,
    sample_library: Any,
) -> Path:
    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    data: dict[str, Any] = {
        "name": pattern_name.strip() or "Untitled Pattern",
        "bpm": float(pattern.bpm),
        "sample_folder": sample_folder.resolve().as_posix(),
        "sample_slots": _serialize_sample_slots(sample_library, sample_folder),
        "bars": [
            {
                "time_signature": {
                    "numerator": int(bar.time_signature.numerator),
                    "denominator": int(bar.time_signature.denominator),
                },
                "tree": _serialize_tree(bar.root),
            }
            for bar in pattern.bars
        ],
    }
    if pattern.playback_order is not None:
        data["playback_order"] = list(pattern.playback_order)

    output.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return output
