"""Turn friendly connection settings into SQLAlchemy URLs."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.engine import URL, make_url


@dataclass(frozen=True)
class DbType:
    label: str
    driver: str
    default_port: Optional[int]
    is_file: bool = False
    is_custom: bool = False
    is_sql_server: bool = False  # connects through ODBC; the only type that supports editing rows


DB_TYPES: list[DbType] = [
    DbType("SQL Server", "mssql+pyodbc", None, is_sql_server=True),
    DbType("PostgreSQL", "postgresql+psycopg", 5432),
    DbType("MySQL / MariaDB", "mysql+pymysql", 3306),
    DbType("SQLite", "sqlite", None, is_file=True),
    DbType("Custom SQLAlchemy URL", "", None, is_custom=True),
]


def db_type(label: str) -> DbType:
    for t in DB_TYPES:
        if t.label == label:
            return t
    raise KeyError(label)


def build_url(
    kind: DbType,
    host: str = "",
    port: str | int | None = None,
    database: str = "",
    username: str = "",
    password: str = "",
    file_path: str = "",
    custom_url: str = "",
) -> URL:
    """Build a SQLAlchemy URL. Raises ValueError with a user-facing message."""
    if kind.is_custom:
        if not custom_url.strip():
            raise ValueError("Enter a connection URL, e.g. postgresql://user:pass@host/db")
        try:
            return normalize_url(make_url(custom_url.strip()))
        except Exception as exc:  # sqlalchemy raises ArgumentError
            raise ValueError(f"That connection URL isn't valid: {exc}") from exc
    if kind.is_file:
        if not file_path.strip():
            raise ValueError("Choose a SQLite database file.")
        return URL.create("sqlite", database=file_path.strip())
    if not host.strip():
        raise ValueError("Enter the database host.")
    if not database.strip():
        raise ValueError("Enter the database name.")
    port_num = None
    if port not in (None, ""):
        try:
            port_num = int(port)
        except ValueError as exc:
            raise ValueError("Port must be a number.") from exc
    return URL.create(
        kind.driver,
        username=username or None,
        password=password or None,
        host=host.strip(),
        port=port_num,
        database=database.strip(),
    )


# Drivers bundled with the app; plain "postgresql://" etc. are pointed at them.
BUNDLED_DRIVERS = {
    "postgresql": "postgresql+psycopg",
    "postgres": "postgresql+psycopg",
    "mysql": "mysql+pymysql",
    "mariadb": "mariadb+pymysql",
    "mssql": "mssql+pyodbc",
}


def normalize_url(url: URL | str) -> URL:
    url = make_url(url) if isinstance(url, str) else url
    target = BUNDLED_DRIVERS.get(url.drivername)
    if target:
        url = url.set(drivername=target)
    if url.drivername == "mssql+pyodbc" and url.host and "driver" not in url.query:
        # pyodbc needs to know which installed ODBC driver to use
        from data_editor.db import available_drivers

        drivers = available_drivers()
        if drivers:
            url = url.update_query_dict({"driver": drivers[0]})
    return url


def safe_url(url: URL) -> str:
    """URL string with the password hidden, for display and reports."""
    return url.render_as_string(hide_password=True)
