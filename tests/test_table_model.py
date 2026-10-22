from PySide6.QtCore import Qt

from data_editor.db import Column
from data_editor.table_model import RowTableModel

COLUMNS = [
    Column("Id", "int", False, True, False, True),
    Column("Name", "nvarchar", True, False, False, False),
    Column("Qty", "int", True, False, False, False),
]


def make_model(columns=COLUMNS):
    model = RowTableModel()
    model.load(columns, [[1, "Apple", 5], [2, "Pear", None]])
    return model


def test_edit_tracks_update():
    model = make_model()
    assert model.setData(model.index(0, 1), "Green Apple")
    inserts, updates, deletes = model.pending_changes()
    assert updates == [({"Id": 1}, {"Name": "Green Apple"})]
    assert not inserts and not deletes


def test_editing_back_to_original_clears_change():
    model = make_model()
    model.setData(model.index(0, 2), "7")
    model.setData(model.index(0, 2), "5")
    assert not model.has_changes()


def test_identity_column_is_read_only():
    model = make_model()
    assert not model.flags(model.index(0, 0)) & Qt.ItemIsEditable


def test_invalid_value_is_rejected():
    model = make_model()
    errors = []
    model.error.connect(errors.append)
    assert not model.setData(model.index(0, 2), "lots")
    assert errors and not model.has_changes()


def test_add_and_delete_rows():
    model = make_model()
    r = model.add_row()
    model.setData(model.index(r, 1), "Plum")
    model.toggle_delete([1])
    inserts, updates, deletes = model.pending_changes()
    assert inserts == [{"Name": "Plum"}]
    assert deletes == [{"Id": 2}]
    assert model.counts() == (1, 0, 1)

    model.toggle_delete([1])  # undelete
    model.toggle_delete([r])  # removing an unsaved row drops it entirely
    assert not model.has_changes()


def test_blank_numeric_cell_becomes_null():
    model = make_model()
    model.setData(model.index(0, 2), "")
    assert model.pending_changes()[1] == [({"Id": 1}, {"Qty": None})]


def test_table_without_primary_key_only_allows_inserts():
    no_pk = [Column(c.name, c.data_type, c.nullable, False, False, False) for c in COLUMNS]
    model = make_model(no_pk)
    assert not model.flags(model.index(0, 1)) & Qt.ItemIsEditable
    r = model.add_row()
    assert model.flags(model.index(r, 1)) & Qt.ItemIsEditable


def test_revert_discards_everything():
    model = make_model()
    model.setData(model.index(0, 1), "X")
    model.add_row()
    model.revert()
    assert not model.has_changes()
    assert model.rowCount() == 2
