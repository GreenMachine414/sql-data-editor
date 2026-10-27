"""End-to-end test against a real SQL Server, using a scratch table in tempdb.

Skipped unless DATA_EDITOR_TEST_SERVER is set, e.g.
    $env:DATA_EDITOR_TEST_SERVER = "localhost"     (signs in with Windows authentication)
"""

import os
import time

import pytest
from PySide6.QtCore import QCoreApplication, Qt

from data_editor.db import ConnectionInfo
from data_editor.main_window import MainWindow
from data_editor.session import open_sql_server

SERVER = os.environ.get("DATA_EDITOR_TEST_SERVER")
pytestmark = pytest.mark.skipif(not SERVER, reason="set DATA_EDITOR_TEST_SERVER to run")

TABLE = "data_editor_test_orders"


def wait_until(condition, timeout=30):
    end = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < end, "timed out"
        QCoreApplication.processEvents()
        time.sleep(0.01)


@pytest.fixture
def window():
    info = ConnectionInfo(server=SERVER, database="tempdb", windows_auth=True, trust_server_certificate=True)
    session = open_sql_server(info)
    cur = session.editor.conn.cursor()
    cur.execute(f"DROP TABLE IF EXISTS dbo.{TABLE}_lines; DROP TABLE IF EXISTS dbo.{TABLE}")
    cur.execute(f"CREATE TABLE dbo.{TABLE} (Id int IDENTITY PRIMARY KEY, Customer nvarchar(50) NOT NULL)")
    cur.execute(f"CREATE TABLE dbo.{TABLE}_lines (Id int IDENTITY PRIMARY KEY, "
                f"OrderId int NOT NULL REFERENCES dbo.{TABLE}(Id), Qty int NULL)")
    cur.execute(f"INSERT INTO dbo.{TABLE} (Customer) VALUES ('Acme'), ('Globex')")
    session.editor.conn.commit()

    w = MainWindow(session)
    w.show()
    wait_until(lambda: not w.busy)
    yield w
    w.editor.model.revert()
    w.close()
    cleanup = open_sql_server(info)
    cleanup.editor.conn.cursor().execute(f"DROP TABLE dbo.{TABLE}_lines; DROP TABLE dbo.{TABLE}")
    cleanup.editor.conn.commit()
    cleanup.close()


def test_edit_and_document_the_same_connection(window, tmp_path):
    assert window.session.can_edit
    assert window.db_combo.currentText() == "tempdb"
    assert "Windows user @" in window.conn_label.text()

    # Edit Data tab
    editor = window.editor
    item = editor.table_list.findItems(f"dbo.{TABLE}", Qt.MatchExactly)[0]
    editor.table_list.setCurrentItem(item)
    wait_until(lambda: not editor.loading and editor.model.rowCount() == 2)
    editor.model.setData(editor.model.index(0, 1), "Acme Corp")
    editor.save()
    wait_until(lambda: not editor.loading)
    assert editor.model.rows[0].values[1] == "Acme Corp"

    # Document Schema tab, through the same sign-in
    page = window.document
    for name in (TABLE, f"{TABLE}_lines"):
        page.table_list.findItems(name, Qt.MatchExactly)[0].setCheckState(Qt.Checked)
    page.open_after.setChecked(False)
    page.fmt_pdf.setChecked(True)
    page.generate_to(str(tmp_path / "orders.pdf"), page.table_list.checked())
    wait_until(lambda: not window.busy)
    assert (tmp_path / "orders.pdf").stat().st_size > 1000
    doc = window.session.reader.read([TABLE, f"{TABLE}_lines"], schema=page._schema())
    assert [(r.child_table, r.parent_table) for r in doc.relationships] == [(f"{TABLE}_lines", TABLE)]
