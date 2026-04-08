from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Input, Static, Tree

from audio.playback import play_once
from audio.renderer import OfflineRenderer
from audio.sample_library import MAX_SLOTS, SampleLibrary
from engine.pattern import Bar, Pattern
from engine.rhythm_tree import RhythmNode
from engine.time_signature import TimeSignature
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
        Binding("a", "add_bar", "Add Bar"),
        Binding("d", "duplicate_bar", "Duplicate Bar"),
        Binding("x", "delete_bar", "Delete Bar"),
        Binding("[", "prev_bar", "Prev Bar"),
        Binding("]", "next_bar", "Next Bar"),
        Binding("r", "refresh_tree", "Refresh"),
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

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Horizontal(
            Vertical(
                Static("", id="bar_list_panel"),
                Tree("Bar 0", id="tree_panel"),
                id="left_panel",
            ),
            Vertical(Static("", id="inspector_panel"), id="right_panel"),
            id="main_row",
        )
        yield Static("", id="status_panel")
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
            return f"{base} slot={node.sample_slot} vel={node.velocity:.2f}"
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
                        f"Velocity: {node.velocity:.2f}",
                    ]
                )
            )

        self._refresh_bar_list()
        info_lines = [
            f"Pattern: {self.pattern_name} | BPM: {self.bpm}",
            f"Loaded slots: {self._samples_summary()}",
            "Keys: 2-6 split | s slot | v vel | p play pattern | b play bar | a/d/x bars | [/] switch | q quit",
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
        self.pattern.bars.insert(insert_at, new_bar)
        self.current_bar_index = insert_at
        self.selected_path = "0"
        self._rebuild_tree()
        self._push_status(f"Added bar {insert_at} ({new_bar.time_signature.as_text()}).")
        self._refresh_panels()

    def action_duplicate_bar(self) -> None:
        source = self.pattern.bars[self.current_bar_index]
        insert_at = self.current_bar_index + 1
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
                node.assign(sample_slot=None, velocity=node.velocity)
                self._push_status(f"Cleared slot on {self.selected_path}.")
            else:
                try:
                    slot = int(value)
                    if slot < 0 or slot >= MAX_SLOTS:
                        raise ValueError
                    node.assign(sample_slot=slot, velocity=node.velocity)
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
                    node.assign(sample_slot=node.sample_slot, velocity=velocity)
                    self._push_status(f"Set velocity {velocity:.2f} on {self.selected_path}.")
                except ValueError:
                    self._push_status("Invalid velocity. Enter a number in [0.0, 1.0].")
            self._rebuild_tree()
            self._refresh_panels()

        self.push_screen(PromptScreen("Set velocity (0.0 to 1.0):"), handle)

    def action_play_pattern(self) -> None:
        self._render_and_play_pattern(self.pattern, "Played full pattern chain")

    def action_play_bar(self) -> None:
        bar = self.pattern.bars[self.current_bar_index]
        self._render_and_play_pattern(Pattern(bars=[bar]), f"Played bar {self.current_bar_index}")

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
