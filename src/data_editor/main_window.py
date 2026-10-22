"""Main application window: table browser and row editor."""

from __future__ import annotations

from time import perf_counter

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableView,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .db import Database
from .table_model import RowTableModel, SortProxy
from .widgets import LoadingOverlay
from .worker import Worker

# Column widths are sized from this many rows rather than every loaded row,
# which was by far the slowest part of opening a table.
SIZE_SAMPLE_ROWS = 60
MAX_COLUMN_WIDTH = 320


class MainWindow(QMainWindow):
    def __init__(self, database: Database):
        super().__init__()
        self.db = database
        self.current: tuple[str, str] | None = None  # (schema, table)
        self.loading = False
        self._queued_load = None  # a load requested while another was running

        self.setWindowTitle(f"Data Editor {__version__}")
        self.resize(1200, 750)

        self.model = RowTableModel(self)
        self.proxy = SortProxy(self)
        self.proxy.setSourceModel(self.model)
        self.model.error.connect(lambda msg: QMessageBox.warning(self, "Invalid value", msg))
        self.model.changes_updated.connect(self._update_state)

        self._build_actions()
        self._build_ui()
        self._load_databases()
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
        self.act_refresh = self._action("⟳ Refresh", "F5", self.reload_rows, "Reload rows from the database")
        self.act_add = self._action("＋ Add Row", "Ctrl+N", self.add_row, "Add a new row")
        self.act_delete = self._action("✕ Delete Row", "Ctrl+D", self.delete_rows, "Mark selected rows for deletion")
        self.act_null = self._action("∅ Set NULL", "Ctrl+0", self.set_null, "Set the selected cells to NULL")
        self.act_save = self._action("💾 Save Changes", "Ctrl+S", self.save, "Write all pending changes")
        self.act_discard = self._action("↶ Discard Changes", "", self.discard, "Throw away unsaved changes")
        self.act_copy = self._action("Copy", QKeySequence.Copy, self.copy_cells, "Copy selected cells")
        self.act_paste = self._action("Paste", QKeySequence.Paste, self.paste_cells, "Paste into cells")

    def _build_ui(self):
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.addToolBar(toolbar)
        toolbar.addWidget(QLabel(" Database: "))
        self.db_combo = QComboBox(minimumWidth=180)
        self.db_combo.activated.connect(self._database_chosen)
        toolbar.addWidget(self.db_combo)
        toolbar.addSeparator()
        for action in (self.act_refresh, self.act_add, self.act_delete, self.act_null):
            toolbar.addAction(action)
        toolbar.addSeparator()
        toolbar.addAction(self.act_save)
        toolbar.addAction(self.act_discard)

        # Left: table list
        self.table_search = QLineEdit(placeholderText="Filter tables…", clearButtonEnabled=True)
        self.table_search.textChanged.connect(self._filter_tables)
        self.table_list = QListWidget(objectName="tableList")
        self.table_list.setMouseTracking(True)  # needed for the hover highlight
        self.table_list.currentItemChanged.connect(self._table_chosen)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(6, 6, 0, 6)
        left_layout.addWidget(QLabel("<b>Tables</b>"))
        left_layout.addWidget(self.table_search)
        left_layout.addWidget(self.table_list)

        # Right: query options + grid
        self.title = QLabel()
        self.title.setStyleSheet("font-size: 15px; font-weight: 600;")
        self.notice = QLabel()
        self.notice.setStyleSheet("color: #b8860b;")
        self.where = QLineEdit(placeholderText="WHERE clause (optional), e.g. Status = 'Open' AND Qty > 5")
        self.where.returnPressed.connect(self.reload_rows)
        self.limit = QSpinBox(minimum=1, maximum=1_000_000, value=1000, singleStep=500)
        self.limit.setPrefix("Max rows: ")
        load_button = QPushButton("Load")
        load_button.clicked.connect(lambda: self.reload_rows())
        self.quick_search = QLineEdit(placeholderText="Search loaded rows…", clearButtonEnabled=True)
        self.quick_search.textChanged.connect(self.proxy.setFilterFixedString)

        query_row = QHBoxLayout()
        query_row.addWidget(self.where, 3)
        query_row.addWidget(self.limit)
        query_row.addWidget(load_button)
        query_row.addWidget(self.quick_search, 2)

        self.view = QTableView()
        self.view.setModel(self.proxy)
        self.view.setSortingEnabled(True)
        self.view.sortByColumn(-1, Qt.AscendingOrder)
        self.view.setAlternatingRowColors(True)
        self.view.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.view.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed | QAbstractItemView.AnyKeyPressed
        )
        self.view.horizontalHeader().setStretchLastSection(True)
        self.view.horizontalHeader().setResizeContentsPrecision(SIZE_SAMPLE_ROWS)
        self.view.verticalHeader().setResizeContentsPrecision(SIZE_SAMPLE_ROWS)
        self.view.verticalHeader().setDefaultSectionSize(24)
        self.overlay = LoadingOverlay(self.view)
        self.view.setContextMenuPolicy(Qt.ActionsContextMenu)
        self.view.addActions([self.act_copy, self.act_paste, self.act_null, self.act_add, self.act_delete])

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 6, 6, 6)
        right_layout.addWidget(self.title)
        right_layout.addWidget(self.notice)
        right_layout.addLayout(query_row)
        right_layout.addWidget(self.view)

        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([260, 940])
        self.setCentralWidget(splitter)

        info = self.db.info
        who = "Windows user" if info.windows_auth else info.username
        self.statusBar().addPermanentWidget(QLabel(f"{who} @ {info.server}  "))
        self.pending_label = QLabel()
        self.statusBar().addWidget(self.pending_label)

    # ---- database / table selection ----------------------------------------------

    def _load_databases(self):
        try:
            names = self.db.databases()
            current = self.db.current_database()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error", f"Could not list databases:\n{exc}")
            return
        self.db_combo.clear()
        self.db_combo.addItems(names)
        self.db_combo.setCurrentText(current)
        self._load_tables()

    def _database_chosen(self, _index):
        name = self.db_combo.currentText()
        if not self._confirm_leave():
            self.db_combo.setCurrentText(self.db.current_database())
            return
        try:
            self.db.use_database(name)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error", f"Could not open database '{name}':\n{exc}")
            self.db_combo.setCurrentText(self.db.current_database())
            return
        self._load_tables()

    def _load_tables(self):
        self.current = None
        self.model.clear()
        self.title.setText("Select a table")
        self.notice.clear()
        self.table_list.blockSignals(True)
        self.table_list.clear()
        try:
            for schema, table in self.db.tables():
                self.table_list.addItem(f"{schema}.{table}")
                self.table_list.item(self.table_list.count() - 1).setData(Qt.UserRole, (schema, table))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Error", f"Could not list tables:\n{exc}")
        self.table_list.blockSignals(False)
        self._filter_tables(self.table_search.text())
        self._update_state()

    def _filter_tables(self, text):
        text = text.lower()
        for i in range(self.table_list.count()):
            item = self.table_list.item(i)
            item.setHidden(text not in item.text().lower())

    def _table_chosen(self, item, previous):
        if item is None:
            return
        if not self._confirm_leave():
            self.table_list.blockSignals(True)
            self.table_list.setCurrentItem(previous)
            self.table_list.blockSignals(False)
            return
        self.current = item.data(Qt.UserRole)
        self.where.clear()
        self.quick_search.clear()
        self.reload_rows(confirm=False)

    def reload_rows(self, confirm=True):
        if not self.current or (confirm and not self._confirm_leave()):
            return
        request = (self.current, self.where.text(), self.limit.value())
        if self.loading:
            # The connection can only run one query at a time; load this once the current one finishes.
            self._queued_load = request
            self.overlay.start(f"Loading {request[0][0]}.{request[0][1]}…")
            return
        self._start_load(request)

    def _start_load(self, request):
        (schema, table), where, limit = request
        self._queued_load = None
        self.loading = True
        self.title.setText(f"{schema}.{table}")
        self.overlay.start(f"Loading {schema}.{table}…")
        self.view.setEnabled(False)
        self._update_state()

        def work():
            started = perf_counter()
            columns = self.db.columns(schema, table)
            rows = self.db.fetch_rows(schema, table, columns, limit, where)
            return request, columns, rows, perf_counter() - started

        self._loader = Worker(work, self)
        self._loader.succeeded.connect(self._rows_loaded)
        self._loader.failed.connect(self._load_failed)
        self._loader.start()

    def _end_load(self) -> bool:
        """Finish a background load. Returns True if a newer load was queued and has started."""
        self.loading = False
        self._loader.wait()
        if self._queued_load:
            self._start_load(self._queued_load)
            return True
        self.overlay.stop()
        self.view.setEnabled(True)
        self._update_state()
        return False

    def _load_failed(self, message: str):
        if self._end_load():
            return
        QMessageBox.critical(self, "Error loading rows", message)

    def _rows_loaded(self, result):
        if self._end_load():
            return  # the user already moved on to another table
        ((schema, table), _where, limit), columns, rows, query_seconds = result

        started = perf_counter()
        self.model.load(columns, rows)
        self.view.sortByColumn(-1, Qt.AscendingOrder)
        self.view.resizeColumnsToContents()
        for c in range(self.model.columnCount()):
            self.view.setColumnWidth(c, min(self.view.columnWidth(c), MAX_COLUMN_WIDTH))
        total_ms = (query_seconds + perf_counter() - started) * 1000

        self.title.setText(f"{schema}.{table}")
        more = " (limit reached — more rows may exist)" if len(rows) >= limit else ""
        self.statusBar().showMessage(f"Loaded {len(rows):,} rows in {total_ms:,.0f} ms{more}", 8000)
        if not self.model.has_primary_key:
            self.notice.setText("⚠ This table has no primary key: you can add rows, but not edit or delete them.")
        else:
            self.notice.clear()
        self._update_state()

    # ---- editing actions ---------------------------------------------------------

    def _selected_source_indexes(self):
        return [self.proxy.mapToSource(i) for i in self.view.selectionModel().selectedIndexes()]

    def add_row(self):
        if not self.current:
            return
        r = self.model.add_row()
        proxy_index = self.proxy.mapFromSource(self.model.index(r, 0))
        first_editable = next((c for c, col in enumerate(self.model.columns) if col.editable), 0)
        target = proxy_index.siblingAtColumn(first_editable)
        self.view.scrollTo(target)
        self.view.setCurrentIndex(target)
        self.view.edit(target)

    def delete_rows(self):
        rows = sorted({i.row() for i in self._selected_source_indexes()})
        if rows:
            self.model.toggle_delete(rows)

    def set_null(self):
        indexes = self._selected_source_indexes()
        if any(not self.model.columns[i.column()].nullable for i in indexes if self.model.can_edit(i)):
            QMessageBox.warning(self, "Not allowed", "One or more selected columns do not allow NULL.")
            return
        self.model.set_null(indexes)

    def copy_cells(self):
        indexes = sorted(self.view.selectionModel().selectedIndexes(), key=lambda i: (i.row(), i.column()))
        if not indexes:
            return
        lines, current_row, cells = [], indexes[0].row(), []
        for index in indexes:
            if index.row() != current_row:
                lines.append("\t".join(cells))
                current_row, cells = index.row(), []
            cells.append(index.data(Qt.EditRole) or "")
        lines.append("\t".join(cells))
        QGuiApplication.clipboard().setText("\n".join(lines))

    def paste_cells(self):
        start = self.view.currentIndex()
        text = QGuiApplication.clipboard().text()
        if not start.isValid() or not text:
            return
        for dr, line in enumerate(text.rstrip("\r\n").split("\n")):
            for dc, value in enumerate(line.rstrip("\r").split("\t")):
                index = self.proxy.index(start.row() + dr, start.column() + dc)
                if index.isValid() and self.proxy.flags(index) & Qt.ItemIsEditable:
                    if not self.proxy.setData(index, value, Qt.EditRole):
                        return  # stop at the first invalid value (error already shown)

    def save(self):
        if not self.current or self.loading or not self.model.has_changes():
            return
        if self.view.state() == QAbstractItemView.EditingState:
            self.view.setFocus()  # commit the cell currently being edited
        new, modified, deleted = self.model.counts()
        if deleted:
            answer = QMessageBox.question(
                self, "Confirm", f"Permanently delete {deleted} row(s) and save all other changes?"
            )
            if answer != QMessageBox.Yes:
                return
        schema, table = self.current
        try:
            self.db.apply_changes(schema, table, self.model.columns, *self.model.pending_changes())
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Save failed", f"No changes were saved.\n\n{exc}")
            return
        self.statusBar().showMessage(
            f"Saved: {new} added, {modified} updated, {deleted} deleted", 8000
        )
        self.reload_rows(confirm=False)

    def discard(self):
        if self.model.has_changes():
            self.model.revert()

    # ---- state ---------------------------------------------------------------------

    def _update_state(self):
        has_table = self.current is not None and not self.loading
        dirty = self.model.has_changes()
        for action in (self.act_refresh, self.act_add, self.act_delete, self.act_null, self.act_paste):
            action.setEnabled(has_table)
        self.act_save.setEnabled(dirty and not self.loading)
        self.act_discard.setEnabled(dirty and not self.loading)
        self.db_combo.setEnabled(not self.loading)
        new, modified, deleted = self.model.counts()
        self.pending_label.setText(
            f"Unsaved changes: {new} new, {modified} modified, {deleted} deleted" if dirty else "No unsaved changes"
        )
        title = f"Data Editor {__version__}"
        if self.current:
            title = f"{'● ' if dirty else ''}{self.current[0]}.{self.current[1]} — {title}"
        self.setWindowTitle(title)

    def _confirm_leave(self) -> bool:
        """If there are unsaved changes, ask what to do. Returns False to cancel."""
        if not self.model.has_changes():
            return True
        answer = QMessageBox.question(
            self,
            "Unsaved changes",
            "You have unsaved changes. Save them first?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
        )
        if answer == QMessageBox.Save:
            self.save()
            return not self.model.has_changes()
        if answer == QMessageBox.Discard:
            self.model.revert()
            return True
        return False

    def closeEvent(self, event):
        if self._confirm_leave():
            if self.loading:
                self._loader.wait()
            self.db.close()
            event.accept()
        else:
            event.ignore()
