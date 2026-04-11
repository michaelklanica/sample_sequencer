from __future__ import annotations

from dataclasses import dataclass

from engine.pattern import Bar
from engine.rhythm_tree import RhythmNode


@dataclass(frozen=True)
class EventValueClipboard:
    sample_slot: int | None
    velocity: float
    pitch_offset: int


def copy_leaf_event_values(node: RhythmNode) -> EventValueClipboard:
    if not node.is_leaf():
        raise ValueError("Can only copy event values from a leaf node.")
    return EventValueClipboard(
        sample_slot=node.sample_slot,
        velocity=node.velocity,
        pitch_offset=node.pitch_offset,
    )


def apply_leaf_event_values(node: RhythmNode, clipboard: EventValueClipboard) -> None:
    if not node.is_leaf():
        raise ValueError("Can only apply event values to a leaf node.")
    node.assign(
        sample_slot=clipboard.sample_slot,
        velocity=clipboard.velocity,
        pitch_offset=clipboard.pitch_offset,
    )


def fill_sibling_leaves(node: RhythmNode, clipboard: EventValueClipboard) -> int:
    if not node.is_leaf():
        raise ValueError("Can only fill siblings from a leaf node.")
    if node.parent is None:
        apply_leaf_event_values(node, clipboard)
        return 1

    filled = 0
    for sibling in node.parent.children:
        if sibling.is_leaf():
            apply_leaf_event_values(sibling, clipboard)
            filled += 1
    return filled


def initialize_bar_grid(bar: Bar, divisions: int) -> None:
    if divisions not in {4, 8, 16}:
        raise ValueError("Grid divisions must be one of: 4, 8, 16.")
    bar.root.reset_to_blank_leaf()
    leaves = [bar.root]
    while len(leaves) < divisions:
        next_leaves: list[RhythmNode] = []
        for leaf in leaves:
            next_leaves.extend(leaf.split_equal(2))
        leaves = next_leaves
