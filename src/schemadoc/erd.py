"""Lay out an entity-relationship diagram without any external tools.

The layout is renderer-neutral: it produces boxes, rows and orthogonal edge
paths in a top-left-origin coordinate space. `draw_erd` then paints them onto
any `Canvas` (SVG for HTML, ReportLab for PDF), so both outputs match.

Layout approach, kept deliberately simple:
  1. Tables go on a grid. Related tables are placed close together by
     ordering them breadth-first, then improving positions with swaps that
     shorten the total distance between connected tables.
  2. Edges run only through the empty channels between grid rows and
     columns, so lines never cross over a table box. Each line gets its own
     lane, and a channel widens when it has to carry many lines.
  3. Crow's-foot notation marks cardinality at each end, and lines are
     coloured by the table they point to so they're easy to follow.

Big tables only show the columns that matter for the diagram (keys and
columns used by a drawn relationship); the table details list every column.
"""
from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Optional, Protocol

from reportlab.pdfbase.pdfmetrics import stringWidth

from .models import Relationship, Schema, Table

# ---- geometry constants (points / px; 1:1 in both renderers) -------------
FONT = "Helvetica"
FONT_BOLD = "Helvetica-Bold"
TITLE_SIZE = 11
ROW_SIZE = 9
HEADER_H = 26
ROW_H = 18
PAD = 10
BADGE_W = 22
MIN_BOX_W = 170
MAX_BOX_W = 380
SMALL_TABLE = 12  # bigger tables show only key / linked columns, then "+ N more columns"
MIN_ROWS = 4      # ...topped up to this many rows when they have hardly any keys
COL_GAP = 96
ROW_GAP = 56
MARGIN = 40
LANE_STEP = 8
LANE_PAD = 14     # space between a channel's outermost lane and the tables beside it

THEME = {
    "paper": "#ffffff",
    "ink": "#1d2b3a",
    "muted": "#5f6f82",
    "box_border": "#9fb0c3",
    "header": "#0f766e",
    "header_text": "#ffffff",
    "row_alt": "#f3f6f9",
    "pk": "#0f766e",
    "fk": "#b45309",
    "edge": "#52667d",
}
# Line colours, one per referenced table (repeats after the last one).
EDGE_COLORS = ["#2563eb", "#c2410c", "#0f766e", "#7c3aed", "#be123c",
               "#4d7c0f", "#0369a1", "#a16207", "#9d174d", "#475569"]


def _w(text: str, size: float, bold: bool = False) -> float:
    return stringWidth(text, FONT_BOLD if bold else FONT, size)


def _truncate(text: str, size: float, max_w: float, bold: bool = False) -> str:
    if _w(text, size, bold) <= max_w:
        return text
    while text and _w(text + "…", size, bold) > max_w:
        text = text[:-1]
    return text + "…"


@dataclass
class Row:
    name: str
    type: str
    pk: bool
    fk: bool
    note: bool = False  # the "+ N more columns" line
    y: float = 0.0  # vertical centre, set during layout


@dataclass
class Box:
    table: Table
    w: float
    h: float
    rows: list[Row]
    x: float = 0.0
    y: float = 0.0
    col: int = 0
    row: int = 0

    def row_y(self, column: str) -> float:
        for r in self.rows:
            if r.name == column:
                return r.y
        return self.y + HEADER_H / 2


@dataclass
class Edge:
    rel: Relationship
    points: list[tuple[float, float]]
    start_dir: int   # +1 means the line leaves the child box heading right
    end_dir: int     # +1 means the line enters the parent box heading right
    color: str = THEME["edge"]


@dataclass
class Layout:
    width: float
    height: float
    boxes: list[Box] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    # y positions between grid rows where the diagram can be cut into pages
    # without slicing a table or a horizontal line
    breaks: list[float] = field(default_factory=list)


# ---------------------------------------------------------------- sizing
def _make_box(t: Table, linked: frozenset[str] = frozenset()) -> Box:
    """`linked` names the columns that a drawn relationship attaches to."""
    rows = [Row(c.name, c.data_type, c.primary_key, c.foreign_key) for c in t.columns]
    if len(rows) > SMALL_TABLE:
        # primary key, then linked columns (lines attach to them), each in table order
        keep = [i for i, r in enumerate(rows) if r.pk]
        keep += [i for i, r in enumerate(rows) if r.name in linked and not r.pk]
        keep += [i for i in range(len(rows)) if i not in keep][:max(0, MIN_ROWS - len(keep))]
        hidden = len(rows) - len(keep)
        rows = [rows[i] for i in keep]
        rows.append(Row(f"+ {hidden} more columns", "", False, False, note=True))
    title_w = _w(t.name, TITLE_SIZE, True) + 2 * PAD
    name_w = max([_w(r.name, ROW_SIZE, r.pk) for r in rows] or [0])
    type_w = max([_w(r.type, ROW_SIZE) for r in rows] or [0])
    body_w = PAD + BADGE_W + name_w + 18 + type_w + PAD
    w = min(MAX_BOX_W, max(MIN_BOX_W, title_w, body_w))
    h = HEADER_H + max(1, len(rows)) * ROW_H + 4
    return Box(t, math.ceil(w), h, rows)


# ---------------------------------------------------------------- placement
def _order(names: list[str], adj: dict[str, set[str]]) -> list[str]:
    seen: set[str] = set()
    order: list[str] = []
    by_degree = sorted(names, key=lambda n: (-len(adj[n]), n.lower()))
    for start in by_degree:
        if start in seen:
            continue
        queue = deque([start])
        seen.add(start)
        while queue:
            n = queue.popleft()
            order.append(n)
            for m in sorted(adj[n], key=lambda k: (-len(adj[k]), k.lower())):
                if m not in seen:
                    seen.add(m)
                    queue.append(m)
    return order


def _improve(cells: dict[str, tuple[int, int]], adj: dict[str, set[str]], slots: list[tuple[int, int]]):
    """Greedy swaps (including into empty slots) that reduce edge length."""
    def cost(name, pos):
        return sum(abs(pos[0] - cells[m][0]) + abs(pos[1] - cells[m][1]) for m in adj[name] if m != name)

    for _ in range(6):
        improved = False
        occupied = {pos: n for n, pos in cells.items()}
        names = list(cells)
        for a in names:
            for slot in slots:
                pa = cells[a]
                if slot == pa:
                    continue
                b = occupied.get(slot)
                before = cost(a, pa) + (cost(b, slot) if b else 0)
                cells[a] = slot
                if b:
                    cells[b] = pa
                after = cost(a, slot) + (cost(b, pa) if b else 0)
                if after < before:
                    occupied[slot] = a
                    if b:
                        occupied[pa] = b
                    else:
                        occupied.pop(pa, None)
                    improved = True
                else:
                    cells[a] = pa
                    if b:
                        cells[b] = slot
        if not improved:
            break


def _pick_columns(boxes: list[Box], aspect: float, max_width: Optional[float]) -> int:
    """Choose the grid width.

    With `max_width`: the most columns that fit that width.
    Otherwise: the shape closest to `aspect` (width / height). Rows are as tall
    as their tallest table, so heights come from the taller tables.
    """
    n = len(boxes)
    avg_w = sum(b.w for b in boxes) / n
    heights = sorted(b.h for b in boxes)
    tall_h = heights[int(n * 0.75)] if n > 1 else heights[0]

    def width(cols: int) -> float:
        return 2 * MARGIN + cols * avg_w + (cols - 1) * COL_GAP

    if max_width is not None:
        return max([c for c in range(1, n + 1) if width(c) <= max_width], default=1)

    def shape(cols: int) -> float:
        rows = math.ceil(n / cols)
        return width(cols) / (2 * MARGIN + rows * tall_h + (rows - 1) * ROW_GAP)

    return min(range(1, n + 1), key=lambda c: abs(math.log(shape(c) / aspect)))


def _route(schema: Schema, boxes: dict[str, Box], vchan: list[float], hchan: list[float],
           vroom: list[float], hroom: list[float]) -> tuple[list[Edge], dict[tuple[str, int], int]]:
    """Route every relationship through the channels; returns the edges and lanes used per channel.

    vchan[i] is the centre of the vertical channel left of column i, hchan[i] of the
    horizontal channel above row i; vroom / hroom say how far a lane may sit from that centre.
    """
    lanes: dict[tuple[str, int], int] = defaultdict(int)
    shared: dict[tuple, float] = {}

    def lane(kind: str, idx: int, share=None) -> float:
        """A free lane in a channel. Lines heading for the same point pass `share`
        to run along one common trunk instead of side by side."""
        if share is not None and (kind, idx, share) in shared:
            return shared[(kind, idx, share)]
        k = lanes[(kind, idx)]
        lanes[(kind, idx)] += 1
        base, room = (vchan[idx], vroom[idx]) if kind == "v" else (hchan[idx], hroom[idx])
        off = ((k + 1) // 2) * LANE_STEP * (1 if k % 2 else -1)
        pos = base + max(-room, min(room, off))
        if share is not None:
            shared[(kind, idx, share)] = pos
        return pos

    parents = sorted({r.parent_table for r in schema.relationships}, key=str.lower)
    colors = {p: EDGE_COLORS[i % len(EDGE_COLORS)] for i, p in enumerate(parents)}

    edges: list[Edge] = []
    for rel in schema.relationships:
        child, parent = boxes[rel.child_table], boxes[rel.parent_table]
        sy = child.row_y(rel.child_columns[0]) if rel.child_columns else child.y + HEADER_H / 2
        ey = parent.row_y(rel.parent_columns[0]) if rel.parent_columns else parent.y + HEADER_H / 2

        if parent.col > child.col:
            sdir, edir = 1, 1
            sv, ev = child.col + 1, parent.col
        elif parent.col < child.col:
            sdir, edir = -1, -1
            sv, ev = child.col, parent.col + 1
        else:  # same column (or self-reference): loop out the right side
            sdir, edir = 1, -1
            sv = ev = child.col + 1

        sx = child.x + child.w if sdir == 1 else child.x
        ex = parent.x if edir == 1 else parent.x + parent.w

        target = (rel.parent_table, round(ex), round(ey))  # where the line ends
        if sv == ev:
            if child is parent and abs(sy - ey) < 1:
                ey += ROW_H / 2  # degenerate self-loop on one column
            x1 = lane("v", sv, target if child is not parent else None)
            pts = [(sx, sy), (x1, sy), (x1, ey), (ex, ey)]
        else:
            x1 = lane("v", sv)
            x2 = lane("v", ev, target)
            candidates = {child.row, child.row + 1, parent.row, parent.row + 1}
            hi = min(candidates, key=lambda k: (abs(hchan[k] - sy) + abs(hchan[k] - ey), k))
            yk = lane("h", hi, target)
            pts = [(sx, sy), (x1, sy), (x1, yk), (x2, yk), (x2, ey), (ex, ey)]
        edges.append(Edge(rel, pts, sdir, edir, colors[rel.parent_table]))
    return edges, lanes


def layout_erd(schema: Schema, aspect: float = 1.6, max_width: Optional[float] = None,
               columns: Optional[int] = None) -> Layout:
    """Lay out the diagram on a grid `columns` tables wide. Without `columns`, aim
    for roughly `aspect` (width / height), or for the most columns that fit
    `max_width` when that is given."""
    linked: dict[str, set[str]] = defaultdict(set)
    for r in schema.relationships:
        linked[r.child_table].update(r.child_columns)
        linked[r.parent_table].update(r.parent_columns)
    boxes = {t.name: _make_box(t, frozenset(linked[t.name])) for t in schema.tables}
    if not boxes:
        return Layout(MARGIN * 2, MARGIN * 2)

    adj: dict[str, set[str]] = defaultdict(set)
    for name in boxes:
        adj[name]
    for r in schema.relationships:
        adj[r.child_table].add(r.parent_table)
        adj[r.parent_table].add(r.child_table)

    n = len(boxes)
    ncols = min(columns, n) if columns else _pick_columns(list(boxes.values()), aspect, max_width)
    nrows = math.ceil(n / ncols)
    slots = [(c, r) for r in range(nrows) for c in range(ncols)]
    order = _order(list(boxes), adj)
    cells = {name: slots[i] for i, name in enumerate(order)}
    _improve(cells, adj, slots)

    # compact away empty columns / rows left by the swaps
    used_cols = sorted({c for c, _ in cells.values()})
    used_rows = sorted({r for _, r in cells.values()})
    cmap = {c: i for i, c in enumerate(used_cols)}
    rmap = {r: i for i, r in enumerate(used_rows)}
    ncols, nrows = len(used_cols), len(used_rows)

    col_w = [0.0] * ncols
    row_h = [0.0] * nrows
    for name, (c, r) in cells.items():
        b = boxes[name]
        b.col, b.row = cmap[c], rmap[r]
        col_w[b.col] = max(col_w[b.col], b.w)
        row_h[b.row] = max(row_h[b.row], b.h)

    # Channel widths: vgap[i] is left of column i (vgap[-1] is the right margin) and
    # hgap[i] is above row i. They start at the defaults and widen until every line
    # in a channel has its own lane; moving things can change the routes, so repeat.
    vgap = [MARGIN] + [COL_GAP] * (ncols - 1) + [MARGIN]
    hgap = [MARGIN] + [ROW_GAP] * (nrows - 1) + [MARGIN]
    for _ in range(4):
        col_x = [sum(vgap[:i + 1]) + sum(col_w[:i]) for i in range(ncols)]
        row_y = [sum(hgap[:i + 1]) + sum(row_h[:i]) for i in range(nrows)]
        for b in boxes.values():
            b.x, b.y = col_x[b.col], row_y[b.row]
            for i, row in enumerate(b.rows):
                row.y = b.y + HEADER_H + i * ROW_H + ROW_H / 2
        vchan = [col_x[i] - vgap[i] / 2 for i in range(ncols)] + [col_x[-1] + col_w[-1] + vgap[-1] / 2]
        hchan = [row_y[i] - hgap[i] / 2 for i in range(nrows)] + [row_y[-1] + row_h[-1] + hgap[-1] / 2]
        edges, lanes = _route(schema, boxes, vchan, hchan,
                              [g / 2 - LANE_PAD for g in vgap], [g / 2 - LANE_PAD for g in hgap])

        def needed(kind: str, i: int, default: float) -> float:
            return max(default, (lanes[(kind, i)] - 1) * LANE_STEP + 2 * LANE_PAD)

        new_v = [max(g, needed("v", i, g)) for i, g in enumerate(vgap)]
        new_h = [max(g, needed("h", i, g)) for i, g in enumerate(hgap)]
        if new_v == vgap and new_h == hgap:
            break
        vgap, hgap = new_v, new_h

    width = col_x[-1] + col_w[-1] + vgap[-1]
    height = row_y[-1] + row_h[-1] + hgap[-1]
    # just above each row after the first: below every horizontal lane (see LANE_PAD)
    breaks = [y - 4 for y in row_y[1:]]
    return Layout(width, height, list(boxes.values()), edges, breaks)


# ---------------------------------------------------------------- drawing
class Canvas(Protocol):
    def rect(self, x, y, w, h, fill=None, stroke=None, radius=0, stroke_width=1): ...
    def line(self, x1, y1, x2, y2, stroke, width=1): ...
    def polyline(self, points, stroke, width=1): ...
    def circle(self, cx, cy, r, fill, stroke, width=1): ...
    def text(self, x, y, s, size, color, bold=False, anchor="start", link: Optional[str] = None): ...


def _markers(cv: Canvas, x: float, y: float, direction: int, many: bool, optional: bool, color: str):
    """Crow's-foot marker at a box edge. `direction` points *into* the box."""
    d = -direction  # points away from the box, back along the line
    if many:
        foot = 12
        cv.line(x + d * foot, y, x, y - 6, color, 1.2)
        cv.line(x + d * foot, y, x, y + 6, color, 1.2)
        cv.line(x + d * 16, y - 6, x + d * 16, y + 6, color, 1.2)
    else:
        cv.line(x + d * 8, y - 6, x + d * 8, y + 6, color, 1.2)
        if optional:
            cv.circle(x + d * 17, y, 4, THEME["paper"], color, 1.2)
        else:
            cv.line(x + d * 13, y - 6, x + d * 13, y + 6, color, 1.2)


def draw_erd(cv: Canvas, lay: Layout, link_tables: bool = False):
    t = THEME
    cv.rect(0, 0, lay.width, lay.height, fill=t["paper"])

    for e in lay.edges:
        cv.polyline(e.points, e.color, 1.3)
    for e in lay.edges:
        (sx, sy), (ex, ey) = e.points[0], e.points[-1]
        # child end: many (or one for 1:1); parent end: one / zero-or-one
        _markers(cv, sx, sy, -e.start_dir, many=not e.rel.one_to_one, optional=False, color=e.color)
        _markers(cv, ex, ey, e.end_dir, many=False, optional=e.rel.optional, color=e.color)

    for b in lay.boxes:
        cv.rect(b.x, b.y, b.w, b.h, fill=t["paper"], stroke=t["box_border"], radius=5)
        cv.rect(b.x, b.y, b.w, HEADER_H, fill=t["header"], radius=5)
        cv.rect(b.x, b.y + HEADER_H - 6, b.w, 6, fill=t["header"])  # square off header bottom
        title = _truncate(b.table.name, TITLE_SIZE, b.w - 2 * PAD, True)
        cv.text(b.x + PAD, b.y + HEADER_H / 2 + 4, title, TITLE_SIZE, t["header_text"], bold=True,
                link=("#" + b.table.anchor) if link_tables else None)

        if not b.rows:
            cv.text(b.x + PAD, b.y + HEADER_H + ROW_H / 2 + 3, "(no columns)", ROW_SIZE, t["muted"])
        for i, r in enumerate(b.rows):
            top = b.y + HEADER_H + i * ROW_H
            if i % 2:
                cv.rect(b.x + 1, top, b.w - 2, ROW_H, fill=t["row_alt"])
            base = r.y + 3.2
            if r.pk:
                cv.text(b.x + PAD, base, "PK", 7, t["pk"], bold=True)
            elif r.fk:
                cv.text(b.x + PAD, base, "FK", 7, t["fk"], bold=True)
            type_w = min(_w(r.type, ROW_SIZE), b.w * 0.45)
            name_space = b.w - PAD - BADGE_W - type_w - 14 - PAD
            name = _truncate(r.name, ROW_SIZE, name_space, r.pk)
            cv.text(b.x + PAD + BADGE_W, base, name, ROW_SIZE, t["muted" if r.note else "ink"], bold=r.pk)
            rtype = _truncate(r.type, ROW_SIZE, b.w * 0.45)
            cv.text(b.x + b.w - PAD, base, rtype, ROW_SIZE, t["muted"], anchor="end")
        # redraw border on top of alternating row fills
        cv.rect(b.x, b.y, b.w, b.h, stroke=t["box_border"], radius=5)
