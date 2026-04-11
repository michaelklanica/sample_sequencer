from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
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
        self._hovered_node: RhythmNode | None = None
        self._leaf_hits: list[LeafHit] = []
        self.setMinimumHeight(120)
        self.setMouseTracking(True)

    def set_bar(self, bar: Bar | None) -> None:
        self._bar = bar
        self._hovered_node = None
        self.update()

    def set_selected_node(self, node_path: str | None) -> None:
        if self._selected_path == node_path:
            return
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
            base_color = self._color_for_slot(hit.node.sample_slot)
            is_selected = hit.path == self._selected_path
            is_hovered = hit.node == self._hovered_node

            fill_color = base_color
            border_color = QColor("#111111")
            border_width = 1
            draw_rect = QRectF(hit.rect)

            if is_selected:
                fill_color = base_color.darker(118)
                border_color = QColor("#FFB347")
                border_width = 3
                draw_rect.adjust(1, 1, -1, -1)
            elif is_hovered:
                fill_color = base_color.lighter(118)
                border_color = QColor("#D0D0D0")
                border_width = 2

            painter.setBrush(fill_color)
            pen = QPen(border_color)
            pen.setWidth(border_width)
            painter.setPen(pen)
            painter.drawRect(draw_rect)

    def _hit_test(self, point: QPointF | QPoint) -> LeafHit | None:
        self._rebuild_hits()
        lookup_point = QPointF(point)
        for hit in self._leaf_hits:
            if hit.rect.contains(lookup_point):
                return hit
        return None

    def _node_at_pos(self, pos: QPointF) -> RhythmNode | None:
        hit = self._hit_test(pos)
        if hit is None:
            return None
        return hit.node

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        node = self._node_at_pos(event.position())
        if node != self._hovered_node:
            self._hovered_node = node
            self.setCursor(Qt.CursorShape.PointingHandCursor if node is not None else Qt.CursorShape.ArrowCursor)
            self.update()

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        del event
        if self._hovered_node is not None:
            self._hovered_node = None
            self.unsetCursor()
            self.update()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        hit = self._hit_test(event.position())
        if event.button() == Qt.MouseButton.LeftButton:
            if hit is not None:
                self.blockSelected.emit(hit.path)
        if event.button() == Qt.MouseButton.RightButton and hit is not None:
            self._open_context_menu(event.globalPosition().toPoint(), hit)

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[override]
        hit = self._hit_test(event.position())
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
