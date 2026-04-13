from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HistoryEntry:
    snapshot: dict[str, Any]
    label: str = ""


class UndoManager:
    def __init__(self, max_history: int = 100) -> None:
        self.max_history = max(1, int(max_history))
        self._undo_stack: list[HistoryEntry] = []
        self._redo_stack: list[HistoryEntry] = []

    def push_undo(self, snapshot: dict[str, Any], label: str = "") -> None:
        self._undo_stack.append(HistoryEntry(snapshot=snapshot, label=label))
        if len(self._undo_stack) > self.max_history:
            self._undo_stack = self._undo_stack[-self.max_history :]
        self._redo_stack.clear()

    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    def undo(self, current_snapshot: dict[str, Any]) -> HistoryEntry | None:
        if not self._undo_stack:
            return None
        entry = self._undo_stack.pop()
        self._redo_stack.append(HistoryEntry(snapshot=current_snapshot, label=entry.label))
        return entry

    def redo(self, current_snapshot: dict[str, Any]) -> HistoryEntry | None:
        if not self._redo_stack:
            return None
        entry = self._redo_stack.pop()
        self._undo_stack.append(HistoryEntry(snapshot=current_snapshot, label=entry.label))
        return entry

    def clear(self) -> None:
        self._undo_stack.clear()
        self._redo_stack.clear()
