from __future__ import annotations

from typing import Literal

EditClass = Literal["live_safe", "transport_invalidating"]


_LIVE_SAFE_ACTIONS: set[str] = {
    "set_velocity",
    "set_slot",
    "set_pitch_offset",
    "toggle_rest",
    "paste_event_values",
    "fill_sibling_event_values",
    "repeat_motif",
    "rotate_sibling_values",
    "alternate_fill_siblings",
    "euclidean_fill_siblings",
    "select_node",
    "refresh_ui",
}


_INVALIDATION_REASONS: dict[str, str] = {
    "split_selected": "split changed loop structure",
    "reset_subtree": "subtree reset changed loop structure",
    "paste_subtree": "subtree paste changed loop structure",
    "edit_playback_order": "playback order changed",
    "add_bar": "bar count changed",
    "duplicate_bar": "bar count changed",
    "delete_bar": "bar count changed",
    "set_time_signature": "time signature changed",
    "set_transport_mode": "transport mode changed",
    "select_bar": "active bar changed while bar-loop mode was active",
    "new_pattern": "pattern replaced",
    "load_pattern": "pattern replaced",
    "set_bpm": "tempo changed",
    "initialize_grid": "grid initialization changed loop structure",
    "apply_subtree_template": "subtree template changed loop structure",
}


def classify_edit(action_name: str) -> EditClass:
    """Classify an edit action for realtime playback safety."""
    if action_name in _LIVE_SAFE_ACTIONS:
        return "live_safe"
    return "transport_invalidating"


def invalidation_reason(action_name: str) -> str:
    return _INVALIDATION_REASONS.get(action_name, "transport structure changed")
