from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget


class PatternPanel(QWidget):
    patternSelected = Signal(int)
    createClicked = Signal()
    renameClicked = Signal(int)
    deleteClicked = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        self.list = QListWidget()
        self.new_btn = QPushButton("+ New Pattern")
        row = QHBoxLayout()
        self.rename_btn = QPushButton("Rename")
        self.delete_btn = QPushButton("Delete")
        row.addWidget(self.rename_btn)
        row.addWidget(self.delete_btn)

        layout.addWidget(self.list)
        layout.addLayout(row)
        layout.addWidget(self.new_btn)

        self.list.currentRowChanged.connect(self.patternSelected.emit)
        self.new_btn.clicked.connect(self.createClicked.emit)
        self.rename_btn.clicked.connect(self._emit_rename)
        self.delete_btn.clicked.connect(self._emit_delete)

    def set_patterns(self, names: list[str], current_index: int) -> None:
        self.list.clear()
        for name in names:
            self.list.addItem(QListWidgetItem(name))
        if 0 <= current_index < len(names):
            self.list.setCurrentRow(current_index)

    def _emit_rename(self) -> None:
        idx = self.list.currentRow()
        if idx >= 0:
            self.renameClicked.emit(idx)

    def _emit_delete(self) -> None:
        idx = self.list.currentRow()
        if idx >= 0:
            self.deleteClicked.emit(idx)
