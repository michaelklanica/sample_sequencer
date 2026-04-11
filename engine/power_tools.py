from __future__ import annotations

from dataclasses import dataclass
from math import floor
from typing import Literal

from engine.rhythm_tree import RhythmNode


TemplateName = Literal[
    "straight_2",
    "straight_4",
    "triplet_3",
    "quintuplet_5",
    "sextuplet_6",
    "four_last_triplet",
    "four_middle_triplet",
]


@dataclass(frozen=True)
class LeafEventValue:
    sample_slot: int | None
    velocity: float
    pitch_offset: int


def _require_sibling_leaf_group(node: RhythmNode) -> list[RhythmNode]:
    if not node.is_leaf():
        raise ValueError("Operation requires a selected leaf node.")

    if node.parent is None:
        return [node]

    siblings = node.parent.children
    if not siblings:
        raise ValueError("Selected node has no sibling group.")
    if any(not sibling.is_leaf() for sibling in siblings):
        raise ValueError("Operation requires all siblings in the group to be leaves.")
    return siblings


def _leaf_value(node: RhythmNode) -> LeafEventValue:
    return LeafEventValue(sample_slot=node.sample_slot, velocity=node.velocity, pitch_offset=node.pitch_offset)


def _apply_leaf_value(node: RhythmNode, value: LeafEventValue) -> None:
    node.assign(sample_slot=value.sample_slot, velocity=value.velocity, pitch_offset=value.pitch_offset)


def apply_subtree_template(node: RhythmNode, template_name: TemplateName) -> int:
    if not node.is_leaf():
        raise ValueError("Subtree templates can only be applied to leaves.")

    if template_name == "straight_2":
        node.split_equal(2)
    elif template_name == "straight_4":
        node.split_equal(4)
    elif template_name == "triplet_3":
        node.split_equal(3)
    elif template_name == "quintuplet_5":
        node.split_equal(5)
    elif template_name == "sextuplet_6":
        node.split_equal(6)
    elif template_name == "four_last_triplet":
        node.split_equal(4)[-1].split_equal(3)
    elif template_name == "four_middle_triplet":
        node.split_equal(4)[1].split_equal(3)
    else:
        raise ValueError(f"Unknown subtree template '{template_name}'.")

    return len(list(node.iter_leaves()))


def repeat_motif_across_siblings(node: RhythmNode, motif_length: int) -> tuple[int, int]:
    siblings = _require_sibling_leaf_group(node)
    if motif_length < 1:
        raise ValueError("Motif length must be at least 1.")
    if motif_length > len(siblings):
        raise ValueError("Motif length cannot exceed sibling count.")

    motif = [_leaf_value(leaf) for leaf in siblings[:motif_length]]
    for index, leaf in enumerate(siblings):
        _apply_leaf_value(leaf, motif[index % motif_length])
    return motif_length, len(siblings)


def rotate_sibling_event_values(node: RhythmNode, direction: Literal["left", "right"]) -> int:
    siblings = _require_sibling_leaf_group(node)
    if len(siblings) <= 1:
        return len(siblings)

    values = [_leaf_value(leaf) for leaf in siblings]
    if direction == "right":
        rotated = [values[-1], *values[:-1]]
    elif direction == "left":
        rotated = [*values[1:], values[0]]
    else:
        raise ValueError("Direction must be 'left' or 'right'.")

    for leaf, value in zip(siblings, rotated):
        _apply_leaf_value(leaf, value)
    return len(siblings)


def alternate_fill_siblings(node: RhythmNode, event_a: LeafEventValue, event_b: LeafEventValue) -> int:
    siblings = _require_sibling_leaf_group(node)
    for index, leaf in enumerate(siblings):
        _apply_leaf_value(leaf, event_a if index % 2 == 0 else event_b)
    return len(siblings)


def _euclidean_steps(step_count: int, pulses: int) -> list[bool]:
    if step_count <= 0:
        return []
    if pulses <= 0:
        return [False] * step_count
    if pulses >= step_count:
        return [True] * step_count
    return [floor((idx + 1) * pulses / step_count) - floor(idx * pulses / step_count) == 1 for idx in range(step_count)]


def euclidean_fill_siblings(
    node: RhythmNode,
    pulses: int,
    event_value: LeafEventValue,
    rotation: int = 0,
) -> tuple[int, int]:
    siblings = _require_sibling_leaf_group(node)
    step_count = len(siblings)
    if pulses < 0 or pulses > step_count:
        raise ValueError("Pulses must be between 0 and sibling count.")

    hit_pattern = _euclidean_steps(step_count, pulses)
    rotation = rotation % step_count if step_count else 0
    if rotation:
        hit_pattern = hit_pattern[-rotation:] + hit_pattern[:-rotation]

    rest_event = LeafEventValue(sample_slot=None, velocity=event_value.velocity, pitch_offset=event_value.pitch_offset)
    for leaf, is_hit in zip(siblings, hit_pattern):
        _apply_leaf_value(leaf, event_value if is_hit else rest_event)
    return pulses, step_count
