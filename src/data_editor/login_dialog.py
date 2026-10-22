"""Connection / sign-in dialog."""

from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from .db import ConnectionInfo, Database, available_drivers
from .worker import Worker

SQL_AUTH = "SQL Server Authentication"
WINDOWS_AUTH = "Windows Authentication"


class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Connect to SQL Server")
        self.setMinimumWidth(440)
        self.database: Database | None = None
        self.settings = QSettings()

        self.server = QLineEdit(placeholderText=r"e.g. sqlserver01 or sqlserver01\INSTANCE,1433")
        self.auth = QComboBox()
        self.auth.addItems([SQL_AUTH, WINDOWS_AUTH])
        self.username = QLineEdit()
        self.password = QLineEdit(echoMode=QLineEdit.Password)
        self.database_name = QLineEdit(placeholderText="(optional) default database")
        self.driver = QComboBox()
        drivers = available_drivers()
        self.driver.addItems(drivers)
        self.encrypt = QCheckBox("Encrypt connection")
        self.trust_cert = QCheckBox("Trust server certificate")

        form = QFormLayout()
        form.addRow("Server:", self.server)
        form.addRow("Authentication:", self.auth)
        form.addRow("Username:", self.username)
        form.addRow("Password:", self.password)
        form.addRow("Database:", self.database_name)
        form.addRow("ODBC driver:", self.driver)
        form.addRow("", self.encrypt)
        form.addRow("", self.trust_cert)

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setStyleSheet("color: #d9534f;")

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText("Connect")
        self.buttons.accepted.connect(self.connect_to_server)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.status)
        layout.addWidget(self.buttons)

        self.auth.currentTextChanged.connect(self._auth_changed)
        self._load_settings()
        self._auth_changed(self.auth.currentText())

        if not drivers:
            self.status.setText(
                "No SQL Server ODBC driver was found. Install 'ODBC Driver 18 for SQL Server' from Microsoft."
            )
            self.buttons.button(QDialogButtonBox.Ok).setEnabled(False)

    def _auth_changed(self, text: str) -> None:
        sql = text == SQL_AUTH
        self.username.setEnabled(sql)
        self.password.setEnabled(sql)

    def _load_settings(self) -> None:
        s = self.settings
        self.server.setText(s.value("login/server", ""))
        self.auth.setCurrentText(s.value("login/auth", SQL_AUTH))
        self.username.setText(s.value("login/username", ""))
        self.database_name.setText(s.value("login/database", ""))
        driver = s.value("login/driver", "")
        if driver and self.driver.findText(driver) >= 0:
            self.driver.setCurrentText(driver)
        self.encrypt.setChecked(s.value("login/encrypt", True, type=bool))
        self.trust_cert.setChecked(s.value("login/trust_cert", False, type=bool))
        (self.password if self.server.text() and self.username.text() else self.server).setFocus()

    def _save_settings(self) -> None:
        s = self.settings
        s.setValue("login/server", self.server.text().strip())
        s.setValue("login/auth", self.auth.currentText())
        s.setValue("login/username", self.username.text().strip())
        s.setValue("login/database", self.database_name.text().strip())
        s.setValue("login/driver", self.driver.currentText())
        s.setValue("login/encrypt", self.encrypt.isChecked())
        s.setValue("login/trust_cert", self.trust_cert.isChecked())

    def connect_to_server(self) -> None:
        if not self.server.text().strip():
            self.status.setText("Please enter a server name.")
            return
        info = ConnectionInfo(
            server=self.server.text().strip(),
            database=self.database_name.text().strip(),
            windows_auth=self.auth.currentText() == WINDOWS_AUTH,
            username=self.username.text().strip(),
            password=self.password.text(),
            driver=self.driver.currentText(),
            encrypt=self.encrypt.isChecked(),
            trust_server_certificate=self.trust_cert.isChecked(),
        )
        self.status.setStyleSheet("color: palette(text);")
        self.status.setText("Connecting…")
        self.setEnabled(False)
        self.worker = Worker(lambda: Database(info), self)
        self.worker.succeeded.connect(self._connected)
        self.worker.failed.connect(self._failed)
        self.worker.start()

    def _connected(self, database: Database) -> None:
        self.database = database
        self._save_settings()
        self.accept()

    def _failed(self, message: str) -> None:
        self.setEnabled(True)
        self.status.setStyleSheet("color: #d9534f;")
        self.status.setText(f"Could not connect:\n{message}")
        self.password.setFocus()
        self.password.selectAll()
