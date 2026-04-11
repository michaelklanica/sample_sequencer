from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from audio.sample_library import MAX_SLOTS, SampleLibrary


class SlotPanel(QWidget):
    slotClicked = Signal(int)
    slotDoubleClicked = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self._list = QListWidget()
        layout = QVBoxLayout(self)
        layout.addWidget(self._list)
        self._list.itemClicked.connect(self._on_clicked)
        self._list.itemDoubleClicked.connect(self._on_double_clicked)

    def set_library(self, library: SampleLibrary) -> None:
        self._list.clear()
        for slot in range(MAX_SLOTS):
            sample = library.slots[slot]
            text = f"{slot:02d} - {sample.path.name if sample is not None else '(empty)'}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, slot)
            self._list.addItem(item)

    def _on_clicked(self, item: QListWidgetItem) -> None:
        slot = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(slot, int):
            self.slotClicked.emit(slot)

    def _on_double_clicked(self, item: QListWidgetItem) -> None:
        slot = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(slot, int):
            self.slotDoubleClicked.emit(slot)
