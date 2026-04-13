from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget


class ArrangementPanel(QWidget):
    addClicked = Signal()
    removeClicked = Signal(int)
    moveUpClicked = Signal(int)
    moveDownClicked = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        self.list = QListWidget()
        layout.addWidget(self.list)

        row = QHBoxLayout()
        self.add_btn = QPushButton("Add Step")
        self.remove_btn = QPushButton("Remove")
        self.up_btn = QPushButton("Up")
        self.down_btn = QPushButton("Down")
        for b in [self.add_btn, self.remove_btn, self.up_btn, self.down_btn]:
            row.addWidget(b)
        layout.addLayout(row)

        self.add_btn.clicked.connect(self.addClicked.emit)
        self.remove_btn.clicked.connect(self._emit_remove)
        self.up_btn.clicked.connect(self._emit_up)
        self.down_btn.clicked.connect(self._emit_down)

    def set_arrangement(self, arrangement: list[int], pattern_names: list[str]) -> None:
        selected = self.list.currentRow()
        self.list.clear()
        for i, pattern_idx in enumerate(arrangement, start=1):
            name = pattern_names[pattern_idx] if 0 <= pattern_idx < len(pattern_names) else "(Invalid)"
            self.list.addItem(QListWidgetItem(f"{i}: {name}"))
        if self.list.count() > 0:
            self.list.setCurrentRow(min(max(selected, 0), self.list.count() - 1))

    def _emit_remove(self) -> None:
        idx = self.list.currentRow()
        if idx >= 0:
            self.removeClicked.emit(idx)

    def _emit_up(self) -> None:
        idx = self.list.currentRow()
        if idx > 0:
            self.moveUpClicked.emit(idx)

    def _emit_down(self) -> None:
        idx = self.list.currentRow()
        if idx >= 0 and idx < self.list.count() - 1:
            self.moveDownClicked.emit(idx)
