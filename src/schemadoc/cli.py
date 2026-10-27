"""Command-line interface, for scripting and CI.

    schemadoc --url sqlite:///shop.db --list
    schemadoc --url sqlite:///shop.db --tables customers,orders -o docs/shop.html
    schemadoc --url postgresql://me@localhost/app --schema public --all -o app.pdf
"""
from __future__ import annotations

import argparse
import sys

from . import __version__
from .generate import generate
from .introspect import SchemaReader


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="schemadoc", description="Document database tables as an ERD plus reference.")
    p.add_argument("--url", required=True, help="SQLAlchemy URL, e.g. postgresql://user:pass@host:5432/db")
    p.add_argument("--schema", help="Database schema (PostgreSQL / SQL Server). Defaults to the default schema.")
    p.add_argument("--list", action="store_true", help="List tables and exit.")
    p.add_argument("--tables", action="append", default=[],
                   help="Tables to document; comma-separated, repeatable.")
    p.add_argument("--all", action="store_true", help="Document every table in the schema.")
    p.add_argument("-o", "--output", default="schema.html", help="Output file (.html or .pdf).")
    p.add_argument("-f", "--format", choices=["html", "pdf"], help="Output format. Defaults to the file extension.")
    p.add_argument("--title", help="Report title.")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        reader = SchemaReader(args.url)
    except Exception as exc:
        print(f"Could not connect: {exc}", file=sys.stderr)
        return 2
    try:
        available = reader.list_tables(args.schema)
        if args.list:
            print("\n".join(available))
            return 0
        tables = available if args.all else [t.strip() for arg in args.tables for t in arg.split(",") if t.strip()]
        if not tables:
            print("No tables given. Use --tables a,b,c or --all (see --list).", file=sys.stderr)
            return 2
        fmt = args.format or ("pdf" if args.output.lower().endswith(".pdf") else "html")
        out = generate(reader, tables, args.output, fmt, schema=args.schema, title=args.title)
        print(f"Wrote {out}")
        return 0
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    finally:
        reader.close()
