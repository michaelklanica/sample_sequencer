from __future__ import annotations

from pathlib import Path

from audio.playback import play_once
from audio.renderer import OfflineRenderer
from audio.sample_library import SampleLibrary
from engine.events import SequencerEvent
from engine.pattern import Pattern
from engine.timing import bar_duration_seconds, fraction_to_seconds
from sequencer_io import LoadedPatternProject, load_pattern_project_from_json
from sequencer_io.json_errors import PatternJsonError, PatternValidationError


def print_events(events: list[SequencerEvent], pattern: Pattern, bpm: float) -> None:
    print("\nFlattened Events:")
    for i, ev in enumerate(events):
        bar = pattern.bars[ev.bar_index]
        bar_secs = bar_duration_seconds(bar.time_signature, bpm)
        start_s = fraction_to_seconds(ev.start_fraction, bar_secs)
        dur_s = fraction_to_seconds(ev.duration_fraction, bar_secs)
        print(
            f"  [{i:02d}] bar={ev.bar_index} "
            f"start={ev.start_fraction:.6f} ({start_s:.4f}s) "
            f"dur={ev.duration_fraction:.6f} ({dur_s:.4f}s) "
            f"slot={ev.sample_slot} vel={ev.velocity:.2f}"
        )


def _load_samples_from_mapping(library: SampleLibrary, project: LoadedPatternProject) -> None:
    if not project.sample_folder.exists() or not project.sample_folder.is_dir():
        raise PatternValidationError(f"sample_folder does not exist or is not a directory: {project.sample_folder}")

    for slot, wav_path in sorted(project.sample_slot_files.items()):
        if not wav_path.exists():
            raise PatternValidationError(
                f"sample slot {slot} references missing WAV file: {wav_path} "
                f"(source JSON: {project.source_path})"
            )
        library.load_wav_into_slot(slot, wav_path)


def run_json_demo(json_file: str | Path) -> None:
    try:
        project = load_pattern_project_from_json(json_file)
    except (PatternJsonError, PatternValidationError) as exc:
        raise RuntimeError(f"Failed to load JSON pattern: {exc}") from exc

    print("=== Sample Sequencer Phase 1b JSON Demo ===")
    print(f"JSON Source: {project.source_path}")
    print(f"Pattern Name: {project.name}")
    print(f"BPM: {project.bpm}")
    print(f"Sample Folder: {project.sample_folder}")
    print(f"Bars Loaded: {len(project.pattern.bars)}")
    print("Behavior: all bars in JSON are flattened and rendered sequentially.")

    print("\nSample slot mappings:")
    for slot, wav_path in sorted(project.sample_slot_files.items()):
        print(f"  slot {slot:02d} -> {wav_path.name}")

    for i, bar in enumerate(project.pattern.bars):
        print(f"\nBar {i}: {bar.time_signature.as_text()}")
        print(bar.root.pretty())

    library = SampleLibrary()
    _load_samples_from_mapping(library, project)
    print("\n" + library.debug_summary())

    events = project.pattern.flatten_events()
    print_events(events, project.pattern, project.bpm)

    renderer = OfflineRenderer(headroom_gain=0.9)
    result = renderer.render_pattern(project.pattern, events, library, project.bpm)

    print("\nRender Info:")
    print(f"  sample_rate: {result.sample_rate}")
    print(f"  channels: {result.buffer.shape[1]}")
    print(f"  total_frames: {result.buffer.shape[0]}")
    print(f"  duration_seconds: {result.duration_seconds:.4f}")
    print(f"  peak: {result.peak:.6f}")

    print("\nPlaying rendered pattern once...")
    play_once(result.buffer, result.sample_rate)
    print("Done.")
