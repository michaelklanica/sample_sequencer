from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from engine.rhythm_tree import RhythmNode


@dataclass(frozen=True)
class SequencerEvent:
    bar_index: int
    start_fraction: float
    duration_fraction: float
    sample_slot: int | None
    velocity: float


def flatten_leaf_events(root: RhythmNode, bar_index: int = 0) -> list[SequencerEvent]:
    events: list[SequencerEvent] = []
    for leaf in root.iter_leaves():
        if leaf.sample_slot is None:
            continue
        events.append(
            SequencerEvent(
                bar_index=bar_index,
                start_fraction=leaf.start_fraction,
                duration_fraction=leaf.duration_fraction,
                sample_slot=leaf.sample_slot,
                velocity=leaf.velocity,
            )
        )
    events.sort(key=lambda ev: (ev.start_fraction, ev.duration_fraction))
    return events


def sorted_events(events: Iterable[SequencerEvent]) -> list[SequencerEvent]:
    return sorted(events, key=lambda ev: (ev.bar_index, ev.start_fraction, ev.duration_fraction))
