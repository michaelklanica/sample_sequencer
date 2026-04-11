from __future__ import annotations

import argparse
from pathlib import Path
from typing import TYPE_CHECKING

from sequencer_io import LoadedPatternProject, load_pattern_project_from_json

if TYPE_CHECKING:
    from audio.sample_library import SampleLibrary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sample Sequencer authoring and export tools")
    parser.add_argument("pattern_json", nargs="?", type=Path, help="Optional path to pattern JSON")
    parser.add_argument("--tui", action="store_true", help="Launch interactive Textual editor (default)")
    parser.add_argument("--demo", action="store_true", help="Run the legacy CLI demo mode")
    parser.add_argument("--export", type=Path, help="Export full pattern WAV from JSON project")
    parser.add_argument("--export-bars", type=Path, help="Export per-bar WAV files from JSON project")
    return parser


def _load_library_for_project(pattern_json: Path) -> tuple[LoadedPatternProject, SampleLibrary]:
    from audio.sample_library import SampleLibrary

    project = load_pattern_project_from_json(pattern_json)
    library = SampleLibrary()
    for slot, wav_path in sorted(project.sample_slot_files.items()):
        if wav_path.exists():
            library.load_wav_into_slot(slot, wav_path)
    return project, library


def main() -> None:
    args = build_parser().parse_args()

    if args.export is not None and args.export_bars is not None:
        raise RuntimeError("Use either --export or --export-bars, not both.")

    if args.export is not None:
        from audio.export import export_pattern

        project, library = _load_library_for_project(args.export)
        setattr(project.pattern, "bpm", project.bpm)
        output = export_pattern(
            project.pattern,
            library,
            output_path="exports",
            filename_prefix=project.name or "pattern",
            sample_rate=int(round(library.sample_rate or 44100)),
            normalize=True,
        )
        print(f"Exported full pattern: {output}")
        return

    if args.export_bars is not None:
        from audio.export import export_bars

        project, library = _load_library_for_project(args.export_bars)
        setattr(project.pattern, "bpm", project.bpm)
        outputs = export_bars(
            project.pattern,
            library,
            output_dir="exports",
            filename_prefix=project.name or "pattern",
            sample_rate=int(round(library.sample_rate or 44100)),
            normalize=True,
        )
        print(f"Exported {len(outputs)} bars into exports/")
        return

    if args.demo:
        from interfaces.cli.phase1_demo import run_phase1_demo

        run_phase1_demo()
        return

    from interfaces.textual import launch_textual_app

    launch_textual_app(args.pattern_json)


if __name__ == "__main__":
    main()
