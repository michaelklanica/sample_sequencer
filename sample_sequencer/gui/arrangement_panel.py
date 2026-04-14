from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QHBoxLayout, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget


class ArrangementPanel(QWidget):
    appendCurrentClicked = Signal()
    insertCurrentClicked = Signal()
    duplicateClicked = Signal(int)
    removeClicked = Signal(int)
    moveUpClicked = Signal(int)
    moveDownClicked = Signal(int)
    jumpToPatternRequested = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        self.list = QListWidget()
        layout.addWidget(self.list)

        row = QHBoxLayout()
        self.add_btn = QPushButton("+ Current")
        self.insert_btn = QPushButton("Insert")
        self.duplicate_btn = QPushButton("Duplicate")
        self.remove_btn = QPushButton("Remove")
        self.up_btn = QPushButton("Up")
        self.down_btn = QPushButton("Down")
        for b in [self.add_btn, self.insert_btn, self.duplicate_btn, self.up_btn, self.down_btn, self.remove_btn]:
            row.addWidget(b)
        layout.addLayout(row)

        self.add_btn.clicked.connect(self.appendCurrentClicked.emit)
        self.insert_btn.clicked.connect(self.insertCurrentClicked.emit)
        self.duplicate_btn.clicked.connect(self._emit_duplicate)
        self.remove_btn.clicked.connect(self._emit_remove)
        self.up_btn.clicked.connect(self._emit_up)
        self.down_btn.clicked.connect(self._emit_down)
        self.list.itemDoubleClicked.connect(self._emit_jump_to_pattern)
        self._install_shortcuts()

    def _install_shortcuts(self) -> None:
        delete_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Delete), self.list)
        delete_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        delete_shortcut.activated.connect(self._emit_remove)

        duplicate_shortcut = QShortcut(QKeySequence("Ctrl+D"), self.list)
        duplicate_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        duplicate_shortcut.activated.connect(self._emit_duplicate)

        move_up_shortcut = QShortcut(QKeySequence("Alt+Up"), self.list)
        move_up_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        move_up_shortcut.activated.connect(self._emit_up)

        move_down_shortcut = QShortcut(QKeySequence("Alt+Down"), self.list)
        move_down_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        move_down_shortcut.activated.connect(self._emit_down)

        self._shortcuts = [delete_shortcut, duplicate_shortcut, move_up_shortcut, move_down_shortcut]

    def selected_row(self) -> int:
        return self.list.currentRow()

    def set_selected_row(self, index: int) -> None:
        if self.list.count() == 0:
            return
        self.list.setCurrentRow(max(0, min(index, self.list.count() - 1)))

    def set_arrangement(self, arrangement: list[int], pattern_names: list[str], selected_index: int | None = None) -> None:
        selected = self.list.currentRow() if selected_index is None else selected_index
        self.list.clear()
        for i, pattern_idx in enumerate(arrangement, start=1):
            name = pattern_names[pattern_idx] if 0 <= pattern_idx < len(pattern_names) else "(Invalid)"
            self.list.addItem(QListWidgetItem(f"{i}. {name} (P{pattern_idx + 1})"))
        if self.list.count() > 0:
            self.list.setCurrentRow(min(max(selected, 0), self.list.count() - 1))
        self.remove_btn.setEnabled(self.list.count() > 1)
        current = self.list.currentRow()
        self.up_btn.setEnabled(current > 0)
        self.down_btn.setEnabled(0 <= current < self.list.count() - 1)
        self.duplicate_btn.setEnabled(current >= 0)
        self.insert_btn.setEnabled(self.list.count() > 0)

    def _emit_remove(self) -> None:
        idx = self.list.currentRow()
        if idx >= 0:
            self.removeClicked.emit(idx)

    def _emit_duplicate(self) -> None:
        idx = self.list.currentRow()
        if idx >= 0:
            self.duplicateClicked.emit(idx)

    def _emit_up(self) -> None:
        idx = self.list.currentRow()
        if idx > 0:
            self.moveUpClicked.emit(idx)

    def _emit_down(self) -> None:
        idx = self.list.currentRow()
        if idx >= 0 and idx < self.list.count() - 1:
            self.moveDownClicked.emit(idx)

    def _emit_jump_to_pattern(self, item: QListWidgetItem) -> None:
        idx = self.list.row(item)
        if idx >= 0:
            self.jumpToPatternRequested.emit(idx)
