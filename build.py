"""Build a single-file Windows executable with PyInstaller.

Usage:  python build.py        ->  dist/DataEditor.exe
"""

import PyInstaller.__main__

PyInstaller.__main__.run(
    [
        "src/data_editor/__main__.py",
        "--name=DataEditor",
        "--onefile",
        "--windowed",
        "--noconfirm",
        "--clean",
        "--paths=src",
        # Database dialects and drivers are loaded by name at runtime, so list them explicitly.
        "--collect-submodules=sqlalchemy.dialects",
        "--collect-submodules=psycopg",
        "--collect-submodules=psycopg_binary",
        "--hidden-import=sqlalchemy.sql.default_comparator",
        "--hidden-import=pymysql",
        "--exclude-module=tkinter",
        "--exclude-module=pytest",
        "--exclude-module=pypdf",
        # Trim Qt modules the app doesn't use to keep the exe small.
        "--exclude-module=PySide6.QtWebEngineCore",
        "--exclude-module=PySide6.QtWebEngineWidgets",
        "--exclude-module=PySide6.QtQml",
        "--exclude-module=PySide6.QtQuick",
        "--exclude-module=PySide6.Qt3DCore",
        "--exclude-module=PySide6.QtMultimedia",
        "--exclude-module=PySide6.QtCharts",
        "--exclude-module=PySide6.QtPdf",
    ]
)
