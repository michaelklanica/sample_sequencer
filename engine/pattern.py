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
            if len(self.playback_order) == 0:
                raise ValueError("playback_order cannot be empty when provided.")
            for index in self.playback_order:
                if index < 0 or index >= len(self.bars):
                    raise ValueError(f"playback_order index out of range: {index}")

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
