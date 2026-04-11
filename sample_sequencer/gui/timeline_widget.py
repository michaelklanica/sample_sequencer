from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QAction, QColor, QPainter, QPen
from PySide6.QtWidgets import QMenu, QWidget

from engine.pattern import Bar
from engine.rhythm_tree import RhythmNode


@dataclass(frozen=True)
class LeafHit:
    path: str
    node: RhythmNode
    rect: QRectF


class TimelineWidget(QWidget):
    blockSelected = Signal(str)
    splitRequested = Signal(str, int)
    clearRequested = Signal(str)
    templateRequested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._bar: Bar | None = None
        self._selected_path: str | None = None
        self._leaf_hits: list[LeafHit] = []
        self.setMinimumHeight(120)

    def set_bar(self, bar: Bar | None) -> None:
        self._bar = bar
        self.update()

    def set_selected_node(self, node_path: str | None) -> None:
        self._selected_path = node_path
        self.update()

    def _iter_leaves(self, node: RhythmNode, path: str) -> list[tuple[str, RhythmNode]]:
        if node.is_leaf():
            return [(path, node)]
        leaves: list[tuple[str, RhythmNode]] = []
        for idx, child in enumerate(node.children):
            leaves.extend(self._iter_leaves(child, f"{path}.{idx}"))
        return leaves

    def _color_for_slot(self, slot: int | None) -> QColor:
        palette = [
            QColor("#5DA5DA"),
            QColor("#60BD68"),
            QColor("#F17CB0"),
            QColor("#B2912F"),
            QColor("#B276B2"),
            QColor("#DECF3F"),
            QColor("#F15854"),
            QColor("#4D4D4D"),
        ]
        if slot is None:
            return QColor("#8A8A8A")
        return palette[slot % len(palette)]

    def _rebuild_hits(self) -> None:
        self._leaf_hits = []
        if self._bar is None:
            return
        leaves = self._iter_leaves(self._bar.root, "0")
        if not leaves:
            return
        width = max(10, self.width() - 16)
        top = 24
        height = max(40, self.height() - 36)
        for path, leaf in leaves:
            x = 8 + (leaf.start_fraction * width)
            w = max(4.0, leaf.duration_fraction * width)
            self._leaf_hits.append(LeafHit(path=path, node=leaf, rect=QRectF(x, top, w, height)))

    def paintEvent(self, event) -> None:  # type: ignore[override]
        del event
        self._rebuild_hits()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#202020"))

        painter.setPen(QColor("#DDDDDD"))
        painter.drawText(8, 16, "Timeline (single bar)")

        for hit in self._leaf_hits:
            color = self._color_for_slot(hit.node.sample_slot)
            painter.setBrush(color)
            pen = QPen(QColor("#111111"))
            pen.setWidth(1)
            painter.setPen(pen)
            painter.drawRect(hit.rect)

            if hit.path == self._selected_path:
                select_pen = QPen(QColor("#FFD166"))
                select_pen.setWidth(3)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(select_pen)
                painter.drawRect(hit.rect)

    def _hit_test(self, point: QPoint) -> LeafHit | None:
        for hit in self._leaf_hits:
            if hit.rect.contains(point):
                return hit
        return None

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        hit = self._hit_test(event.position().toPoint())
        if event.button() == Qt.MouseButton.LeftButton and hit is not None:
            self.blockSelected.emit(hit.path)
        if event.button() == Qt.MouseButton.RightButton and hit is not None:
            self._open_context_menu(event.globalPosition().toPoint(), hit)

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[override]
        hit = self._hit_test(event.position().toPoint())
        if event.button() == Qt.MouseButton.LeftButton and hit is not None:
            self.splitRequested.emit(hit.path, 2)

    def _open_context_menu(self, global_pos: QPoint, hit: LeafHit) -> None:
        menu = QMenu(self)

        split_menu = menu.addMenu("Split")
        for parts in (2, 3, 4, 5, 6):
            action = QAction(str(parts), self)
            action.triggered.connect(lambda _checked=False, p=parts: self.splitRequested.emit(hit.path, p))
            split_menu.addAction(action)

        clear_action = QAction("Clear", self)
        clear_action.triggered.connect(lambda: self.clearRequested.emit(hit.path))
        menu.addAction(clear_action)

        template_action = QAction("Apply Template (stub)", self)
        template_action.triggered.connect(lambda: self.templateRequested.emit(hit.path))
        menu.addAction(template_action)

        menu.exec(global_pos)
