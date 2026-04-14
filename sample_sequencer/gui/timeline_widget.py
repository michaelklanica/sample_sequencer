from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QMenu, QToolTip, QWidget

from audio.sample_library import MAX_SLOTS, SampleLibrary
from engine.pattern import Bar
from engine.rhythm_tree import RhythmNode
from sample_sequencer.gui.template_defs import TEMPLATE_DEFINITIONS


@dataclass(frozen=True)
class LeafHit:
    path: str
    node: RhythmNode
    rect: QRectF


@dataclass(frozen=True)
class GroupRegion:
    node: RhythmNode
    start_fraction: float
    duration_fraction: float
    depth: int
    sibling_index: int


class TimelineWidget(QWidget):
    blockSelected = Signal(str, object)
    splitRequested = Signal(str, int)
    clearRequested = Signal(str)
    slotAssignRequested = Signal(str, int)
    templateRequested = Signal(str, str)

    def __init__(self) -> None:
        super().__init__()
        self._bar: Bar | None = None
        self._sample_library: SampleLibrary | None = None
        self._selected_path: str | None = None
        self._hovered_node: RhythmNode | None = None
        self._leaf_hits: list[LeafHit] = []
        self.setMinimumHeight(120)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_bar(self, bar: Bar | None) -> None:
        self._bar = bar
        self._selected_path = None
        self._hovered_node = None
        self._leaf_hits = []
        self.update()

    def set_selected_node(self, node: RhythmNode | None, node_path: str | None = None) -> None:
        selected_path = node_path if node is not None and node.is_leaf() and self._leaf_path_exists(node_path) else None
        if self._selected_path == selected_path:
            return
        self._selected_path = selected_path
        self.update()

    def set_sample_library(self, sample_library: SampleLibrary | None) -> None:
        self._sample_library = sample_library
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

    def _leaf_path_exists(self, path: str) -> bool:
        if self._bar is None:
            return False
        return any(candidate_path == path for candidate_path, _node in self._iter_leaves(self._bar.root, "0"))

    def _short_sample_name(self, slot: int) -> str | None:
        if self._sample_library is None:
            return None
        if slot < 0 or slot >= len(self._sample_library.slots):
            return None
        sample = self._sample_library.slots[slot]
        if sample is None:
            return None
        stem = Path(sample.path.name).stem.replace("_", " ").strip()
        if not stem:
            return None
        words = stem.split()
        compact = " ".join(words[:2]) if words else stem
        return compact[:18]

    def _label_for_hit(self, hit: LeafHit) -> str:
        width = hit.rect.width()
        slot = hit.node.sample_slot
        if width <= 45:
            return ""
        if slot is None:
            return "Rest" if width >= 90 else "—"

        slot_label = f"S{slot}"
        if width < 90:
            return slot_label

        sample_name = self._short_sample_name(slot)
        if sample_name:
            return f"{slot_label} {sample_name}"
        return slot_label

    def _collect_group_regions(self, root_node: RhythmNode) -> list[GroupRegion]:
        regions: list[GroupRegion] = []

        def walk(node: RhythmNode, depth: int) -> None:
            if node.is_leaf():
                return
            for sibling_index, child in enumerate(node.children):
                if not child.is_leaf():
                    regions.append(
                        GroupRegion(
                            node=child,
                            start_fraction=child.start_fraction,
                            duration_fraction=child.duration_fraction,
                            depth=depth,
                            sibling_index=sibling_index,
                        )
                    )
                walk(child, depth + 1)

        walk(root_node, depth=0)
        return regions

    def _draw_group_regions(self, painter: QPainter, width: float, top: float, height: float) -> None:
        if self._bar is None:
            return
        min_region_width = 24.0
        max_visual_depth = 2
        regions = self._collect_group_regions(self._bar.root)
        for region in regions:
            region_width = region.duration_fraction * width
            if region_width < min_region_width:
                continue

            visual_depth = min(region.depth, max_visual_depth - 1)
            inset = 2.0 + (visual_depth * 4.0)
            region_top = top + inset
            region_height = max(10.0, height - (inset * 2.0))
            x = 8 + (region.start_fraction * width)

            if visual_depth == 0:
                alpha = 22 if region.sibling_index % 2 == 0 else 16
                outline_alpha = 55
            else:
                alpha = 14 if region.sibling_index % 2 == 0 else 10
                outline_alpha = 38

            fill_color = QColor(190, 210, 235, alpha)
            outline_color = QColor(220, 228, 240, outline_alpha)
            painter.fillRect(QRectF(x, region_top, region_width, region_height), fill_color)
            pen = QPen(outline_color)
            pen.setWidth(1)
            painter.setPen(pen)
            painter.drawLine(
                QPointF(x + 0.5, region_top + 0.5),
                QPointF(x + region_width - 0.5, region_top + 0.5),
            )
            painter.drawRect(QRectF(x + 0.5, region_top + 0.5, region_width - 1.0, region_height - 1.0))

    def paintEvent(self, event) -> None:  # type: ignore[override]
        del event
        self._rebuild_hits()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#202020"))

        painter.setPen(QColor("#DDDDDD"))
        painter.drawText(8, 16, "Timeline (single bar)")
        font_metrics = painter.fontMetrics()
        width = max(10, self.width() - 16)
        top = 24
        height = max(40, self.height() - 36)

        self._draw_group_regions(painter, width=float(width), top=float(top), height=float(height))

        for hit in self._leaf_hits:
            base_color = self._color_for_slot(hit.node.sample_slot)
            is_selected = hit.path == self._selected_path
            is_hovered = hit.node == self._hovered_node
            is_rest = hit.node.sample_slot is None

            fill_color = base_color
            border_color = QColor("#111111")
            border_width = 1
            draw_rect = QRectF(hit.rect)
            border_style = Qt.PenStyle.SolidLine

            if is_rest:
                fill_color = QColor("#5B5B5B")
                border_color = QColor("#9A9A9A")
                border_style = Qt.PenStyle.DashLine
            if is_selected:
                fill_color = base_color.darker(118)
                if is_rest:
                    fill_color = QColor("#4A4A4A")
                border_color = QColor("#FFB347")
                border_width = 3
                draw_rect.adjust(1, 1, -1, -1)
            elif is_hovered:
                fill_color = base_color.lighter(118)
                if is_rest:
                    fill_color = QColor("#6E6E6E")
                border_color = QColor("#D0D0D0")
                border_width = 2

            painter.setBrush(fill_color)
            pen = QPen(border_color)
            pen.setWidth(border_width)
            pen.setStyle(border_style)
            painter.setPen(pen)
            painter.drawRect(draw_rect)

            label = self._label_for_hit(hit)
            if not label:
                continue

            text_padding = 6
            text_rect = draw_rect.adjusted(text_padding, 0, -text_padding, 0)
            if text_rect.width() <= 6:
                continue

            text_color = QColor("#101010")
            if is_selected:
                text_color = QColor("#FFFFFF")
            elif is_rest:
                text_color = QColor("#E5E5E5")

            painter.setPen(text_color)
            text = font_metrics.elidedText(label, Qt.TextElideMode.ElideRight, int(text_rect.width()))
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)

    def _hit_test(self, point: QPointF | QPoint) -> LeafHit | None:
        self._rebuild_hits()
        lookup_point = QPointF(point)
        for hit in self._leaf_hits:
            if hit.rect.contains(lookup_point):
                return hit
        return None

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        hit = self._hit_test(event.position())
        node = None if hit is None else hit.node
        if node != self._hovered_node:
            self._hovered_node = node
            self.setCursor(Qt.CursorShape.PointingHandCursor if node is not None else Qt.CursorShape.ArrowCursor)
            self.update()
        if hit is not None:
            slot_text = "Rest" if hit.node.sample_slot is None else f"S{hit.node.sample_slot}"
            name = ""
            if hit.node.sample_slot is not None:
                short_name = self._short_sample_name(hit.node.sample_slot)
                if short_name:
                    name = f" · {short_name}"
            vel = f" · v{hit.node.velocity:.2f}"
            dur = f" · {hit.node.duration_fraction:.3f}"
            QToolTip.showText(event.globalPosition().toPoint(), f"{slot_text}{name}{vel}{dur}", self)
        else:
            QToolTip.hideText()

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        del event
        if self._hovered_node is not None:
            self._hovered_node = None
            self.unsetCursor()
            self.update()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            self.setFocus(Qt.FocusReason.MouseFocusReason)
        hit = self._hit_test(event.position())
        if event.button() == Qt.MouseButton.LeftButton:
            if hit is not None:
                self.blockSelected.emit(hit.path, hit.node)
            else:
                self.blockSelected.emit("", None)
        if event.button() == Qt.MouseButton.RightButton and hit is not None:
            self._open_context_menu(event.globalPosition().toPoint(), hit)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[override]
        hit = self._hit_test(event.position())
        if event.button() == Qt.MouseButton.LeftButton and hit is not None and hit.node.is_leaf():
            parts = 3 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 2
            self.splitRequested.emit(hit.path, parts)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.isAutoRepeat():
            super().keyPressEvent(event)
            return
        key_to_parts = {
            Qt.Key.Key_2: 2,
            Qt.Key.Key_3: 3,
            Qt.Key.Key_4: 4,
            Qt.Key.Key_5: 5,
            Qt.Key.Key_6: 6,
        }
        parts = key_to_parts.get(event.key())
        if parts is not None and self._selected_path is not None:
            node_map: dict[str, RhythmNode] = {}
            if self._bar is not None:
                node_map = dict(self._iter_leaves(self._bar.root, "0"))
            selected_node = node_map.get(self._selected_path)
            if selected_node is not None and selected_node.is_leaf():
                self.splitRequested.emit(self._selected_path, parts)
                event.accept()
                return
        super().keyPressEvent(event)

    def _selected_info_label(self, node: RhythmNode) -> str:
        if not node.is_leaf():
            return "Selected: Internal Group"
        if node.sample_slot is None:
            return "Selected: Rest"
        return f"Selected: Slot {node.sample_slot}"

    def _add_selection_info(self, menu: QMenu, node: RhythmNode) -> None:
        info_action = menu.addAction(self._selected_info_label(node))
        info_action.setEnabled(False)
        menu.addSeparator()

    def _add_split_actions(self, menu: QMenu, path: str) -> None:
        split_two_action = menu.addAction("Split into 2")
        split_two_action.triggered.connect(lambda: self.splitRequested.emit(path, 2))

        split_three_action = menu.addAction("Split into 3")
        split_three_action.triggered.connect(lambda: self.splitRequested.emit(path, 3))

        split_menu = menu.addMenu("Split More")
        for parts in (4, 5, 6):
            action = split_menu.addAction(f"Split into {parts}")
            action.triggered.connect(lambda _checked=False, p=parts: self.splitRequested.emit(path, p))

    def _add_template_actions(self, menu: QMenu, path: str) -> None:
        template_menu = menu.addMenu("Apply Template")
        for index, definition in enumerate(TEMPLATE_DEFINITIONS):
            if index == 5:
                template_menu.addSeparator()
            action = template_menu.addAction(definition.label)
            action.triggered.connect(
                lambda _checked=False, template_id=definition.template_id: self.templateRequested.emit(path, template_id)
            )

    def _build_leaf_context_menu(self, menu: QMenu, hit: LeafHit) -> None:
        self._add_split_actions(menu, hit.path)
        self._add_template_actions(menu, hit.path)
        menu.addSeparator()

        assign_menu = menu.addMenu("Assign Slot")
        for slot in range(MAX_SLOTS):
            action = assign_menu.addAction(f"Slot {slot}")
            action.triggered.connect(lambda _checked=False, s=slot: self.slotAssignRequested.emit(hit.path, s))

        menu.addSeparator()
        set_rest_action = menu.addAction("Set Rest")
        set_rest_action.triggered.connect(lambda: self.clearRequested.emit(hit.path))
        clear_assignment_action = menu.addAction("Clear Assignment")
        clear_assignment_action.triggered.connect(lambda: self.clearRequested.emit(hit.path))

    def _build_internal_context_menu(self, menu: QMenu, hit: LeafHit) -> None:
        del menu
        del hit

    def _open_context_menu(self, global_pos: QPoint, hit: LeafHit) -> None:
        menu = QMenu(self)
        self._add_selection_info(menu, hit.node)
        if hit.node.is_leaf():
            self._build_leaf_context_menu(menu, hit)
        else:
            self._build_internal_context_menu(menu, hit)

        menu.exec(global_pos)
