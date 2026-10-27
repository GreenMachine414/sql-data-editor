"""Decide what the report says, once, for every output format.

The HTML and PDF renderers only lay these values out; any wording, key
badge, rule text or link target is worked out here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .models import ForeignKey, Schema, Table


@dataclass
class Ref:
    """A pointer to another table, linkable when that table is in the report."""
    text: str
    anchor: Optional[str] = None  # None: the target table isn't documented

    @property
    def documented(self) -> bool:
        return self.anchor is not None


@dataclass
class ColumnRow:
    position: int
    name: str
    data_type: str
    autoincrement: bool
    nullable: bool
    default: Optional[str]
    keys: list[str]            # any of "PK", "FK", "UQ"
    ref: Optional[Ref]
    comment: Optional[str]


@dataclass
class IndexRow:
    columns: list[str]
    unique: bool


@dataclass
class RelRow:
    child: Ref
    child_columns: list[str]
    parent: Ref
    parent_columns: list[str]
    cardinality: str           # "Many to exactly one", plus any "on delete ..." rules


@dataclass
class Section:
    name: str
    anchor: str
    comment: Optional[str]
    columns: list[ColumnRow]
    has_defaults: bool
    has_comments: bool
    primary_key: list[str]
    foreign_key_count: int
    indexes: list[IndexRow]    # indexes and unique constraints, without names or duplicates


@dataclass
class Report:
    title: str
    subtitle: str
    meta: list[tuple[str, str]]
    stats: list[tuple[int, str]]
    relationships: list[RelRow]
    sections: list[Section] = field(default_factory=list)


def _table_ref(schema: Schema, name: str, prefix: Optional[str] = None, text: Optional[str] = None) -> Ref:
    target = schema.table(name)
    return Ref(text or (f"{prefix}.{name}" if prefix else name), target.anchor if target else None)


def _rules(fk: ForeignKey) -> str:
    parts = [f"on delete {fk.on_delete.lower()}" if fk.on_delete else "",
             f"on update {fk.on_update.lower()}" if fk.on_update else ""]
    return " / ".join(p for p in parts if p)


def _indexes(t: Table) -> list[IndexRow]:
    """Each distinct column set once (unique if any index on it is), skipping the primary key's own."""
    found: dict[tuple[str, ...], bool] = {}
    for cols, unique in [(ix.columns, ix.unique) for ix in t.indexes] +                         [(u.columns, True) for u in t.unique_constraints]:
        key = tuple(cols)
        if key and key != tuple(t.primary_key):
            found[key] = found.get(key, False) or unique
    return [IndexRow(list(cols), unique) for cols, unique in found.items()]


def _section(t: Table, schema: Schema) -> Section:
    columns = []
    for i, c in enumerate(t.columns, 1):
        keys = [k for k, on in (("PK", c.primary_key), ("FK", c.foreign_key),
                                ("UQ", c.unique and not c.primary_key)) if on]
        ref = _table_ref(schema, c.references.partition(".")[0], text=c.references) if c.references else None
        columns.append(ColumnRow(i, c.name, c.data_type, c.autoincrement, c.nullable, c.default,
                                 keys, ref, c.comment))
    return Section(t.name, t.anchor, t.comment, columns,
                   any(c.default is not None for c in t.columns), any(c.comment for c in t.columns),
                   t.primary_key, len(t.foreign_keys), _indexes(t))


def _rel_rules(schema: Schema, child: str, columns: list[str]) -> str:
    t = schema.table(child)
    fk = next((f for f in (t.foreign_keys if t else []) if f.columns == columns), None)
    return _rules(fk) if fk else ""


def build_report(schema: Schema, title: Optional[str] = None) -> Report:
    n = len(schema.tables)
    engine = f"{schema.dialect} {schema.server_version or ''}".strip()
    meta = [("Database", schema.database), ("Engine", engine)]
    if schema.schema_name:
        meta.append(("Schema", schema.schema_name))
    meta.append(("Generated", f"{schema.generated_at:%Y-%m-%d %H:%M}"))

    sections = [_section(t, schema) for t in schema.tables]
    stats = [(n, "tables"),
             (sum(len(t.columns) for t in schema.tables), "columns"),
             (len(schema.relationships), "relationships"),
             (sum(len(s.indexes) for s in sections), "indexes")]

    rels = []
    for r in schema.relationships:
        rules = _rel_rules(schema, r.child_table, r.child_columns)
        rels.append(RelRow(_table_ref(schema, r.child_table), r.child_columns,
                           _table_ref(schema, r.parent_table), r.parent_columns,
                           r.cardinality + (f" ({rules})" if rules else "")))

    return Report(
        title=title or f"{schema.database} schema",
        subtitle=f"Schema reference for {n} selected table{'s' if n != 1 else ''}",
        meta=meta,
        stats=stats,
        relationships=rels,
        sections=sections,
    )
