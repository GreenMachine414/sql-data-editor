"""Entry point: python -m data_editor"""

import sys

from PySide6.QtWidgets import QApplication, QDialog

from data_editor import APP_NAME, __version__
from data_editor.connect_dialog import ConnectDialog
from data_editor.main_window import MainWindow
from data_editor.theme import apply_theme


def main() -> int:
    app = QApplication(sys.argv)
    app.setOrganizationName("DataEditor")
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setStyle("Fusion")
    apply_theme(app)

    dialog = ConnectDialog()
    if dialog.exec() != QDialog.Accepted or dialog.session is None:
        return 0

    window = MainWindow(dialog.session)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
