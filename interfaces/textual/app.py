from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Input, Static, Tree

from audio.export import export_bars, export_pattern
from audio.playback import play_once
from audio.renderer import OfflineRenderer
from audio.sample_library import MAX_SLOTS, SampleLibrary
from engine.pattern import Bar, Pattern
from engine.rhythm_tree import RhythmNode
from engine.time_signature import TimeSignature
from engine.tree_ops import copy_subtree, paste_subtree_over_target, reset_subtree
from interfaces.cli.phase1_demo import build_demo_pattern
from sequencer_io import LoadedPatternProject, load_pattern_project_from_json
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

    CSS = """
    Screen { layout: vertical; }
    #main_row { height: 1fr; }
    #left_panel { width: 2fr; }
    #right_panel { width: 1fr; }
    #bar_list_panel, #tree_panel, #inspector_panel, #status_panel {
        border: solid $accent;
    }
    #bar_list_panel { height: 8; }
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
        Binding("v", "set_velocity", "Set Velocity"),
        Binding("p", "play_pattern", "Play Pattern"),
        Binding("b", "play_bar", "Play Bar"),
        Binding("e", "export_pattern", "Export Pattern WAV"),
        Binding("E", "export_bars", "Export Bars WAV"),
        Binding("m", "toggle_rest", "Toggle Rest"),
        Binding("t", "set_pitch_offset", "Set Pitch"),
        Binding("y", "copy_subtree", "Copy"),
        Binding("u", "paste_subtree", "Paste"),
        Binding("r", "reset_subtree", "Reset Node"),
        Binding("o", "edit_playback_order", "Playback Order"),
        Binding("a", "add_bar", "Add Bar"),
        Binding("d", "duplicate_bar", "Duplicate Bar"),
        Binding("x", "delete_bar", "Delete Bar"),
        Binding("[", "prev_bar", "Prev Bar"),
        Binding("]", "next_bar", "Next Bar"),
        Binding("R", "refresh_tree", "Refresh"),
    ]

    def __init__(self, pattern: Pattern, bpm: float, pattern_name: str, sample_library: SampleLibrary) -> None:
        super().__init__()
        self.pattern = pattern
        self.bpm = bpm
        self.pattern_name = pattern_name
        self.sample_library = sample_library
        self.current_bar_index = 0
        self.selected_path = "0"
        self.node_map: dict[str, RhythmNode] = {}
        self.status_lines: list[str] = []
        self.subtree_clipboard: RhythmNode | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Horizontal(
            Vertical(
                Static("", id="bar_list_panel", markup=False),
                Tree("Bar 0", id="tree_panel"),
                id="left_panel",
            ),
            Vertical(Static("", id="inspector_panel", markup=False), id="right_panel"),
            id="main_row",
        )
        yield Static("", id="status_panel", markup=False)
        yield Footer()

    def on_mount(self) -> None:
        self._rebuild_tree()
        self._push_status("Ready. Use [ ] to switch bars and arrows to navigate nodes.")
        self._refresh_panels()

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
        lines = []
        for slot in self.sample_library.loaded_slots():
            sample = self.sample_library.slots[slot]
            if sample is not None:
                lines.append(f"{slot}: {sample.path.name}")
        return "No sample slots loaded" if not lines else ", ".join(lines)

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
        info_lines = [
            f"Pattern: {self.pattern_name} | BPM: {self.bpm}",
            f"Loaded slots: {self._samples_summary()}",
            (
                "Keys: 2-6 split | s slot | v vel | t pitch | m rest | y copy | u paste | r reset | "
                "o order | p pattern | b bar | e export | E bars export | a/d/x bars | [/] switch | q quit"
            ),
        ]
        info_lines.extend(self.status_lines[-5:])
        status.update("\n".join(info_lines))

    def _push_status(self, message: str) -> None:
        self.status_lines.append(message)

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        data = event.node.data
        if isinstance(data, NodeRef):
            self.selected_path = data.path
            self._refresh_panels()

    def action_refresh_tree(self) -> None:
        self._rebuild_tree()
        self._refresh_panels()

    def action_prev_bar(self) -> None:
        self.current_bar_index = (self.current_bar_index - 1) % len(self.pattern.bars)
        self.selected_path = "0"
        self._rebuild_tree()
        self._push_status(f"Selected bar {self.current_bar_index}.")
        self._refresh_panels()

    def action_next_bar(self) -> None:
        self.current_bar_index = (self.current_bar_index + 1) % len(self.pattern.bars)
        self.selected_path = "0"
        self._rebuild_tree()
        self._push_status(f"Selected bar {self.current_bar_index}.")
        self._refresh_panels()

    def action_add_bar(self) -> None:
        if self.pattern.bars:
            ts = self.pattern.bars[self.current_bar_index].time_signature
        else:
            ts = TimeSignature(4, 4)
        new_bar = Bar(time_signature=TimeSignature(ts.numerator, ts.denominator))
        insert_at = self.current_bar_index + 1
        self.pattern.remap_playback_order_for_insert(insert_at)
        self.pattern.bars.insert(insert_at, new_bar)
        self.current_bar_index = insert_at
        self.selected_path = "0"
        self._rebuild_tree()
        self._push_status(f"Added bar {insert_at} ({new_bar.time_signature.as_text()}).")
        self._refresh_panels()

    def action_duplicate_bar(self) -> None:
        source = self.pattern.bars[self.current_bar_index]
        insert_at = self.current_bar_index + 1
        self.pattern.remap_playback_order_for_insert(insert_at)
        self.pattern.bars.insert(insert_at, source.clone())
        self.current_bar_index = insert_at
        self.selected_path = "0"
        self._rebuild_tree()
        self._push_status(f"Duplicated bar {insert_at - 1} into bar {insert_at}.")
        self._refresh_panels()

    def action_delete_bar(self) -> None:
        if len(self.pattern.bars) == 1:
            self._push_status("Delete rejected: pattern must contain at least one bar.")
            self._refresh_panels()
            return
        deleted = self.current_bar_index
        self.pattern.bars.pop(self.current_bar_index)
        self.pattern.remap_playback_order_for_delete(deleted)
        self.current_bar_index = min(self.current_bar_index, len(self.pattern.bars) - 1)
        self.selected_path = "0"
        self._rebuild_tree()
        self._push_status(f"Deleted bar {deleted}. Now editing bar {self.current_bar_index}.")
        self._refresh_panels()

    def action_split_selected(self, parts: int) -> None:
        node = self._selected_node()
        if node is None:
            self._push_status("No node selected.")
        elif not node.is_leaf():
            self._push_status("Split rejected: selected node is already internal.")
        else:
            node.split_equal(parts)
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
                node.assign(sample_slot=None, velocity=node.velocity, pitch_offset=node.pitch_offset)
                self._push_status(f"Cleared slot on {self.selected_path}.")
            else:
                try:
                    slot = int(value)
                    if slot < 0 or slot >= MAX_SLOTS:
                        raise ValueError
                    node.assign(sample_slot=slot, velocity=node.velocity, pitch_offset=node.pitch_offset)
                    self._push_status(f"Assigned slot {slot} to {self.selected_path}.")
                except ValueError:
                    self._push_status("Invalid slot. Enter 0..15, blank, or x.")
            self._rebuild_tree()
            self._refresh_panels()

        self.push_screen(PromptScreen("Set sample slot (0-15, blank/x clears):"), handle)

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
                    node.assign(sample_slot=node.sample_slot, velocity=velocity, pitch_offset=node.pitch_offset)
                    self._push_status(f"Set velocity {velocity:.2f} on {self.selected_path}.")
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
                    node.assign(sample_slot=node.sample_slot, velocity=node.velocity, pitch_offset=pitch_offset)
                    self._push_status(f"Pitch offset for leaf {self.selected_path} set to {pitch_offset}.")
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

        became_active = node.toggle_rest()
        if became_active:
            self._push_status(f"Leaf {self.selected_path} toggled to active (slot={node.sample_slot}).")
        else:
            self._push_status(f"Leaf {self.selected_path} toggled to rest.")
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
        if node.parent is None:
            self.selected_path = "0"
        self._rebuild_tree()
        self._push_status(f"Pasted subtree over node {self.selected_path}.")
        self._refresh_panels()

    def action_reset_subtree(self) -> None:
        node = self._selected_node()
        if node is None:
            self._push_status("No node selected.")
            self._refresh_panels()
            return
        reset_subtree(node)
        self._rebuild_tree()
        self._push_status(f"Reset subtree {self.selected_path} to blank leaf.")
        self._refresh_panels()

    def action_edit_playback_order(self) -> None:
        current = self.pattern.resolved_playback_order()

        def handle(value: str | None) -> None:
            if value is None:
                self._push_status("Playback order edit canceled.")
                self._refresh_panels()
                return

            if value == "":
                self.pattern.set_playback_order(None)
                self._push_status("Playback order cleared; using natural bar order.")
                self._refresh_panels()
                return

            try:
                order = [int(part.strip()) for part in value.split(",") if part.strip() != ""]
                self.pattern.set_playback_order(order)
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

    def action_play_pattern(self) -> None:
        self._render_and_play_pattern(self.pattern, "Played full pattern chain")

    def action_play_bar(self) -> None:
        bar = self.pattern.bars[self.current_bar_index]
        self._render_and_play_pattern(Pattern(bars=[bar]), f"Played bar {self.current_bar_index}")

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


def _load_demo_library() -> SampleLibrary:
    library = SampleLibrary()
    sample_dir = Path("assets/samples")
    if sample_dir.exists() and sample_dir.is_dir():
        library.auto_load_folder(sample_dir)
    return library


def _load_samples_from_project(library: SampleLibrary, project: LoadedPatternProject) -> None:
    for slot, wav_path in sorted(project.sample_slot_files.items()):
        if wav_path.exists():
            library.load_wav_into_slot(slot, wav_path)


def launch_textual_app(json_file: Path | None = None) -> None:
    if json_file is None:
        pattern = build_demo_pattern()
        bpm = 120.0
        pattern_name = "Phase 3 Demo Pattern"
        library = _load_demo_library()
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

    SequencerTUI(pattern=pattern, bpm=bpm, pattern_name=pattern_name, sample_library=library).run()
