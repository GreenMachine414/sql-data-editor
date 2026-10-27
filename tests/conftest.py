import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session", autouse=True)
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path):
    """Keep tests from reading or overwriting the real app's remembered settings."""
    from PySide6.QtCore import QCoreApplication, QSettings

    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path))
    QCoreApplication.setOrganizationName("DataEditorTests")


@pytest.fixture
def sample_db(tmp_path):
    from make_sample_db import make

    return make(tmp_path / "sample.db")


@pytest.fixture
def reader(sample_db):
    from schemadoc.introspect import SchemaReader

    r = SchemaReader(f"sqlite:///{sample_db}")
    yield r
    r.close()
