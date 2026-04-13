from __future__ import annotations

from dataclasses import dataclass

from engine.pattern import Pattern, create_blank_pattern


@dataclass
class Project:
    patterns: list[Pattern]
    current_pattern_index: int
    arrangement: list[int]
    bpm: float

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if not self.patterns:
            raise ValueError("Project must contain at least one pattern.")
        self.bpm = Pattern.clamp_bpm(self.bpm)
        self.current_pattern_index = max(0, min(self.current_pattern_index, len(self.patterns) - 1))
        self.arrangement = self._validated_arrangement(self.arrangement)

    def _validated_arrangement(self, arrangement: list[int]) -> list[int]:
        filtered = [idx for idx in arrangement if 0 <= idx < len(self.patterns)]
        if not filtered:
            filtered = [self.current_pattern_index]
        return filtered

    @property
    def current_pattern(self) -> Pattern:
        return self.patterns[self.current_pattern_index]

    def set_current_pattern_index(self, index: int) -> None:
        if index < 0 or index >= len(self.patterns):
            raise ValueError("Pattern index out of range.")
        self.current_pattern_index = index

    def add_pattern_duplicate_current(self) -> int:
        duplicated = self.current_pattern.clone()
        duplicated.name = self._next_pattern_name()
        self.patterns.append(duplicated)
        return len(self.patterns) - 1

    def _next_pattern_name(self) -> str:
        existing = {pattern.name for pattern in self.patterns}
        n = 1
        while True:
            candidate = f"Pattern {n}"
            if candidate not in existing:
                return candidate
            n += 1

    @classmethod
    def create_default(cls) -> "Project":
        pattern = create_blank_pattern(name="Pattern 1", bpm=120.0, numerator=4, denominator=4)
        return cls(patterns=[pattern], current_pattern_index=0, arrangement=[0], bpm=120.0)
