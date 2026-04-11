from __future__ import annotations

from PySide6.QtCore import Signal
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
        self._list.blockSignals(True)
        self._list.clear()
        for index, bar in enumerate(pattern.bars):
            text = f"Bar {index} - {bar.time_signature.as_text()}"
            self._list.addItem(QListWidgetItem(text))
        self._list.setCurrentRow(selected_index)
        self._list.blockSignals(False)
