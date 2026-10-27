"""Run blocking database calls off the UI thread."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal


def friendly_error(exc: BaseException) -> str:
    """The message to show for a failed connection or report."""
    if isinstance(exc, ModuleNotFoundError):
        return (f"The database driver '{exc.name}' isn't installed.\n\n"
                "If you're running from source, install it with pip (see README).")
    orig = getattr(exc, "orig", None)
    msg = (str(orig).strip() if orig is not None else "") or str(exc)
    low = msg.lower()
    if "timeout" in low or "timed out" in low or "refused" in low:
        msg += ("\n\nThe server couldn't be reached. Check the host and port, and make sure "
                "the database accepts connections from outside its own network.")
    return msg


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
            self.failed.emit(friendly_error(exc))
