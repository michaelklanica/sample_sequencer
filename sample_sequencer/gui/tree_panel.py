from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from engine.pattern import Bar
from engine.rhythm_tree import RhythmNode


class TreePanel(QWidget):
    nodeSelected = Signal(str, object)

    def __init__(self) -> None:
        super().__init__()
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Subdivision Tree"])
        self._items_by_path: dict[str, QTreeWidgetItem] = {}
        layout = QVBoxLayout(self)
        layout.addWidget(self._tree)
        self._tree.itemSelectionChanged.connect(self._emit_selection)

    def _emit_selection(self) -> None:
        selected = self._tree.selectedItems()
        if not selected:
            self.nodeSelected.emit("", None)
            return
        item = selected[0]
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(path, str):
            self.nodeSelected.emit(path, None)

    def set_bar(self, bar: Bar, selected_path: str | None) -> None:
        self._items_by_path.clear()
        blocker = QSignalBlocker(self._tree)
        self._tree.clear()

        def add_item(parent: QTreeWidgetItem | QTreeWidget, node: RhythmNode, path: str) -> None:
            label = f"{path} | start={node.start_fraction:.3f} dur={node.duration_fraction:.3f}"
            if node.is_leaf():
                label += f" | slot={node.sample_slot} vel={node.velocity:.2f} pitch={node.pitch_offset}"
            item = QTreeWidgetItem([label])
            item.setData(0, Qt.ItemDataRole.UserRole, path)
            self._items_by_path[path] = item
            parent.addChild(item) if isinstance(parent, QTreeWidgetItem) else parent.addTopLevelItem(item)
            for idx, child in enumerate(node.children):
                add_item(item, child, f"{path}.{idx}")

        add_item(self._tree, bar.root, "0")
        self._tree.expandAll()
        del blocker
        self.set_selected_path(selected_path)

    def set_selected_path(self, path: str | None) -> None:
        blocker = QSignalBlocker(self._tree)
        if not path:
            self._tree.clearSelection()
            self._tree.setCurrentItem(None)
            del blocker
            return
        item = self._items_by_path.get(path)
        if item is None:
            self._tree.clearSelection()
            self._tree.setCurrentItem(None)
            del blocker
            return
        self._tree.setCurrentItem(item)
        item.setSelected(True)
        del blocker
