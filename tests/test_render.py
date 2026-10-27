from pypdf import PdfReader

from schemadoc.erd import layout_erd
from schemadoc.generate import generate

ALL = ["customers", "addresses", "categories", "products", "orders", "order_items", "payments", "audit_log"]


def test_html_report(reader, tmp_path):
    out = generate(reader, ALL, tmp_path / "doc", "html", title="Shop")
    html = out.read_text(encoding="utf-8")
    assert out.suffix == ".html"
    assert "<svg" in html and "Entity relationship diagram" in html
    for t in ALL:
        assert f"id='t-{t.replace('_', '-')}'" in html
    # indexes are listed by their columns; constraint and index names are left out
    assert "<code>customer_id</code>, <code>placed_at</code>" in html
    assert "ix_orders_customer_placed" not in html and "Constraint" not in html


def test_pdf_report(reader, tmp_path):
    out = generate(reader, ALL, tmp_path / "doc.pdf", "pdf", title="Shop")
    pdf = PdfReader(str(out))
    text = "".join(p.extract_text() for p in pdf.pages)
    assert len(pdf.pages) >= 3
    assert "order_items" in text and "(sku) unique" in text
    assert "ux_products_sku" not in text


def test_edges_avoid_boxes(reader):
    lay = layout_erd(reader.read(ALL))
    boxes = [(b.x, b.y, b.x + b.w, b.y + b.h) for b in lay.boxes]
    for e in lay.edges:
        pts = e.points
        # interior segments (not the stubs touching the boxes) must not pass through any box
        for (x1, y1), (x2, y2) in zip(pts[1:-1], pts[2:-1]):
            for bx1, by1, bx2, by2 in boxes:
                if x1 == x2:
                    hit = bx1 < x1 < bx2 and max(y1, y2) > by1 and min(y1, y2) < by2
                else:
                    hit = by1 < y1 < by2 and max(x1, x2) > bx1 and min(x1, x2) < bx2
                assert not hit, (e.rel, (x1, y1, x2, y2))


def test_layout_follows_requested_shape(reader):
    doc = reader.read(ALL)
    tall, wide = layout_erd(doc, aspect=0.75), layout_erd(doc, aspect=2.0)
    assert tall.width / tall.height < wide.width / wide.height


def test_pdf_pages_share_one_size(reader, tmp_path):
    out = generate(reader, ALL, tmp_path / "doc.pdf", "pdf")
    sizes = {tuple(round(float(v)) for v in p.mediabox[2:]) for p in PdfReader(str(out)).pages}
    assert sizes == {(612, 792)}


def test_big_tables_show_only_key_and_linked_columns():
    from schemadoc.erd import MIN_ROWS, SMALL_TABLE, _make_box
    from schemadoc.models import Column, Table
    cols = [Column(f"c{i}", "INTEGER", True) for i in range(100)]
    cols[0] = Column("id", "INTEGER", False, primary_key=True)
    cols[70] = Column("owner_id", "INTEGER", False, references="users.id")
    cols[80] = Column("other_id", "INTEGER", False, references="lookup.id")
    box = _make_box(Table("wide", columns=cols), frozenset({"owner_id"}))
    names = [r.name for r in box.rows]
    # primary key, the column a drawn line attaches to, topped up to MIN_ROWS, then the note
    assert names[:2] == ["id", "owner_id"] and len(box.rows) == MIN_ROWS + 1
    assert "other_id" not in names
    assert box.rows[-1].note and names[-1] == f"+ {100 - MIN_ROWS} more columns"

    small = _make_box(Table("small", columns=cols[:SMALL_TABLE]))
    assert len(small.rows) == SMALL_TABLE and not small.rows[-1].note


def test_lines_to_the_same_column_share_a_trunk(reader):
    lay = layout_erd(reader.read(ALL))
    by_target = {}
    for e in lay.edges:
        by_target.setdefault((e.rel.parent_table, e.points[-1]), []).append(e)
    for edges in by_target.values():
        assert len({e.color for e in edges}) == 1  # coloured by the table they point to


def test_big_diagrams_continue_on_more_pages(tmp_path):
    import sqlite3
    from schemadoc.introspect import SchemaReader
    from schemadoc.render_pdf import _page_bands
    db = tmp_path / "big.db"
    con = sqlite3.connect(db)
    for i in range(40):
        ref = f", parent_id INTEGER REFERENCES t{i - 1}(id)" if i else ""
        con.execute(f"CREATE TABLE t{i} (id INTEGER PRIMARY KEY{ref}, " +
                    ", ".join(f"c{j} TEXT" for j in range(10)) + ")")
    con.commit()
    con.close()
    r = SchemaReader(f"sqlite:///{db}")
    doc = r.read(r.list_tables())
    lay = layout_erd(doc, max_width=1000)
    bands = _page_bands(lay, 1200)
    assert len(bands) > 1
    assert bands[0][0] == 0 and bands[-1][1] == lay.height
    assert all(b - a <= 1200 for a, b in bands)
    assert all(prev[1] == nxt[0] for prev, nxt in zip(bands, bands[1:]))  # no gaps or overlaps

    out = generate(r, r.list_tables(), tmp_path / "big.pdf", "pdf")
    text = [p.extract_text() for p in PdfReader(str(out)).pages]
    assert any("Entity relationship diagram (page 2 of" in t for t in text)
    r.close()
