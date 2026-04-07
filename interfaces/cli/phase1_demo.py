from __future__ import annotations

from pathlib import Path

from audio.playback import play_once
from audio.renderer import OfflineRenderer
from audio.sample_library import SampleLibrary
from engine.events import SequencerEvent
from engine.pattern import Pattern
from engine.time_signature import TimeSignature
from engine.timing import bar_duration_seconds, fraction_to_seconds


def build_demo_pattern() -> Pattern:
    pattern = Pattern.one_bar(TimeSignature(4, 4))
    root = pattern.bars[0].root

    quarters = root.split_equal(4)
    triplet_group = quarters[1].split_equal(3)
    quint_group = quarters[3].split_equal(5)

    quarters[0].assign(sample_slot=0, velocity=1.0)
    triplet_group[0].assign(sample_slot=2, velocity=0.8)
    triplet_group[1].assign(sample_slot=2, velocity=0.6)
    triplet_group[2].assign(sample_slot=1, velocity=0.9)

    quarters[2].assign(sample_slot=0, velocity=1.0)

    for i, node in enumerate(quint_group):
        # alternating accent hats/snare-ish source if available
        slot = 2 if i % 2 == 0 else 1
        velocity = 0.55 + 0.1 * (i % 3)
        node.assign(sample_slot=slot, velocity=velocity)

    return pattern


def ensure_minimum_slots(library: SampleLibrary, min_count: int = 3) -> None:
    if len(library.loaded_slots()) < min_count:
        raise RuntimeError(
            "Not enough WAV samples loaded for demo. "
            f"Expected at least {min_count} files in assets/samples/."
        )


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


def run_phase1_demo() -> None:
    bpm = 120.0
    pattern = build_demo_pattern()
    bar = pattern.bars[0]

    print("=== Sample Sequencer Phase 1a Demo ===")
    print(f"Time Signature: {bar.time_signature.as_text()}")
    print(f"BPM: {bpm}")
    print("\nSubdivision Tree:")
    print(bar.root.pretty())

    library = SampleLibrary()
    sample_dir = Path("assets/samples")
    loaded_count = library.auto_load_folder(sample_dir)
    print(f"\nLoaded {loaded_count} sample(s) from {sample_dir}.")
    ensure_minimum_slots(library, min_count=3)

    # Explicit override support demo (safe no-op if file missing)
    explicit_override = sample_dir / "kick.wav"
    if explicit_override.exists():
        library.load_wav_into_slot(0, explicit_override)

    print("\n" + library.debug_summary())

    events = pattern.flatten_events()
    print_events(events, pattern, bpm)

    renderer = OfflineRenderer(headroom_gain=0.9)
    result = renderer.render_pattern(pattern, events, library, bpm)

    print("\nRender Info:")
    print(f"  sample_rate: {result.sample_rate}")
    print(f"  channels: {result.buffer.shape[1]}")
    print(f"  total_frames: {result.buffer.shape[0]}")
    print(f"  duration_seconds: {result.duration_seconds:.4f}")
    print(f"  peak: {result.peak:.6f}")

    print("\nPlaying rendered bar once...")
    play_once(result.buffer, result.sample_rate)
    print("Done.")


if __name__ == "__main__":
    run_phase1_demo()
