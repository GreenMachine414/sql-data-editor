"""One entry point used by both the GUI and the command line."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

from .introspect import SchemaReader
from .render_html import render_html
from .render_pdf import render_pdf

FORMATS = ("html", "pdf")


def generate(reader: SchemaReader, tables: Iterable[str], output: str | Path, fmt: str,
             schema: Optional[str] = None, title: Optional[str] = None) -> Path:
    fmt = fmt.lower()
    if fmt not in FORMATS:
        raise ValueError(f"Unknown format '{fmt}'. Use html or pdf.")
    tables = list(tables)
    if not tables:
        raise ValueError("Select at least one table to document.")
    output = Path(output)
    if output.suffix.lower() != f".{fmt}":
        output = output.with_suffix(f".{fmt}")
    output.parent.mkdir(parents=True, exist_ok=True)

    doc = reader.read(tables, schema=schema)
    if fmt == "html":
        return render_html(doc, output, title)
    return render_pdf(doc, output, title)
