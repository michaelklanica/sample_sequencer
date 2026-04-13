from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engine.pattern import Bar, Pattern
from engine.rhythm_tree import RhythmNode
from engine.time_signature import TimeSignature
from sequencer_io.json_errors import PatternJsonError, PatternValidationError
from sequencer_io.json_schema import validate_pattern_json


@dataclass(frozen=True)
class LoadedPatternProject:
    source_path: Path
    name: str
    bpm: float
    sample_folder: Path
    sample_slot_files: dict[int, Path]
    pattern: Pattern


def _slot_to_int(raw_slot: Any) -> int:
    return int(raw_slot) if isinstance(raw_slot, str) else raw_slot


def _build_tree(node_data: dict[str, Any], parent: RhythmNode) -> None:
    if "split" in node_data:
        split = int(node_data["split"])
        children = parent.split_equal(split)
        for idx, child_data in enumerate(node_data["children"]):
            _build_tree(child_data, children[idx])
        return

    velocity_raw = node_data.get("velocity", 1.0)
    velocity = float(velocity_raw)
    pitch_offset = int(node_data.get("pitch_offset", 0))
    sample_slot = node_data.get("sample_slot")
    if sample_slot is not None:
        sample_slot = _slot_to_int(sample_slot)
    parent.assign(sample_slot=sample_slot, velocity=velocity, pitch_offset=pitch_offset)


def load_pattern_project_from_json(json_path: Path | str) -> LoadedPatternProject:
    source_path = Path(json_path).expanduser().resolve()
    if not source_path.exists():
        raise PatternJsonError(f"JSON file not found: {source_path}")

    try:
        raw_text = source_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PatternJsonError(f"Failed to read JSON file: {source_path}") from exc

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise PatternJsonError(
            f"Malformed JSON in {source_path} (line {exc.lineno}, column {exc.colno}): {exc.msg}"
        ) from exc

    validate_pattern_json(data)

    bars: list[Bar] = []
    for bar_data in data["bars"]:
        ts_data = bar_data["time_signature"]
        time_signature = TimeSignature(ts_data["numerator"], ts_data["denominator"])
        bar = Bar(time_signature=time_signature)
        _build_tree(bar_data["tree"], bar.root)
        bars.append(bar)

    sample_folder_raw = Path(data["sample_folder"])
    if sample_folder_raw.is_absolute():
        sample_folder = sample_folder_raw
    else:
        sample_folder = (source_path.parent / sample_folder_raw).resolve()

    sample_slot_files: dict[int, Path] = {}
    for raw_slot, filename in data["sample_slots"].items():
        slot = _slot_to_int(raw_slot)
        file_path = Path(filename)
        if file_path.is_absolute():
            resolved = file_path
        else:
            resolved = (sample_folder / file_path).resolve()
        sample_slot_files[slot] = resolved

    pattern = Pattern(bars=bars, bpm=float(data["bpm"]), playback_order=data.get("playback_order"))
    return LoadedPatternProject(
        source_path=source_path,
        name=data["name"],
        bpm=pattern.bpm,
        sample_folder=sample_folder,
        sample_slot_files=sample_slot_files,
        pattern=pattern,
    )
