"""Self-contained HTML report: one file, no internet needed to view it."""
from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Optional

from . import APP_NAME, __version__
from .canvas import erd_svg
from .erd import layout_erd
from .models import Schema
from .report import Ref, Section, build_report

CSS = """
:root{
  --paper:#fbfcfd; --panel:#ffffff; --ink:#1d2b3a; --muted:#5f6f82; --line:#dde4ec;
  --head:#0f766e; --pk:#0f766e; --fk:#b45309; --uq:#6d28d9; --hover:#e9edf1;
  --mono: ui-monospace, "SF Mono", "Cascadia Code", Consolas, "Liberation Mono", monospace;
  --sans: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}
@media (prefers-color-scheme: dark){
  :root{ --paper:#0f1720; --panel:#16212d; --ink:#e3eaf2; --muted:#93a3b5; --line:#2a3847;
         --head:#2dd4bf; --pk:#34d3bf; --fk:#f5a54a; --uq:#b69cf7; --hover:#1d2b3a; }
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 var(--sans)}
a{color:inherit}
header{padding:48px 24px 28px;border-bottom:1px solid var(--line);background:var(--panel)}
.wrap{max-width:1180px;margin:0 auto;padding:0 24px}
header .wrap{padding:0}
h1{font-size:34px;line-height:1.15;margin:0 0 6px;letter-spacing:-.01em}
h1 small{display:block;font-size:15px;font-weight:500;color:var(--muted);margin-top:8px;letter-spacing:0}
.meta{color:var(--muted);font-size:13.5px;display:flex;flex-wrap:wrap;gap:4px 20px;margin-top:14px}
.meta b{color:var(--ink);font-weight:600}
.stats{display:flex;gap:32px;margin-top:22px;flex-wrap:wrap}
.stats div{font-size:13px;color:var(--muted)}
.stats strong{display:block;font-size:26px;color:var(--head);font-weight:650;line-height:1.1}
h2{font-size:21px;margin:44px 0 14px}
section{scroll-margin-top:16px}
.erd-bar{display:flex;gap:8px;align-items:center;margin-bottom:10px;flex-wrap:wrap}
.erd-bar .hint{color:var(--muted);font-size:13px;margin-right:auto}
button{font:inherit;font-size:13px;padding:6px 12px;border-radius:6px;border:1px solid var(--line);
  background:var(--panel);color:var(--ink);cursor:pointer}
button:hover{background:var(--hover)}
button:focus-visible,a:focus-visible,input:focus-visible{outline:2px solid var(--head);outline-offset:2px}
.erd{border:1px solid var(--line);border-radius:8px;overflow:auto;background:#fff;max-height:78vh}
.erd svg{display:block;transform-origin:0 0}
.legend{display:flex;gap:22px;color:var(--muted);font-size:12.5px;margin-top:10px;flex-wrap:wrap}
.legend svg{vertical-align:middle;margin-right:6px}
.scroll{overflow-x:auto;border:1px solid var(--line);border-radius:8px;background:var(--panel)}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{text-align:left;padding:8px 12px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:12.5px;font-weight:600;color:var(--muted);background:var(--paper);white-space:nowrap}
tr:last-child td{border-bottom:0}
tbody tr:hover td{background:var(--hover)}
code,.id{font-family:var(--mono);font-size:13px}
.type{font-family:var(--mono);font-size:13px;color:var(--muted)}
.k{display:inline-block;font-size:11px;font-weight:700;padding:1px 6px;border-radius:4px;margin-right:4px;
   border:1px solid currentColor}
.k.pk{color:var(--pk)} .k.fk{color:var(--fk)} .k.uq{color:var(--uq)}
.nn{color:var(--muted)}
.toc{display:flex;flex-wrap:wrap;gap:8px}
.toc a{font-family:var(--mono);font-size:13px;text-decoration:none;padding:5px 10px;border:1px solid var(--line);
  border-radius:6px;background:var(--panel)}
.toc a:hover{border-color:var(--head)}
.filter{width:100%;max-width:360px;padding:8px 12px;border-radius:6px;border:1px solid var(--line);
  background:var(--panel);color:var(--ink);font:inherit;margin-bottom:12px}
.tbl{margin-top:36px;padding-top:4px}
.tbl h3{font-family:var(--mono);font-size:19px;margin:0 0 4px;display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}
.tbl h3 a.top{font-family:var(--sans);font-size:12.5px;font-weight:400;color:var(--muted);margin-left:auto}
.tbl p.comment{margin:0 0 10px;color:var(--muted)}
.tbl h4{font-size:13.5px;margin:18px 0 8px;color:var(--muted);font-weight:600}
.none{color:var(--muted);font-size:13.5px;margin:0}
.ext{color:var(--muted);font-size:12px}
.out{color:var(--muted)}
.ix{display:flex;flex-wrap:wrap;gap:6px}
.ix span{border:1px solid var(--line);border-radius:6px;padding:3px 8px;background:var(--panel)}
footer{color:var(--muted);font-size:12.5px;padding:40px 24px 48px;text-align:center}
@media (max-width:640px){ h1{font-size:26px} header{padding:32px 16px 20px} .wrap{padding:0 16px} }
@media print{ .erd-bar,.filter{display:none} .erd{max-height:none;overflow:visible} .tbl{break-inside:avoid-page} }
"""

JS = """
(function(){
  var svg = document.querySelector('.erd svg'), scale = 1;
  var w = svg ? svg.width.baseVal.value : 0, h = svg ? svg.height.baseVal.value : 0;
  function apply(){ if(!svg) return; svg.setAttribute('width', w*scale); svg.setAttribute('height', h*scale);
    document.getElementById('zoomval').textContent = Math.round(scale*100) + '%'; }
  function fit(){ var box = document.querySelector('.erd'); scale = Math.min(1, (box.clientWidth-2)/w); apply(); }
  document.getElementById('zin').onclick = function(){ scale = Math.min(3, scale*1.2); apply(); };
  document.getElementById('zout').onclick = function(){ scale = Math.max(0.15, scale/1.2); apply(); };
  document.getElementById('zfit').onclick = fit;
  document.getElementById('dl').onclick = function(){
    var clone = svg.cloneNode(true); clone.setAttribute('width', w); clone.setAttribute('height', h);
    var blob = new Blob([new XMLSerializer().serializeToString(clone)], {type:'image/svg+xml'});
    var a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'erd.svg';
    document.body.appendChild(a); a.click(); a.remove(); };
  if (svg) fit();
  var f = document.getElementById('filter');
  if (f) f.oninput = function(){ var q = f.value.toLowerCase();
    document.querySelectorAll('.tbl').forEach(function(s){ s.hidden = q && s.dataset.name.indexOf(q) < 0; });
    document.querySelectorAll('.toc a').forEach(function(a){ a.hidden = q && a.dataset.name.indexOf(q) < 0; }); };
})();
"""

LEGEND = """
<div class="legend" aria-label="Diagram legend">
  <span><svg width="44" height="14"><line x1="0" y1="7" x2="44" y2="7" stroke="#52667d" stroke-width="1.2"/>
    <line x1="36" y1="1" x2="36" y2="13" stroke="#52667d" stroke-width="1.2"/>
    <line x1="31" y1="1" x2="31" y2="13" stroke="#52667d" stroke-width="1.2"/></svg>exactly one</span>
  <span><svg width="44" height="14"><line x1="0" y1="7" x2="44" y2="7" stroke="#52667d" stroke-width="1.2"/>
    <line x1="36" y1="1" x2="36" y2="13" stroke="#52667d" stroke-width="1.2"/>
    <circle cx="27" cy="7" r="4" fill="#fff" stroke="#52667d" stroke-width="1.2"/></svg>zero or one</span>
  <span><svg width="44" height="14"><line x1="0" y1="7" x2="44" y2="7" stroke="#52667d" stroke-width="1.2"/>
    <line x1="32" y1="7" x2="44" y2="1" stroke="#52667d" stroke-width="1.2"/>
    <line x1="32" y1="7" x2="44" y2="13" stroke="#52667d" stroke-width="1.2"/>
    <line x1="28" y1="1" x2="28" y2="13" stroke="#52667d" stroke-width="1.2"/></svg>many</span>
  <span><b style="color:#0f766e">PK</b> primary key &nbsp; <b style="color:#b45309">FK</b> foreign key</span>
  <span>Lines are coloured by the table they point to.</span>
</div>
"""


def _e(value) -> str:
    return escape("" if value is None else str(value))


def _cols(cols) -> str:
    return ", ".join(f"<code>{_e(c)}</code>" for c in cols)


def _ref(ref: Ref) -> str:
    if ref.documented:
        return f'<a href="#{ref.anchor}"><code>{_e(ref.text)}</code></a>'
    return f'<code class="out" title="Table not included in this document">{_e(ref.text)}</code>'


def _grid(head: list[str], rows: list[list[str]]) -> str:
    th = "".join(f"<th>{h}</th>" for h in head)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f"<div class='scroll'><table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>"


def _section(s: Section) -> str:
    head = ["#", "Column", "Type", "Nullable"] + (["Default"] if s.has_defaults else []) +            ["Keys", "References"] + (["Comment"] if s.has_comments else [])
    rows = []
    for c in s.columns:
        row = [f"<span class='nn'>{c.position}</span>",
               f"<span class='id'>{_e(c.name)}</span>",
               f"<span class='type'>{_e(c.data_type)}</span>" + (" <span class='ext'>auto</span>" if c.autoincrement else ""),
               "Yes" if c.nullable else "<span class='nn'>No</span>"]
        if s.has_defaults:
            row.append(f"<span class='type'>{_e(c.default)}</span>" if c.default is not None else "")
        row += ["".join(f'<span class="k {k.lower()}">{k}</span>' for k in c.keys),
                _ref(c.ref) if c.ref else ""]
        rows.append(row + ([_e(c.comment)] if s.has_comments else []))

    if s.indexes:
        unique = ' <span class="k uq">unique</span>'
        ixs = "<div class='ix'>" + "".join(
            f"<span>{_cols(ix.columns)}{unique if ix.unique else ''}</span>" for ix in s.indexes) + "</div>"
    else:
        ixs = "<p class='none'>None.</p>"

    comment = f"<p class='comment'>{_e(s.comment)}</p>" if s.comment else ""
    pk = "" if s.primary_key else " <span class='ext'>no primary key</span>"
    return (
        f"<section class='tbl' id='{s.anchor}' data-name='{_e(s.name.lower())}'>"
        f"<h3>{_e(s.name)} <span class='ext'>{len(s.columns)} columns</span>{pk}"
        f"<a class='top' href='#tables'>Back to table list</a></h3>{comment}"
        f"{_grid(head, rows)}<h4>Indexes</h4>{ixs}</section>"
    )


def render_html(schema: Schema, path: str | Path, title: Optional[str] = None) -> Path:
    path = Path(path)
    rep = build_report(schema, title)
    svg = erd_svg(layout_erd(schema), link_tables=True)

    meta = "".join(f"<span>{_e(k)} <b>{_e(v)}</b></span>" for k, v in rep.meta)
    stats = "".join(f"<div><strong>{v}</strong>{_e(label)}</div>" for v, label in rep.stats)
    rels = _grid(["Table (foreign key)", "Refers to", "Cardinality"],
                 [[f"{_ref(r.child)} ({_cols(r.child_columns)})", f"{_ref(r.parent)} ({_cols(r.parent_columns)})",
                   _e(r.cardinality)] for r in rep.relationships]
                 ) if rep.relationships else "<p class='none'>None of the selected tables reference each other.</p>"
    toc = "".join(f"<a href='#{s.anchor}' data-name='{_e(s.name.lower())}'>{_e(s.name)}</a>" for s in rep.sections)
    sections = "".join(_section(s) for s in rep.sections)

    doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(rep.title)}</title><style>{CSS}</style></head>
<body>
<header><div class="wrap">
  <h1>{_e(rep.title)}<small>{_e(rep.subtitle)}</small></h1>
  <div class="meta">{meta}</div>
  <div class="stats">{stats}</div>
</div></header>
<main class="wrap">
  <section id="erd"><h2>Entity relationship diagram</h2>
    <div class="erd-bar"><span class="hint">Click a table name to jump to its details.</span>
      <button id="zout" aria-label="Zoom out">−</button><span id="zoomval" class="ext">100%</span>
      <button id="zin" aria-label="Zoom in">+</button><button id="zfit">Fit</button>
      <button id="dl">Download SVG</button></div>
    <div class="erd">{svg}</div>{LEGEND}
  </section>
  <section id="relationships"><h2>Relationships</h2>{rels}</section>
  <section id="tables"><h2>Tables</h2>
    <input id="filter" class="filter" type="search" placeholder="Filter tables" aria-label="Filter tables">
    <nav class="toc">{toc}</nav>{sections}
  </section>
</main>
<footer>Generated by {APP_NAME} {__version__}</footer>
<script>{JS}</script>
</body></html>"""
    path.write_text(doc, encoding="utf-8")
    return path
