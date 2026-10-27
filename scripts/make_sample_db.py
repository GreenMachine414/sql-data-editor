"""Create sample.db, a small SQLite shop database for trying the app.

    python scripts/make_sample_db.py            -> ./sample.db
    python scripts/make_sample_db.py other.db
"""
import sqlite3
import sys
from pathlib import Path

DDL = """
PRAGMA foreign_keys = ON;
CREATE TABLE customers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    email       VARCHAR(255) NOT NULL UNIQUE,
    full_name   VARCHAR(120) NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE addresses (
    id          INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    line1       VARCHAR(200) NOT NULL,
    city        VARCHAR(80) NOT NULL,
    postcode    VARCHAR(20),
    country     CHAR(2) NOT NULL DEFAULT 'US'
);
CREATE INDEX ix_addresses_customer ON addresses(customer_id);
CREATE TABLE categories (
    id          INTEGER PRIMARY KEY,
    name        VARCHAR(80) NOT NULL,
    parent_id   INTEGER REFERENCES categories(id)
);
CREATE TABLE products (
    id          INTEGER PRIMARY KEY,
    sku         VARCHAR(40) NOT NULL,
    name        VARCHAR(200) NOT NULL,
    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    price       NUMERIC(10, 2) NOT NULL,
    active      BOOLEAN NOT NULL DEFAULT 1
);
CREATE UNIQUE INDEX ux_products_sku ON products(sku);
CREATE INDEX ix_products_category ON products(category_id, active);
CREATE TABLE orders (
    id                  INTEGER PRIMARY KEY,
    customer_id         INTEGER NOT NULL REFERENCES customers(id),
    shipping_address_id INTEGER REFERENCES addresses(id),
    status              VARCHAR(20) NOT NULL DEFAULT 'pending',
    placed_at           TIMESTAMP NOT NULL
);
CREATE INDEX ix_orders_customer_placed ON orders(customer_id, placed_at);
CREATE TABLE order_items (
    order_id    INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id  INTEGER NOT NULL REFERENCES products(id),
    quantity    INTEGER NOT NULL DEFAULT 1,
    unit_price  NUMERIC(10, 2) NOT NULL,
    PRIMARY KEY (order_id, product_id)
);
CREATE TABLE payments (
    id          INTEGER PRIMARY KEY,
    order_id    INTEGER NOT NULL UNIQUE REFERENCES orders(id),
    amount      NUMERIC(10, 2) NOT NULL,
    method      VARCHAR(20) NOT NULL,
    paid_at     TIMESTAMP
);
CREATE TABLE audit_log (
    id          INTEGER PRIMARY KEY,
    happened_at TIMESTAMP NOT NULL,
    actor       VARCHAR(80),
    action      TEXT NOT NULL
);
"""


def make(path: Path) -> Path:
    if path.exists():
        path.unlink()
    con = sqlite3.connect(path)
    con.executescript(DDL)
    con.close()
    return path


if __name__ == "__main__":
    out = make(Path(sys.argv[1] if len(sys.argv) > 1 else "sample.db"))
    print(f"Created {out}")
