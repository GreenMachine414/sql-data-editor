"""Document Schema tab: pick tables, choose an output format, generate an ERD + reference document."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from schemadoc.generate import generate

from . import APP_NAME
from .session import Session
from .widgets import LoadingOverlay
from .worker import Worker


def open_file(path: Path) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:  # noqa: BLE001 - fall back to the browser
        import webbrowser
        webbrowser.open(path.resolve().as_uri())


class TableList(QListWidget):
    """Table names with check boxes. Clicking anywhere on a row, or Space, toggles it."""

    def __init__(self):
        super().__init__(objectName="tableList")
        self.setMouseTracking(True)  # needed for the hover highlight
        self.itemClicked.connect(self.toggle)

    def toggle(self, item: QListWidgetItem) -> None:
        checked = item.checkState() == Qt.Checked
        item.setCheckState(Qt.Unchecked if checked else Qt.Checked)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Space and self.currentItem():
            self.toggle(self.currentItem())
            return
        super().keyPressEvent(event)

    def set_tables(self, names: list[str]) -> None:
        self.clear()
        for name in names:
            item = QListWidgetItem(name)
            # not user-checkable: the row click above does the toggling, so the box doesn't toggle twice
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            item.setCheckState(Qt.Unchecked)
            self.addItem(item)

    def items(self) -> list[QListWidgetItem]:
        return [self.item(i) for i in range(self.count())]

    def checked(self) -> list[str]:
        return [i.text() for i in self.items() if i.checkState() == Qt.Checked]


class DocumentPage(QWidget):
    message = Signal(str, int)  # text for the status bar, timeout in ms
    busy_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.session: Session | None = None
        self.busy = False
        self.settings = QSettings()
        self._build_actions()
        self._build_ui()
        self._update_state()

    # ---- UI construction -------------------------------------------------------

    def _action(self, text, shortcut, slot, tip):
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.setToolTip(f"{tip} ({QKeySequence(shortcut).toString()})" if shortcut else tip)
        action.triggered.connect(lambda: slot())  # don't forward the "checked" argument
        return action

    def _build_actions(self):
        self.act_refresh = self._action("⟳ Refresh", "F5", self.load_tables, "Reload the table list")
        self.act_all = self._action("☑ Select All", "Ctrl+A", self.select_all, "Tick every listed table")
        self.act_none = self._action("☐ Clear", "", self.select_none, "Untick the listed tables")
        self.act_generate = self._action("📄 Generate Document", "Ctrl+G", self.generate,
                                         "Write the document for the ticked tables")

    def _build_ui(self):
        toolbar = QToolBar("Document")
        toolbar.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.schema_label = QLabel(" Schema: ")
        self.schema_combo = QComboBox(minimumWidth=160)
        self.schema_combo.activated.connect(lambda _i: self.load_tables())
        self.schema_actions = [toolbar.addWidget(self.schema_label), toolbar.addWidget(self.schema_combo)]
        self.schema_separator = toolbar.addSeparator()
        for action in (self.act_refresh, self.act_all, self.act_none):
            toolbar.addAction(action)
        toolbar.addSeparator()
        toolbar.addAction(self.act_generate)

        # Left: table list
        self.table_search = QLineEdit(placeholderText="Filter tables…", clearButtonEnabled=True)
        self.table_search.textChanged.connect(self._filter_tables)
        self.table_list = TableList()
        self.table_list.itemChanged.connect(lambda _item: self._update_state())
        self.count_label = QLabel()
        self.overlay = LoadingOverlay(self.table_list)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(6, 6, 0, 6)
        left_layout.addWidget(QLabel("<b>Tables</b>"))
        left_layout.addWidget(self.table_search)
        left_layout.addWidget(self.table_list)
        left_layout.addWidget(self.count_label)

        # Right: output options
        self.title = QLineEdit()
        self.fmt_html = QRadioButton("HTML page")
        self.fmt_pdf = QRadioButton("PDF document")
        self.fmt_group = QButtonGroup(self)
        self.fmt_group.addButton(self.fmt_html)
        self.fmt_group.addButton(self.fmt_pdf)
        (self.fmt_pdf if self.settings.value("output/format", "html") == "pdf" else self.fmt_html).setChecked(True)
        fmt_row = QHBoxLayout()
        fmt_row.addWidget(self.fmt_html)
        fmt_row.addWidget(self.fmt_pdf)
        fmt_row.addStretch()
        self.open_after = QCheckBox("Open when finished")
        self.open_after.setChecked(self.settings.value("output/open", True, type=bool))
        self.generate_button = QPushButton("Generate document", objectName="primary")
        self.generate_button.clicked.connect(lambda: self.generate())

        output = QGroupBox("Output")
        form = QFormLayout(output)
        form.addRow("Title:", self.title)
        form.addRow("Format:", fmt_row)
        form.addRow("", self.open_after)
        about = QLabel("The document has an entity relationship diagram, the relationships between "
                       "the ticked tables, and every column with its type and keys.")
        about.setWordWrap(True)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 6, 6, 6)
        right_layout.addWidget(output)
        right_layout.addWidget(about)
        right_layout.addStretch()
        right_layout.addWidget(self.generate_button, alignment=Qt.AlignRight)

        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setSizes([560, 440])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(toolbar)
        layout.addWidget(splitter)

    # ---- connection / tables ---------------------------------------------------------

    def set_session(self, session: Session) -> None:
        self.session = session
        schemas = session.schemas
        self.schema_combo.clear()
        self.schema_combo.addItems(schemas)
        if session.default_schema in schemas:
            self.schema_combo.setCurrentText(session.default_schema)
        for action in self.schema_actions + [self.schema_separator]:
            action.setVisible(len(schemas) > 1)
        self.title.setText(f"{session.reader.database_name} schema")
        self.load_tables()

    def _schema(self):
        return self.schema_combo.currentText() if len(self.session.schemas) > 1 else None

    def _run(self, work, done, message):
        """Run `work` in the background, showing the loading overlay, then call `done(result)`."""
        self.busy = True
        self.overlay.start(message)
        self.table_list.setEnabled(False)
        self._update_state()
        self.worker = Worker(work, self)

        def finish():
            self.worker.wait()
            self.busy = False
            self.overlay.stop()
            self.table_list.setEnabled(True)
            self._update_state()

        def succeeded(result):
            finish()
            done(result)

        def failed(text):
            finish()
            self.message.emit("Something went wrong. See the message for details.", 8000)
            QMessageBox.critical(self, APP_NAME, text)

        self.worker.succeeded.connect(succeeded)
        self.worker.failed.connect(failed)
        self.worker.start()

    def wait(self) -> None:
        """Block until background work has finished (before closing the connection)."""
        if self.busy:
            self.worker.wait()

    def load_tables(self):
        if self.busy or not self.session:
            return
        reader, schema = self.session.reader, self._schema()

        def done(tables):
            self.table_list.set_tables(tables)
            self._filter_tables(self.table_search.text())
            where = f" in {schema}" if schema else ""
            self.message.emit(f"Found {len(tables)} tables{where}.", 8000)
            self._update_state()

        self._run(lambda: reader.list_tables(schema), done, "Reading table list…")

    def _filter_tables(self, text):
        text = text.lower()
        for item in self.table_list.items():
            item.setHidden(text not in item.text().lower())

    def _visible(self):
        return [i for i in self.table_list.items() if not i.isHidden()]

    def select_all(self):
        for item in self._visible():
            item.setCheckState(Qt.Checked)

    def select_none(self):
        for item in self._visible():
            item.setCheckState(Qt.Unchecked)

    # ---- output ----------------------------------------------------------------------

    def _format(self) -> str:
        return "pdf" if self.fmt_pdf.isChecked() else "html"

    def generate(self):
        tables = self.table_list.checked()
        if self.busy or not tables:
            return
        fmt = self._format()
        title = self.title.text().strip() or self.session.reader.database_name or "schema"
        folder = self.settings.value("output/folder", "")
        start = str(Path(folder) / f"{title.replace(' ', '_')}.{fmt}") if folder else f"{title.replace(' ', '_')}.{fmt}"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save document", start, "HTML page (*.html)" if fmt == "html" else "PDF document (*.pdf)")
        if path:
            self.generate_to(path, tables)

    def generate_to(self, path: str, tables: list[str]):
        """Write the document for `tables` to `path` in the background."""
        fmt = self._format()
        title = self.title.text().strip() or None
        reader, schema = self.session.reader, self._schema()
        self.settings.setValue("output/folder", str(Path(path).parent))
        self.settings.setValue("output/format", fmt)
        self.settings.setValue("output/open", self.open_after.isChecked())

        def done(out: Path):
            self.message.emit(f"Saved {out}", 15000)
            if self.open_after.isChecked():
                open_file(out)

        self._run(lambda: generate(reader, tables, path, fmt, schema=schema, title=title), done,
                  f"Documenting {len(tables)} table{'s' if len(tables) != 1 else ''}…")

    # ---- state -----------------------------------------------------------------------

    def _update_state(self):
        checked = len(self.table_list.checked())
        total = self.table_list.count()
        if not total:
            self.count_label.setText("No tables found.")
        elif not checked:
            self.count_label.setText(f"Click the tables to document ({total} available).")
        else:
            self.count_label.setText(f"{checked} of {total} tables ticked")
        ready = checked > 0 and not self.busy
        self.generate_button.setEnabled(ready)
        self.act_generate.setEnabled(ready)
        for action in (self.act_refresh, self.act_all, self.act_none):
            action.setEnabled(not self.busy)
        self.schema_combo.setEnabled(not self.busy)
        self.busy_changed.emit()
