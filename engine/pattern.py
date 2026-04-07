from __future__ import annotations

from dataclasses import dataclass, field

from engine.events import SequencerEvent, flatten_leaf_events
from engine.rhythm_tree import RhythmNode, create_bar_root
from engine.time_signature import TimeSignature


@dataclass
class Bar:
    time_signature: TimeSignature
    root: RhythmNode = field(default_factory=create_bar_root)

    def flatten_events(self, bar_index: int) -> list[SequencerEvent]:
        return flatten_leaf_events(self.root, bar_index=bar_index)


@dataclass
class Pattern:
    bars: list[Bar]

    def flatten_events(self) -> list[SequencerEvent]:
        events: list[SequencerEvent] = []
        for i, bar in enumerate(self.bars):
            events.extend(bar.flatten_events(i))
        events.sort(key=lambda ev: (ev.bar_index, ev.start_fraction))
        return events

    @classmethod
    def one_bar(cls, time_signature: TimeSignature) -> "Pattern":
        return cls(bars=[Bar(time_signature=time_signature)])
