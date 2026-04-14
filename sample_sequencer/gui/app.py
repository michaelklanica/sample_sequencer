from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog, QMessageBox

from audio.export import export_arrangement, export_pattern
from audio.playback import play_once
from audio.realtime import RealtimeLooper
from audio.sample_library import MAX_SLOTS, SampleLibrary
from engine.edit_policy import classify_edit, invalidation_reason
from engine.project import Project
from engine.power_tools import apply_subtree_template
from engine.rhythm_tree import RhythmNode
from sample_sequencer.gui.export_dialog import ExportDialog
from sample_sequencer.gui.main_window import MainWindow
from sample_sequencer.gui.template_defs import TEMPLATE_BY_ID
from sample_sequencer.gui.undo_manager import UndoManager
from sequencer_io import (
    LoadedPatternProject,
    deserialize_project,
    deserialize_sample_slot_files,
    deserialize_slot_choke_groups,
    load_pattern_project_from_json,
    save_pattern_project_to_json,
    serialize_project,
    serialize_sample_slot_files,
    serialize_slot_choke_groups,
)


class SequencerGuiApp:
    def __init__(self, project: LoadedPatternProject | None = None) -> None:
        self.sample_library = SampleLibrary()
        if project is None:
            self.project = Project.create_default()
            self.sample_folder = Path("assets/samples").resolve()
            self.project_path: Path | None = None
        else:
            self.project = project.project
            self.sample_folder = project.sample_folder
            self.project_path = project.source_path
            for slot, wav_path in project.sample_slot_files.items():
                if wav_path.exists():
                    self.sample_library.load_wav_into_slot(slot, wav_path)
            for slot, choke_group in project.slot_choke_groups.items():
                self.sample_library.set_choke_group(slot, choke_group)

        self.current_bar_index: int = 0
        self.selected_node: RhythmNode | None = None
        self.selected_node_path: str | None = None
        self.transport_mode = "bar"
        self.export_mode = "truncate"
        self._ui_status_message: str | None = None
        self._is_dirty = False
        self.undo_manager = UndoManager(max_history=100)

        self.realtime_looper = RealtimeLooper(sample_library=self.sample_library, bpm=self.project.bpm)

        self.window = MainWindow()
        self._wire_events()
        self.refresh_ui()

        self.timer = QTimer()
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._refresh_transport)
        self.timer.start()

    def _wire_events(self) -> None:
        w = self.window
        w.pattern_panel.patternSelected.connect(self._set_current_pattern)
        w.pattern_panel.createClicked.connect(self._create_pattern)
        w.pattern_panel.renameClicked.connect(self._rename_pattern)
        w.pattern_panel.deleteClicked.connect(self._delete_pattern)
        w.arrangement_panel.addClicked.connect(self._arrangement_add_step)
        w.arrangement_panel.removeClicked.connect(self._arrangement_remove_step)
        w.arrangement_panel.moveUpClicked.connect(self._arrangement_move_up)
        w.arrangement_panel.moveDownClicked.connect(self._arrangement_move_down)
        w.bar_list_panel.barSelected.connect(self.set_current_bar)
        w.tree_panel.nodeSelected.connect(self._on_widget_selected_node)
        w.timeline_widget.blockSelected.connect(self._on_widget_selected_node)
        w.timeline_widget.splitRequested.connect(self._split_path)
        w.timeline_widget.clearRequested.connect(self._clear_path)
        w.timeline_widget.slotAssignRequested.connect(self._assign_slot_to_path)
        w.timeline_widget.templateRequested.connect(self._apply_template_to_path)

        w.inspector_panel.slotChanged.connect(self._set_slot_for_selected)
        w.inspector_panel.velocityChanged.connect(self._set_velocity_for_selected)
        w.inspector_panel.pitchChanged.connect(self._set_pitch_for_selected)
        w.inspector_panel.splitRequested.connect(self._split_selected)
        w.inspector_panel.clearRequested.connect(self._reset_selected_subtree)
        w.inspector_panel.templateRequested.connect(self._apply_template_to_selected)
        w.inspector_panel.bpmChanged.connect(self.set_bpm)
        w.inspector_panel.chokeGroupChanged.connect(self._set_choke_group_for_selected_slot)

        w.slot_panel.slotClicked.connect(self._assign_slot_from_panel)
        w.slot_panel.slotDoubleClicked.connect(self._audition_slot)

        w.modeChanged.connect(self._set_mode)
        w.playClicked.connect(self._play)
        w.stopClicked.connect(self._stop)
        w.newClicked.connect(self._new_project)
        w.undoClicked.connect(self._undo)
        w.redoClicked.connect(self._redo)
        w.saveClicked.connect(self._save_project)
        w.loadClicked.connect(self._load_project)
        w.exportClicked.connect(self._export)
        w.exportModeChanged.connect(self._set_export_mode)
        w.loadSamplesClicked.connect(self._choose_and_load_samples)
        w.reloadSamplesClicked.connect(self._reload_samples)
        w.bpmChanged.connect(self.set_bpm)

    def _iter_nodes(self, node: RhythmNode, path: str) -> list[tuple[str, RhythmNode]]:
        nodes = [(path, node)]
        for idx, child in enumerate(node.children):
            nodes.extend(self._iter_nodes(child, f"{path}.{idx}"))
        return nodes

    def _node_map(self) -> dict[str, RhythmNode]:
        return dict(self._iter_nodes(self.project.current_pattern.bars[self.current_bar_index].root, "0"))

    def _path_for_node(self, target: RhythmNode | None) -> str | None:
        if target is None:
            return None
        for path, node in self._node_map().items():
            if node is target:
                return path
        return None

    def _normalize_selection(self, path: str | None, node: RhythmNode | None) -> tuple[str | None, RhythmNode | None]:
        node_map = self._node_map()
        if path and path in node_map:
            resolved = node_map[path]
            if node is None or node is resolved:
                return path, resolved
        if node is not None:
            resolved_path = self._path_for_node(node)
            if resolved_path is not None:
                return resolved_path, node_map[resolved_path]
        return None, None

    def _ensure_valid_current_indices(self) -> None:
        if not self.project.patterns:
            raise RuntimeError("Project must contain at least one pattern.")
        self.project.current_pattern_index = max(0, min(self.project.current_pattern_index, len(self.project.patterns) - 1))
        pattern = self.project.current_pattern
        if not pattern.bars:
            raise RuntimeError("Current pattern must contain at least one bar.")
        self.current_bar_index = max(0, min(self.current_bar_index, len(pattern.bars) - 1))

    def _selection_belongs_to_current_bar(self) -> bool:
        if self.selected_node is None or self.selected_node_path is None:
            return False
        node_map = self._node_map()
        return node_map.get(self.selected_node_path) is self.selected_node

    def _stop_realtime_for_pattern_change(self, reason: str) -> None:
        if self.realtime_looper.is_playing:
            self.realtime_looper.stop(reason=reason)

    def set_current_bar(self, bar_index: int) -> None:
        if bar_index < 0 or bar_index >= len(self.project.current_pattern.bars):
            return
        if self.current_bar_index == bar_index:
            return
        self._apply_edit_policy("select_bar")
        self.current_bar_index = bar_index
        self.clear_selection(refresh=False)
        self.refresh_bar_views()
        self.refresh_selection_views()

    def set_selected_node(self, node: RhythmNode | None, path: str | None = None) -> None:
        normalized_path, normalized_node = self._normalize_selection(path=path, node=node)
        if self.selected_node is normalized_node and self.selected_node_path == normalized_path:
            return
        self.selected_node = normalized_node
        self.selected_node_path = normalized_path
        self.refresh_selection_views()

    def clear_selection(self, refresh: bool = True) -> None:
        if self.selected_node is None and self.selected_node_path is None:
            return
        self.selected_node = None
        self.selected_node_path = None
        if refresh:
            self.refresh_selection_views()

    def refresh_bar_views(self) -> None:
        self._ensure_valid_current_indices()
        bar = self.project.current_pattern.bars[self.current_bar_index]
        self.window.bar_list_panel.set_selected_bar(self.current_bar_index)
        self.window.tree_panel.set_bar(bar, self.selected_node_path)
        self.window.timeline_widget.set_bar(bar)

    def _selected_slot_for_ui(self) -> int | None:
        if self.selected_node is None or not self.selected_node.is_leaf():
            return None
        return self.selected_node.sample_slot

    def _selected_leaf(self) -> tuple[str, RhythmNode] | None:
        if self.selected_node is None or self.selected_node_path is None or not self.selected_node.is_leaf():
            return None
        return self.selected_node_path, self.selected_node

    def _first_leaf_under_path(self, path: str) -> tuple[str, RhythmNode] | None:
        node = self._node_map().get(path)
        if node is None:
            return None
        current_path = path
        current_node = node
        while not current_node.is_leaf():
            if not current_node.children:
                return None
            current_node = current_node.children[0]
            current_path = f"{current_path}.0"
        return current_path, current_node

    def refresh_selection_views(self) -> None:
        if not self._selection_belongs_to_current_bar():
            self.selected_node = None
            self.selected_node_path = None
        self.window.tree_panel.set_selected_path(self.selected_node_path)
        self.window.timeline_widget.set_selected_node(self.selected_node, self.selected_node_path)
        self.window.inspector_panel.set_node(self.current_bar_index, self.selected_node_path, self.selected_node)
        self.window.slot_panel.set_assignment_enabled(self._selected_leaf() is not None)
        self.window.slot_panel.set_selected_slot(self._selected_slot_for_ui())
        selected_slot = self._selected_slot_for_ui()
        selected_choke = self.sample_library.choke_group(selected_slot) if selected_slot is not None else None
        self.window.inspector_panel.set_selected_slot_choke_group(selected_choke)
        self._refresh_transport()

    def refresh_ui(self) -> None:
        self._ensure_valid_current_indices()
        names = [pattern.name for pattern in self.project.patterns]
        self.window.pattern_panel.set_patterns(names, self.project.current_pattern_index)
        self.window.arrangement_panel.set_arrangement(self.project.arrangement, names)
        self.window.bar_list_panel.set_pattern(self.project.current_pattern, self.current_bar_index)
        self.window.timeline_widget.set_sample_library(self.sample_library)
        self.window.slot_panel.set_library(self.sample_library)
        self.window.inspector_panel.set_sample_library(self.sample_library)
        self.window.set_export_mode(self.export_mode)
        self.window.set_bpm_value(self.project.bpm)
        self.window.inspector_panel.set_bpm_value(self.project.bpm)
        self._update_undo_redo_state()
        self.refresh_bar_views()
        self.refresh_selection_views()

    def _update_undo_redo_state(self) -> None:
        self.window.set_undo_redo_enabled(self.undo_manager.can_undo(), self.undo_manager.can_redo())

    def _capture_project_snapshot(self) -> dict[str, object]:
        return {
            "sample_folder": str(self.sample_folder.resolve()),
            "project_path": str(self.project_path.resolve()) if self.project_path else None,
            "export_mode": self.export_mode,
            "project": serialize_project(self.project),
            "sample_slots": serialize_sample_slot_files(self.sample_library),
            "slot_choke_groups": serialize_slot_choke_groups(self.sample_library),
        }

    def begin_mutating_action(self, label: str = "") -> None:
        self.undo_manager.push_undo(self._capture_project_snapshot(), label=label)
        self._update_undo_redo_state()

    def _restore_project_snapshot(self, snapshot: dict[str, object]) -> None:
        self.sample_folder = Path(str(snapshot["sample_folder"])).expanduser().resolve()
        project_path = snapshot.get("project_path")
        self.project_path = Path(str(project_path)).expanduser().resolve() if project_path else None
        self.export_mode = str(snapshot.get("export_mode", "truncate"))
        self.project = deserialize_project(dict(snapshot["project"]))
        sample_slot_files = deserialize_sample_slot_files(dict(snapshot.get("sample_slots", {})))
        slot_choke_groups = deserialize_slot_choke_groups(dict(snapshot.get("slot_choke_groups", {})))

        self.sample_library = SampleLibrary()
        for slot, wav_path in sample_slot_files.items():
            if wav_path.exists():
                self.sample_library.load_wav_into_slot(slot, wav_path)
        for slot, choke_group in slot_choke_groups.items():
            self.sample_library.set_choke_group(slot, choke_group)
        self.realtime_looper = RealtimeLooper(sample_library=self.sample_library, bpm=self.project.bpm)

        self.current_bar_index = min(self.current_bar_index, len(self.project.current_pattern.bars) - 1)
        self.selected_node = None
        self.selected_node_path = None
        self.refresh_ui()

    def _stop_playback_before_history_restore(self, operation: str) -> None:
        if self.realtime_looper.is_playing:
            self.realtime_looper.stop(reason=f"{operation} restore")
            self._set_ui_status(f"Stopped realtime playback before {operation}.")

    def _undo(self) -> None:
        if not self.undo_manager.can_undo():
            return
        self._stop_playback_before_history_restore("undo")
        entry = self.undo_manager.undo(self._capture_project_snapshot())
        if entry is None:
            return
        self._restore_project_snapshot(entry.snapshot)
        self._is_dirty = True
        self._update_undo_redo_state()
        self._set_ui_status(f"Undo: {entry.label}" if entry.label else "Undo performed")

    def _redo(self) -> None:
        if not self.undo_manager.can_redo():
            return
        self._stop_playback_before_history_restore("redo")
        entry = self.undo_manager.redo(self._capture_project_snapshot())
        if entry is None:
            return
        self._restore_project_snapshot(entry.snapshot)
        self._is_dirty = True
        self._update_undo_redo_state()
        self._set_ui_status(f"Redo: {entry.label}" if entry.label else "Redo performed")

    def set_bpm(self, bpm: float) -> None:
        requested_bpm = float(bpm)
        normalized_bpm = self.project.current_pattern.clamp_bpm(requested_bpm)
        if abs(self.project.bpm - normalized_bpm) < 1e-9:
            self.window.set_bpm_value(self.project.bpm)
            self.window.inspector_panel.set_bpm_value(self.project.bpm)
            return

        status_parts: list[str] = []
        if self.realtime_looper.is_playing:
            self.realtime_looper.stop(reason="bpm changed")
            status_parts.append("Playback stopped due to BPM change.")

        self.begin_mutating_action(f"Set BPM to {normalized_bpm:.1f}")
        self.project.bpm = normalized_bpm
        self.realtime_looper.update_bpm(self.project.bpm)
        self._is_dirty = True
        self.window.set_bpm_value(self.project.bpm)
        self.window.inspector_panel.set_bpm_value(self.project.bpm)
        status_parts.append(f"BPM set to {self.project.bpm:.1f}.")
        self._set_ui_status(" ".join(status_parts))

    def _on_widget_selected_node(self, path: str, node: RhythmNode | None) -> None:
        if not path:
            self.clear_selection()
            return
        resolved = self._node_map().get(path)
        if resolved is None:
            self.clear_selection()
            return
        self.set_selected_node(node=resolved, path=path)

    def _split_selected(self, parts: int) -> None:
        if self.selected_node_path is None:
            return
        self._split_path(self.selected_node_path, parts)

    def _apply_template_to_selected(self, template_id: str) -> None:
        if self.selected_node_path is None:
            return
        self._apply_template_to_path(self.selected_node_path, template_id)

    def _iter_leaf_nodes(self, node: RhythmNode) -> list[RhythmNode]:
        if node.is_leaf():
            return [node]
        leaves: list[RhythmNode] = []
        for child in node.children:
            leaves.extend(self._iter_leaf_nodes(child))
        return leaves

    def _reset_selected_subtree(self) -> None:
        if self.selected_node_path is None:
            return
        subtree_path = self.selected_node_path
        node = self._node_map().get(subtree_path)
        if node is None:
            return
        leaves = self._iter_leaf_nodes(node)
        changed = False
        for leaf in leaves:
            if leaf.sample_slot is not None or abs(leaf.velocity - 1.0) > 1e-9 or leaf.pitch_offset != 0:
                if not changed:
                    self.begin_mutating_action("Reset selected subtree")
                leaf.assign(sample_slot=None, velocity=1.0, pitch_offset=0)
                changed = True
        if not changed:
            return
        self._apply_edit_policy("clear_selected")
        self._is_dirty = True
        next_selection = self._first_leaf_under_path(subtree_path)
        if next_selection is not None:
            self.selected_node_path, self.selected_node = next_selection
        else:
            self.selected_node_path, self.selected_node = None, None
        self.refresh_bar_views()
        self.refresh_selection_views()
        self._set_ui_status("Reset selected subtree to rest events")

    def _split_path(self, path: str, parts: int) -> None:
        node = self._node_map().get(path)
        if node is None or not node.is_leaf():
            return
        self.begin_mutating_action(f"Split node into {parts}")
        self._apply_edit_policy("split_selected")
        children = node.split_equal(parts)
        if children:
            self.selected_node = children[0]
            self.selected_node_path = f"{path}.0"
        else:
            self.selected_node = None
            self.selected_node_path = None
        self.refresh_bar_views()
        self.refresh_selection_views()

    def _clear_path(self, path: str) -> None:
        node = self._node_map().get(path)
        if node is None or not node.is_leaf():
            return
        self._set_leaf_sample_slot(node=node, path=path, slot=None, status_message="Set selected leaf to rest")

    def _assign_slot_to_path(self, path: str, slot: int) -> None:
        node = self._node_map().get(path)
        if node is None or not node.is_leaf():
            return
        if slot < 0 or slot >= MAX_SLOTS:
            return
        self._set_leaf_sample_slot(node=node, path=path, slot=slot, status_message=f"Assigned slot {slot} to selected leaf")

    def _first_leaf_descendant(self, node: RhythmNode, path: str) -> tuple[str, RhythmNode] | None:
        current_node = node
        current_path = path
        while not current_node.is_leaf():
            if not current_node.children:
                return None
            current_node = current_node.children[0]
            current_path = f"{current_path}.0"
        return current_path, current_node

    def _apply_template_to_path(self, path: str, template_id: str) -> None:
        node = self._node_map().get(path)
        if node is None or not node.is_leaf():
            self._set_ui_status("Templates can only be applied to leaf nodes.")
            return

        playing_before = self.realtime_looper.is_playing
        if template_id not in TEMPLATE_BY_ID:
            self._set_ui_status(f"Unknown template: {template_id}")
            return
        label = TEMPLATE_BY_ID[template_id].label
        self.begin_mutating_action(f"Apply template '{label}'")
        self._apply_edit_policy("apply_subtree_template")

        try:
            apply_subtree_template(node, template_id)
        except ValueError as exc:
            self._set_ui_status(str(exc))
            QMessageBox.warning(self.window, "Template", str(exc))
            return

        self._is_dirty = True
        next_selection = self._first_leaf_descendant(node, path)
        if next_selection is not None:
            self.selected_node_path, self.selected_node = next_selection
        else:
            self.selected_node_path, self.selected_node = None, None

        self.refresh_bar_views()
        self.refresh_selection_views()

        status_parts: list[str] = []
        if playing_before:
            status_parts.append("Stopped realtime playback because template changed loop structure.")
        status_parts.append(f"Applied template '{label}'.")
        self._set_ui_status(" ".join(status_parts))

    def _set_slot_for_selected(self, slot: int) -> None:
        resolved = None if slot < 0 else slot
        self.set_selected_leaf_sample_slot(resolved)

    def set_selected_leaf_sample_slot(self, slot: int | None) -> None:
        selected = self._selected_leaf()
        if selected is None:
            self._set_ui_status("Select a leaf block to assign a slot.")
            return
        path, node = selected
        if slot is not None and (slot < 0 or slot >= MAX_SLOTS):
            return
        msg = "Set selected leaf to rest" if slot is None else f"Assigned slot {slot} to selected leaf"
        self._set_leaf_sample_slot(node=node, path=path, slot=slot, status_message=msg)

    def _set_leaf_sample_slot(self, node: RhythmNode, path: str, slot: int | None, status_message: str) -> None:
        if node.sample_slot == slot:
            return
        if slot is None:
            self.begin_mutating_action("Set leaf rest")
        else:
            self.begin_mutating_action(f"Set leaf slot to {slot}")
        self._apply_edit_policy("set_slot")
        node.assign(sample_slot=slot, velocity=node.velocity, pitch_offset=node.pitch_offset)
        self._apply_leaf_value_changes(node=node, path=path, status_message=status_message)

    def _set_velocity_for_selected(self, velocity: float) -> None:
        self.set_selected_leaf_velocity(velocity)

    def set_selected_leaf_velocity(self, velocity: float) -> None:
        selected = self._selected_leaf()
        if selected is None:
            return
        path, node = selected
        if abs(node.velocity - velocity) < 1e-9:
            return
        self.begin_mutating_action(f"Set velocity to {velocity:.2f}")
        self._apply_edit_policy("set_velocity")
        node.assign(sample_slot=node.sample_slot, velocity=velocity, pitch_offset=node.pitch_offset)
        self._apply_leaf_value_changes(node=node, path=path, status_message=f"Updated velocity to {velocity:.2f}")

    def _set_pitch_for_selected(self, pitch: int) -> None:
        self.set_selected_leaf_pitch_offset(pitch)

    def _set_choke_group_for_selected_slot(self, choke_group: int) -> None:
        selected_slot = self._selected_slot_for_ui()
        if selected_slot is None:
            return
        normalized_group = None if choke_group <= 0 else int(choke_group)
        if self.sample_library.choke_group(selected_slot) == normalized_group:
            return
        label = "None" if normalized_group is None else str(normalized_group)
        self.begin_mutating_action(f"Set slot {selected_slot} choke group to {label}")
        self.sample_library.set_choke_group(selected_slot, normalized_group)
        self._is_dirty = True
        self.window.inspector_panel.set_selected_slot_choke_group(normalized_group)
        self._set_ui_status(f"Set choke group for slot {selected_slot} to {label}")

    def set_selected_leaf_pitch_offset(self, pitch: int) -> None:
        selected = self._selected_leaf()
        if selected is None:
            return
        path, node = selected
        if node.pitch_offset == pitch:
            return
        self.begin_mutating_action(f"Set pitch offset to {pitch}")
        self._apply_edit_policy("set_pitch_offset")
        node.assign(sample_slot=node.sample_slot, velocity=node.velocity, pitch_offset=pitch)
        self._apply_leaf_value_changes(node=node, path=path, status_message=f"Updated pitch offset to {pitch}")

    def set_selected_leaf_rest_state(self, is_rest: bool) -> None:
        if is_rest:
            self.set_selected_leaf_sample_slot(None)
            return
        selected = self._selected_leaf()
        if selected is None:
            self._set_ui_status("Select a leaf block before clearing rest.")
            return
        _path, node = selected
        fallback_slot = 0 if self.sample_library.slots and self.sample_library.slots[0] is not None else None
        slot = node.sample_slot if node.sample_slot is not None else fallback_slot
        self.set_selected_leaf_sample_slot(slot)

    def _apply_leaf_value_changes(self, node: RhythmNode, path: str, status_message: str | None = None) -> None:
        self._is_dirty = True
        self.selected_node = node
        self.selected_node_path = path
        self.refresh_bar_views()
        self.refresh_selection_views()
        if status_message:
            self._set_ui_status(status_message)

    def _assign_slot_from_panel(self, slot: int) -> None:
        if slot < 0 or slot >= MAX_SLOTS:
            return
        if self._selected_leaf() is None:
            self._set_ui_status("Cannot assign slot: select a leaf block.")
            return
        self.set_selected_leaf_sample_slot(slot)

    def _audition_slot(self, slot: int) -> None:
        sample = self.sample_library.slots[slot]
        if sample is None:
            return
        if self.realtime_looper.is_playing:
            self.realtime_looper.stop(reason="audition")
        play_once(sample.audio, sample.sample_rate)

    def _set_mode(self, mode: str) -> None:
        mapping = {"Bar": "bar", "Pattern": "pattern", "Chain": "chain"}
        self.transport_mode = mapping.get(mode, "bar")

    def _set_export_mode(self, mode: str) -> None:
        self.export_mode = mode if mode in {"truncate", "wrap", "tail"} else "truncate"

    def _has_loaded_samples(self) -> bool:
        return self.sample_library.sample_rate is not None and bool(self.sample_library.loaded_slots())

    def _set_ui_status(self, message: str | None) -> None:
        self._ui_status_message = message
        self._refresh_transport()

    def _prepare_realtime_for_current_mode(self) -> bool:
        if not self._has_loaded_samples():
            self._set_ui_status("Cannot start playback: no samples loaded.")
            return False
        try:
            if self.transport_mode == "bar":
                self.realtime_looper.set_bar_loop(self.project.current_pattern.bars[self.current_bar_index], bpm=self.project.bpm)
            elif self.transport_mode == "pattern":
                self.realtime_looper.set_pattern_loop(self.project.current_pattern, bpm=self.project.bpm)
            else:
                self.realtime_looper.set_chain_loop(self.project, bpm=self.project.bpm)
        except Exception as exc:
            self._set_ui_status(str(exc))
            QMessageBox.warning(self.window, "Playback", str(exc))
            return False
        self._set_ui_status(None)
        return True

    def _play(self) -> None:
        if not self._prepare_realtime_for_current_mode():
            return
        try:
            self.realtime_looper.start()
        except Exception as exc:
            self._set_ui_status(str(exc))
            QMessageBox.warning(self.window, "Playback", str(exc))

    def _stop(self) -> None:
        self.realtime_looper.stop(reason="user")

    def _new_project(self) -> None:
        self.begin_mutating_action("New project")
        self._apply_edit_policy("new_pattern")
        self.project = Project.create_default()
        self.current_bar_index = 0
        self.selected_node = None
        self.selected_node_path = None
        self._is_dirty = False
        self.project_path = None
        self._ui_status_message = None
        self.export_mode = "truncate"
        self.window.set_export_mode(self.export_mode)
        self.refresh_ui()

    def _choose_and_load_samples(self) -> None:
        start_dir = str(self.sample_folder) if self.sample_folder.exists() else str(Path.cwd())
        selected = QFileDialog.getExistingDirectory(self.window, "Choose Sample Folder", start_dir)
        if not selected:
            return
        self._load_samples_from_folder(Path(selected))

    def _reload_samples(self) -> None:
        if self.sample_folder is None or not self.sample_folder.exists():
            self._set_ui_status("Cannot reload: no sample folder selected.")
            return
        self._load_samples_from_folder(self.sample_folder)

    def _load_samples_from_folder(self, folder: Path) -> None:
        folder = folder.expanduser().resolve()
        if not folder.exists() or not folder.is_dir():
            self._set_ui_status(f"Sample folder does not exist: {folder}")
            return

        wav_files = sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".wav"), key=lambda p: p.name.lower())
        if not wav_files:
            self._set_ui_status("No WAV files found in selected folder.")
            return

        if self.realtime_looper.is_playing:
            self.realtime_looper.stop(reason="samples reloaded")

        fresh_library = SampleLibrary()
        loaded = 0
        failures: list[str] = []
        ignored = 0

        for wav_path in wav_files:
            if loaded >= MAX_SLOTS:
                ignored += 1
                continue
            try:
                fresh_library.load_wav_into_slot(loaded, wav_path)
                loaded += 1
            except Exception:
                failures.append(wav_path.name)

        if loaded == 0:
            self._set_ui_status("No valid WAV files could be loaded from selected folder.")
            return

        self.begin_mutating_action("Load samples from folder")
        self.sample_folder = folder
        self.sample_library = fresh_library
        self.realtime_looper = RealtimeLooper(sample_library=self.sample_library, bpm=self.project.bpm)
        self.refresh_ui()

        parts = [f"Loaded {loaded} sample{'s' if loaded != 1 else ''} from {folder}"]
        if ignored > 0:
            parts.append(f"{ignored} additional file{'s' if ignored != 1 else ''} ignored")
        if failures:
            parts.append(f"{len(failures)} failed ({', '.join(failures[:3])}{'...' if len(failures) > 3 else ''})")
        self._set_ui_status(". ".join(parts))

    def _save_project(self) -> None:
        if self.project_path is None:
            self.project_path = Path(
                QFileDialog.getSaveFileName(self.window, "Save Pattern", "pattern.json", "JSON (*.json)")[0]
            )
        if not self.project_path:
            return
        save_pattern_project_to_json(
            self.project_path,
            project=self.project,
            sample_folder=self.sample_folder,
            sample_library=self.sample_library,
        )
        self._is_dirty = False
        self._set_ui_status(f"Saved {self.project_path.name}")

    def _load_project(self) -> None:
        selected = QFileDialog.getOpenFileName(self.window, "Load Pattern", "", "JSON (*.json)")[0]
        if not selected:
            return
        project = load_pattern_project_from_json(Path(selected))
        self._apply_edit_policy("load_pattern")
        self.project = project.project
        self.sample_folder = project.sample_folder
        self.project_path = project.source_path
        self.sample_library = SampleLibrary()
        for slot, wav_path in project.sample_slot_files.items():
            if wav_path.exists():
                self.sample_library.load_wav_into_slot(slot, wav_path)
        for slot, choke_group in project.slot_choke_groups.items():
            self.sample_library.set_choke_group(slot, choke_group)
        self.realtime_looper = RealtimeLooper(sample_library=self.sample_library, bpm=self.project.bpm)
        self.current_bar_index = 0
        self.selected_node = None
        self.selected_node_path = None
        self._is_dirty = False
        self._ui_status_message = None
        self.export_mode = "truncate"
        self.window.set_export_mode(self.export_mode)
        self.undo_manager.clear()
        self.refresh_ui()

    def _export(self) -> None:
        dialog = ExportDialog(current_mode=self.export_mode, parent=self.window)
        if dialog.exec() == 0:
            return
        selected_mode = dialog.selected_mode()
        self.export_mode = selected_mode
        self.window.set_export_mode(selected_mode)
        if self.transport_mode == "chain":
            output = export_arrangement(
                self.project,
                self.sample_library,
                output_path="exports",
                filename_prefix="arrangement",
                sample_rate=int(round(self.sample_library.sample_rate or 44100)),
                normalize=True,
                mode=selected_mode,
                bpm=self.project.bpm,
            )
        else:
            output = export_pattern(
                self.project.current_pattern,
                self.sample_library,
                output_path="exports",
                filename_prefix=self.project.current_pattern.name,
                sample_rate=int(round(self.sample_library.sample_rate or 44100)),
                normalize=True,
                mode=selected_mode,
                bpm=self.project.bpm,
            )
        QMessageBox.information(self.window, "Export", f"Exported to {output}\nMode: {selected_mode}")

    def set_current_pattern_index(self, index: int, *, mark_dirty: bool = False) -> None:
        if index < 0 or index >= len(self.project.patterns):
            return
        if self.project.current_pattern_index == index and not mark_dirty:
            self._ensure_valid_current_indices()
            return

        self._stop_realtime_for_pattern_change("pattern changed")
        self.clear_selection(refresh=False)
        self.project.set_current_pattern_index(index)
        self.current_bar_index = 0
        self._ensure_valid_current_indices()

        names = [pattern.name for pattern in self.project.patterns]
        self.window.pattern_panel.set_patterns(names, self.project.current_pattern_index)
        self.window.arrangement_panel.set_arrangement(self.project.arrangement, names)
        self.window.bar_list_panel.set_pattern(self.project.current_pattern, self.current_bar_index)
        self.window.tree_panel.set_bar(self.project.current_pattern.bars[self.current_bar_index], selected_path=None)
        self.window.timeline_widget.set_bar(self.project.current_pattern.bars[self.current_bar_index])
        self.window.inspector_panel.set_node(self.current_bar_index, None, None)
        self.window.slot_panel.set_assignment_enabled(False)
        self.window.slot_panel.set_selected_slot(None)
        self._refresh_transport()

        if mark_dirty:
            self._is_dirty = True

    def _set_current_pattern(self, index: int) -> None:
        if index < 0 or index >= len(self.project.patterns) or self.project.current_pattern_index == index:
            return
        self.begin_mutating_action("Switch pattern")
        self.set_current_pattern_index(index, mark_dirty=True)

    def _create_pattern(self) -> None:
        self.begin_mutating_action("Create pattern")
        self._stop_realtime_for_pattern_change("pattern created")
        new_index = self.project.add_pattern_duplicate_current()
        self.set_current_pattern_index(new_index, mark_dirty=True)

    def _rename_pattern(self, index: int) -> None:
        if index < 0 or index >= len(self.project.patterns):
            return
        value, ok = QInputDialog.getText(self.window, "Rename Pattern", "Pattern name:", text=self.project.patterns[index].name)
        if not ok or not value.strip():
            return
        self.begin_mutating_action("Rename pattern")
        self.project.patterns[index].name = Path(value).name
        self._is_dirty = True
        self.refresh_ui()

    def _delete_pattern(self, index: int) -> None:
        if len(self.project.patterns) <= 1 or index < 0 or index >= len(self.project.patterns):
            return
        self.begin_mutating_action("Delete pattern")
        self._stop_realtime_for_pattern_change("pattern deleted")
        del self.project.patterns[index]
        self.project.arrangement = [i for i in self.project.arrangement if i != index]
        self.project.arrangement = [i - 1 if i > index else i for i in self.project.arrangement]
        if not self.project.arrangement:
            self.project.arrangement = [0]
        next_index = min(self.project.current_pattern_index, len(self.project.patterns) - 1)
        self.project.current_pattern_index = max(0, next_index)
        self.set_current_pattern_index(self.project.current_pattern_index, mark_dirty=True)

    def _arrangement_add_step(self) -> None:
        self.begin_mutating_action("Arrangement add step")
        self.project.arrangement.append(self.project.current_pattern_index)
        self._is_dirty = True
        self.refresh_ui()

    def _arrangement_remove_step(self, index: int) -> None:
        if len(self.project.arrangement) <= 1 or index < 0 or index >= len(self.project.arrangement):
            return
        self.begin_mutating_action("Arrangement remove step")
        del self.project.arrangement[index]
        self._is_dirty = True
        self.refresh_ui()

    def _arrangement_move_up(self, index: int) -> None:
        if index <= 0 or index >= len(self.project.arrangement):
            return
        self.begin_mutating_action("Arrangement move up")
        self.project.arrangement[index - 1], self.project.arrangement[index] = self.project.arrangement[index], self.project.arrangement[index - 1]
        self._is_dirty = True
        self.refresh_ui()

    def _arrangement_move_down(self, index: int) -> None:
        if index < 0 or index >= len(self.project.arrangement) - 1:
            return
        self.begin_mutating_action("Arrangement move down")
        self.project.arrangement[index], self.project.arrangement[index + 1] = self.project.arrangement[index + 1], self.project.arrangement[index]
        self._is_dirty = True
        self.refresh_ui()

    def _apply_edit_policy(self, action_name: str) -> bool:
        classification = classify_edit(action_name)
        if classification == "live_safe":
            return True
        if self.realtime_looper.is_playing:
            self.realtime_looper.stop(reason=invalidation_reason(action_name))
        return False

    def _refresh_transport(self) -> None:
        snap = self.realtime_looper.transport_snapshot()
        state = "PLAYING" if snap.is_playing else "STOPPED"
        mode = "-" if snap.mode is None else snap.mode.upper()
        progress = f"{snap.loop_progress * 100:.0f}%"
        if snap.mode == "chain" and snap.current_chain_position is not None:
            bar_chain = f"Step: {snap.current_chain_position + 1}"
        else:
            bar_chain = f"Bar: {self.current_bar_index}"
        status = self._ui_status_message or snap.status_message or "Ready"
        if self._is_dirty and not status.endswith("• unsaved"):
            status = f"{status} • unsaved"
        self.window.transport_panel.set_values(
            state=state,
            mode=mode,
            progress=progress,
            bar_chain=bar_chain,
            status=status,
        )


def launch() -> None:
    project: LoadedPatternProject | None = None
    if len(sys.argv) > 1:
        candidate = Path(sys.argv[1])
        if candidate.suffix == ".json" and candidate.exists():
            project = load_pattern_project_from_json(candidate)

    app = QApplication(sys.argv)
    gui = SequencerGuiApp(project)
    gui.window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    launch()
