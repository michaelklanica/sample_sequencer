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
    name: str
    bars: list[Bar]

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if len(self.bars) == 0:
            raise ValueError("Pattern must contain at least one bar.")
        if not self.name.strip():
            raise ValueError("Pattern name cannot be empty.")

    @staticmethod
    def clamp_bpm(bpm: float) -> float:
        return max(20.0, min(300.0, float(bpm)))

    def flatten_events(self) -> list[SequencerEvent]:
        events: list[SequencerEvent] = []
        for i, bar in enumerate(self.bars):
            events.extend(bar.flatten_events(i))
        events.sort(key=lambda ev: (ev.bar_index, ev.start_fraction))
        return events

    @property
    def time_signature(self) -> tuple[int, int]:
        ts = self.bars[0].time_signature
        return (ts.numerator, ts.denominator)

    def clone(self) -> "Pattern":
        return Pattern(name=self.name, bars=[bar.clone() for bar in self.bars])

    @classmethod
    def one_bar(cls, time_signature: TimeSignature) -> "Pattern":
        return cls(name="Pattern", bars=[Bar(time_signature=time_signature)])


def create_blank_bar(time_signature: TimeSignature) -> Bar:
    """Create a new blank bar with a single default leaf covering the full span."""
    return Bar(time_signature=time_signature)


def create_blank_pattern(name: str, bpm: float, numerator: int, denominator: int) -> Pattern:
    """Create a new single-bar blank pattern for authoring workflows."""
    if not name.strip():
        raise ValueError("Pattern name cannot be empty.")
    _ = Pattern.clamp_bpm(bpm)

    time_signature = TimeSignature(numerator=numerator, denominator=denominator)
    return Pattern(name=name.strip(), bars=[create_blank_bar(time_signature=time_signature)])
