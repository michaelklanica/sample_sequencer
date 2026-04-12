from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QWidget, QVBoxLayout

from engine.pattern import Pattern


class BarListPanel(QWidget):
    barSelected = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self._list = QListWidget()
        layout = QVBoxLayout(self)
        layout.addWidget(self._list)
        self._list.currentRowChanged.connect(self.barSelected.emit)

    def set_pattern(self, pattern: Pattern, selected_index: int) -> None:
        blocker = QSignalBlocker(self._list)
        self._list.clear()
        for index, bar in enumerate(pattern.bars):
            text = f"Bar {index} - {bar.time_signature.as_text()}"
            self._list.addItem(QListWidgetItem(text))
        self._list.setCurrentRow(selected_index)
        del blocker

    def set_selected_bar(self, index: int) -> None:
        blocker = QSignalBlocker(self._list)
        self._list.setCurrentRow(index)
        del blocker
