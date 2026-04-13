from __future__ import annotations

from PySide6.QtWidgets import QButtonGroup, QDialog, QDialogButtonBox, QLabel, QRadioButton, QVBoxLayout


EXPORT_MODE_OPTIONS = (
    ("truncate", "Truncate — Cut audio at end of pattern"),
    ("wrap", "Wrap — Wrap overflow to start (loop)"),
    ("tail", "Tail — Allow sounds to finish naturally"),
)


class ExportDialog(QDialog):
    def __init__(self, current_mode: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export")
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Export Mode:"))

        self.mode_group = QButtonGroup(self)
        self.mode_buttons: dict[str, QRadioButton] = {}
        for index, (mode, label) in enumerate(EXPORT_MODE_OPTIONS):
            button = QRadioButton(label)
            self.mode_group.addButton(button, index)
            layout.addWidget(button)
            self.mode_buttons[mode] = button

        selected_mode = current_mode if current_mode in self.mode_buttons else "truncate"
        self.mode_buttons[selected_mode].setChecked(True)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_mode(self) -> str:
        for mode, button in self.mode_buttons.items():
            if button.isChecked():
                return mode
        return "truncate"
