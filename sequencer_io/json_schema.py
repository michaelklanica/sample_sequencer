from __future__ import annotations

from typing import Any

from sequencer_io.json_errors import PatternValidationError
from sequencer_io.snapshot import deserialize_project


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
    """Validate canonical versioned project JSON payloads used for saves."""
    if not isinstance(data, dict):
        raise _err("$", "top-level JSON must be an object")

    schema_version = data.get("schema_version")
    if schema_version != 1:
        raise _err("$.schema_version", "schema_version must be exactly 1")

    if "project" not in data:
        raise _err("$", "missing required field 'project'")
    if "samples" not in data:
        raise _err("$", "missing required field 'samples'")

    project_payload = data["project"]
    if not isinstance(project_payload, dict):
        raise _err("$.project", "project must be an object")
    try:
        deserialize_project(project_payload)
    except Exception as exc:
        raise _err("$.project", str(exc)) from exc

    samples = data["samples"]
    if not isinstance(samples, dict):
        raise _err("$.samples", "samples must be an object")

    sample_folder = samples.get("sample_folder")
    if not isinstance(sample_folder, str) or not sample_folder.strip():
        raise _err("$.samples.sample_folder", "sample_folder must be a non-empty string")

    slot_files = samples.get("slot_files", {})
    if not isinstance(slot_files, dict):
        raise _err("$.samples.slot_files", "slot_files must be an object mapping slot ids to filenames")
    for raw_slot, filename in slot_files.items():
        slot = _validate_slot_id(raw_slot, "$.samples.slot_files")
        if not isinstance(filename, str) or not filename.strip():
            raise _err(f"$.samples.slot_files['{slot}']", "filename must be a non-empty string")

    choke_groups = samples.get("choke_groups", {})
    if not isinstance(choke_groups, dict):
        raise _err("$.samples.choke_groups", "choke_groups must be an object mapping slot ids to choke group ids")
    for raw_slot, raw_group in choke_groups.items():
        slot = _validate_slot_id(raw_slot, "$.samples.choke_groups")
        if isinstance(raw_group, bool) or not isinstance(raw_group, int):
            raise _err(f"$.samples.choke_groups['{slot}']", "choke group must be a positive integer")
        if raw_group <= 0:
            raise _err(f"$.samples.choke_groups['{slot}']", "choke group must be >= 1")
