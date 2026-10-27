from schemadoc.models import Column, ForeignKey, Index, Relationship, Schema, Table, UniqueConstraint
from schemadoc.report import build_report


def test_report_content(reader):
    rep = build_report(reader.read(["orders", "customers", "payments"]), "Shop")
    assert rep.title == "Shop"
    assert rep.subtitle == "Schema reference for 3 selected tables"
    assert dict((label, v) for v, label in rep.stats)["relationships"] == 2

    orders = next(s for s in rep.sections if s.name == "orders")
    cols = {c.name: c for c in orders.columns}
    assert cols["id"].keys == ["PK"]
    assert cols["customer_id"].keys == ["FK"]
    assert cols["customer_id"].ref.text == "customers.id" and cols["customer_id"].ref.documented
    # addresses wasn't selected, so the link is marked as not documented
    assert not cols["shipping_address_id"].ref.documented

    payments = next(s for s in rep.sections if s.name == "payments")
    assert {c.name: c.keys for c in payments.columns}["order_id"] == ["FK", "UQ"]


def test_fk_rules_and_external_targets():
    fk = ForeignKey("fk_addr_cust", ["customer_id"], "customers", ["id"], ref_schema="crm",
                    on_delete="CASCADE", on_update="RESTRICT")
    t = Table("addresses", columns=[Column("customer_id", "INTEGER", False, references="customers.id")],
              foreign_keys=[fk])
    rel = Relationship(None, "addresses", ["customer_id"], "addresses", ["customer_id"])
    rep = build_report(Schema("db", "postgresql", None, [t], [rel]))
    assert rep.relationships[0].cardinality == "Many to exactly one (on delete cascade / on update restrict)"
    assert rep.sections[0].foreign_key_count == 1
    assert not rep.sections[0].columns[0].ref.documented
    assert rep.title == "db schema" and rep.subtitle.endswith("1 selected table")


def test_indexes_are_merged_without_names():
    t = Table("t", columns=[Column("id", "INTEGER", False, primary_key=True), Column("a", "INTEGER", True)],
              primary_key=["id"],
              indexes=[Index("ix_a", ["a"], False), Index("ux_a", ["a"], True), Index("pk_ix", ["id"], True)],
              unique_constraints=[UniqueConstraint("uq_a", ["a"])])
    section = build_report(Schema("db", "sqlite", None, [t], [])).sections[0]
    assert [(ix.columns, ix.unique) for ix in section.indexes] == [(["a"], True)]
    assert not section.has_defaults
