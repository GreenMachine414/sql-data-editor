"""SQL Server access layer: connecting, introspection, reading and writing rows."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

import pyodbc

INT_TYPES = {"tinyint", "smallint", "int", "bigint"}
DECIMAL_TYPES = {"decimal", "numeric", "money", "smallmoney"}
FLOAT_TYPES = {"float", "real"}
DATE_TYPES = {"date"}
DATETIME_TYPES = {"datetime", "datetime2", "smalldatetime"}
TIME_TYPES = {"time"}
BINARY_TYPES = {"binary", "varbinary", "image", "timestamp", "rowversion"}
# Types we can display but not safely round-trip through a text cell.
READONLY_TYPES = BINARY_TYPES | {"geography", "geometry", "hierarchyid", "sql_variant", "xml"}


def quote_ident(name: str) -> str:
    """Quote a SQL Server identifier, e.g. my]table -> [my]]table]."""
    return "[" + name.replace("]", "]]") + "]"


@dataclass
class ConnectionInfo:
    server: str
    database: str = ""
    windows_auth: bool = False
    username: str = ""
    password: str = field(default="", repr=False)
    driver: str = "ODBC Driver 18 for SQL Server"
    encrypt: bool = True
    trust_server_certificate: bool = False

    def connection_string(self) -> str:
        parts = [f"DRIVER={{{self.driver}}}", f"SERVER={self.server}"]
        if self.database:
            parts.append(f"DATABASE={self.database}")
        if self.windows_auth:
            parts.append("Trusted_Connection=yes")
        else:
            parts.append(f"UID={self.username}")
            parts.append("PWD={" + self.password.replace("}", "}}") + "}")
        parts.append(f"Encrypt={'yes' if self.encrypt else 'no'}")
        if self.trust_server_certificate:
            parts.append("TrustServerCertificate=yes")
        parts.append("Application Name=Data Editor")
        return ";".join(parts) + ";"


@dataclass
class Column:
    name: str
    data_type: str
    nullable: bool
    is_identity: bool
    is_computed: bool
    is_primary_key: bool

    @property
    def editable(self) -> bool:
        return not (self.is_identity or self.is_computed or self.data_type in READONLY_TYPES)


def available_drivers() -> list[str]:
    """SQL Server ODBC drivers installed on this machine, newest first."""
    drivers = [d for d in pyodbc.drivers() if "SQL Server" in d]
    modern = sorted((d for d in drivers if d.startswith("ODBC Driver")), reverse=True)
    return modern + [d for d in drivers if d not in modern]


def coerce(text: str | None, column: Column):
    """Convert text typed into a cell to a Python value suitable for the column.

    Raises ValueError with a friendly message when the text is not valid.
    """
    if text is None:
        return None
    t = column.data_type
    s = text.strip()
    try:
        if t in INT_TYPES:
            return int(s)
        if t in DECIMAL_TYPES:
            return Decimal(s)
        if t in FLOAT_TYPES:
            return float(s)
        if t == "bit":
            if s.lower() in ("1", "true", "yes", "y", "t"):
                return True
            if s.lower() in ("0", "false", "no", "n", "f"):
                return False
            raise ValueError
        if t in DATE_TYPES:
            return dt.date.fromisoformat(s)
        if t in DATETIME_TYPES:
            return dt.datetime.fromisoformat(s)
        if t in TIME_TYPES:
            return dt.time.fromisoformat(s)
    except (ValueError, InvalidOperation):
        raise ValueError(f"'{text}' is not a valid {t} value for column '{column.name}'.") from None
    return text


def format_value(value) -> str:
    """Render a database value as editable text."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, dt.datetime):
        if not value.microsecond:
            return value.isoformat(sep=" ", timespec="seconds")
        return value.isoformat(sep=" ", timespec="milliseconds" if value.microsecond % 1000 == 0 else "microseconds")
    if isinstance(value, (bytes, bytearray)):
        return "0x" + bytes(value).hex().upper()
    return str(value)


class Database:
    def __init__(self, info: ConnectionInfo):
        self.info = info
        self.conn = pyodbc.connect(info.connection_string(), autocommit=False, timeout=15)

    def close(self) -> None:
        try:
            self.conn.close()
        except pyodbc.Error:
            pass

    # ---- introspection -------------------------------------------------

    def databases(self) -> list[str]:
        cur = self.conn.cursor()
        cur.execute("SELECT name FROM sys.databases WHERE HAS_DBACCESS(name) = 1 ORDER BY name")
        return [r[0] for r in cur.fetchall()]

    def current_database(self) -> str:
        return self.conn.cursor().execute("SELECT DB_NAME()").fetchone()[0]

    def use_database(self, name: str) -> None:
        self.conn.cursor().execute(f"USE {quote_ident(name)}")
        self.conn.commit()

    def tables(self) -> list[tuple[str, str]]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_TYPE = 'BASE TABLE' ORDER BY TABLE_SCHEMA, TABLE_NAME"
        )
        return [(r[0], r[1]) for r in cur.fetchall()]

    def columns(self, schema: str, table: str) -> list[Column]:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT c.name, t.name, c.is_nullable, c.is_identity, c.is_computed,
                   CASE WHEN pk.column_id IS NULL THEN 0 ELSE 1 END
            FROM sys.columns c
            JOIN sys.types t ON t.user_type_id = c.user_type_id
            LEFT JOIN (
                SELECT ic.object_id, ic.column_id
                FROM sys.indexes i
                JOIN sys.index_columns ic
                  ON ic.object_id = i.object_id AND ic.index_id = i.index_id
                WHERE i.is_primary_key = 1
            ) pk ON pk.object_id = c.object_id AND pk.column_id = c.column_id
            WHERE c.object_id = OBJECT_ID(?)
            ORDER BY c.column_id
            """,
            f"{quote_ident(schema)}.{quote_ident(table)}",
        )
        return [
            Column(name, dtype.lower(), bool(nul), bool(ident), bool(comp), bool(pk))
            for name, dtype, nul, ident, comp, pk in cur.fetchall()
        ]

    # ---- data ------------------------------------------------------------

    def fetch_rows(
        self, schema: str, table: str, columns: list[Column], limit: int, where: str = ""
    ) -> list[list]:
        cols = ", ".join(quote_ident(c.name) for c in columns)
        sql = f"SELECT TOP ({int(limit)}) {cols} FROM {quote_ident(schema)}.{quote_ident(table)}"
        if where.strip():
            sql += f" WHERE {where}"
        pk = [quote_ident(c.name) for c in columns if c.is_primary_key]
        if pk:
            sql += " ORDER BY " + ", ".join(pk)
        cur = self.conn.cursor()
        cur.execute(sql)
        rows = [list(r) for r in cur.fetchall()]
        self.conn.commit()  # end the implicit read transaction so we don't hold locks
        return rows

    def apply_changes(
        self,
        schema: str,
        table: str,
        columns: list[Column],
        inserts: list[dict],
        updates: list[tuple[dict, dict]],
        deletes: list[dict],
    ) -> None:
        """Apply all changes in a single transaction; roll back on any error.

        inserts: {column: value} for each new row
        updates: (key values, changed values) pairs
        deletes: key values for each row to delete
        """
        target = f"{quote_ident(schema)}.{quote_ident(table)}"
        cur = self.conn.cursor()
        try:
            for keys in deletes:
                where, params = _where(keys)
                cur.execute(f"DELETE FROM {target} WHERE {where}", params)
                _expect_one(cur, "delete")
            for keys, changes in updates:
                sets = ", ".join(f"{quote_ident(c)} = ?" for c in changes)
                where, params = _where(keys)
                cur.execute(f"UPDATE {target} SET {sets} WHERE {where}", [*changes.values(), *params])
                _expect_one(cur, "update")
            for values in inserts:
                if values:
                    cols = ", ".join(quote_ident(c) for c in values)
                    marks = ", ".join("?" for _ in values)
                    cur.execute(f"INSERT INTO {target} ({cols}) VALUES ({marks})", list(values.values()))
                else:
                    cur.execute(f"INSERT INTO {target} DEFAULT VALUES")
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise


def _where(keys: dict) -> tuple[str, list]:
    clauses, params = [], []
    for col, val in keys.items():
        if val is None:
            clauses.append(f"{quote_ident(col)} IS NULL")
        else:
            clauses.append(f"{quote_ident(col)} = ?")
            params.append(val)
    return " AND ".join(clauses), params


def _expect_one(cur, action: str) -> None:
    if cur.rowcount != 1:
        raise RuntimeError(
            f"Expected to {action} 1 row but {cur.rowcount} were affected. "
            "The row may have been changed or removed by someone else. Refresh and try again."
        )
