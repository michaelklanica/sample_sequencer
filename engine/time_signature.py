from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TimeSignature:
    """Simple time signature container with basic validation."""

    numerator: int
    denominator: int

    def __post_init__(self) -> None:
        if self.numerator <= 0:
            raise ValueError("Time signature numerator must be > 0.")
        if self.denominator <= 0:
            raise ValueError("Time signature denominator must be > 0.")
        if self.denominator not in {1, 2, 4, 8, 16, 32, 64}:
            raise ValueError(
                "Time signature denominator should be a sensible note value "
                "(1,2,4,8,16,32,64)."
            )

    def as_text(self) -> str:
        return f"{self.numerator}/{self.denominator}"
