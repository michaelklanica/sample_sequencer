from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QDoubleSpinBox,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QComboBox,
)

from audio.sample_library import MAX_SLOTS, SampleLibrary
from engine.rhythm_tree import RhythmNode
from sample_sequencer.gui.template_defs import COMMON_TEMPLATE_IDS, TEMPLATE_BY_ID, TEMPLATE_DEFINITIONS


class InspectorPanel(QWidget):
    slotChanged = Signal(int)
    velocityChanged = Signal(float)
    pitchChanged = Signal(int)
    splitRequested = Signal(int)
    clearRequested = Signal()
    templateRequested = Signal(str)
    bpmChanged = Signal(float)

    def __init__(self) -> None:
        super().__init__()
        self._bar_index: int | None = None
        self._bpm = QDoubleSpinBox()
        self._bpm.setRange(20.0, 300.0)
        self._bpm.setSingleStep(1.0)
        self._bpm.setDecimals(1)
        self._bpm.setValue(120.0)

        self._summary = QLabel("No node selected")
        self._summary.setWordWrap(True)
        self._timing_summary = QLabel("-")
        self._timing_summary.setWordWrap(True)

        self._slot_combo = QComboBox()
        self._slot_combo.addItem("None / Rest", None)
        for slot in range(MAX_SLOTS):
            self._slot_combo.addItem(f"{slot:02d} — (empty)", slot)

        self._velocity = QSlider(Qt.Orientation.Horizontal)
        self._velocity.setMinimum(0)
        self._velocity.setMaximum(100)
        self._velocity_value = QLabel("1.00")

        self._pitch = QSpinBox()
        self._pitch.setRange(-24, 24)

        self._rest_note = QLabel("")
        self._rest_note.setWordWrap(True)
        self._set_rest_btn = QPushButton("Set Rest")

        self._helper_text = QLabel("Select a block in the timeline or tree to edit it.")
        self._helper_text.setWordWrap(True)
        self._internal_info = QLabel("Internal group details will appear here.")
        self._internal_info.setWordWrap(True)

        main = QVBoxLayout(self)
        project_group = QGroupBox("Project")
        project_form = QFormLayout(project_group)
        project_form.addRow("BPM", self._bpm)

        summary_group = QGroupBox("Selection Summary")
        summary_form = QFormLayout(summary_group)
        summary_form.addRow("Selection", self._summary)
        summary_form.addRow("Timing", self._timing_summary)

        event_group = QGroupBox("Leaf Event Values")
        event_form = QFormLayout(event_group)
        event_form.addRow("Sample Slot", self._slot_combo)

        velocity_row_widget = QWidget()
        velocity_row = QHBoxLayout(velocity_row_widget)
        velocity_row.setContentsMargins(0, 0, 0, 0)
        velocity_row.addWidget(self._velocity, 1)
        velocity_row.addWidget(self._velocity_value)
        event_form.addRow("Velocity", velocity_row_widget)

        event_form.addRow("Pitch Offset", self._pitch)
        event_form.addRow(self._set_rest_btn)
        event_form.addRow(self._rest_note)

        structure_group = QGroupBox("Structural Actions")
        structure_layout = QVBoxLayout(structure_group)
        split_row = QHBoxLayout()
        self._split_buttons: list[QPushButton] = []
        for parts in (2, 3, 4, 5, 6):
            btn = QPushButton(f"Split into {parts}")
            btn.clicked.connect(lambda _checked=False, p=parts: self.splitRequested.emit(p))
            split_row.addWidget(btn)
            self._split_buttons.append(btn)
        structure_layout.addLayout(split_row)

        template_group = QGroupBox("Templates")
        template_layout = QVBoxLayout(template_group)
        quick_row = QHBoxLayout()
        self._template_quick_buttons: list[tuple[str, QPushButton]] = []
        for template_id in COMMON_TEMPLATE_IDS:
            definition = TEMPLATE_BY_ID[template_id]
            label = definition.label.split()[-1] if "Straight" in definition.label else "3T"
            btn = QPushButton(label)
            btn.setToolTip(definition.label)
            btn.clicked.connect(lambda _checked=False, tid=template_id: self.templateRequested.emit(tid))
            quick_row.addWidget(btn)
            self._template_quick_buttons.append((template_id, btn))
        template_layout.addLayout(quick_row)

        template_picker_row = QHBoxLayout()
        self._template_combo = QComboBox()
        for definition in TEMPLATE_DEFINITIONS:
            self._template_combo.addItem(definition.label, definition.template_id)
        self._template_btn = QPushButton("Apply Template")
        self._template_btn.clicked.connect(self._emit_selected_template)
        template_picker_row.addWidget(self._template_combo, 1)
        template_picker_row.addWidget(self._template_btn)
        template_layout.addLayout(template_picker_row)

        self._template_desc = QLabel("Select a leaf to apply a template.")
        self._template_desc.setWordWrap(True)
        template_layout.addWidget(self._template_desc)

        self._clear_btn = QPushButton("Reset Subtree")
        self._clear_btn.clicked.connect(self.clearRequested.emit)
        structure_layout.addWidget(template_group)
        structure_layout.addWidget(self._clear_btn)

        info_group = QGroupBox("Internal Info / Help")
        info_layout = QVBoxLayout(info_group)
        info_layout.addWidget(self._helper_text)
        info_layout.addWidget(self._internal_info)

        main.addWidget(project_group)
        main.addWidget(summary_group)
        main.addWidget(event_group)
        main.addWidget(structure_group)
        main.addWidget(info_group)
        main.addStretch(1)

        self._slot_combo.currentIndexChanged.connect(self._emit_slot)
        self._velocity.valueChanged.connect(self._on_velocity_changed)
        self._pitch.valueChanged.connect(self.pitchChanged.emit)
        self._set_rest_btn.clicked.connect(self._set_rest)
        self._template_combo.currentIndexChanged.connect(self._update_template_description)
        self._bpm.valueChanged.connect(self.bpmChanged.emit)

        self._set_leaf_controls_enabled(False)
        self._set_structure_enabled(selection_exists=False, leaf_selected=False)
        self._show_mode_help(show_none=True, show_internal=False)

    def set_bpm_value(self, bpm: float) -> None:
        blocker = QSignalBlocker(self._bpm)
        self._bpm.setValue(bpm)
        del blocker

    def set_sample_library(self, library: SampleLibrary | None) -> None:
        blocker = QSignalBlocker(self._slot_combo)
        selected_value = self._slot_combo.currentData()
        self._slot_combo.clear()
        self._slot_combo.addItem("None / Rest", None)
        for slot in range(MAX_SLOTS):
            label = f"{slot:02d} — (empty)"
            if library is not None:
                sample = library.slots[slot]
                if sample is not None:
                    label = f"{slot:02d} — {Path(sample.path).name}"
            self._slot_combo.addItem(label, slot)
        if selected_value is None:
            self._slot_combo.setCurrentIndex(0)
        elif isinstance(selected_value, int) and 0 <= selected_value < MAX_SLOTS:
            self._slot_combo.setCurrentIndex(selected_value + 1)
        del blocker

    def set_bar_context(self, bar_index: int | None) -> None:
        self._bar_index = bar_index

    def _on_velocity_changed(self, value: int) -> None:
        velocity = value / 100.0
        self._velocity_value.setText(f"{velocity:.2f}")
        self.velocityChanged.emit(velocity)

    def _set_rest(self) -> None:
        self._slot_combo.setCurrentIndex(0)

    def _emit_slot(self) -> None:
        value = self._slot_combo.currentData()
        if value is None:
            self.slotChanged.emit(-1)
            return
        self.slotChanged.emit(int(value))

    def _emit_selected_template(self) -> None:
        template_id = self._template_combo.currentData()
        if isinstance(template_id, str):
            self.templateRequested.emit(template_id)

    def _update_template_description(self) -> None:
        template_id = self._template_combo.currentData()
        if not isinstance(template_id, str):
            self._template_desc.setText("Select a leaf to apply a template.")
            return
        definition = TEMPLATE_BY_ID.get(template_id)
        if definition is None:
            self._template_desc.setText("Select a leaf to apply a template.")
            return
        self._template_desc.setText(definition.description)

    def _set_leaf_controls_enabled(self, enabled: bool) -> None:
        self._slot_combo.setEnabled(enabled)
        self._velocity.setEnabled(enabled)
        self._pitch.setEnabled(enabled)
        self._set_rest_btn.setEnabled(enabled)

    def _set_structure_enabled(self, selection_exists: bool, leaf_selected: bool) -> None:
        for btn in self._split_buttons:
            btn.setEnabled(leaf_selected)
        self._template_combo.setEnabled(leaf_selected)
        self._template_btn.setEnabled(leaf_selected)
        for _template_id, quick_button in self._template_quick_buttons:
            quick_button.setEnabled(leaf_selected)
        self._clear_btn.setEnabled(selection_exists)

    def _show_mode_help(self, show_none: bool, show_internal: bool) -> None:
        self._helper_text.setVisible(show_none)
        self._internal_info.setVisible(show_internal)

    def set_node(self, bar_index: int | None, path: str | None, node: RhythmNode | None) -> None:
        self.set_bar_context(bar_index)
        blockers = [
            QSignalBlocker(self._slot_combo),
            QSignalBlocker(self._velocity),
            QSignalBlocker(self._pitch),
        ]

        if node is None:
            self._summary.setText("No node selected")
            self._timing_summary.setText("-")
            self._slot_combo.setCurrentIndex(0)
            self._velocity.setValue(100)
            self._velocity_value.setText("1.00")
            self._pitch.setValue(0)
            self._rest_note.setText("")
            self._template_desc.setText("Select a leaf to apply a template.")
            self._set_leaf_controls_enabled(False)
            self._set_structure_enabled(selection_exists=False, leaf_selected=False)
            self._show_mode_help(show_none=True, show_internal=False)
            del blockers
            return

        bar_text = f"Bar {bar_index}" if bar_index is not None else "Bar ?"
        node_path_text = path if path else "-"
        timing_text = (
            f"Start {node.start_fraction:.6f} • Duration {node.duration_fraction:.6f}"
        )

        if node.is_leaf():
            self._summary.setText(f"{bar_text} • Leaf • Path {node_path_text}")
            self._timing_summary.setText(timing_text)
            self._slot_combo.setCurrentIndex(0 if node.sample_slot is None else node.sample_slot + 1)
            self._velocity.setValue(int(round(node.velocity * 100)))
            self._velocity_value.setText(f"{node.velocity:.2f}")
            self._pitch.setValue(int(node.pitch_offset))
            self._rest_note.setText("This leaf is currently a rest." if node.sample_slot is None else "")
            self._internal_info.setText("Internal group details will appear here.")
            self._update_template_description()
            self._set_leaf_controls_enabled(True)
            self._set_structure_enabled(selection_exists=True, leaf_selected=True)
            self._show_mode_help(show_none=False, show_internal=False)
            del blockers
            return

        self._summary.setText(f"{bar_text} • Internal Group • Path {node_path_text}")
        self._timing_summary.setText(timing_text)
        self._slot_combo.setCurrentIndex(0)
        self._velocity.setValue(100)
        self._velocity_value.setText("1.00")
        self._pitch.setValue(0)
        self._rest_note.setText("")
        self._template_desc.setText("Templates can only be applied to leaf nodes.")
        child_count = len(node.children)
        self._internal_info.setText(
            "\n".join(
                [
                    f"Children: {child_count}",
                    f"Start Fraction: {node.start_fraction:.6f}",
                    f"Duration Fraction: {node.duration_fraction:.6f}",
                ]
            )
        )
        self._set_leaf_controls_enabled(False)
        self._set_structure_enabled(selection_exists=True, leaf_selected=False)
        self._show_mode_help(show_none=False, show_internal=True)
        del blockers
