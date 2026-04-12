from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QComboBox,
)

from audio.sample_library import MAX_SLOTS
from engine.rhythm_tree import RhythmNode


class InspectorPanel(QWidget):
    slotChanged = Signal(int)
    velocityChanged = Signal(float)
    pitchChanged = Signal(int)
    splitRequested = Signal(int)
    clearRequested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._path = QLabel("-")
        self._duration = QLabel("-")
        self._node_type = QLabel("None")
        self._slot_combo = QComboBox()
        self._slot_combo.addItem("None", None)
        for slot in range(MAX_SLOTS):
            self._slot_combo.addItem(f"Slot {slot}", slot)
        self._velocity = QSlider(Qt.Orientation.Horizontal)
        self._velocity.setMinimum(0)
        self._velocity.setMaximum(100)
        self._pitch = QSpinBox()
        self._pitch.setRange(-24, 24)

        main = QVBoxLayout(self)

        info_group = QGroupBox("Block Info")
        info_form = QFormLayout(info_group)
        info_form.addRow("Path", self._path)
        info_form.addRow("Duration", self._duration)
        info_form.addRow("Type", self._node_type)

        sample_group = QGroupBox("Sample Controls")
        sample_form = QFormLayout(sample_group)
        sample_form.addRow("Slot", self._slot_combo)
        sample_form.addRow("Velocity", self._velocity)
        sample_form.addRow("Pitch", self._pitch)

        action_group = QGroupBox("Actions")
        action_layout = QVBoxLayout(action_group)
        split_row = QHBoxLayout()
        self._split_buttons: list[QPushButton] = []
        for parts in (2, 3, 4):
            btn = QPushButton(f"Split {parts}")
            btn.clicked.connect(lambda _checked=False, p=parts: self.splitRequested.emit(p))
            split_row.addWidget(btn)
            self._split_buttons.append(btn)
        action_layout.addLayout(split_row)
        self._clear_btn = QPushButton("Clear")
        self._clear_btn.clicked.connect(self.clearRequested.emit)
        action_layout.addWidget(self._clear_btn)

        main.addWidget(info_group)
        main.addWidget(sample_group)
        main.addWidget(action_group)
        main.addStretch(1)

        self._slot_combo.currentIndexChanged.connect(self._emit_slot)
        self._velocity.valueChanged.connect(lambda value: self.velocityChanged.emit(value / 100.0))
        self._pitch.valueChanged.connect(self.pitchChanged.emit)

    def _emit_slot(self) -> None:
        value = self._slot_combo.currentData()
        if value is None:
            self.slotChanged.emit(-1)
            return
        self.slotChanged.emit(int(value))

    def _set_leaf_controls_enabled(self, enabled: bool) -> None:
        self._slot_combo.setEnabled(enabled)
        self._velocity.setEnabled(enabled)
        self._pitch.setEnabled(enabled)
        self._clear_btn.setEnabled(enabled)

    def set_node(self, path: str | None, node: RhythmNode | None) -> None:
        blockers = [
            QSignalBlocker(self._slot_combo),
            QSignalBlocker(self._velocity),
            QSignalBlocker(self._pitch),
        ]
        self._path.setText(path if node is not None and path else "-")

        if node is None:
            self._duration.setText("-")
            self._node_type.setText("None")
            self._slot_combo.setCurrentIndex(0)
            self._velocity.setValue(100)
            self._pitch.setValue(0)
            self._set_leaf_controls_enabled(False)
            for btn in self._split_buttons:
                btn.setEnabled(False)
            del blockers
            return

        self._duration.setText(f"{node.duration_fraction:.6f}")
        if node.is_leaf():
            self._node_type.setText("Leaf")
            self._slot_combo.setCurrentIndex(0 if node.sample_slot is None else node.sample_slot + 1)
            self._velocity.setValue(int(round(node.velocity * 100)))
            self._pitch.setValue(int(node.pitch_offset))
            self._set_leaf_controls_enabled(True)
            for btn in self._split_buttons:
                btn.setEnabled(True)
            del blockers
            return

        self._node_type.setText("Internal")
        self._slot_combo.setCurrentIndex(0)
        self._velocity.setValue(100)
        self._pitch.setValue(0)
        self._set_leaf_controls_enabled(False)
        for btn in self._split_buttons:
            btn.setEnabled(False)
        del blockers
