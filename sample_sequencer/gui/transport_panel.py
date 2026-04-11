from __future__ import annotations

from PySide6.QtWidgets import QFormLayout, QLabel, QWidget


class TransportPanel(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._state = QLabel("STOPPED")
        self._mode = QLabel("BAR")
        self._progress = QLabel("0%")
        self._bar_chain = QLabel("Bar: 0")
        self._status = QLabel("Ready")

        layout = QFormLayout(self)
        layout.addRow("State", self._state)
        layout.addRow("Mode", self._mode)
        layout.addRow("Progress", self._progress)
        layout.addRow("Bar/Step", self._bar_chain)
        layout.addRow("Status", self._status)

    def set_values(self, *, state: str, mode: str, progress: str, bar_chain: str, status: str) -> None:
        self._state.setText(state)
        self._mode.setText(mode)
        self._progress.setText(progress)
        self._bar_chain.setText(bar_chain)
        self._status.setText(status)
