from __future__ import annotations

from pathlib import Path
from typing import Any

from engine.pattern import Bar, Pattern
from engine.project import Project
from engine.rhythm_tree import RhythmNode
from engine.time_signature import TimeSignature


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


def _deserialize_tree(node_data: dict[str, Any], parent: RhythmNode) -> None:
    if "split" in node_data:
        split = int(node_data["split"])
        children = parent.split_equal(split)
        for idx, child_data in enumerate(node_data["children"]):
            _deserialize_tree(child_data, children[idx])
        return

    velocity = float(node_data.get("velocity", 1.0))
    pitch_offset = int(node_data.get("pitch_offset", 0))
    sample_slot = node_data.get("sample_slot")
    if sample_slot is not None:
        sample_slot = int(sample_slot)
    parent.assign(sample_slot=sample_slot, velocity=velocity, pitch_offset=pitch_offset)


def serialize_pattern(pattern: Pattern) -> dict[str, Any]:
    return {
        "name": pattern.name,
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


def deserialize_pattern(payload: dict[str, Any]) -> Pattern:
    bars: list[Bar] = []
    for bar_data in payload["bars"]:
        ts_data = bar_data["time_signature"]
        bar = Bar(time_signature=TimeSignature(ts_data["numerator"], ts_data["denominator"]))
        _deserialize_tree(bar_data["tree"], bar.root)
        bars.append(bar)
    return Pattern(name=str(payload.get("name", "Pattern")), bars=bars)


def serialize_project(project: Project) -> dict[str, Any]:
    return {
        "patterns": [serialize_pattern(pattern) for pattern in project.patterns],
        "current_pattern_index": int(project.current_pattern_index),
        "arrangement": list(project.arrangement),
        "bpm": float(project.bpm),
    }


def deserialize_project(payload: dict[str, Any]) -> Project:
    patterns = [deserialize_pattern(pattern_payload) for pattern_payload in payload["patterns"]]
    return Project(
        patterns=patterns,
        current_pattern_index=int(payload.get("current_pattern_index", 0)),
        arrangement=[int(i) for i in payload.get("arrangement", [0])],
        bpm=float(payload.get("bpm", 120.0)),
    )


def serialize_sample_slot_files(sample_library: Any) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for slot in sample_library.loaded_slots():
        sample = sample_library.slots[slot]
        if sample is None:
            continue
        mapping[str(slot)] = str(sample.path.resolve())
    return mapping


def deserialize_sample_slot_files(payload: dict[str, Any]) -> dict[int, Path]:
    mapping: dict[int, Path] = {}
    for raw_slot, filename in payload.items():
        mapping[int(raw_slot)] = Path(filename).expanduser().resolve()
    return mapping


def serialize_slot_choke_groups(sample_library: Any) -> dict[str, int]:
    return sample_library.serialized_choke_groups()


def deserialize_slot_choke_groups(payload: dict[str, Any]) -> dict[int, int]:
    mapping: dict[int, int] = {}
    for raw_slot, raw_group in payload.items():
        mapping[int(raw_slot)] = int(raw_group)
    return mapping
