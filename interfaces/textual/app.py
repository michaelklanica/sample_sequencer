from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal
from textual.timer import Timer

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Input, Static, Tree

from audio.export import export_bars, export_pattern
from audio.playback import play_once
from audio.realtime import RealtimeLooper
from audio.renderer import OfflineRenderer
from audio.sample_library import MAX_SLOTS, SampleLibrary
from engine.edit_policy import classify_edit, invalidation_reason
from engine.event_value_ops import (
    EventValueClipboard,
    apply_leaf_event_values,
    copy_leaf_event_values,
    fill_sibling_leaves,
    initialize_bar_grid,
)
from engine.pattern import Pattern, create_blank_bar, create_blank_pattern
from engine.project import Project
from engine.power_tools import (
    LeafEventValue,
    apply_subtree_template,
    alternate_fill_siblings,
    euclidean_fill_siblings,
    repeat_motif_across_siblings,
    rotate_sibling_event_values,
)
from engine.rhythm_tree import RhythmNode
from engine.time_signature import TimeSignature
from engine.tree_ops import copy_subtree, paste_subtree_over_target, reset_subtree
from sequencer_io import LoadedPatternProject, load_pattern_project_from_json, save_pattern_project_to_json
from sequencer_io.json_errors import PatternJsonError, PatternValidationError


@dataclass(frozen=True)
class NodeRef:
    path: str


class PromptScreen(ModalScreen[str | None]):
    def __init__(self, title: str, placeholder: str = "") -> None:
        super().__init__()
        self._title = title
        self._placeholder = placeholder

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static(self._title, id="prompt_title"),
            Input(placeholder=self._placeholder, id="prompt_input"),
            Static("Press Enter to submit, Esc to cancel."),
            id="prompt_box",
        )

    def on_mount(self) -> None:
        self.query_one("#prompt_input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip())

    def action_cancel(self) -> None:
        self.dismiss(None)


class SequencerTUI(App[None]):
    DEFAULT_EXPORT_DIR = Path("exports")
    TRANSPORT_REFRESH_SECONDS = 0.15

    CSS = """
    Screen { layout: vertical; }
    #main_row { height: 1fr; }
    #left_panel { width: 2fr; }
    #right_panel { width: 1fr; }
    #bar_list_panel, #tree_panel, #inspector_panel, #slots_panel, #status_panel, #transport_panel {
        border: solid $accent;
    }
    #slots_panel { height: 1fr; }
    #bar_list_panel { height: 8; }
    #transport_panel { height: 11; }
    #status_panel { height: 12; }
    #prompt_box {
        width: 60;
        height: auto;
        padding: 1;
        border: thick $accent;
        background: $surface;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("2", "split_selected(2)", "Split 2"),
        Binding("3", "split_selected(3)", "Split 3"),
        Binding("4", "split_selected(4)", "Split 4"),
        Binding("5", "split_selected(5)", "Split 5"),
        Binding("6", "split_selected(6)", "Split 6"),
        Binding("s", "set_slot", "Set/Clear Slot"),
        Binding("z", "audition_selected_slot", "Audition Leaf Slot"),
        Binding("Z", "audition_slot_prompt", "Audition Slot #"),
        Binding("v", "set_velocity", "Set Velocity"),
        Binding("c", "copy_event_values", "Copy Event Values"),
        Binding("j", "paste_event_values", "Paste Event Values"),
        Binding("f", "fill_sibling_event_values", "Fill Sibling Leaves"),
        Binding("M", "repeat_motif", "Repeat Motif"),
        Binding("(", "rotate_sibling_values_left", "Rotate Values Left"),
        Binding(")", "rotate_sibling_values_right", "Rotate Values Right"),
        Binding("F", "alternate_fill_siblings", "Alternate Fill"),
        Binding("T", "apply_subtree_template", "Apply Template"),
        Binding("U", "euclidean_fill_siblings", "Euclidean Fill"),
        Binding("g", "quick_init_grid", "Quick Grid"),
        Binding("n", "new_pattern", "New Pattern"),
        Binding("l", "load_pattern", "Load Pattern"),
        Binding("w", "save_pattern", "Save"),
        Binding("W", "save_pattern_as", "Save As"),
        Binding("N", "rename_pattern", "Rename Pattern"),
        Binding("B", "edit_bpm", "Edit BPM"),
        Binding("p", "play_pattern", "Play Pattern"),
        Binding("b", "play_bar", "Play Bar"),
        Binding("space", "toggle_realtime_bar_playback", "Loop Current Bar"),
        Binding("P", "toggle_realtime_pattern_playback", "Loop Full Pattern"),
        Binding("C", "toggle_realtime_chain_playback", "Loop Chain"),
        Binding("e", "export_pattern", "Export Pattern WAV"),
        Binding("E", "export_bars", "Export Bars WAV"),
        Binding("m", "toggle_rest", "Toggle Rest"),
        Binding("t", "set_pitch_offset", "Set Pitch"),
        Binding("y", "copy_subtree", "Copy"),
        Binding("u", "paste_subtree", "Paste"),
        Binding("r", "reset_subtree", "Reset Node"),
        Binding("o", "edit_playback_order", "Playback Order"),
        Binding("a", "add_bar", "Add Bar"),
        Binding("A", "add_custom_bar", "Add Bar (Custom TS)"),
        Binding("d", "duplicate_bar", "Duplicate Bar"),
        Binding("x", "delete_bar", "Delete Bar"),
        Binding("[", "prev_bar", "Prev Bar"),
        Binding("]", "next_bar", "Next Bar"),
        Binding("R", "refresh_tree", "Refresh"),
    ]

    def __init__(
        self,
        pattern: Pattern,
        bpm: float,
        pattern_name: str,
        sample_library: SampleLibrary,
        *,
        sample_folder: Path,
        project_path: Path | None = None,
    ) -> None:
        super().__init__()
        self.pattern = pattern
        self.bpm = bpm
        self.pattern_name = pattern_name
        self.sample_library = sample_library
        self.sample_folder = sample_folder
        self.project_path = project_path
        self.is_dirty = False
        self.current_bar_index = 0
        self.selected_path = "0"
        self.node_map: dict[str, RhythmNode] = {}
        self.status_lines: list[str] = []
        self.subtree_clipboard: RhythmNode | None = None
        self.event_value_clipboard: EventValueClipboard | None = None
        self.realtime_looper = RealtimeLooper(sample_library=sample_library, bpm=bpm)
        self._transport_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Horizontal(
            Vertical(
                Static("", id="bar_list_panel", markup=False),
                Tree("Bar 0", id="tree_panel"),
                id="left_panel",
            ),
            Vertical(
                Static("", id="inspector_panel", markup=False),
                Static("", id="slots_panel", markup=False),
                Static("", id="transport_panel", markup=False),
                id="right_panel",
            ),
            id="main_row",
        )
        yield Static("", id="status_panel", markup=False)
        yield Footer()

    def on_mount(self) -> None:
        self.realtime_looper.set_bar_loop(self.pattern.bars[self.current_bar_index], bpm=self.bpm)
        self._transport_timer = self.set_interval(self.TRANSPORT_REFRESH_SECONDS, self._refresh_transport_only)
        self._rebuild_tree()
        self._push_status("Ready. Press n for a new pattern or l to load an existing pattern.")
        self._refresh_panels()

    def on_unmount(self) -> None:
        self.realtime_looper.shutdown()

    def _bar_root(self) -> RhythmNode:
        return self.pattern.bars[self.current_bar_index].root

    def _iter_nodes(self, node: RhythmNode, path: str) -> list[tuple[str, RhythmNode]]:
        items = [(path, node)]
        for i, child in enumerate(node.children):
            items.extend(self._iter_nodes(child, f"{path}.{i}"))
        return items

    def _node_label(self, path: str, node: RhythmNode) -> str:
        node_type = "Leaf" if node.is_leaf() else "Node"
        base = f"[{node_type} {path}] start={node.start_fraction:.3f} dur={node.duration_fraction:.3f}"
        if node.is_leaf():
            return f"{base} slot={node.sample_slot} vel={node.velocity:.2f} pitch={node.pitch_offset}"
        return f"{base} split={len(node.children)}"

    def _rebuild_tree(self) -> None:
        tree = self.query_one("#tree_panel", Tree)
        tree.clear()
        root = self._bar_root()
        self.node_map = dict(self._iter_nodes(root, "0"))

        tree.root.label = self._node_label("0", root)
        tree.root.data = NodeRef(path="0")
        tree.root.expand()

        def add_children(parent_tree_node: Tree.Node, parent_path: str, parent_node: RhythmNode) -> None:
            for i, child in enumerate(parent_node.children):
                child_path = f"{parent_path}.{i}"
                child_tree_node = parent_tree_node.add(self._node_label(child_path, child), data=NodeRef(path=child_path))
                if child.children:
                    child_tree_node.expand()
                    add_children(child_tree_node, child_path, child)

        add_children(tree.root, "0", root)

        if self.selected_path not in self.node_map:
            self.selected_path = "0"

    def _selected_node(self) -> RhythmNode | None:
        return self.node_map.get(self.selected_path)

    def _samples_summary(self) -> str:
        lines: list[str] = []
        for slot in self.sample_library.loaded_slots():
            sample = self.sample_library.slots[slot]
            if sample is not None:
                lines.append(f"{slot}: {sample.path.name}")
        return "No sample slots loaded" if not lines else ", ".join(lines)

    def _sample_slot_listing(self) -> str:
        lines = ["Loaded sample slots:"]
        for slot in range(MAX_SLOTS):
            sample = self.sample_library.slots[slot]
            if sample is None:
                continue
            lines.append(f"  {slot:02d} -> {sample.path.name} ({sample.channels}ch @{sample.sample_rate}Hz)")
        if len(lines) == 1:
            lines.append("  (none loaded)")
        return "\n".join(lines)

    def _sample_slot_panel_text(self) -> str:
        selected = self._selected_node()
        selected_slot = selected.sample_slot if selected is not None and selected.is_leaf() else None
        lines = ["Sample slots:"]
        for slot in range(MAX_SLOTS):
            marker = ">" if slot == selected_slot else " "
            sample = self.sample_library.slots[slot]
            if sample is None:
                lines.append(f"{marker} {slot:02d}  —")
            else:
                lines.append(f"{marker} {slot:02d}  {sample.path.name} ({sample.channels}ch @{sample.sample_rate}Hz)")
        return "\n".join(lines)

    def _mark_dirty(self) -> None:
        self.is_dirty = True

    def _mark_saved(self, project_path: Path) -> None:
        self.project_path = project_path
        self.is_dirty = False

    def _project_label(self) -> str:
        return self.project_path.as_posix() if self.project_path is not None else "unsaved"

    def _refresh_bar_list(self) -> None:
        bar_lines: list[str] = ["Bars:"]
        for i, bar in enumerate(self.pattern.bars):
            marker = "*" if i == self.current_bar_index else " "
            bar_lines.append(f"{marker} [{i}] {bar.time_signature.as_text()}")
        bar_lines.append(f"Playback order: {self.pattern.resolved_playback_order()}")
        self.query_one("#bar_list_panel", Static).update("\n".join(bar_lines))

    def _refresh_panels(self) -> None:
        node = self._selected_node()
        inspector = self.query_one("#inspector_panel", Static)
        slots = self.query_one("#slots_panel", Static)
        transport = self.query_one("#transport_panel", Static)
        status = self.query_one("#status_panel", Static)

        if node is None:
            inspector.update("No node selected.")
        else:
            node_type = "leaf" if node.is_leaf() else "internal"
            inspector.update(
                "\n".join(
                    [
                        f"Bar: {self.current_bar_index}",
                        f"Path: {self.selected_path}",
                        f"Type: {node_type}",
                        f"Start: {node.start_fraction:.6f}",
                        f"Duration: {node.duration_fraction:.6f}",
                        f"Sample Slot: {node.sample_slot}",
                        f"Rest: {node.sample_slot is None}",
                        f"Velocity: {node.velocity:.2f}",
                        f"Pitch Offset: {node.pitch_offset}",
                    ]
                )
            )

        self._refresh_bar_list()
        slots.update(self._sample_slot_panel_text())
        transport.update(self._format_transport_panel())
        info_lines = [
            f"Pattern: {self.pattern_name} | BPM: {self.bpm:.2f}",
            f"File: {self._project_label()} | Status: {'modified' if self.is_dirty else 'saved'}",
            f"Loaded slots: {self._samples_summary()}",
            (
                "Keys: n new | l load | w save | W save-as | N rename | B bpm | "
                "2-6 split | g grid | s slot | z/Z audition | v vel | t pitch | m rest | "
                "c copy-events | j paste-events | f fill-siblings | M motif-repeat | (/) rotate-values | "
                "F alternate-fill | T template | U euclidean-fill | y copy-subtree | u paste-subtree | r reset | "
                "o order | p pattern | b bar | space current-bar-loop | P pattern-loop | C chain-loop | e export | E bars export | "
                "a add bar | A custom bar | d/x bars | [/] switch | q quit"
            ),
        ]
        info_lines.extend(self.status_lines[-5:])
        status.update("\n".join(info_lines))

    def _refresh_transport_only(self) -> None:
        if not self.is_mounted:
            return
        self.query_one("#transport_panel", Static).update(self._format_transport_panel())

    def _format_transport_panel(self) -> str:
        snap = self.realtime_looper.transport_snapshot()
        lines: list[str] = ["Transport:"]
        lines.append(f"State: {'PLAYING' if snap.is_playing else 'STOPPED'}")
        lines.append("Live-safe edits: ON (velocity/slot/pitch/rest)")

        mode_label = {
            "bar": "BAR LOOP",
            "pattern": "PATTERN LOOP",
            "chain": "CHAIN LOOP",
            None: "—",
        }[snap.mode]
        lines.append(f"Mode: {mode_label}")

        if not snap.is_playing or snap.mode is None:
            lines.append("Position: —")
        else:
            lines.append(f"Progress: {self._format_progress_line(snap.loop_progress)}")
            if snap.mode == "bar":
                lines.append(f"Bar: {self.current_bar_index}")
            elif snap.mode == "pattern":
                if snap.current_bar_index is not None:
                    lines.append(f"Bar: {snap.current_bar_index + 1} of {len(self.pattern.bars)}")
            elif snap.mode == "chain":
                order = self.pattern.resolved_playback_order()
                if snap.current_chain_position is not None:
                    lines.append(f"Chain Step: {snap.current_chain_position + 1} of {len(order)}")
                if snap.current_chain_bar_index is not None:
                    lines.append(f"Bar Ref: {snap.current_chain_bar_index}")

        if snap.last_stop_reason:
            lines.append(f"Last stop: {snap.last_stop_reason}")
        return "\n".join(lines)

    def _format_progress_line(self, progress: float) -> str:
        clamped = max(0.0, min(1.0, progress))
        bar_chars = 20
        filled = int(round(clamped * bar_chars))
        return f"[{'#' * filled}{'-' * (bar_chars - filled)}] {clamped * 100:0.0f}%"

    def _push_status(self, message: str) -> None:
        self.status_lines.append(message)

    def _parse_optional_slot(self, raw_value: str, *, allow_rest: bool = True) -> int | None:
        value = raw_value.strip().lower()
        if value in {"", "x", "none"}:
            if allow_rest:
                return None
            raise ValueError("Slot is required for this operation.")
        slot = int(value)
        if slot < 0 or slot >= MAX_SLOTS:
            raise ValueError(f"Slot must be in range 0..{MAX_SLOTS - 1}.")
        return slot

    def _parse_optional_velocity(self, raw_value: str, *, default: float) -> float:
        value = raw_value.strip()
        if value == "":
            return default
        velocity = float(value)
        if velocity < 0.0 or velocity > 1.0:
            raise ValueError("Velocity must be in [0.0, 1.0].")
        return velocity

    def _confirm_discard_if_dirty(self, next_action_label: str, on_confirm: Callable[[], None]) -> None:
        if not self.is_dirty:
            on_confirm()
            return

        def handle(value: str | None) -> None:
            if value is None:
                self._push_status(f"{next_action_label} canceled.")
            elif value.lower() in {"y", "yes"}:
                on_confirm()
                return
            else:
                self._push_status(f"{next_action_label} canceled (unsaved changes kept).")
            self._refresh_panels()

        self.push_screen(PromptScreen("Unsaved changes exist. Discard and continue? (y/N):"), handle)

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        data = event.node.data
        if isinstance(data, NodeRef):
            self.selected_path = data.path
            self._refresh_panels()

    def action_refresh_tree(self) -> None:
        self._rebuild_tree()
        self._refresh_panels()

    def action_prev_bar(self) -> None:
        self._apply_edit_policy("select_bar")
        self.current_bar_index = (self.current_bar_index - 1) % len(self.pattern.bars)
        self.selected_path = "0"
        self.realtime_looper.set_bar_loop(self.pattern.bars[self.current_bar_index], bpm=self.bpm)
        self._rebuild_tree()
        self._push_status(f"Selected bar {self.current_bar_index}.")
        self._refresh_panels()

    def action_next_bar(self) -> None:
        self._apply_edit_policy("select_bar")
        self.current_bar_index = (self.current_bar_index + 1) % len(self.pattern.bars)
        self.selected_path = "0"
        self.realtime_looper.set_bar_loop(self.pattern.bars[self.current_bar_index], bpm=self.bpm)
        self._rebuild_tree()
        self._push_status(f"Selected bar {self.current_bar_index}.")
        self._refresh_panels()

    def action_add_bar(self) -> None:
        if self.pattern.bars:
            ts = self.pattern.bars[self.current_bar_index].time_signature
        else:
            ts = TimeSignature(4, 4)
        self._insert_new_bar(TimeSignature(ts.numerator, ts.denominator))

    def action_add_custom_bar(self) -> None:
        def handle_num(raw_num: str | None) -> None:
            if raw_num is None:
                self._push_status("Custom bar add canceled.")
                self._refresh_panels()
                return
            try:
                numerator = int(raw_num)
            except ValueError:
                self._push_status("Invalid numerator.")
                self._refresh_panels()
                return

            def handle_den(raw_den: str | None) -> None:
                if raw_den is None:
                    self._push_status("Custom bar add canceled.")
                    self._refresh_panels()
                    return
                try:
                    denominator = int(raw_den)
                    self._insert_new_bar(TimeSignature(numerator=numerator, denominator=denominator))
                except ValueError as exc:
                    self._push_status(f"Invalid time signature: {exc}")
                    self._refresh_panels()

            self.push_screen(PromptScreen("Custom bar denominator (1,2,4,8,16,32,64):", placeholder="4"), handle_den)

        self.push_screen(PromptScreen("Custom bar numerator:", placeholder="4"), handle_num)

    def _insert_new_bar(self, time_signature: TimeSignature) -> None:
        self._apply_edit_policy("add_bar")
        new_bar = create_blank_bar(time_signature=time_signature)
        insert_at = self.current_bar_index + 1
        self.pattern.remap_playback_order_for_insert(insert_at)
        self.pattern.bars.insert(insert_at, new_bar)
        self.current_bar_index = insert_at
        self.selected_path = "0"
        self._mark_dirty()
        self.realtime_looper.set_bar_loop(self.pattern.bars[self.current_bar_index], bpm=self.bpm)
        self._rebuild_tree()
        self._push_status(f"Added bar {insert_at} ({new_bar.time_signature.as_text()}).")
        self._refresh_panels()

    def action_duplicate_bar(self) -> None:
        self._apply_edit_policy("duplicate_bar")
        source = self.pattern.bars[self.current_bar_index]
        insert_at = self.current_bar_index + 1
        self.pattern.remap_playback_order_for_insert(insert_at)
        self.pattern.bars.insert(insert_at, source.clone())
        self.current_bar_index = insert_at
        self.selected_path = "0"
        self._mark_dirty()
        self.realtime_looper.set_bar_loop(self.pattern.bars[self.current_bar_index], bpm=self.bpm)
        self._rebuild_tree()
        self._push_status(f"Duplicated bar {insert_at - 1} into bar {insert_at}.")
        self._refresh_panels()

    def action_delete_bar(self) -> None:
        self._apply_edit_policy("delete_bar")
        if len(self.pattern.bars) == 1:
            self._push_status("Delete rejected: pattern must contain at least one bar.")
            self._refresh_panels()
            return
        deleted = self.current_bar_index
        self.pattern.bars.pop(self.current_bar_index)
        self.pattern.remap_playback_order_for_delete(deleted)
        self.current_bar_index = min(self.current_bar_index, len(self.pattern.bars) - 1)
        self.selected_path = "0"
        self._mark_dirty()
        self.realtime_looper.set_bar_loop(self.pattern.bars[self.current_bar_index], bpm=self.bpm)
        self._rebuild_tree()
        self._push_status(f"Deleted bar {deleted}. Now editing bar {self.current_bar_index}.")
        self._refresh_panels()

    def action_split_selected(self, parts: int) -> None:
        self._apply_edit_policy("split_selected")
        node = self._selected_node()
        if node is None:
            self._push_status("No node selected.")
        elif not node.is_leaf():
            self._push_status("Split rejected: selected node is already internal.")
        else:
            node.split_equal(parts)
            self._mark_dirty()
            self._push_status(f"Split {self.selected_path} into {parts} parts.")
            self._rebuild_tree()
        self._refresh_panels()

    def action_set_slot(self) -> None:
        node = self._selected_node()
        if node is None or not node.is_leaf():
            self._push_status("Slot assignment requires a selected leaf.")
            self._refresh_panels()
            return

        def handle(value: str | None) -> None:
            if value is None:
                self._push_status("Slot edit canceled.")
            elif value == "" or value.lower() == "x":
                was_live_safe = self._apply_edit_policy("set_slot")
                node.assign(sample_slot=None, velocity=node.velocity, pitch_offset=node.pitch_offset)
                self._mark_dirty()
                self._push_status(f"Cleared slot on {self.selected_path}.")
                if was_live_safe:
                    self._push_status(f"Playback continues: updated sample slot for leaf {self.selected_path}.")
            else:
                try:
                    slot = int(value)
                    if slot < 0 or slot >= MAX_SLOTS:
                        raise ValueError
                    was_live_safe = self._apply_edit_policy("set_slot")
                    node.assign(sample_slot=slot, velocity=node.velocity, pitch_offset=node.pitch_offset)
                    self._mark_dirty()
                    self._push_status(f"Assigned slot {slot} to {self.selected_path}.")
                    if was_live_safe:
                        self._push_status(f"Playback continues: updated sample slot for leaf {self.selected_path}.")
                except ValueError:
                    self._push_status("Invalid slot. Enter 0..15, blank, or x.")
            self._rebuild_tree()
            self._refresh_panels()

        current_slot = "none" if node.sample_slot is None else str(node.sample_slot)
        prompt_title = (
            f"Set sample slot for {self.selected_path} (current={current_slot}, 0-15, blank/x clears)\n"
            f"{self._sample_slot_listing()}"
        )
        self.push_screen(PromptScreen(prompt_title), handle)

    def _audition_slot(self, slot: int) -> None:
        if slot < 0 or slot >= MAX_SLOTS:
            self._push_status("Audition failed: slot must be 0..15.")
            self._refresh_panels()
            return
        sample = self.sample_library.slots[slot]
        if sample is None:
            self._push_status(f"Audition failed: slot {slot} is empty.")
            self._refresh_panels()
            return
        if self.realtime_looper.is_playing:
            self.realtime_looper.stop(reason="sample audition")
            self._push_status("Stopped realtime playback before sample audition.")
        try:
            play_once(sample.audio, sample.sample_rate)
            self._push_status(f"Auditioned slot {slot}: {sample.path.name}.")
        except Exception as exc:
            self._push_status(f"Audition failed: {exc}")
        self._refresh_panels()

    def action_audition_selected_slot(self) -> None:
        node = self._selected_node()
        if node is None or not node.is_leaf():
            self._push_status("Audition requires a selected leaf.")
            self._refresh_panels()
            return
        if node.sample_slot is None:
            self._push_status("Audition failed: selected leaf has no assigned slot.")
            self._refresh_panels()
            return
        self._audition_slot(node.sample_slot)

    def action_audition_slot_prompt(self) -> None:
        def handle(value: str | None) -> None:
            if value is None:
                self._push_status("Audition canceled.")
                self._refresh_panels()
                return
            try:
                slot = int(value)
            except ValueError:
                self._push_status("Audition failed: enter a slot number 0..15.")
                self._refresh_panels()
                return
            self._audition_slot(slot)

        self.push_screen(PromptScreen(f"Audition slot number (0-{MAX_SLOTS - 1}):"), handle)

    def action_set_velocity(self) -> None:
        node = self._selected_node()
        if node is None or not node.is_leaf():
            self._push_status("Velocity edit requires a selected leaf.")
            self._refresh_panels()
            return

        def handle(value: str | None) -> None:
            if value is None:
                self._push_status("Velocity edit canceled.")
            else:
                try:
                    velocity = float(value)
                    if velocity < 0.0 or velocity > 1.0:
                        raise ValueError
                    was_live_safe = self._apply_edit_policy("set_velocity")
                    node.assign(sample_slot=node.sample_slot, velocity=velocity, pitch_offset=node.pitch_offset)
                    self._mark_dirty()
                    self._push_status(f"Set velocity {velocity:.2f} on {self.selected_path}.")
                    if was_live_safe:
                        self._push_status(f"Playback continues: updated velocity for leaf {self.selected_path}.")
                except ValueError:
                    self._push_status("Invalid velocity. Enter a number in [0.0, 1.0].")
            self._rebuild_tree()
            self._refresh_panels()

        self.push_screen(PromptScreen("Set velocity (0.0 to 1.0):"), handle)

    def action_set_pitch_offset(self) -> None:
        node = self._selected_node()
        if node is None or not node.is_leaf():
            self._push_status("Pitch edit requires a selected leaf.")
            self._refresh_panels()
            return

        def handle(value: str | None) -> None:
            if value is None:
                self._push_status("Pitch edit canceled.")
            else:
                try:
                    pitch_offset = int(value)
                    if pitch_offset < -24 or pitch_offset > 24:
                        raise ValueError
                    was_live_safe = self._apply_edit_policy("set_pitch_offset")
                    node.assign(sample_slot=node.sample_slot, velocity=node.velocity, pitch_offset=pitch_offset)
                    self._mark_dirty()
                    self._push_status(f"Pitch offset for leaf {self.selected_path} set to {pitch_offset}.")
                    if was_live_safe:
                        self._push_status(f"Playback continues: updated pitch offset for leaf {self.selected_path}.")
                except ValueError:
                    self._push_status("Invalid pitch offset. Enter an integer in [-24, 24].")
            self._rebuild_tree()
            self._refresh_panels()

        self.push_screen(PromptScreen("Set pitch offset in semitones (-24 to 24):"), handle)

    def action_toggle_rest(self) -> None:
        node = self._selected_node()
        if node is None or not node.is_leaf():
            self._push_status("Rest toggle requires a selected leaf.")
            self._refresh_panels()
            return

        was_live_safe = self._apply_edit_policy("toggle_rest")
        became_active = node.toggle_rest()
        self._mark_dirty()
        if became_active:
            self._push_status(f"Leaf {self.selected_path} toggled to active (slot={node.sample_slot}).")
        else:
            self._push_status(f"Leaf {self.selected_path} toggled to rest.")
        if was_live_safe:
            self._push_status(f"Playback continues: updated rest state for leaf {self.selected_path}.")
        self._rebuild_tree()
        self._refresh_panels()

    def action_copy_subtree(self) -> None:
        node = self._selected_node()
        if node is None:
            self._push_status("No node selected.")
            self._refresh_panels()
            return
        self.subtree_clipboard = copy_subtree(node)
        self._push_status(f"Copied subtree at path {self.selected_path}.")
        self._refresh_panels()

    def action_paste_subtree(self) -> None:
        self._apply_edit_policy("paste_subtree")
        if self.subtree_clipboard is None:
            self._push_status("Paste rejected: clipboard is empty.")
            self._refresh_panels()
            return
        node = self._selected_node()
        if node is None:
            self._push_status("No node selected.")
            self._refresh_panels()
            return

        paste_subtree_over_target(node, self.subtree_clipboard)
        self._mark_dirty()
        if node.parent is None:
            self.selected_path = "0"
        self._rebuild_tree()
        self._push_status(f"Pasted subtree over node {self.selected_path}.")
        self._refresh_panels()

    def action_copy_event_values(self) -> None:
        node = self._selected_node()
        if node is None or not node.is_leaf():
            self._push_status("Copy event values requires a selected leaf.")
            self._refresh_panels()
            return
        self.event_value_clipboard = copy_leaf_event_values(node)
        self._push_status(f"Copied leaf event values from {self.selected_path}.")
        self._refresh_panels()

    def action_paste_event_values(self) -> None:
        node = self._selected_node()
        if node is None or not node.is_leaf():
            self._push_status("Paste event values requires a selected leaf.")
            self._refresh_panels()
            return
        if self.event_value_clipboard is None:
            self._push_status("Paste event values rejected: clipboard is empty.")
            self._refresh_panels()
            return
        was_live_safe = self._apply_edit_policy("paste_event_values")
        apply_leaf_event_values(node, self.event_value_clipboard)
        self._mark_dirty()
        self._push_status(f"Pasted event values onto {self.selected_path}.")
        if was_live_safe:
            self._push_status(f"Playback continues: pasted event values to leaf {self.selected_path}.")
        self._rebuild_tree()
        self._refresh_panels()

    def action_fill_sibling_event_values(self) -> None:
        node = self._selected_node()
        if node is None or not node.is_leaf():
            self._push_status("Fill siblings requires a selected leaf.")
            self._refresh_panels()
            return
        if self.event_value_clipboard is None:
            self._push_status("Fill siblings rejected: event clipboard is empty.")
            self._refresh_panels()
            return
        was_live_safe = self._apply_edit_policy("fill_sibling_event_values")
        filled = fill_sibling_leaves(node, self.event_value_clipboard)
        self._mark_dirty()
        self._push_status(f"Filled {filled} sibling leaves with copied event values.")
        if was_live_safe:
            self._push_status("Playback continues: sibling leaf values updated.")
        self._rebuild_tree()
        self._refresh_panels()

    def action_repeat_motif(self) -> None:
        node = self._selected_node()
        if node is None or not node.is_leaf():
            self._push_status("Repeat motif requires a selected leaf.")
            self._refresh_panels()
            return

        def handle(value: str | None) -> None:
            if value is None:
                self._push_status("Repeat motif canceled.")
                self._refresh_panels()
                return
            try:
                motif_length = int(value)
                was_live_safe = self._apply_edit_policy("repeat_motif")
                motif_len, sibling_count = repeat_motif_across_siblings(node, motif_length)
            except ValueError as exc:
                self._push_status(f"Repeat motif failed: {exc}")
                self._refresh_panels()
                return

            self._mark_dirty()
            self._push_status(f"Repeated {motif_len}-step motif across {sibling_count} sibling leaves.")
            if was_live_safe:
                self._push_status("Playback continues: sibling leaf values updated.")
            self._rebuild_tree()
            self._refresh_panels()

        self.push_screen(PromptScreen("Motif length in leaves:", placeholder="2"), handle)

    def action_rotate_sibling_values_left(self) -> None:
        self._rotate_sibling_values("left")

    def action_rotate_sibling_values_right(self) -> None:
        self._rotate_sibling_values("right")

    def _rotate_sibling_values(self, direction: Literal["left", "right"]) -> None:
        node = self._selected_node()
        if node is None or not node.is_leaf():
            self._push_status("Rotate values requires a selected leaf.")
            self._refresh_panels()
            return
        try:
            was_live_safe = self._apply_edit_policy("rotate_sibling_values")
            count = rotate_sibling_event_values(node, direction=direction)
        except ValueError as exc:
            self._push_status(f"Rotate failed: {exc}")
            self._refresh_panels()
            return

        self._mark_dirty()
        self._push_status(f"Rotated sibling event values {direction} across {count} leaves.")
        if was_live_safe:
            self._push_status("Playback continues: sibling leaf values updated.")
        self._rebuild_tree()
        self._refresh_panels()

    def action_alternate_fill_siblings(self) -> None:
        node = self._selected_node()
        if node is None or not node.is_leaf():
            self._push_status("Alternate fill requires a selected leaf.")
            self._refresh_panels()
            return

        def handle_slot_a(raw_slot_a: str | None) -> None:
            if raw_slot_a is None:
                self._push_status("Alternate fill canceled.")
                self._refresh_panels()
                return

            def handle_slot_b(raw_slot_b: str | None) -> None:
                if raw_slot_b is None:
                    self._push_status("Alternate fill canceled.")
                    self._refresh_panels()
                    return

                def handle_vel_a(raw_vel_a: str | None) -> None:
                    if raw_vel_a is None:
                        self._push_status("Alternate fill canceled.")
                        self._refresh_panels()
                        return

                    def handle_vel_b(raw_vel_b: str | None) -> None:
                        if raw_vel_b is None:
                            self._push_status("Alternate fill canceled.")
                            self._refresh_panels()
                            return
                        try:
                            event_a = LeafEventValue(
                                sample_slot=self._parse_optional_slot(raw_slot_a),
                                velocity=self._parse_optional_velocity(raw_vel_a, default=1.0),
                                pitch_offset=0,
                            )
                            event_b = LeafEventValue(
                                sample_slot=self._parse_optional_slot(raw_slot_b),
                                velocity=self._parse_optional_velocity(raw_vel_b, default=1.0),
                                pitch_offset=0,
                            )
                            was_live_safe = self._apply_edit_policy("alternate_fill_siblings")
                            count = alternate_fill_siblings(node, event_a=event_a, event_b=event_b)
                        except ValueError as exc:
                            self._push_status(f"Alternate fill failed: {exc}")
                            self._refresh_panels()
                            return

                        self._mark_dirty()
                        self._push_status(f"Applied alternate fill across {count} sibling leaves.")
                        if was_live_safe:
                            self._push_status("Playback continues: sibling leaf values updated.")
                        self._rebuild_tree()
                        self._refresh_panels()

                    self.push_screen(PromptScreen("Alternate fill velocity B (blank=1.0):", placeholder="1.0"), handle_vel_b)

                self.push_screen(PromptScreen("Alternate fill velocity A (blank=1.0):", placeholder="1.0"), handle_vel_a)

            self.push_screen(PromptScreen("Alternate fill slot B (0-15, blank/x = rest):"), handle_slot_b)

        self.push_screen(PromptScreen("Alternate fill slot A (0-15, blank/x = rest):"), handle_slot_a)

    def action_euclidean_fill_siblings(self) -> None:
        node = self._selected_node()
        if node is None or not node.is_leaf():
            self._push_status("Euclidean fill requires a selected leaf.")
            self._refresh_panels()
            return

        def handle_pulses(raw_pulses: str | None) -> None:
            if raw_pulses is None:
                self._push_status("Euclidean fill canceled.")
                self._refresh_panels()
                return

            def handle_slot(raw_slot: str | None) -> None:
                if raw_slot is None:
                    self._push_status("Euclidean fill canceled.")
                    self._refresh_panels()
                    return

                def handle_velocity(raw_velocity: str | None) -> None:
                    if raw_velocity is None:
                        self._push_status("Euclidean fill canceled.")
                        self._refresh_panels()
                        return

                    def handle_rotation(raw_rotation: str | None) -> None:
                        if raw_rotation is None:
                            self._push_status("Euclidean fill canceled.")
                            self._refresh_panels()
                            return
                        try:
                            pulses = int(raw_pulses)
                            event_value = LeafEventValue(
                                sample_slot=self._parse_optional_slot(raw_slot, allow_rest=False),
                                velocity=self._parse_optional_velocity(raw_velocity, default=1.0),
                                pitch_offset=0,
                            )
                            rotation = int(raw_rotation) if raw_rotation.strip() else 0
                            was_live_safe = self._apply_edit_policy("euclidean_fill_siblings")
                            pulse_count, step_count = euclidean_fill_siblings(
                                node,
                                pulses=pulses,
                                event_value=event_value,
                                rotation=rotation,
                            )
                        except ValueError as exc:
                            self._push_status(f"Euclidean fill failed: {exc}")
                            self._refresh_panels()
                            return

                        self._mark_dirty()
                        self._push_status(
                            f"Applied Euclidean fill: {pulse_count} pulses over {step_count} leaves (rotation={rotation})."
                        )
                        if was_live_safe:
                            self._push_status("Playback continues: sibling leaf values updated.")
                        self._rebuild_tree()
                        self._refresh_panels()

                    self.push_screen(PromptScreen("Euclidean rotation offset (integer, blank=0):", placeholder="0"), handle_rotation)

                self.push_screen(PromptScreen("Euclidean velocity (blank=1.0):", placeholder="1.0"), handle_velocity)

            self.push_screen(PromptScreen("Euclidean pulse slot (0-15):"), handle_slot)

        self.push_screen(PromptScreen("Euclidean pulses (k):", placeholder="3"), handle_pulses)

    def action_apply_subtree_template(self) -> None:
        node = self._selected_node()
        if node is None or not node.is_leaf():
            self._push_status("Subtree template requires a selected leaf.")
            self._refresh_panels()
            return

        template_map: dict[str, tuple[Literal[
            "straight_2",
            "straight_4",
            "triplet_3",
            "quintuplet_5",
            "sextuplet_6",
            "four_last_triplet",
            "four_middle_triplet",
        ], str]] = {
            "1": ("straight_2", "Straight 2"),
            "2": ("straight_4", "Straight 4"),
            "3": ("triplet_3", "Triplet 3"),
            "4": ("quintuplet_5", "Quintuplet 5"),
            "5": ("sextuplet_6", "Sextuplet 6"),
            "6": ("four_last_triplet", "4 then subdivide last into 3"),
            "7": ("four_middle_triplet", "4 then subdivide middle into 3"),
        }
        prompt = (
            "Select subtree template:\\n"
            "1) Straight 2\\n"
            "2) Straight 4\\n"
            "3) Triplet 3\\n"
            "4) Quintuplet 5\\n"
            "5) Sextuplet 6\\n"
            "6) 4 then subdivide last into 3\\n"
            "7) 4 then subdivide middle into 3"
        )

        def handle(raw_choice: str | None) -> None:
            if raw_choice is None:
                self._push_status("Subtree template apply canceled.")
                self._refresh_panels()
                return
            choice = raw_choice.strip()
            if choice not in template_map:
                self._push_status("Template apply failed: choose 1-7.")
                self._refresh_panels()
                return
            template_name, label = template_map[choice]
            self._apply_edit_policy("apply_subtree_template")
            try:
                apply_subtree_template(node, template_name=template_name)
            except ValueError as exc:
                self._push_status(f"Template apply failed: {exc}")
                self._refresh_panels()
                return
            self._mark_dirty()
            self._rebuild_tree()
            self._push_status(f"Applied template '{label}' to leaf {self.selected_path}.")
            self._refresh_panels()

        self.push_screen(PromptScreen(prompt), handle)

    def action_reset_subtree(self) -> None:
        self._apply_edit_policy("reset_subtree")
        node = self._selected_node()
        if node is None:
            self._push_status("No node selected.")
            self._refresh_panels()
            return
        reset_subtree(node)
        self._mark_dirty()
        self._rebuild_tree()
        self._push_status(f"Reset subtree {self.selected_path} to blank leaf.")
        self._refresh_panels()

    def action_quick_init_grid(self) -> None:
        def handle(value: str | None) -> None:
            if value is None:
                self._push_status("Grid initialization canceled.")
                self._refresh_panels()
                return
            try:
                divisions = int(value)
            except ValueError:
                self._push_status("Grid initialization failed: choose 4, 8, or 16.")
                self._refresh_panels()
                return
            if divisions not in {4, 8, 16}:
                self._push_status("Grid initialization failed: choose 4, 8, or 16.")
                self._refresh_panels()
                return

            self._apply_edit_policy("initialize_grid")
            bar = self.pattern.bars[self.current_bar_index]
            initialize_bar_grid(bar, divisions)
            self._mark_dirty()
            self.selected_path = "0"
            self.realtime_looper.set_bar_loop(self.pattern.bars[self.current_bar_index], bpm=self.bpm)
            self._rebuild_tree()
            self._push_status(f"Initialized bar {self.current_bar_index} to a {divisions}-leaf grid.")
            self._refresh_panels()

        self.push_screen(PromptScreen("Initialize current bar grid (4, 8, 16):", placeholder="16"), handle)

    def action_edit_playback_order(self) -> None:
        current = self.pattern.resolved_playback_order()

        def handle(value: str | None) -> None:
            if value is None:
                self._push_status("Playback order edit canceled.")
                self._refresh_panels()
                return

            if value == "":
                self._apply_edit_policy("edit_playback_order")
                self.pattern.set_playback_order(None)
                self._mark_dirty()
                self._push_status("Playback order cleared; using natural bar order.")
                self._refresh_panels()
                return

            try:
                order = [int(part.strip()) for part in value.split(",") if part.strip() != ""]
                self._apply_edit_policy("edit_playback_order")
                self.pattern.set_playback_order(order)
                self._mark_dirty()
                self._push_status(f"Playback order set to {self.pattern.resolved_playback_order()}.")
            except ValueError as exc:
                self._push_status(f"Invalid playback order: {exc}")
            self._refresh_panels()

        self.push_screen(
            PromptScreen(
                "Set playback order as comma-separated bar indices (blank clears):",
                placeholder=",".join(str(idx) for idx in current),
            ),
            handle,
        )

    def action_new_pattern(self) -> None:
        def do_new_pattern() -> None:
            self._apply_edit_policy("new_pattern")

            def handle_name(raw_name: str | None) -> None:
                if raw_name is None:
                    self._push_status("New pattern canceled.")
                    self._refresh_panels()
                    return
                pattern_name = raw_name.strip() or "Untitled Pattern"

                def handle_bpm(raw_bpm: str | None) -> None:
                    if raw_bpm is None:
                        self._push_status("New pattern canceled.")
                        self._refresh_panels()
                        return
                    try:
                        bpm = float(raw_bpm)
                        if bpm <= 0:
                            raise ValueError
                    except ValueError:
                        self._push_status("Invalid BPM for new pattern.")
                        self._refresh_panels()
                        return

                    def handle_num(raw_num: str | None) -> None:
                        if raw_num is None:
                            self._push_status("New pattern canceled.")
                            self._refresh_panels()
                            return
                        try:
                            numerator = int(raw_num)
                        except ValueError:
                            self._push_status("Invalid time-signature numerator.")
                            self._refresh_panels()
                            return

                        def handle_den(raw_den: str | None) -> None:
                            if raw_den is None:
                                self._push_status("New pattern canceled.")
                                self._refresh_panels()
                                return
                            try:
                                denominator = int(raw_den)
                                self.pattern = create_blank_pattern(
                                    name=pattern_name,
                                    bpm=bpm,
                                    numerator=numerator,
                                    denominator=denominator,
                                )
                            except ValueError as exc:
                                self._push_status(f"Invalid new pattern values: {exc}")
                                self._refresh_panels()
                                return
                            self.pattern_name = pattern_name
                            self.bpm = bpm
                            self.project_path = None
                            self.is_dirty = True
                            self.current_bar_index = 0
                            self.selected_path = "0"
                            self.realtime_looper.set_bar_loop(self.pattern.bars[0], bpm=self.bpm)
                            self._rebuild_tree()
                            self._push_status(
                                f"Created new pattern '{self.pattern_name}' ({numerator}/{denominator}, {self.bpm:.2f} BPM)."
                            )
                            self._refresh_panels()

                        self.push_screen(
                            PromptScreen("Initial time signature denominator (1,2,4,8,16,32,64):", placeholder="4"),
                            handle_den,
                        )

                    self.push_screen(PromptScreen("Initial time signature numerator:", placeholder="4"), handle_num)

                self.push_screen(PromptScreen("New pattern BPM:", placeholder="120"), handle_bpm)

            self.push_screen(PromptScreen("New pattern name:", placeholder="Untitled Pattern"), handle_name)

        self._confirm_discard_if_dirty("New pattern", do_new_pattern)

    def action_rename_pattern(self) -> None:
        def handle(value: str | None) -> None:
            if value is None:
                self._push_status("Rename canceled.")
            elif not value.strip():
                self._push_status("Rename rejected: name cannot be blank.")
            else:
                self.pattern_name = value.strip()
                self._mark_dirty()
                self._push_status(f"Pattern renamed to '{self.pattern_name}'.")
            self._refresh_panels()

        self.push_screen(PromptScreen("New pattern name:", placeholder=self.pattern_name), handle)

    def action_edit_bpm(self) -> None:
        def handle(value: str | None) -> None:
            if value is None:
                self._push_status("BPM edit canceled.")
                self._refresh_panels()
                return

            try:
                bpm = float(value)
                if bpm <= 0:
                    raise ValueError
            except ValueError:
                self._push_status("Invalid BPM. Enter a positive number.")
                self._refresh_panels()
                return

            self._apply_edit_policy("set_bpm")
            self.bpm = bpm
            self._mark_dirty()
            self.realtime_looper.set_bar_loop(self.pattern.bars[self.current_bar_index], bpm=self.bpm)
            self._push_status(f"BPM set to {self.bpm:.2f}.")
            self._refresh_panels()

        self.push_screen(PromptScreen("Set BPM:", placeholder=f"{self.bpm:.2f}"), handle)

    def action_save_pattern(self) -> None:
        if self.project_path is None:
            self.action_save_pattern_as()
            return
        self._save_to_path(self.project_path)

    def action_save_pattern_as(self) -> None:
        def handle(value: str | None) -> None:
            if value is None:
                self._push_status("Save-as canceled.")
                self._refresh_panels()
                return
            if not value.strip():
                self._push_status("Save-as rejected: path cannot be blank.")
                self._refresh_panels()
                return
            self._save_to_path(Path(value.strip()))

        placeholder = self._project_label() if self.project_path is not None else "patterns/new_pattern.json"
        self.push_screen(PromptScreen("Save JSON path:", placeholder=placeholder), handle)

    def _save_to_path(self, path: Path) -> None:
        try:
            project = Project(
                patterns=[self.pattern.clone()],
                current_pattern_index=0,
                arrangement=[0],
                bpm=self.bpm,
            )
            saved_path = save_pattern_project_to_json(
                path,
                project=project,
                sample_folder=self.sample_folder,
                sample_library=self.sample_library,
            )
            self._mark_saved(saved_path)
            self._push_status(f"Saved pattern to {saved_path}.")
        except Exception as exc:
            self._push_status(f"Save failed: {exc}")
        self._refresh_panels()

    def action_load_pattern(self) -> None:
        def do_load() -> None:
            self._apply_edit_policy("load_pattern")

            def handle(value: str | None) -> None:
                if value is None:
                    self._push_status("Load canceled.")
                    self._refresh_panels()
                    return
                if not value.strip():
                    self._push_status("Load rejected: path cannot be blank.")
                    self._refresh_panels()
                    return
                path = Path(value.strip())
                try:
                    project = load_pattern_project_from_json(path)
                except (PatternJsonError, PatternValidationError, OSError) as exc:
                    self._push_status(f"Load failed: {exc}")
                    self._refresh_panels()
                    return

                self.pattern = project.pattern
                self.pattern_name = project.name
                self.bpm = project.bpm
                self.sample_folder = project.sample_folder
                self.sample_library = SampleLibrary()
                _load_samples_from_project(self.sample_library, project)
                self.realtime_looper.shutdown()
                self.realtime_looper = RealtimeLooper(sample_library=self.sample_library, bpm=self.bpm)
                self.project_path = project.source_path
                self.is_dirty = False
                self.current_bar_index = 0
                self.selected_path = "0"
                self.realtime_looper.set_bar_loop(self.pattern.bars[0], bpm=self.bpm)
                self._rebuild_tree()
                self._push_status(f"Loaded pattern from {project.source_path}.")
                self._refresh_panels()

            self.push_screen(PromptScreen("Load JSON path:"), handle)

        self._confirm_discard_if_dirty("Load pattern", do_load)

    def action_play_pattern(self) -> None:
        self._render_and_play_pattern(self.pattern, "Played full pattern chain")

    def action_play_bar(self) -> None:
        bar = self.pattern.bars[self.current_bar_index]
        self._render_and_play_pattern(Pattern(name=self.pattern.name, bars=[bar]), f"Played bar {self.current_bar_index}")

    def action_toggle_realtime_bar_playback(self) -> None:
        if self.realtime_looper.is_playing and self.realtime_looper.mode == "bar":
            self.realtime_looper.stop(reason="explicit user stop")
            self._push_status("Realtime bar loop stopped.")
            self._refresh_panels()
            return

        if self.sample_library.sample_rate is None:
            self._push_status("Cannot start realtime bar loop: no samples loaded.")
            self._refresh_panels()
            return

        if self.realtime_looper.is_playing:
            self.realtime_looper.stop(reason="switched playback mode")

        try:
            self.realtime_looper.set_bar_loop(self.pattern.bars[self.current_bar_index], bpm=self.bpm)
            self.realtime_looper.start()
            self._push_status(f"Realtime bar loop started for bar {self.current_bar_index}.")
        except Exception as exc:
            self._push_status(f"Cannot start realtime bar loop: {exc}")
        self._refresh_panels()

    def action_toggle_realtime_pattern_playback(self) -> None:
        if self.realtime_looper.is_playing and self.realtime_looper.mode == "pattern":
            self.realtime_looper.stop(reason="explicit user stop")
            self._push_status("Realtime pattern loop stopped.")
            self._refresh_panels()
            return

        if self.sample_library.sample_rate is None:
            self._push_status("Cannot start realtime pattern loop: no samples loaded.")
            self._refresh_panels()
            return

        if not self.pattern.bars:
            self._push_status("Cannot start realtime pattern loop: no bars in pattern.")
            self._refresh_panels()
            return

        if self.realtime_looper.is_playing:
            self.realtime_looper.stop(reason="switched playback mode")

        try:
            self.realtime_looper.set_pattern_loop(self.pattern, bpm=self.bpm)
            self.realtime_looper.start()
            self._push_status("Realtime pattern loop started (natural bar order).")
        except Exception as exc:
            self._push_status(f"Cannot start realtime pattern loop: {exc}")
        self._refresh_panels()


    def action_toggle_realtime_chain_playback(self) -> None:
        if self.realtime_looper.is_playing and self.realtime_looper.mode == "chain":
            self.realtime_looper.stop(reason="explicit user stop")
            self._push_status("Realtime chain loop stopped.")
            self._refresh_panels()
            return

        if self.sample_library.sample_rate is None:
            self._push_status("Cannot start chain loop: no samples loaded.")
            self._refresh_panels()
            return

        if self.pattern.playback_order is None or len(self.pattern.playback_order) == 0:
            self._push_status("Cannot start chain loop: no playback order defined.")
            self._refresh_panels()
            return

        try:
            Pattern.validate_playback_order(self.pattern.playback_order, len(self.pattern.bars))
        except ValueError:
            self._push_status("Cannot start chain loop: invalid playback order.")
            self._refresh_panels()
            return

        if self.realtime_looper.is_playing:
            self.realtime_looper.stop(reason="switched playback mode")

        try:
            self.realtime_looper.set_chain_loop(self.pattern, bpm=self.bpm)
            self.realtime_looper.start()
            self._push_status("Realtime chain loop started.")
            self._push_status(
                "Chain debug: order="
                f"{self.pattern.playback_order} | {self.realtime_looper.describe_transport()}"
            )
        except Exception as exc:
            self._push_status(f"Cannot start realtime chain loop: {exc}")
        self._refresh_panels()

    def action_export_pattern(self) -> None:
        setattr(self.pattern, "bpm", self.bpm)
        export_dir = self.DEFAULT_EXPORT_DIR
        prefix = self.pattern_name or "pattern"
        try:
            exported = export_pattern(
                self.pattern,
                self.sample_library,
                output_path=str(export_dir),
                filename_prefix=prefix,
                sample_rate=int(round(self.sample_library.sample_rate or 44100)),
                normalize=True,
            )
            self._push_status(f"Exported full pattern → {exported}")
        except Exception as exc:
            self._push_status(f"Export failed: {exc}")
        self._refresh_panels()

    def action_export_bars(self) -> None:
        setattr(self.pattern, "bpm", self.bpm)
        export_dir = self.DEFAULT_EXPORT_DIR
        prefix = self.pattern_name or "pattern"
        try:
            exported = export_bars(
                self.pattern,
                self.sample_library,
                output_dir=str(export_dir),
                filename_prefix=prefix,
                sample_rate=int(round(self.sample_library.sample_rate or 44100)),
                normalize=True,
            )
            self._push_status(f"Exported {len(exported)} bars → {export_dir}/")
        except Exception as exc:
            self._push_status(f"Bar export failed: {exc}")
        self._refresh_panels()

    def _render_and_play_pattern(self, pattern: Pattern, label: str) -> None:
        if self.realtime_looper.is_playing:
            self.realtime_looper.stop(reason="switched to one-shot playback")
            self._push_status("Realtime playback stopped before one-shot playback.")

        if self.sample_library.sample_rate is None:
            self._push_status("Playback unavailable: no samples loaded.")
            self._refresh_panels()
            return

        renderer = OfflineRenderer(headroom_gain=0.9)
        try:
            result = renderer.render_pattern(pattern, self.sample_library, self.bpm)
            play_once(result.buffer, result.sample_rate)
            self._push_status(
                f"{label}. Frames={result.buffer.shape[0]} Peak={result.peak:.4f} Duration={result.duration_seconds:.3f}s"
            )
        except Exception as exc:  # runtime audio/render errors should be non-fatal to UI
            self._push_status(f"Render/play failed: {exc}")
        self._refresh_panels()

    def _apply_edit_policy(self, action_name: str) -> bool:
        """Apply centralized live-safe/transport-invalidating realtime edit policy.

        Returns True when the edit is live-safe and playback is currently active.
        """
        if classify_edit(action_name) == "live_safe":
            return self.realtime_looper.is_playing

        if not self.realtime_looper.is_playing:
            return False

        if action_name == "select_bar" and self.realtime_looper.mode != "bar":
            return False

        reason = invalidation_reason(action_name)
        self.realtime_looper.stop(reason=reason)
        self._push_status(f"Stopped realtime playback because {reason}.")
        return False


def _load_default_library(sample_folder: Path) -> SampleLibrary:
    library = SampleLibrary()
    if sample_folder.exists() and sample_folder.is_dir():
        library.auto_load_folder(sample_folder)
    return library


def _load_samples_from_project(library: SampleLibrary, project: LoadedPatternProject) -> None:
    for slot, wav_path in sorted(project.sample_slot_files.items()):
        if wav_path.exists():
            library.load_wav_into_slot(slot, wav_path)
    for slot, choke_group in sorted(project.slot_choke_groups.items()):
        library.set_choke_group(slot, choke_group)


def launch_textual_app(json_file: Path | None = None) -> None:
    default_sample_folder = Path("assets/samples").resolve()
    if json_file is None:
        pattern = create_blank_pattern(name="Untitled Pattern", bpm=120.0, numerator=4, denominator=4)
        bpm = 120.0
        pattern_name = "Untitled Pattern"
        library = _load_default_library(default_sample_folder)
        project_path: Path | None = None
        sample_folder = default_sample_folder
    else:
        try:
            project = load_pattern_project_from_json(json_file)
        except (PatternJsonError, PatternValidationError) as exc:
            raise RuntimeError(f"Failed to load JSON pattern for TUI: {exc}") from exc
        pattern = project.pattern
        bpm = project.bpm
        pattern_name = project.name
        library = SampleLibrary()
        _load_samples_from_project(library, project)
        project_path = project.source_path
        sample_folder = project.sample_folder

    SequencerTUI(
        pattern=pattern,
        bpm=bpm,
        pattern_name=pattern_name,
        sample_library=library,
        project_path=project_path,
        sample_folder=sample_folder,
    ).run()
