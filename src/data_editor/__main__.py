"""Entry point: python -m data_editor"""

import sys

from PySide6.QtWidgets import QApplication, QDialog

from data_editor import __version__
from data_editor.login_dialog import LoginDialog
from data_editor.main_window import MainWindow
from data_editor.theme import apply_theme


def main() -> int:
    app = QApplication(sys.argv)
    app.setOrganizationName("DataEditor")
    app.setApplicationName("Data Editor")
    app.setApplicationVersion(__version__)
    app.setStyle("Fusion")
    apply_theme(app)

    login = LoginDialog()
    if login.exec() != QDialog.Accepted or login.database is None:
        return 0

    window = MainWindow(login.database)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
