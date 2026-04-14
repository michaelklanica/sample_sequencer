from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from engine.pattern import Pattern
from engine.project import Project
from sequencer_io.json_errors import PatternJsonError
from sequencer_io.json_schema import validate_pattern_json
from sequencer_io.snapshot import deserialize_pattern, deserialize_project


@dataclass(frozen=True)
class LoadedPatternProject:
    source_path: Path
    sample_folder: Path
    sample_slot_files: dict[int, Path]
    slot_choke_groups: dict[int, int]
    project: Project

    @property
    def pattern(self) -> Pattern:
        """Compatibility shim for older single-pattern call sites."""
        return self.project.current_pattern

    @property
    def bpm(self) -> float:
        """Compatibility shim for older single-pattern call sites."""
        return self.project.bpm

    @property
    def name(self) -> str:
        """Compatibility shim for older single-pattern call sites."""
        return self.project.current_pattern.name


def _resolve_path(path_value: Path | str, *, base_dir: Path) -> Path:
    raw = Path(path_value).expanduser()
    if raw.is_absolute():
        return raw.resolve()
    return (base_dir / raw).resolve()


def _load_canonical_project_payload(data: dict, source_path: Path) -> LoadedPatternProject:
    validate_pattern_json(data)
    project_payload = data.get("project")
    if project_payload is None:
        raise PatternJsonError("Missing 'project' payload")
    project = deserialize_project(project_payload)

    samples = data.get("samples")
    if samples is None:
        sample_folder_raw = data.get("sample_folder", "assets/samples")
        slot_files_raw = data.get("sample_slots", {})
        choke_groups_raw = data.get("slot_choke_groups", {})
    else:
        sample_folder_raw = samples.get("sample_folder", "assets/samples")
        slot_files_raw = samples.get("slot_files", {})
        choke_groups_raw = samples.get("choke_groups", {})

    sample_folder = _resolve_path(sample_folder_raw, base_dir=source_path.parent)
    sample_slot_files = {
        int(k): _resolve_path(v, base_dir=sample_folder)
        for k, v in slot_files_raw.items()
    }
    slot_choke_groups = {int(k): int(v) for k, v in choke_groups_raw.items()}

    return LoadedPatternProject(
        source_path=source_path,
        sample_folder=sample_folder,
        sample_slot_files=sample_slot_files,
        slot_choke_groups=slot_choke_groups,
        project=project,
    )


def _load_legacy_flat_payload(data: dict, source_path: Path) -> LoadedPatternProject:
    if "bars" not in data:
        raise PatternJsonError("Unrecognized JSON format: expected canonical 'project' or legacy flat pattern keys.")

    pattern = deserialize_pattern({"name": data.get("name", "Pattern"), "bars": data["bars"]})
    bpm = Pattern.clamp_bpm(float(data.get("bpm", 120.0)))
    project = Project(patterns=[pattern], current_pattern_index=0, arrangement=[0], bpm=bpm)

    sample_folder = _resolve_path(data.get("sample_folder", "assets/samples"), base_dir=source_path.parent)
    sample_slot_files = {
        int(k): _resolve_path(v, base_dir=sample_folder)
        for k, v in data.get("sample_slots", {}).items()
    }
    slot_choke_groups = {int(k): int(v) for k, v in data.get("slot_choke_groups", {}).items()}

    return LoadedPatternProject(
        source_path=source_path,
        sample_folder=sample_folder,
        sample_slot_files=sample_slot_files,
        slot_choke_groups=slot_choke_groups,
        project=project,
    )


def load_pattern_project_from_json(json_path: Path | str) -> LoadedPatternProject:
    source_path = Path(json_path).expanduser().resolve()
    if not source_path.exists():
        raise PatternJsonError(f"JSON file not found: {source_path}")

    try:
        data = json.loads(source_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PatternJsonError(f"Malformed JSON in {source_path}: {exc}") from exc

    if not isinstance(data, dict):
        raise PatternJsonError("Top-level JSON must be an object.")

    if "project" in data:
        return _load_canonical_project_payload(data, source_path)
    return _load_legacy_flat_payload(data, source_path)
