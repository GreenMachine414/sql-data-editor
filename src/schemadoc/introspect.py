"""Read table structure from a live database using SQLAlchemy's inspector.

Works with any database SQLAlchemy supports (PostgreSQL, MySQL/MariaDB,
SQL Server, SQLite, Oracle, ...) as long as the driver is installed.
"""
from __future__ import annotations

import copy
from typing import Iterable, Optional

from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import URL

from .connection import normalize_url
from .models import Column, ForeignKey, Index, Relationship, Schema, Table, UniqueConstraint

# Schemas that belong to the database engine itself, hidden from the picker.
SYSTEM_SCHEMAS = {
    "information_schema", "pg_catalog", "pg_toast", "mysql", "performance_schema",
    "sys", "guest", "db_owner", "db_accessadmin", "db_securityadmin", "db_ddladmin",
    "db_backupoperator", "db_datareader", "db_datawriter", "db_denydatareader",
    "db_denydatawriter",
}


def _is_system_schema(name: str) -> bool:
    low = name.lower()
    return low in SYSTEM_SCHEMAS or low.startswith("pg_temp") or low.startswith("pg_toast")


CONNECT_TIMEOUT = 10  # seconds


def _timeout_args(url: URL) -> dict:
    """Driver-specific options so an unreachable server fails fast instead of hanging."""
    driver = url.get_driver_name()
    if driver in ("psycopg", "psycopg2", "pymysql"):
        return {"connect_timeout": CONNECT_TIMEOUT}
    if driver == "pyodbc":
        return {"timeout": CONNECT_TIMEOUT}
    return {}


class SchemaReader:
    """Holds one database connection for the lifetime of a session.

    `creator`, if given, opens the DBAPI connection itself (Data Editor passes one that
    reuses its ODBC connection string, so SQL Server documenting supports Windows sign-in).
    """

    def __init__(self, url: URL | str, creator=None):
        self.url = normalize_url(url)
        options = {"creator": creator} if creator else {"connect_args": _timeout_args(self.url)}
        self.engine = create_engine(self.url, pool_pre_ping=True, **options)
        # Connect now so bad credentials fail here, not later.
        with self.engine.connect():
            pass
        self.inspector = inspect(self.engine)

    # ---------------------------------------------------------------- listing
    @property
    def dialect(self) -> str:
        return self.engine.dialect.name

    @property
    def database_name(self) -> str:
        db = self.engine.url.database or ""
        if self.dialect == "sqlite":
            name = db.replace("\\", "/").rsplit("/", 1)[-1]
            return name.rsplit(".", 1)[0] if "." in name else (name or "SQLite database")
        return db

    @property
    def server_version(self) -> Optional[str]:
        info = getattr(self.engine.dialect, "server_version_info", None)
        return ".".join(str(p) for p in info) if info else None

    def default_schema(self) -> Optional[str]:
        return self.inspector.default_schema_name

    def list_schemas(self) -> list[str]:
        try:
            names = self.inspector.get_schema_names()
        except NotImplementedError:
            return []
        user = [n for n in names if not _is_system_schema(n)]
        default = self.default_schema()
        if default and default not in user:
            user.insert(0, default)
        return sorted(user, key=lambda n: (n != default, n.lower()))

    def list_tables(self, schema: Optional[str] = None) -> list[str]:
        return sorted(self.inspector.get_table_names(schema=schema), key=str.lower)

    # ---------------------------------------------------------------- reading
    def _type_name(self, sa_type) -> str:
        if getattr(sa_type, "collation", None):  # show NVARCHAR(50), not NVARCHAR(50) COLLATE ...
            sa_type = copy.copy(sa_type)
            sa_type.collation = None
        try:
            return sa_type.compile(dialect=self.engine.dialect)
        except Exception:
            try:
                return str(sa_type)
            except Exception:
                return type(sa_type).__name__

    def _multi(self, method: str, schema: Optional[str], names: list[str]) -> dict:
        """Run one batched inspector call, returning {table_name: result}.

        PostgreSQL and Oracle answer each call with a single query for all
        tables; other dialects loop internally, so results are identical.
        """
        try:
            found = getattr(self.inspector, method)(schema=schema, filter_names=names)
        except NotImplementedError:  # e.g. table comments on SQLite
            return {}
        return {name: value for (_, name), value in found.items()}

    def read(self, tables: Iterable[str], schema: Optional[str] = None) -> Schema:
        wanted = list(dict.fromkeys(tables))  # de-duplicate, keep order
        available = set(self.list_tables(schema))
        missing = [t for t in wanted if t not in available]
        if missing:
            raise ValueError("These tables were not found: " + ", ".join(missing))

        parts = {kind: self._multi(f"get_multi_{kind}", schema, wanted) for kind in
                 ("columns", "pk_constraint", "foreign_keys", "indexes", "unique_constraints", "table_comment")}
        docs = [self._build_table(t, schema, {k: v.get(t) for k, v in parts.items()}) for t in wanted]
        return Schema(
            database=self.database_name,
            dialect=self.dialect,
            schema_name=schema,
            tables=docs,
            relationships=find_relationships(docs, schema, self.default_schema()),
            server_version=self.server_version,
        )

    def _build_table(self, name: str, schema: Optional[str], raw: dict) -> Table:
        """Turn one table's reflected dictionaries into a Table."""
        table = Table(name=name, schema=schema, comment=(raw["table_comment"] or {}).get("text"))

        pk = raw["pk_constraint"] or {}
        table.primary_key = list(pk.get("constrained_columns") or [])
        table.primary_key_name = pk.get("name")

        for fk in raw["foreign_keys"] or []:
            opts = fk.get("options") or {}
            table.foreign_keys.append(ForeignKey(
                name=fk.get("name"),
                columns=list(fk.get("constrained_columns") or []),
                ref_table=fk.get("referred_table"),
                ref_columns=list(fk.get("referred_columns") or []),
                ref_schema=fk.get("referred_schema"),
                on_delete=opts.get("ondelete") or None,
                on_update=opts.get("onupdate") or None,
            ))

        for ix in raw["indexes"] or []:
            cols = [c for c in (ix.get("column_names") or []) if c]
            exprs = [e for e in (ix.get("expressions") or []) if e and e not in cols]
            table.indexes.append(Index(ix.get("name") or "(unnamed)", cols + exprs, bool(ix.get("unique"))))

        for uc in raw["unique_constraints"] or []:
            table.unique_constraints.append(UniqueConstraint(uc.get("name"), list(uc.get("column_names") or [])))

        single_unique = {tuple(ix.columns) for ix in table.indexes if ix.unique and len(ix.columns) == 1}
        single_unique |= {tuple(u.columns) for u in table.unique_constraints if len(u.columns) == 1}
        fk_targets = {col: f"{fk.ref_table}.{ref}" for fk in table.foreign_keys
                      for col, ref in zip(fk.columns, fk.ref_columns)}

        for col in raw["columns"] or []:
            cname = col["name"]
            default = col.get("default")
            table.columns.append(Column(
                name=cname,
                data_type=self._type_name(col["type"]),
                nullable=bool(col.get("nullable", True)) and cname not in table.primary_key,
                default=None if default is None else str(default),
                primary_key=cname in table.primary_key,
                unique=(cname,) in single_unique,
                autoincrement=col.get("autoincrement") is True,
                comment=col.get("comment"),
                references=fk_targets.get(cname),
            ))
        return table

    def close(self) -> None:
        self.engine.dispose()


def find_relationships(tables: list[Table], schema: Optional[str] = None,
                       default_schema: Optional[str] = None) -> list[Relationship]:
    """Relationships whose both ends are among the documented tables."""
    names = {t.name for t in tables}
    same_schema = {None, schema, default_schema}
    rels: list[Relationship] = []
    for t in tables:
        unique_sets = {frozenset(t.primary_key)} if t.primary_key else set()
        unique_sets |= {frozenset(ix.columns) for ix in t.indexes if ix.unique}
        unique_sets |= {frozenset(u.columns) for u in t.unique_constraints}
        for fk in t.foreign_keys:
            if fk.ref_table not in names or fk.ref_schema not in same_schema:
                continue
            cols = [t.column(c) for c in fk.columns]
            rels.append(Relationship(
                name=fk.name,
                child_table=t.name,
                child_columns=fk.columns,
                parent_table=fk.ref_table,
                parent_columns=fk.ref_columns,
                one_to_one=frozenset(fk.columns) in unique_sets,
                optional=any(c is not None and c.nullable for c in cols),
            ))
    return rels


def is_external_fk(fk: ForeignKey, schema: Schema) -> bool:
    """True when a foreign key points at a table that isn't in the document."""
    return schema.table(fk.ref_table) is None
