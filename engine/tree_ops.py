from __future__ import annotations

from engine.rhythm_tree import RhythmNode, clone_tree


def parse_node_path(path: str) -> list[int]:
    parts = path.split(".")
    if not parts or parts[0] != "0":
        raise ValueError(f"Invalid path '{path}'. Paths must start with '0'.")
    try:
        return [int(part) for part in parts]
    except ValueError as exc:
        raise ValueError(f"Invalid path '{path}'. Path segments must be integers.") from exc


def get_node_by_path(root: RhythmNode, path: str) -> RhythmNode:
    indices = parse_node_path(path)
    node = root
    for idx in indices[1:]:
        node = node.children[idx]
    return node


def copy_subtree(node: RhythmNode) -> RhythmNode:
    return clone_tree(node)


def reset_subtree(node: RhythmNode) -> None:
    node.reset_to_blank_leaf()


def _clone_with_target_span(
    source_node: RhythmNode,
    source_root: RhythmNode,
    target_parent: RhythmNode | None,
    target_start: float,
    target_duration: float,
) -> RhythmNode:
    source_root_duration = source_root.duration_fraction
    if source_root_duration <= 0:
        start_ratio = 0.0
        duration_ratio = 1.0
    else:
        start_ratio = (source_node.start_fraction - source_root.start_fraction) / source_root_duration
        duration_ratio = source_node.duration_fraction / source_root_duration

    cloned = RhythmNode(
        start_fraction=target_start + (start_ratio * target_duration),
        duration_fraction=duration_ratio * target_duration,
        parent=target_parent,
        sample_slot=source_node.sample_slot,
        velocity=source_node.velocity,
        pitch_offset=source_node.pitch_offset,
    )
    cloned.children = [
        _clone_with_target_span(
            source_node=child,
            source_root=source_root,
            target_parent=cloned,
            target_start=target_start,
            target_duration=target_duration,
        )
        for child in source_node.children
    ]
    return cloned


def paste_subtree_over_target(target: RhythmNode, source_subtree: RhythmNode) -> RhythmNode:
    replacement = _clone_with_target_span(
        source_node=source_subtree,
        source_root=source_subtree,
        target_parent=target.parent,
        target_start=target.start_fraction,
        target_duration=target.duration_fraction,
    )

    if target.parent is None:
        target.children = replacement.children
        for child in target.children:
            child.parent = target
        target.sample_slot = replacement.sample_slot
        target.velocity = replacement.velocity
        target.pitch_offset = replacement.pitch_offset
        return target

    parent = target.parent
    for idx, child in enumerate(parent.children):
        if child is target:
            parent.children[idx] = replacement
            return replacement
    raise ValueError("Target node was not found in its parent children.")
