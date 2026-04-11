from __future__ import annotations

from dataclasses import dataclass, field

from engine.events import SequencerEvent, flatten_leaf_events
from engine.rhythm_tree import RhythmNode, clone_tree, create_bar_root
from engine.time_signature import TimeSignature


@dataclass
class Bar:
    time_signature: TimeSignature
    root: RhythmNode = field(default_factory=create_bar_root)

    def flatten_events(self, bar_index: int) -> list[SequencerEvent]:
        return flatten_leaf_events(self.root, bar_index=bar_index)

    def clone(self) -> "Bar":
        return Bar(time_signature=self.time_signature, root=clone_tree(self.root))


@dataclass
class Pattern:
    bars: list[Bar]
    playback_order: list[int] | None = None

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if len(self.bars) == 0:
            raise ValueError("Pattern must contain at least one bar.")

        if self.playback_order is not None:
            self.validate_playback_order(self.playback_order, len(self.bars))

    @staticmethod
    def validate_playback_order(order: list[int], bar_count: int) -> None:
        if len(order) == 0:
            raise ValueError("playback_order cannot be empty when provided.")
        for index in order:
            if index < 0 or index >= bar_count:
                raise ValueError(f"playback_order index out of range: {index}")

    def set_playback_order(self, order: list[int] | None) -> None:
        if order is None:
            self.playback_order = None
            return
        self.validate_playback_order(order, len(self.bars))
        self.playback_order = list(order)

    def remap_playback_order_for_insert(self, insert_index: int) -> None:
        if self.playback_order is None:
            return
        self.playback_order = [idx + 1 if idx >= insert_index else idx for idx in self.playback_order]

    def remap_playback_order_for_delete(self, deleted_index: int) -> None:
        if self.playback_order is None:
            return
        remapped: list[int] = []
        for idx in self.playback_order:
            if idx == deleted_index:
                continue
            remapped.append(idx - 1 if idx > deleted_index else idx)
        self.playback_order = remapped if remapped else None

    def flatten_events(self) -> list[SequencerEvent]:
        events: list[SequencerEvent] = []
        for i, bar in enumerate(self.bars):
            events.extend(bar.flatten_events(i))
        events.sort(key=lambda ev: (ev.bar_index, ev.start_fraction))
        return events

    def resolved_playback_order(self) -> list[int]:
        if self.playback_order is None:
            return list(range(len(self.bars)))
        return list(self.playback_order)

    @classmethod
    def one_bar(cls, time_signature: TimeSignature) -> "Pattern":
        return cls(bars=[Bar(time_signature=time_signature)])


def create_blank_bar(time_signature: TimeSignature) -> Bar:
    """Create a new blank bar with a single default leaf covering the full span."""
    return Bar(time_signature=time_signature)


def create_blank_pattern(name: str, bpm: float, numerator: int, denominator: int) -> Pattern:
    """Create a new single-bar blank pattern for authoring workflows.

    The Pattern model stores bar/tree structure; metadata like name and BPM are
    validated here for caller convenience and tracked by app/project state.
    """
    if not name.strip():
        raise ValueError("Pattern name cannot be empty.")
    if bpm <= 0:
        raise ValueError("BPM must be greater than zero.")

    time_signature = TimeSignature(numerator=numerator, denominator=denominator)
    return Pattern(bars=[create_blank_bar(time_signature=time_signature)])
