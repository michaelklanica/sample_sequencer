from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from engine.project import Project
from sequencer_io.json_errors import PatternJsonError
from sequencer_io.snapshot import deserialize_project


@dataclass(frozen=True)
class LoadedPatternProject:
    source_path: Path
    sample_folder: Path
    sample_slot_files: dict[int, Path]
    slot_choke_groups: dict[int, int]
    project: Project


def load_pattern_project_from_json(json_path: Path | str) -> LoadedPatternProject:
    source_path = Path(json_path).expanduser().resolve()
    if not source_path.exists():
        raise PatternJsonError(f"JSON file not found: {source_path}")

    try:
        data = json.loads(source_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PatternJsonError(f"Malformed JSON in {source_path}: {exc}") from exc

    project_payload = data.get("project")
    if project_payload is None:
        raise PatternJsonError("Missing 'project' payload")
    project = deserialize_project(project_payload)

    sample_folder = Path(data.get("sample_folder", "assets/samples")).expanduser().resolve()
    sample_slot_files = {int(k): Path(v).expanduser().resolve() for k, v in data.get("sample_slots", {}).items()}
    slot_choke_groups = {int(k): int(v) for k, v in data.get("slot_choke_groups", {}).items()}

    return LoadedPatternProject(
        source_path=source_path,
        sample_folder=sample_folder,
        sample_slot_files=sample_slot_files,
        slot_choke_groups=slot_choke_groups,
        project=project,
    )
