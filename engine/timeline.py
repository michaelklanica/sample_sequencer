from __future__ import annotations

from dataclasses import dataclass

from engine.events import SequencerEvent
from engine.pattern import Pattern
from engine.timing import bar_duration_seconds, fraction_to_seconds


@dataclass(frozen=True)
class TimelineEvent:
    chain_position: int
    source_bar_index: int
    start_seconds: float
    local_start_fraction: float
    local_duration_fraction: float
    sample_slot: int | None
    velocity: float
    pitch_offset: int


def build_timeline_events(pattern: Pattern, bpm: float) -> list[TimelineEvent]:
    local_events = pattern.flatten_events()
    events_by_bar: dict[int, list[SequencerEvent]] = {i: [] for i in range(len(pattern.bars))}
    for event in local_events:
        events_by_bar[event.bar_index].append(event)

    timeline_events: list[TimelineEvent] = []
    chain_indices = pattern.resolved_playback_order()
    current_offset_seconds = 0.0

    for chain_position, bar_index in enumerate(chain_indices):
        bar = pattern.bars[bar_index]
        bar_seconds = bar_duration_seconds(bar.time_signature, bpm)
        for event in events_by_bar.get(bar_index, []):
            timeline_events.append(
                TimelineEvent(
                    chain_position=chain_position,
                    source_bar_index=bar_index,
                    start_seconds=current_offset_seconds + fraction_to_seconds(event.start_fraction, bar_seconds),
                    local_start_fraction=event.start_fraction,
                    local_duration_fraction=event.duration_fraction,
                    sample_slot=event.sample_slot,
                    velocity=event.velocity,
                    pitch_offset=event.pitch_offset,
                )
            )
        current_offset_seconds += bar_seconds

    timeline_events.sort(key=lambda event: event.start_seconds)
    return timeline_events


def pattern_duration_seconds(pattern: Pattern, bpm: float) -> float:
    return sum(
        bar_duration_seconds(pattern.bars[bar_index].time_signature, bpm)
        for bar_index in pattern.resolved_playback_order()
    )
