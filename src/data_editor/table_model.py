"""Qt table model that holds a table's rows and tracks unsaved edits."""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QColor, QFont

from .db import Column, coerce, format_value

SORT_ROLE = Qt.UserRole + 1
TEXT_TYPES = {"char", "varchar", "nchar", "nvarchar", "text", "ntext", "sysname"}

NEW_COLOR = QColor(46, 160, 67, 70)
CHANGED_COLOR = QColor(219, 171, 9, 90)
DELETED_COLOR = QColor(218, 54, 51, 70)
NULL_COLOR = QColor(128, 128, 128)


@dataclass
class Row:
    values: list
    original: list | None = None  # None means the row has not been saved yet
    deleted: bool = False
    changed: set[int] = field(default_factory=set)

    @property
    def is_new(self) -> bool:
        return self.original is None


class RowTableModel(QAbstractTableModel):
    error = Signal(str)
    changes_updated = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.columns: list[Column] = []
        self.rows: list[Row] = []

    # ---- loading -------------------------------------------------------------

    def load(self, columns: list[Column], rows: list[list]) -> None:
        self.beginResetModel()
        self.columns = columns
        self.rows = [Row(values=list(r), original=list(r)) for r in rows]
        self.endResetModel()
        self.changes_updated.emit()

    def clear(self) -> None:
        self.load([], [])

    @property
    def has_primary_key(self) -> bool:
        return any(c.is_primary_key for c in self.columns)

    # ---- Qt model interface --------------------------------------------------

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.columns)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        col = index.column()
        value = row.values[col]

        if role == Qt.DisplayRole:
            return "NULL" if value is None else format_value(value)
        if role == Qt.EditRole:
            return format_value(value)
        if role == SORT_ROLE:
            return value
        if role == Qt.ForegroundRole and value is None:
            return NULL_COLOR
        if role == Qt.FontRole and (value is None or row.deleted):
            font = QFont()
            font.setItalic(value is None)
            font.setStrikeOut(row.deleted)
            return font
        if role == Qt.BackgroundRole:
            if row.deleted:
                return DELETED_COLOR
            if row.is_new:
                return NEW_COLOR
            if col in row.changed:
                return CHANGED_COLOR
        if role == Qt.ToolTipRole and not row.is_new and col in row.changed:
            return f"Original: {'NULL' if row.original[col] is None else format_value(row.original[col])}"
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and section < len(self.columns):
            column = self.columns[section]
            if role == Qt.DisplayRole:
                return ("🔑 " if column.is_primary_key else "") + column.name
            if role == Qt.ToolTipRole:
                notes = [column.data_type, "NULL" if column.nullable else "NOT NULL"]
                if column.is_identity:
                    notes.append("identity")
                if column.is_computed:
                    notes.append("computed")
                if not column.editable:
                    notes.append("read-only")
                return ", ".join(notes)
        if orientation == Qt.Vertical and role == Qt.DisplayRole and section < len(self.rows):
            return "＋" if self.rows[section].is_new else str(section + 1)
        return None

    def flags(self, index):
        flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if self.can_edit(index):
            flags |= Qt.ItemIsEditable
        return flags

    def can_edit(self, index) -> bool:
        if not index.isValid():
            return False
        row = self.rows[index.row()]
        column = self.columns[index.column()]
        return column.editable and not row.deleted and (row.is_new or self.has_primary_key)

    def setData(self, index, value, role=Qt.EditRole):
        if role != Qt.EditRole or not self.can_edit(index):
            return False
        column = self.columns[index.column()]
        text = "" if value is None else str(value)
        if text == "" and column.data_type not in TEXT_TYPES:
            new_value = None  # blank in a non-text column means NULL
        else:
            try:
                new_value = coerce(text, column)
            except ValueError as exc:
                self.error.emit(str(exc))
                return False
        self._set_value(index.row(), index.column(), new_value)
        return True

    # ---- editing operations --------------------------------------------------

    def _set_value(self, r: int, c: int, value) -> None:
        row = self.rows[r]
        row.values[c] = value
        if not row.is_new:
            if value == row.original[c] and type(value) is type(row.original[c]):
                row.changed.discard(c)
            else:
                row.changed.add(c)
        idx = self.index(r, c)
        self.dataChanged.emit(idx, idx)
        self.changes_updated.emit()

    def set_null(self, indexes) -> None:
        for index in indexes:
            if self.can_edit(index):
                self._set_value(index.row(), index.column(), None)

    def add_row(self) -> int:
        r = len(self.rows)
        self.beginInsertRows(QModelIndex(), r, r)
        self.rows.append(Row(values=[None] * len(self.columns)))
        self.endInsertRows()
        self.changes_updated.emit()
        return r

    def toggle_delete(self, row_numbers: list[int]) -> None:
        """Mark rows deleted (or undelete them if they are all already marked).

        Unsaved new rows are simply removed.
        """
        existing = [r for r in row_numbers if not self.rows[r].is_new]
        if existing and not self.has_primary_key:
            self.error.emit("This table has no primary key, so existing rows can't be deleted safely.")
            existing = []
        undelete = bool(existing) and all(self.rows[r].deleted for r in existing)
        for r in existing:
            self.rows[r].deleted = not undelete
        if existing:
            self.dataChanged.emit(self.index(min(existing), 0), self.index(max(existing), self.columnCount() - 1))
        for r in sorted((r for r in row_numbers if self.rows[r].is_new), reverse=True):
            self.beginRemoveRows(QModelIndex(), r, r)
            del self.rows[r]
            self.endRemoveRows()
        self.changes_updated.emit()

    def revert(self) -> None:
        self.load(self.columns, [r.original for r in self.rows if not r.is_new])

    # ---- change tracking -------------------------------------------------------

    def counts(self) -> tuple[int, int, int]:
        """(new, modified, deleted) row counts."""
        new = sum(1 for r in self.rows if r.is_new)
        deleted = sum(1 for r in self.rows if r.deleted)
        modified = sum(1 for r in self.rows if r.changed and not r.deleted)
        return new, modified, deleted

    def has_changes(self) -> bool:
        return any(self.counts())

    def pending_changes(self) -> tuple[list[dict], list[tuple[dict, dict]], list[dict]]:
        names = [c.name for c in self.columns]
        pk = [i for i, c in enumerate(self.columns) if c.is_primary_key]
        inserts, updates, deletes = [], [], []
        for row in self.rows:
            if row.is_new:
                inserts.append(
                    {names[i]: v for i, v in enumerate(row.values) if v is not None and self.columns[i].editable}
                )
                continue
            keys = {names[i]: row.original[i] for i in pk}
            if row.deleted:
                deletes.append(keys)
            elif row.changed:
                updates.append((keys, {names[i]: row.values[i] for i in sorted(row.changed)}))
        return inserts, updates, deletes


class SortProxy(QSortFilterProxyModel):
    """Sorts by the raw database value, with NULLs first."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSortRole(SORT_ROLE)
        self.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.setFilterKeyColumn(-1)

    def lessThan(self, left, right):
        a, b = left.data(SORT_ROLE), right.data(SORT_ROLE)
        if a is None or b is None:
            return a is None and b is not None
        try:
            return a < b
        except TypeError:
            return str(a) < str(b)
