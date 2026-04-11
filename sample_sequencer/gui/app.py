from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from audio.export import export_pattern
from audio.playback import play_once
from audio.realtime import RealtimeLooper
from audio.sample_library import MAX_SLOTS, SampleLibrary
from engine.edit_policy import classify_edit, invalidation_reason
from engine.pattern import Pattern, create_blank_pattern
from engine.rhythm_tree import RhythmNode
from sample_sequencer.gui.main_window import MainWindow
from sequencer_io import LoadedPatternProject, load_pattern_project_from_json, save_pattern_project_to_json


class SequencerGuiApp:
    def __init__(self, project: LoadedPatternProject | None = None) -> None:
        self.sample_library = SampleLibrary()
        if project is None:
            self.pattern = create_blank_pattern("Untitled", bpm=120.0, numerator=4, denominator=4)
            self.bpm = 120.0
            self.pattern_name = "Untitled"
            self.sample_folder = Path("assets/samples").resolve()
            self.project_path: Path | None = None
        else:
            self.pattern = project.pattern
            self.bpm = project.bpm
            self.pattern_name = project.name
            self.sample_folder = project.sample_folder
            self.project_path = project.source_path
            for slot, wav_path in project.sample_slot_files.items():
                if wav_path.exists():
                    self.sample_library.load_wav_into_slot(slot, wav_path)

        self.current_bar_index = 0
        self.selected_path = "0"
        self.transport_mode = "bar"
        self._ui_status_message: str | None = None

        self.realtime_looper = RealtimeLooper(sample_library=self.sample_library, bpm=self.bpm)

        self.window = MainWindow()
        self._wire_events()
        self.refresh_ui()

        self.timer = QTimer()
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._refresh_transport)
        self.timer.start()

    def _wire_events(self) -> None:
        w = self.window
        w.bar_list_panel.barSelected.connect(self._select_bar)
        w.tree_panel.nodeSelected.connect(self._select_path)
        w.timeline_widget.blockSelected.connect(self._select_path)
        w.timeline_widget.splitRequested.connect(self._split_path)
        w.timeline_widget.clearRequested.connect(self._clear_path)
        w.timeline_widget.templateRequested.connect(self._template_stub)

        w.inspector_panel.slotChanged.connect(self._set_slot_for_selected)
        w.inspector_panel.velocityChanged.connect(self._set_velocity_for_selected)
        w.inspector_panel.pitchChanged.connect(self._set_pitch_for_selected)
        w.inspector_panel.splitRequested.connect(lambda parts: self._split_path(self.selected_path, parts))
        w.inspector_panel.clearRequested.connect(lambda: self._clear_path(self.selected_path))

        w.slot_panel.slotClicked.connect(self._assign_slot_from_panel)
        w.slot_panel.slotDoubleClicked.connect(self._audition_slot)

        w.modeChanged.connect(self._set_mode)
        w.playClicked.connect(self._play)
        w.stopClicked.connect(self._stop)
        w.newClicked.connect(self._new_project)
        w.saveClicked.connect(self._save_project)
        w.loadClicked.connect(self._load_project)
        w.exportClicked.connect(self._export)

    def _iter_nodes(self, node: RhythmNode, path: str) -> list[tuple[str, RhythmNode]]:
        nodes = [(path, node)]
        for idx, child in enumerate(node.children):
            nodes.extend(self._iter_nodes(child, f"{path}.{idx}"))
        return nodes

    def _node_map(self) -> dict[str, RhythmNode]:
        return dict(self._iter_nodes(self.pattern.bars[self.current_bar_index].root, "0"))

    def _selected_node(self) -> RhythmNode | None:
        return self._node_map().get(self.selected_path)

    def _select_bar(self, index: int) -> None:
        if index < 0 or index >= len(self.pattern.bars):
            return
        self._apply_edit_policy("select_bar")
        self.current_bar_index = index
        self.selected_path = "0"
        self.refresh_ui()

    def _select_path(self, path: str) -> None:
        if path in self._node_map():
            self.selected_path = path
            self.refresh_ui()

    def _split_path(self, path: str, parts: int) -> None:
        node = self._node_map().get(path)
        if node is None or not node.is_leaf():
            return
        self._apply_edit_policy("split_selected")
        node.split_equal(parts)
        self.selected_path = path
        self.refresh_ui()

    def _clear_path(self, path: str) -> None:
        node = self._node_map().get(path)
        if node is None or not node.is_leaf():
            return
        self._apply_edit_policy("set_slot")
        node.assign(sample_slot=None, velocity=node.velocity, pitch_offset=node.pitch_offset)
        self.selected_path = path
        self.refresh_ui()

    def _template_stub(self, path: str) -> None:
        QMessageBox.information(self.window, "Template", f"Apply template is a stub in MVP. (path={path})")

    def _set_slot_for_selected(self, slot: int) -> None:
        node = self._selected_node()
        if node is None or not node.is_leaf():
            return
        self._apply_edit_policy("set_slot")
        resolved = None if slot < 0 else slot
        node.assign(sample_slot=resolved, velocity=node.velocity, pitch_offset=node.pitch_offset)
        self.refresh_ui()

    def _set_velocity_for_selected(self, velocity: float) -> None:
        node = self._selected_node()
        if node is None or not node.is_leaf():
            return
        self._apply_edit_policy("set_velocity")
        node.assign(sample_slot=node.sample_slot, velocity=velocity, pitch_offset=node.pitch_offset)
        self.refresh_ui()

    def _set_pitch_for_selected(self, pitch: int) -> None:
        node = self._selected_node()
        if node is None or not node.is_leaf():
            return
        self._apply_edit_policy("set_pitch_offset")
        node.assign(sample_slot=node.sample_slot, velocity=node.velocity, pitch_offset=pitch)
        self.refresh_ui()

    def _assign_slot_from_panel(self, slot: int) -> None:
        node = self._selected_node()
        if node is None or not node.is_leaf() or slot < 0 or slot >= MAX_SLOTS:
            return
        self._set_slot_for_selected(slot)

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
                self.realtime_looper.set_bar_loop(self.pattern.bars[self.current_bar_index], bpm=self.bpm)
            elif self.transport_mode == "pattern":
                self.realtime_looper.set_pattern_loop(self.pattern, bpm=self.bpm)
            else:
                self.realtime_looper.set_chain_loop(self.pattern, bpm=self.bpm)
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
        self._apply_edit_policy("new_pattern")
        self.pattern = create_blank_pattern("Untitled", bpm=120.0, numerator=4, denominator=4)
        self.pattern_name = "Untitled"
        self.bpm = 120.0
        self.current_bar_index = 0
        self.selected_path = "0"
        self.project_path = None
        self._ui_status_message = None
        self.refresh_ui()

    def _save_project(self) -> None:
        if self.project_path is None:
            self.project_path = Path(
                QFileDialog.getSaveFileName(self.window, "Save Pattern", "pattern.json", "JSON (*.json)")[0]
            )
        if not self.project_path:
            return
        save_pattern_project_to_json(
            self.project_path,
            pattern_name=self.pattern_name,
            bpm=self.bpm,
            pattern=self.pattern,
            sample_folder=self.sample_folder,
            sample_library=self.sample_library,
        )

    def _load_project(self) -> None:
        selected = QFileDialog.getOpenFileName(self.window, "Load Pattern", "", "JSON (*.json)")[0]
        if not selected:
            return
        project = load_pattern_project_from_json(Path(selected))
        self._apply_edit_policy("load_pattern")
        self.pattern = project.pattern
        self.pattern_name = project.name
        self.bpm = project.bpm
        self.sample_folder = project.sample_folder
        self.project_path = project.source_path
        self.sample_library = SampleLibrary()
        for slot, wav_path in project.sample_slot_files.items():
            if wav_path.exists():
                self.sample_library.load_wav_into_slot(slot, wav_path)
        self.realtime_looper = RealtimeLooper(sample_library=self.sample_library, bpm=self.bpm)
        self.current_bar_index = 0
        self.selected_path = "0"
        self._ui_status_message = None
        self.refresh_ui()

    def _export(self) -> None:
        output = export_pattern(
            self.pattern,
            self.sample_library,
            output_path="exports",
            filename_prefix=self.pattern_name,
            sample_rate=int(round(self.sample_library.sample_rate or 44100)),
            normalize=True,
        )
        QMessageBox.information(self.window, "Export", f"Exported to {output}")

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
        self.window.transport_panel.set_values(
            state=state,
            mode=mode,
            progress=progress,
            bar_chain=bar_chain,
            status=status,
        )

    def refresh_ui(self) -> None:
        bar = self.pattern.bars[self.current_bar_index]
        selected = self._selected_node()
        self.window.bar_list_panel.set_pattern(self.pattern, self.current_bar_index)
        self.window.tree_panel.set_bar(bar, self.selected_path)
        self.window.timeline_widget.set_bar(bar)
        self.window.timeline_widget.set_sample_library(self.sample_library)
        self.window.timeline_widget.set_selected_node(self.selected_path)
        self.window.inspector_panel.set_node(self.selected_path, selected)
        self.window.slot_panel.set_library(self.sample_library)
        self._refresh_transport()


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
