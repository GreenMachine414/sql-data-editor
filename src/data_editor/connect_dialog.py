"""Sign-in dialog: database type and credentials."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy.engine import make_url

from schemadoc.connection import DB_TYPES, build_url, db_type

from .db import ConnectionInfo, available_drivers
from .session import Session, open_sql_server, open_url
from .worker import Worker

SQL_AUTH = "SQL Server Authentication"
WINDOWS_AUTH = "Windows Authentication"
ERROR_STYLE = "color: #d9534f;"


def without_password(url: str) -> str:
    """The custom URL to remember: passwords are never saved."""
    try:
        parsed = make_url(url)
    except Exception:  # noqa: BLE001 - not a valid URL, nothing secret to strip
        return url
    # URL.set() ignores None, so replace the field directly
    return parsed._replace(password=None).render_as_string(hide_password=False) if parsed.password else url


class ConnectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Connect to a database")
        self.setMinimumWidth(480)
        self.session: Optional[Session] = None
        self.settings = QSettings()

        self.kind = QComboBox()
        self.kind.addItems([t.label for t in DB_TYPES])
        self.host = QLineEdit()
        self.port = QLineEdit()
        self.auth = QComboBox()
        self.auth.addItems([SQL_AUTH, WINDOWS_AUTH])
        self.username = QLineEdit()
        self.password = QLineEdit(echoMode=QLineEdit.Password)
        self.database = QLineEdit()
        self.driver = QComboBox()
        self.driver.addItems(available_drivers())
        self.encrypt = QCheckBox("Encrypt connection")
        self.trust_cert = QCheckBox("Trust server certificate")
        self.file = QLineEdit(placeholderText="Path to a .db / .sqlite file")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        file_row = QWidget()
        file_layout = QHBoxLayout(file_row)
        file_layout.setContentsMargins(0, 0, 0, 0)
        file_layout.addWidget(self.file)
        file_layout.addWidget(browse)
        self.url = QLineEdit(placeholderText="e.g. oracle+oracledb://user:pass@host:1521/?service_name=XE")

        self.form = QFormLayout()
        self.form.addRow("Database type:", self.kind)
        self.form.addRow("Server:", self.host)
        self.form.addRow("Port:", self.port)
        self.form.addRow("Authentication:", self.auth)
        self.form.addRow("Username:", self.username)
        self.form.addRow("Password:", self.password)
        self.form.addRow("Database:", self.database)
        self.form.addRow("ODBC driver:", self.driver)
        self.form.addRow("", self.encrypt)
        self.form.addRow("", self.trust_cert)
        self.form.addRow("Database file:", file_row)
        self.form.addRow("SQLAlchemy URL:", self.url)

        self.status = QLabel()
        self.status.setWordWrap(True)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText("Connect")
        self.buttons.accepted.connect(self.connect_to_database)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(self.form)
        layout.addWidget(self.status)
        layout.addWidget(self.buttons)

        self.kind.currentTextChanged.connect(self._kind_changed)
        self.auth.currentTextChanged.connect(self._auth_changed)
        self._load_settings()
        self._kind_changed(self.kind.currentText(), keep_port=True)

    # ---- field visibility --------------------------------------------------------

    def _kind_changed(self, label: str, keep_port: bool = False) -> None:
        kind = db_type(label)
        server = not (kind.is_file or kind.is_custom)
        for widget in (self.host, self.username, self.password, self.database):
            self.form.setRowVisible(widget, server)
        self.form.setRowVisible(self.port, server and not kind.is_sql_server)
        for widget in (self.auth, self.driver, self.encrypt, self.trust_cert):
            self.form.setRowVisible(widget, kind.is_sql_server)
        self.form.setRowVisible(self.file.parentWidget(), kind.is_file)
        self.form.setRowVisible(self.url, kind.is_custom)

        if kind.is_sql_server:
            self.host.setPlaceholderText(r"e.g. sqlserver01 or sqlserver01\INSTANCE,1433")
            self.database.setPlaceholderText("(optional) default database")
        else:
            self.host.setPlaceholderText("e.g. db.example.com")
            self.database.setPlaceholderText("")
            if server and not (keep_port and self.port.text()):
                self.port.setText(str(kind.default_port or ""))
        self._auth_changed(self.auth.currentText())
        self.adjustSize()

    def _auth_changed(self, text: str) -> None:
        windows = db_type(self.kind.currentText()).is_sql_server and text == WINDOWS_AUTH
        self.username.setEnabled(not windows)
        self.password.setEnabled(not windows)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open SQLite database", self.file.text(),
            "SQLite databases (*.db *.sqlite *.sqlite3 *.db3);;All files (*)")
        if path:
            self.file.setText(path)

    # ---- remembered settings (never the password) ----------------------------------

    def _load_settings(self) -> None:
        s = self.settings
        if not s.contains("connect/kind") and s.contains("login/server"):
            # carry over what Data Editor 1.x remembered
            for old, new in (("server", "host"), ("username", "username"), ("database", "database"),
                             ("auth", "auth"), ("driver", "driver"), ("encrypt", "encrypt"),
                             ("trust_cert", "trust_cert")):
                if s.contains(f"login/{old}"):
                    s.setValue(f"connect/{new}", s.value(f"login/{old}"))
            s.setValue("connect/kind", "SQL Server")

        self.kind.setCurrentText(s.value("connect/kind", DB_TYPES[0].label))
        self.host.setText(s.value("connect/host", ""))
        self.port.setText(s.value("connect/port", ""))
        self.auth.setCurrentText(s.value("connect/auth", SQL_AUTH))
        self.username.setText(s.value("connect/username", ""))
        self.database.setText(s.value("connect/database", ""))
        driver = s.value("connect/driver", "")
        if driver and self.driver.findText(driver) >= 0:
            self.driver.setCurrentText(driver)
        self.encrypt.setChecked(s.value("connect/encrypt", True, type=bool))
        self.trust_cert.setChecked(s.value("connect/trust_cert", False, type=bool))
        self.file.setText(s.value("connect/file", ""))
        self.url.setText(s.value("connect/url", ""))
        (self.password if self.host.text() and self.username.text() else self.host).setFocus()

    def _save_settings(self) -> None:
        s = self.settings
        s.setValue("connect/kind", self.kind.currentText())
        s.setValue("connect/host", self.host.text().strip())
        s.setValue("connect/port", self.port.text().strip())
        s.setValue("connect/auth", self.auth.currentText())
        s.setValue("connect/username", self.username.text().strip())
        s.setValue("connect/database", self.database.text().strip())
        s.setValue("connect/driver", self.driver.currentText())
        s.setValue("connect/encrypt", self.encrypt.isChecked())
        s.setValue("connect/trust_cert", self.trust_cert.isChecked())
        s.setValue("connect/file", self.file.text().strip())
        s.setValue("connect/url", without_password(self.url.text().strip()))

    # ---- connecting -----------------------------------------------------------------

    def _error(self, text: str) -> None:
        self.status.setStyleSheet(ERROR_STYLE)
        self.status.setText(text)

    def _opener(self):
        """A function that opens the session, or raises ValueError for missing input."""
        kind = db_type(self.kind.currentText())
        if kind.is_sql_server:
            if not self.host.text().strip():
                raise ValueError("Enter the server name.")
            if not self.driver.count():
                raise ValueError("No SQL Server ODBC driver was found. Install "
                                 "'ODBC Driver 18 for SQL Server' from Microsoft.")
            info = ConnectionInfo(
                server=self.host.text().strip(),
                database=self.database.text().strip(),
                windows_auth=self.auth.currentText() == WINDOWS_AUTH,
                username=self.username.text().strip(),
                password=self.password.text(),
                driver=self.driver.currentText(),
                encrypt=self.encrypt.isChecked(),
                trust_server_certificate=self.trust_cert.isChecked(),
            )
            return lambda: open_sql_server(info)
        url = build_url(kind, self.host.text(), self.port.text(), self.database.text(), self.username.text(),
                        self.password.text(), self.file.text(), self.url.text())
        if kind.is_file and not Path(self.file.text().strip()).is_file():
            raise ValueError("That SQLite file doesn't exist.")
        return lambda: open_url(url)

    def connect_to_database(self) -> None:
        try:
            opener = self._opener()
        except ValueError as exc:
            self._error(str(exc))
            return
        self.status.setStyleSheet("color: palette(text);")
        self.status.setText("Connecting…")
        self.setEnabled(False)
        self.worker = Worker(opener, self)
        self.worker.succeeded.connect(self._connected)
        self.worker.failed.connect(self._failed)
        self.worker.start()

    def _connected(self, session: Session) -> None:
        self.worker.wait()
        self.session = session
        self._save_settings()
        self.accept()

    def _failed(self, message: str) -> None:
        self.worker.wait()
        self.setEnabled(True)
        self._error(f"Could not connect:\n{message}")
        self.password.setFocus()
        self.password.selectAll()
