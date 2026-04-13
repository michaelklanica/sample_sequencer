from __future__ import annotations

from typing import Any

from sequencer_io.json_errors import PatternValidationError


def _err(path: str, message: str) -> PatternValidationError:
    return PatternValidationError(f"{path}: {message}")


def _is_power_of_two(value: int) -> bool:
    return value > 0 and (value & (value - 1) == 0)


def _validate_slot_id(raw_slot: Any, path: str) -> int:
    if isinstance(raw_slot, bool):
        raise _err(path, "slot id must be an integer 0..15, not boolean")

    if isinstance(raw_slot, int):
        slot = raw_slot
    elif isinstance(raw_slot, str):
        try:
            slot = int(raw_slot)
        except ValueError as exc:
            raise _err(path, f"slot id '{raw_slot}' is not an integer") from exc
    else:
        raise _err(path, "slot id must be an integer-like string or integer")

    if not (0 <= slot <= 15):
        raise _err(path, f"slot id {slot} out of range (expected 0..15)")
    return slot


def _validate_leaf_node(node: dict[str, Any], path: str) -> None:
    if "sample_slot" in node:
        _validate_slot_id(node["sample_slot"], f"{path}.sample_slot")

    if "velocity" in node:
        velocity = node["velocity"]
        if isinstance(velocity, bool) or not isinstance(velocity, (int, float)):
            raise _err(f"{path}.velocity", "velocity must be a number in range 0.0..1.0")
        if not (0.0 <= float(velocity) <= 1.0):
            raise _err(f"{path}.velocity", f"velocity {velocity} out of range (expected 0.0..1.0)")

    if "pitch_offset" in node:
        pitch_offset = node["pitch_offset"]
        if isinstance(pitch_offset, bool) or not isinstance(pitch_offset, int):
            raise _err(f"{path}.pitch_offset", "pitch_offset must be an integer in range -24..24")
        if not (-24 <= pitch_offset <= 24):
            raise _err(
                f"{path}.pitch_offset",
                f"pitch_offset {pitch_offset} out of range (expected -24..24)",
            )


def _validate_tree_node(node: Any, path: str) -> None:
    if not isinstance(node, dict):
        raise _err(path, "node must be an object")

    has_internal_fields = "split" in node or "children" in node
    has_leaf_fields = "sample_slot" in node or "velocity" in node or "pitch_offset" in node

    if has_internal_fields and has_leaf_fields:
        raise _err(
            path,
            "node cannot mix internal fields (split/children) with leaf fields (sample_slot/velocity/pitch_offset)",
        )

    if has_internal_fields:
        if "split" not in node or "children" not in node:
            raise _err(path, "internal node must include both 'split' and 'children'")

        split = node["split"]
        if isinstance(split, bool) or not isinstance(split, int):
            raise _err(f"{path}.split", "split must be an integer")
        if split < 2:
            raise _err(f"{path}.split", "split must be >= 2")

        children = node["children"]
        if not isinstance(children, list):
            raise _err(f"{path}.children", "children must be a list")
        if len(children) != split:
            raise _err(
                f"{path}.children",
                f"children length ({len(children)}) must equal split ({split})",
            )

        for idx, child in enumerate(children):
            _validate_tree_node(child, f"{path}.children[{idx}]")
        return

    _validate_leaf_node(node, path)


def validate_pattern_json(data: Any) -> None:
    if not isinstance(data, dict):
        raise _err("$", "top-level JSON must be an object")

    required_keys = ["name", "bpm", "sample_folder", "sample_slots", "bars"]
    for key in required_keys:
        if key not in data:
            raise _err("$", f"missing required field '{key}'")

    if not isinstance(data["name"], str) or not data["name"].strip():
        raise _err("$.name", "name must be a non-empty string")

    bpm = data["bpm"]
    if isinstance(bpm, bool) or not isinstance(bpm, (int, float)):
        raise _err("$.bpm", "bpm must be a number in range 20..300")
    if not (20.0 <= float(bpm) <= 300.0):
        raise _err("$.bpm", f"bpm must be in range 20..300 (got {bpm})")

    sample_folder = data["sample_folder"]
    if not isinstance(sample_folder, str) or not sample_folder.strip():
        raise _err("$.sample_folder", "sample_folder must be a non-empty string")

    sample_slots = data["sample_slots"]
    if not isinstance(sample_slots, dict):
        raise _err("$.sample_slots", "sample_slots must be an object mapping slot ids to filenames")

    for raw_slot, filename in sample_slots.items():
        slot = _validate_slot_id(raw_slot, "$.sample_slots")
        if not isinstance(filename, str) or not filename.strip():
            raise _err(f"$.sample_slots['{slot}']", "filename must be a non-empty string")

    slot_choke_groups = data.get("slot_choke_groups")
    if slot_choke_groups is not None:
        if not isinstance(slot_choke_groups, dict):
            raise _err("$.slot_choke_groups", "slot_choke_groups must be an object mapping slot ids to choke group ids")
        for raw_slot, raw_group in slot_choke_groups.items():
            slot = _validate_slot_id(raw_slot, "$.slot_choke_groups")
            if isinstance(raw_group, bool) or not isinstance(raw_group, int):
                raise _err(
                    f"$.slot_choke_groups['{slot}']",
                    "choke group must be a positive integer",
                )
            if raw_group <= 0:
                raise _err(f"$.slot_choke_groups['{slot}']", "choke group must be >= 1")


    playback_order = data.get("playback_order")
    if playback_order is not None:
        if not isinstance(playback_order, list) or len(playback_order) == 0:
            raise _err("$.playback_order", "playback_order must be a non-empty list when provided")
        for idx, bar_index in enumerate(playback_order):
            if isinstance(bar_index, bool) or not isinstance(bar_index, int):
                raise _err(f"$.playback_order[{idx}]", "bar index must be an integer")
            if bar_index < 0:
                raise _err(f"$.playback_order[{idx}]", "bar index must be >= 0")

    bars = data["bars"]
    if not isinstance(bars, list) or len(bars) == 0:
        raise _err("$.bars", "bars must be a non-empty list")

    for bar_idx, bar in enumerate(bars):
        bpath = f"$.bars[{bar_idx}]"
        if not isinstance(bar, dict):
            raise _err(bpath, "bar must be an object")

        if "time_signature" not in bar:
            raise _err(bpath, "missing required field 'time_signature'")
        if "tree" not in bar:
            raise _err(bpath, "missing required field 'tree'")

        ts = bar["time_signature"]
        if not isinstance(ts, dict):
            raise _err(f"{bpath}.time_signature", "time_signature must be an object")

        if "numerator" not in ts or "denominator" not in ts:
            raise _err(f"{bpath}.time_signature", "time_signature requires numerator and denominator")

        numerator = ts["numerator"]
        denominator = ts["denominator"]
        if isinstance(numerator, bool) or not isinstance(numerator, int) or numerator <= 0:
            raise _err(f"{bpath}.time_signature.numerator", "numerator must be a positive integer")
        if isinstance(denominator, bool) or not isinstance(denominator, int) or denominator <= 0:
            raise _err(f"{bpath}.time_signature.denominator", "denominator must be a positive integer")
        if not _is_power_of_two(denominator):
            raise _err(f"{bpath}.time_signature.denominator", "denominator should be a power of two")

        _validate_tree_node(bar["tree"], f"{bpath}.tree")

    if playback_order is not None:
        for idx, bar_index in enumerate(playback_order):
            if bar_index >= len(bars):
                raise _err(
                    f"$.playback_order[{idx}]",
                    f"bar index {bar_index} out of range for {len(bars)} bars",
                )
