from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from engine.project import Project
from sequencer_io.snapshot import serialize_project


def _serialize_sample_slots(sample_library: Any) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for slot in sample_library.loaded_slots():
        sample = sample_library.slots[slot]
        if sample is None:
            continue
        mapping[str(slot)] = sample.path.resolve().as_posix()
    return mapping


def save_pattern_project_to_json(
    output_path: Path | str,
    *,
    project: Project,
    sample_folder: Path,
    sample_library: Any,
) -> Path:
    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "schema_version": 1,
        "project": serialize_project(project),
        "samples": {
            "sample_folder": sample_folder.resolve().as_posix(),
            "slot_files": _serialize_sample_slots(sample_library),
            "choke_groups": sample_library.serialized_choke_groups(),
        },
    }

    output.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return output
