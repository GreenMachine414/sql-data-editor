"""Plain data structures describing a documented schema.

Everything the renderers need lives here, so the HTML/PDF/ERD code never
touches SQLAlchemy directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Column:
    name: str
    data_type: str
    nullable: bool
    default: Optional[str] = None
    primary_key: bool = False
    unique: bool = False
    autoincrement: bool = False
    comment: Optional[str] = None
    # "table.column" this column points to, if it is part of a foreign key
    references: Optional[str] = None

    @property
    def foreign_key(self) -> bool:
        return self.references is not None


@dataclass
class ForeignKey:
    name: Optional[str]
    columns: list[str]
    ref_table: str
    ref_columns: list[str]
    ref_schema: Optional[str] = None
    on_delete: Optional[str] = None
    on_update: Optional[str] = None


@dataclass
class Index:
    name: str
    columns: list[str]
    unique: bool


@dataclass
class UniqueConstraint:
    name: Optional[str]
    columns: list[str]


@dataclass
class Table:
    name: str
    schema: Optional[str] = None
    columns: list[Column] = field(default_factory=list)
    primary_key: list[str] = field(default_factory=list)
    primary_key_name: Optional[str] = None
    foreign_keys: list[ForeignKey] = field(default_factory=list)
    indexes: list[Index] = field(default_factory=list)
    unique_constraints: list[UniqueConstraint] = field(default_factory=list)
    comment: Optional[str] = None

    def column(self, name: str) -> Optional[Column]:
        for c in self.columns:
            if c.name == name:
                return c
        return None

    @property
    def anchor(self) -> str:
        """A safe id for links inside the HTML report."""
        raw = f"{self.schema}-{self.name}" if self.schema else self.name
        return "t-" + "".join(ch if ch.isalnum() else "-" for ch in raw)


@dataclass
class Relationship:
    name: Optional[str]
    child_table: str
    child_columns: list[str]
    parent_table: str
    parent_columns: list[str]
    one_to_one: bool = False   # child side is unique -> "one" instead of "many"
    optional: bool = False     # FK columns nullable -> parent is "zero or one"

    @property
    def cardinality(self) -> str:
        child = "One" if self.one_to_one else "Many"
        parent = "zero or one" if self.optional else "exactly one"
        return f"{child} to {parent}"


@dataclass
class Schema:
    database: str
    dialect: str
    schema_name: Optional[str]
    tables: list[Table]
    relationships: list[Relationship]
    server_version: Optional[str] = None
    generated_at: datetime = field(default_factory=datetime.now)

    def table(self, name: str) -> Optional[Table]:
        for t in self.tables:
            if t.name == name:
                return t
        return None
