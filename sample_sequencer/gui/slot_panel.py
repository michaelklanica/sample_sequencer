from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from audio.sample_library import MAX_SLOTS, SampleLibrary


class SlotPanel(QWidget):
    slotClicked = Signal(int)
    slotDoubleClicked = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self._list = QListWidget()
        self._selected_slot: int | None = None
        self._items_by_slot: dict[int, QListWidgetItem] = {}
        self._assignment_enabled = False
        layout = QVBoxLayout(self)
        layout.addWidget(self._list)
        self._list.itemClicked.connect(self._on_clicked)
        self._list.itemDoubleClicked.connect(self._on_double_clicked)
        self.set_assignment_enabled(False)

    def set_library(self, library: SampleLibrary) -> None:
        self._items_by_slot.clear()
        self._list.clear()
        for slot in range(MAX_SLOTS):
            sample = library.slots[slot]
            text = f"{slot:02d} - {sample.path.name if sample is not None else '(empty)'}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, slot)
            self._items_by_slot[slot] = item
            self._list.addItem(item)
        self.set_selected_slot(self._selected_slot)

    def set_selected_slot(self, slot: int | None) -> None:
        self._selected_slot = slot
        blocker = QSignalBlocker(self._list)
        if slot is None or slot not in self._items_by_slot:
            self._list.clearSelection()
            self._list.setCurrentItem(None)
            del blocker
            return
        item = self._items_by_slot[slot]
        self._list.setCurrentItem(item)
        item.setSelected(True)
        del blocker

    def set_assignment_enabled(self, enabled: bool) -> None:
        self._assignment_enabled = enabled
        self._list.setEnabled(enabled)

    def _on_clicked(self, item: QListWidgetItem) -> None:
        if not self._assignment_enabled:
            return
        slot = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(slot, int):
            self.slotClicked.emit(slot)

    def _on_double_clicked(self, item: QListWidgetItem) -> None:
        slot = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(slot, int):
            self.slotDoubleClicked.emit(slot)
