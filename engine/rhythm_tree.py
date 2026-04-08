from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, Optional


@dataclass
class RhythmNode:
    """A recursive equal-subdivision tree node for one bar."""

    start_fraction: float
    duration_fraction: float
    parent: Optional["RhythmNode"] = None
    children: list["RhythmNode"] = field(default_factory=list)
    sample_slot: Optional[int] = None
    velocity: float = 1.0

    def is_leaf(self) -> bool:
        return len(self.children) == 0

    def split_equal(self, parts: int) -> list["RhythmNode"]:
        """Split this leaf into `parts` equal children."""
        if parts < 2:
            raise ValueError("Split parts must be >= 2.")
        if not self.is_leaf():
            raise ValueError("Can only split a leaf node.")

        child_duration = self.duration_fraction / parts
        self.children = []
        # Once a node becomes internal, it no longer holds playable metadata.
        self.sample_slot = None
        self.velocity = 1.0

        for i in range(parts):
            child_start = self.start_fraction + (i * child_duration)
            self.children.append(
                RhythmNode(
                    start_fraction=child_start,
                    duration_fraction=child_duration,
                    parent=self,
                )
            )
        return self.children

    def assign(self, sample_slot: Optional[int], velocity: float = 1.0) -> None:
        if not self.is_leaf():
            raise ValueError("Can only assign sample data to a leaf node.")
        if velocity < 0.0:
            raise ValueError("Velocity must be >= 0.0.")
        self.sample_slot = sample_slot
        self.velocity = velocity

    def iter_leaves(self) -> Iterator["RhythmNode"]:
        if self.is_leaf():
            yield self
            return
        for child in self.children:
            yield from child.iter_leaves()

    def pretty(self, depth: int = 0) -> str:
        indent = "  " * depth
        marker = "leaf" if self.is_leaf() else "node"
        assign = ""
        if self.is_leaf():
            assign = f", slot={self.sample_slot}, vel={self.velocity:.2f}"
        text = (
            f"{indent}- {marker}(start={self.start_fraction:.6f}, "
            f"dur={self.duration_fraction:.6f}{assign})"
        )
        if self.is_leaf():
            return text
        lines = [text]
        for child in self.children:
            lines.append(child.pretty(depth + 1))
        return "\n".join(lines)



def clone_tree(node: RhythmNode, parent: Optional[RhythmNode] = None) -> RhythmNode:
    """Deep-clone a rhythm subtree while preserving timing fractions and assignments."""
    cloned = RhythmNode(
        start_fraction=node.start_fraction,
        duration_fraction=node.duration_fraction,
        parent=parent,
        sample_slot=node.sample_slot,
        velocity=node.velocity,
    )
    cloned.children = [clone_tree(child, parent=cloned) for child in node.children]
    return cloned



def create_bar_root() -> RhythmNode:
    return RhythmNode(start_fraction=0.0, duration_fraction=1.0, parent=None)
