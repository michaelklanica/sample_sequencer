from __future__ import annotations

from pathlib import Path

from audio.playback import play_once
from audio.renderer import OfflineRenderer
from audio.sample_library import SampleLibrary
from engine.pattern import Pattern
from engine.timeline import build_timeline_events, pattern_duration_seconds
from engine.timing import bar_duration_seconds, fraction_to_seconds
from sequencer_io import LoadedPatternProject, load_pattern_project_from_json
from sequencer_io.json_errors import PatternJsonError, PatternValidationError


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
    for slot, choke_group in sorted(project.slot_choke_groups.items()):
        library.set_choke_group(slot, choke_group)


def _print_pattern_debug(pattern: Pattern, bpm: float, name: str) -> None:
    playback_order = list(range(len(pattern.bars)))
    print("\nPattern Info:")
    print(f"  name: {name}")
    print(f"  bpm: {bpm}")
    print(f"  bars: {len(pattern.bars)}")
    print(f"  playback_order: {playback_order}")

    print("\nPer-bar Info:")
    for i, bar in enumerate(pattern.bars):
        bar_events = bar.flatten_events(i)
        duration = bar_duration_seconds(bar.time_signature, bpm)
        print(
            f"  bar={i} ts={bar.time_signature.as_text()} duration={duration:.4f}s "
            f"playable_leaf_events={len(bar_events)}"
        )


def _print_timeline_debug(pattern: Pattern, bpm: float) -> None:
    print("\nTimeline Events:")
    timeline_events = build_timeline_events(pattern, bpm)
    for i, event in enumerate(timeline_events):
        bar = pattern.bars[event.source_bar_index]
        bar_secs = bar_duration_seconds(bar.time_signature, bpm)
        dur_s = fraction_to_seconds(event.local_duration_fraction, bar_secs)
        print(
            f"  [{i:02d}] chain_pos={event.chain_position} src_bar={event.source_bar_index} "
            f"abs_start={event.start_seconds:.4f}s local_start={event.local_start_fraction:.6f} "
            f"local_dur={event.local_duration_fraction:.6f} (~{dur_s:.4f}s) "
            f"slot={event.sample_slot} vel={event.velocity:.2f} pitch={event.pitch_offset}"
        )

    print(f"\nTimeline duration: {pattern_duration_seconds(pattern, bpm):.4f}s")


def run_json_demo(json_file: str | Path) -> None:
    try:
        project = load_pattern_project_from_json(json_file)
    except (PatternJsonError, PatternValidationError) as exc:
        raise RuntimeError(f"Failed to load JSON pattern: {exc}") from exc

    print("=== Sample Sequencer Phase 3 JSON Demo ===")
    print(f"JSON Source: {project.source_path}")
    print(f"Pattern Name: {project.name}")
    print(f"BPM: {project.bpm}")
    print(f"Sample Folder: {project.sample_folder}")

    print("\nSample slot mappings:")
    for slot, wav_path in sorted(project.sample_slot_files.items()):
        print(f"  slot {slot:02d} -> {wav_path.name}")

    _print_pattern_debug(project.pattern, project.bpm, project.name)
    _print_timeline_debug(project.pattern, project.bpm)

    library = SampleLibrary()
    _load_samples_from_mapping(library, project)
    print("\n" + library.debug_summary())

    renderer = OfflineRenderer(headroom_gain=0.9)
    result = renderer.render_pattern(project.pattern, library, project.bpm)

    print("\nRender Info:")
    print(f"  sample_rate: {result.sample_rate}")
    print(f"  channels: {result.buffer.shape[1]}")
    print(f"  total_frames: {result.buffer.shape[0]}")
    print(f"  duration_seconds: {result.duration_seconds:.4f}")
    print(f"  peak: {result.peak:.6f}")

    print("\nPlaying rendered pattern chain once...")
    play_once(result.buffer, result.sample_rate)
    print("Done.")
