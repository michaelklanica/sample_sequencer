from __future__ import annotations

from engine.time_signature import TimeSignature


def bar_quarter_note_count(time_signature: TimeSignature) -> float:
    """Return how many quarter notes are in one bar."""
    return time_signature.numerator * (4.0 / time_signature.denominator)


def bar_duration_seconds(time_signature: TimeSignature, bpm: float) -> float:
    """Compute one bar duration at the given BPM.

    BPM is treated as quarter-note BPM.
    """
    if bpm <= 0:
        raise ValueError("BPM must be > 0.")
    quarter_notes = bar_quarter_note_count(time_signature)
    return quarter_notes * (60.0 / bpm)


def fraction_to_seconds(fraction_of_bar: float, full_bar_seconds: float) -> float:
    return fraction_of_bar * full_bar_seconds
