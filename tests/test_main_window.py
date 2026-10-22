import threading
import time

from PySide6.QtCore import QCoreApplication, Qt

from data_editor.db import Column, ConnectionInfo
from data_editor.main_window import MainWindow

COLUMNS = [Column("Id", "int", False, True, False, True), Column("Name", "nvarchar", True, False, False, False)]
TABLES = {
    ("dbo", "Fruit"): [[1, "Apple"], [2, "Pear"]],
    ("dbo", "Veg"): [[1, "Kale"], [2, "Leek"], [3, "Okra"]],
}


class FakeDatabase:
    """Stands in for db.Database; optionally slow, and fails if two threads query at once."""

    def __init__(self, delay=0.0):
        self.info = ConnectionInfo(server="fake", username="tester")
        self.delay = delay
        self.in_use = threading.Lock()
        self.thread_ids = set()

    def databases(self):
        return ["FakeDb"]

    def current_database(self):
        return "FakeDb"

    def tables(self):
        return list(TABLES)

    def columns(self, schema, table):
        return COLUMNS

    def fetch_rows(self, schema, table, columns, limit, where=""):
        assert self.in_use.acquire(blocking=False), "connection used by two threads at once"
        try:
            self.thread_ids.add(threading.get_ident())
            time.sleep(self.delay)
            return [list(r) for r in TABLES[(schema, table)]]
        finally:
            self.in_use.release()

    def close(self):
        pass


def wait_until(condition, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        QCoreApplication.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    return False


def select_table(window, name):
    item = window.table_list.findItems(name, Qt.MatchExactly)[0]
    window.table_list.setCurrentItem(item)


def test_table_loads_in_background_thread():
    db = FakeDatabase(delay=0.3)
    window = MainWindow(db)
    window.show()
    select_table(window, "dbo.Fruit")

    assert window.loading
    assert not window.view.isEnabled()
    assert wait_until(lambda: window.overlay.isVisible()), "spinner should appear for slow loads"

    assert wait_until(lambda: not window.loading)
    assert window.model.rowCount() == 2
    assert not window.overlay.isVisible()
    assert window.view.isEnabled()
    assert threading.get_ident() not in db.thread_ids
    window.close()


def test_switching_tables_mid_load_shows_the_last_one():
    db = FakeDatabase(delay=0.2)
    window = MainWindow(db)
    window.show()
    select_table(window, "dbo.Fruit")
    select_table(window, "dbo.Veg")  # clicked while Fruit is still loading

    assert wait_until(lambda: not window.loading)
    assert window.current == ("dbo", "Veg")
    assert [r.values[1] for r in window.model.rows] == ["Kale", "Leek", "Okra"]
    window.close()


def test_fast_load_does_not_flash_spinner():
    window = MainWindow(FakeDatabase())
    window.show()
    select_table(window, "dbo.Fruit")
    assert wait_until(lambda: not window.loading)
    assert not window.overlay.isVisible()
    window.close()
