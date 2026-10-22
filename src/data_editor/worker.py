"""Run blocking database calls off the UI thread."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal


class Worker(QThread):
    """Runs a blocking function in a background thread.

    Results are delivered back on the UI thread through the signals.
    """

    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn

    def run(self):
        try:
            self.succeeded.emit(self.fn())
        except Exception as exc:  # noqa: BLE001 - surface any driver error to the user
            self.failed.emit(str(exc))
