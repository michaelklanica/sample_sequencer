from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from engine.pattern import Bar
from engine.rhythm_tree import RhythmNode


class TreePanel(QWidget):
    nodeSelected = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Subdivision Tree"])
        layout = QVBoxLayout(self)
        layout.addWidget(self._tree)
        self._tree.itemSelectionChanged.connect(self._emit_selection)

    def _emit_selection(self) -> None:
        selected = self._tree.selectedItems()
        if not selected:
            return
        path = selected[0].data(0, Qt.ItemDataRole.UserRole)
        if isinstance(path, str):
            self.nodeSelected.emit(path)

    def set_bar(self, bar: Bar, selected_path: str) -> None:
        self._tree.blockSignals(True)
        self._tree.clear()

        def add_item(parent: QTreeWidgetItem | QTreeWidget, node: RhythmNode, path: str) -> None:
            label = f"{path} | start={node.start_fraction:.3f} dur={node.duration_fraction:.3f}"
            if node.is_leaf():
                label += f" | slot={node.sample_slot} vel={node.velocity:.2f} pitch={node.pitch_offset}"
            item = QTreeWidgetItem([label])
            item.setData(0, Qt.ItemDataRole.UserRole, path)
            parent.addChild(item) if isinstance(parent, QTreeWidgetItem) else parent.addTopLevelItem(item)
            if path == selected_path:
                self._tree.setCurrentItem(item)
            for idx, child in enumerate(node.children):
                add_item(item, child, f"{path}.{idx}")

        add_item(self._tree, bar.root, "0")
        self._tree.expandAll()
        self._tree.blockSignals(False)
