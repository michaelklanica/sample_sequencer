from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from sample_sequencer.gui.bar_list_panel import BarListPanel
from sample_sequencer.gui.inspector_panel import InspectorPanel
from sample_sequencer.gui.slot_panel import SlotPanel
from sample_sequencer.gui.timeline_widget import TimelineWidget
from sample_sequencer.gui.transport_panel import TransportPanel
from sample_sequencer.gui.tree_panel import TreePanel


class MainWindow(QMainWindow):
    modeChanged = Signal(str)
    playClicked = Signal()
    stopClicked = Signal()
    newClicked = Signal()
    saveClicked = Signal()
    loadClicked = Signal()
    exportClicked = Signal()
    exportModeChanged = Signal(str)
    loadSamplesClicked = Signal()
    reloadSamplesClicked = Signal()
    bpmChanged = Signal(float)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Sample Sequencer - GUI Phase 1")
        self.resize(1280, 760)

        root = QWidget()
        root_layout = QVBoxLayout(root)

        toolbar = QWidget()
        toolbar_layout = QHBoxLayout(toolbar)
        self.play_btn = QPushButton("Play")
        self.stop_btn = QPushButton("Stop")
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Bar", "Pattern", "Chain"])
        self.new_btn = QPushButton("New")
        self.save_btn = QPushButton("Save")
        self.load_btn = QPushButton("Load")
        self.export_btn = QPushButton("Export")
        self.export_mode_label = QLabel("Export Mode:")
        self.export_mode_combo = QComboBox()
        self.export_mode_combo.addItem("Truncate", userData="truncate")
        self.export_mode_combo.addItem("Wrap", userData="wrap")
        self.export_mode_combo.addItem("Tail", userData="tail")
        self.load_samples_btn = QPushButton("Load Samples")
        self.reload_samples_btn = QPushButton("Reload Samples")
        self.bpm_label = QLabel("BPM:")
        self.bpm_spin = QDoubleSpinBox()
        self.bpm_spin.setRange(20.0, 300.0)
        self.bpm_spin.setSingleStep(1.0)
        self.bpm_spin.setDecimals(1)
        self.bpm_spin.setValue(120.0)
        for widget in [
            self.play_btn,
            self.stop_btn,
            self.mode_combo,
            self.new_btn,
            self.save_btn,
            self.load_btn,
            self.export_btn,
            self.export_mode_label,
            self.export_mode_combo,
            self.load_samples_btn,
            self.reload_samples_btn,
            self.bpm_label,
            self.bpm_spin,
        ]:
            toolbar_layout.addWidget(widget)
        toolbar_layout.addStretch(1)

        self.bar_list_panel = BarListPanel()
        self.tree_panel = TreePanel()
        self.timeline_widget = TimelineWidget()
        self.inspector_panel = InspectorPanel()
        self.slot_panel = SlotPanel()
        self.transport_panel = TransportPanel()

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(self.bar_list_panel)
        left_layout.addWidget(self.tree_panel)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(self.inspector_panel)
        right_layout.addWidget(self.slot_panel)

        center_split = QSplitter()
        center_split.addWidget(left)
        center_split.addWidget(self.timeline_widget)
        center_split.addWidget(right)
        center_split.setSizes([260, 700, 320])

        root_layout.addWidget(toolbar)
        root_layout.addWidget(center_split, 1)
        root_layout.addWidget(self.transport_panel)
        self.setCentralWidget(root)

        self.play_btn.clicked.connect(self.playClicked.emit)
        self.stop_btn.clicked.connect(self.stopClicked.emit)
        self.new_btn.clicked.connect(self.newClicked.emit)
        self.save_btn.clicked.connect(self.saveClicked.emit)
        self.load_btn.clicked.connect(self.loadClicked.emit)
        self.export_btn.clicked.connect(self.exportClicked.emit)
        self.export_mode_combo.currentIndexChanged.connect(self._emit_export_mode_changed)
        self.load_samples_btn.clicked.connect(self.loadSamplesClicked.emit)
        self.reload_samples_btn.clicked.connect(self.reloadSamplesClicked.emit)
        self.mode_combo.currentTextChanged.connect(self.modeChanged.emit)
        self.bpm_spin.valueChanged.connect(self.bpmChanged.emit)

    def set_bpm_value(self, bpm: float) -> None:
        blocker = QSignalBlocker(self.bpm_spin)
        self.bpm_spin.setValue(bpm)
        del blocker

    def _emit_export_mode_changed(self) -> None:
        self.exportModeChanged.emit(self.export_mode())

    def export_mode(self) -> str:
        return str(self.export_mode_combo.currentData() or "truncate")

    def set_export_mode(self, mode: str) -> None:
        for idx in range(self.export_mode_combo.count()):
            if self.export_mode_combo.itemData(idx) == mode:
                blocker = QSignalBlocker(self.export_mode_combo)
                self.export_mode_combo.setCurrentIndex(idx)
                del blocker
                return
