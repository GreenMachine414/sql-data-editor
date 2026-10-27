"""Main window: connection bar plus the Edit Data and Document Schema tabs."""

from __future__ import annotations

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QTabWidget,
    QToolBar,
)

from . import APP_NAME, __version__
from .connect_dialog import ConnectDialog
from .document_page import DocumentPage
from .editor_page import EditorPage
from .session import Session

EDIT_TAB, DOCUMENT_TAB = 0, 1


class MainWindow(QMainWindow):
    def __init__(self, session: Session):
        super().__init__()
        self.session = session
        self.settings = QSettings()
        self.resize(1200, 750)

        self.editor = EditorPage()
        self.document = DocumentPage()
        for page in (self.editor, self.document):
            page.message.connect(lambda text, ms: self.statusBar().showMessage(text, ms))
        self.editor.state_changed.connect(self._update_state)
        self.document.busy_changed.connect(self._update_state)

        self._build_ui()
        self.use_session(session)
        self.tabs.setCurrentIndex(self.settings.value("window/tab", EDIT_TAB, type=int))
        if not session.can_edit:
            self.tabs.setCurrentIndex(DOCUMENT_TAB)

    def _build_ui(self):
        self.act_connect = QAction("⇄ Connect…", self)
        self.act_connect.setShortcut(QKeySequence("Ctrl+O"))
        self.act_connect.setToolTip("Connect to another server or database (Ctrl+O)")
        self.act_connect.triggered.connect(lambda: self.reconnect())

        toolbar = QToolBar("Connection")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.addToolBar(toolbar)
        toolbar.addAction(self.act_connect)
        self.db_label = QLabel(" Database: ")
        self.db_combo = QComboBox(minimumWidth=200)
        self.db_combo.activated.connect(lambda _i: self._database_chosen(self.db_combo.currentText()))
        self.db_actions = [toolbar.addSeparator(), toolbar.addWidget(self.db_label), toolbar.addWidget(self.db_combo)]

        self.tabs = QTabWidget(documentMode=True)
        self.tabs.addTab(self.editor, "✎  Edit Data")
        self.tabs.addTab(self.document, "📄  Document Schema")
        self.tabs.currentChanged.connect(self._tab_changed)
        self.setCentralWidget(self.tabs)

        self.conn_label = QLabel()
        self.statusBar().addPermanentWidget(self.conn_label)

    # ---- connection ------------------------------------------------------------------

    def use_session(self, session: Session) -> None:
        self.session = session
        self.conn_label.setText(f"{session.label}  ")
        self.db_combo.clear()
        if session.can_edit:
            try:
                self.db_combo.addItems(session.databases())
            except Exception as exc:  # noqa: BLE001
                QMessageBox.warning(self, APP_NAME, f"Could not list databases:\n{exc}")
            self.db_combo.setCurrentText(session.current_database())
        for action in self.db_actions:
            action.setVisible(session.can_edit)
        self.editor.set_database(session.editor)
        self.document.set_session(session)
        self._update_state()

    @property
    def busy(self) -> bool:
        return self.editor.busy or self.document.busy

    def _database_chosen(self, name: str) -> None:
        if name == self.session.current_database():
            return
        if self.busy or not self.editor.confirm_leave():
            self.db_combo.setCurrentText(self.session.current_database())
            return
        QGuiApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.session.switch_database(name)
        except Exception as exc:  # noqa: BLE001
            QGuiApplication.restoreOverrideCursor()
            QMessageBox.critical(self, APP_NAME, f"Could not open database '{name}':\n{exc}")
            self.db_combo.setCurrentText(self.session.current_database())
            return
        QGuiApplication.restoreOverrideCursor()
        self.editor.set_database(self.session.editor)
        self.document.set_session(self.session)
        self._update_state()

    def reconnect(self) -> None:
        if self.busy or not self.editor.confirm_leave():
            return
        dialog = ConnectDialog(self)
        if dialog.exec() != QDialog.Accepted or dialog.session is None:
            return
        old = self.session
        self.use_session(dialog.session)
        old.close()
        if not self.session.can_edit:
            self.tabs.setCurrentIndex(DOCUMENT_TAB)

    # ---- state -----------------------------------------------------------------------

    def _tab_changed(self, index: int) -> None:
        self.settings.setValue("window/tab", index)
        self._update_state()

    def _update_state(self) -> None:
        busy = self.busy
        self.act_connect.setEnabled(not busy)
        self.db_combo.setEnabled(not busy)
        title = f"{APP_NAME} {__version__}"
        if self.tabs.currentIndex() == EDIT_TAB and self.editor.current:
            dirty = "● " if self.editor.model.has_changes() else ""
            schema, table = self.editor.current
            title = f"{dirty}{schema}.{table} — {title}"
        self.setWindowTitle(title)

    def closeEvent(self, event):
        if not self.editor.confirm_leave():
            event.ignore()
            return
        self.editor.wait()
        self.document.wait()
        self.session.close()
        event.accept()
