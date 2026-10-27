"""One signed-in connection, shared by the Edit Data and Document Schema tabs."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional

import pyodbc
from sqlalchemy.engine import URL

from schemadoc.introspect import SchemaReader

from .db import ConnectionInfo, Database


def sql_server_reader(info: ConnectionInfo, database: str) -> SchemaReader:
    """A schema reader that connects with the same ODBC settings as the editor."""
    connection_string = replace(info, database=database).connection_string()
    url = URL.create(
        "mssql+pyodbc",
        username=None if info.windows_auth else info.username or None,
        host=info.server,
        database=database,
    )
    return SchemaReader(url, creator=lambda: pyodbc.connect(connection_string, timeout=15))


def _schemas(reader: SchemaReader) -> list[str]:
    return reader.list_schemas() if reader.dialect != "sqlite" else []


@dataclass
class Session:
    reader: SchemaReader  # reads table structure for documenting (any database type)
    schemas: list[str]  # empty when the database has no schemas worth picking
    default_schema: Optional[str]
    editor: Optional[Database] = None  # row editing, SQL Server only

    @property
    def can_edit(self) -> bool:
        return self.editor is not None

    @property
    def label(self) -> str:
        """Who is connected where, for the status bar."""
        if self.editor:
            info = self.editor.info
            who = "Windows user" if info.windows_auth else info.username
            return f"{who} @ {info.server}"
        reader = self.reader
        if reader.dialect == "sqlite":
            return f"sqlite: {reader.database_name}"
        url = reader.url
        return f"{reader.dialect}: {url.username + '@' if url.username else ''}{url.host or ''} / {url.database or ''}"

    def databases(self) -> list[str]:
        return self.editor.databases() if self.editor else []

    def current_database(self) -> str:
        return self.editor.current_database() if self.editor else self.reader.database_name

    def switch_database(self, name: str) -> None:
        """SQL Server only: point both the editor and the schema reader at another database."""
        reader = sql_server_reader(self.editor.info, name)
        self.editor.use_database(name)
        self.reader.close()
        self.reader = reader
        self.schemas = _schemas(reader)
        self.default_schema = reader.default_schema()

    def close(self) -> None:
        self.reader.close()
        if self.editor:
            self.editor.close()


def open_sql_server(info: ConnectionInfo) -> Session:
    editor = Database(info)
    try:
        reader = sql_server_reader(info, editor.current_database())
    except Exception:
        editor.close()
        raise
    return Session(reader, _schemas(reader), reader.default_schema(), editor)


def open_url(url) -> Session:
    reader = SchemaReader(url)
    return Session(reader, _schemas(reader), reader.default_schema())
