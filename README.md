# Data Editor

A Windows desktop app with two tabs that share one sign-in:

- **Edit Data**: browse SQL Server tables and edit their rows. You can change cells, add rows, delete rows and set values to NULL, then save everything in one transaction.
- **Document Schema**: choose tables and produce an **HTML page** or **PDF** containing an entity relationship diagram and a reference for every column, key and index. Works with SQL Server, PostgreSQL, MySQL/MariaDB and SQLite.

The database's own permissions decide what you can see and change.

## Download

Download `DataEditor.exe` from the **[latest release](../../releases/latest)** and run it.

- **For SQL Server**, install the [Microsoft ODBC Driver 18 for SQL Server](https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server) if you don't already have it. Driver 17 also works.
- **For other databases**, nothing else is needed. Their drivers are built into the app.

> Windows SmartScreen may warn about an unsigned app. Click **More info → Run anyway**.

## Connecting

Choose the database type and sign in. The app remembers everything except your password.

| Database | Edit Data | Document Schema | Sign-in |
|---|:-:|:-:|---|
| SQL Server | ✓ | ✓ | SQL Server or Windows authentication |
| PostgreSQL | | ✓ | username and password |
| MySQL / MariaDB | | ✓ | username and password |
| SQLite | | ✓ | browse to the `.db` file |
| Anything else SQLAlchemy supports | | ✓ | **Custom SQLAlchemy URL** (install its driver when running from source) |

For SQL Server, the server can include an instance and port, such as `sql01\PROD,1433`. The database is optional. Switch databases with the **Database** picker at the top of the window, and use **Connect…** (`Ctrl+O`) to connect somewhere else.

## Edit Data

Pick a table on the left. Rows load in the background, and you can filter with a `WHERE` clause and a row limit. You can also search the loaded rows and sort by any column.

- **Edit cells** in place, **add rows**, **delete rows** and **set values to NULL**. Copy and paste cells to and from Excel.
- Changes stay pending until you click **Save**:
  - 🟩 new rows · 🟨 changed cells (hover to see the original value) · 🟥 rows to be deleted
  - All changes are saved in **one transaction**. If any part fails, nothing is saved.
  - Values are checked against the column type before saving.
- Identity, computed, rowversion and binary columns are read-only.
- Tables without a primary key are insert-only, because there's no safe way to identify a row to change or delete.

| Action | Shortcut |
|---|---|
| Save changes | `Ctrl+S` |
| Add row | `Ctrl+N` |
| Delete / undelete selected rows | `Ctrl+D` |
| Set selected cells to NULL | `Ctrl+0` |
| Refresh | `F5` |
| Copy / paste | `Ctrl+C` / `Ctrl+V` |

## Document Schema

1. Pick a **Schema** in the toolbar, if the database has more than one.
2. Click the tables to include (or press Space), or use **Select All**. *Filter tables* narrows long lists, and *Select All* and *Clear* only affect the tables shown.
3. Set a title, choose **HTML page** or **PDF document**, and click **Generate document** (`Ctrl+G`).

The document contains:

- an **entity relationship diagram** (crow's-foot notation) of the selected tables
- how the tables relate: foreign key columns, the table they point to, and cardinality
- every column with its **data type**, whether it can be NULL, and its key flags (PK / FK / unique)
- which columns are **indexed**

Documenting only reads table definitions, never row data, so a read-only account is enough. Relationships are drawn between the tables you selected. A foreign key that points at a table you didn't select still appears in that table's column list, greyed out.

![ERD example](docs/erd.png)

Examples generated from the bundled sample database: [`docs/examples/shop.html`](docs/examples/shop.html) · [`docs/examples/shop.pdf`](docs/examples/shop.pdf)

### Diagram notes

- The diagram layout is built in, so no Graphviz or other tools are needed. Lines are routed between tables, never through them, and each line is coloured by the table it points to.
- In the PDF, every page is the same size. A diagram too big to read on one page continues onto more pages, splitting only between rows of tables so no table is cut in half. In the HTML page you can zoom and download the diagram as SVG.
- Tables with more than 12 columns show only their primary key and the columns the diagram's lines connect to. Every column is still listed in the table details.
- The HTML report is a single file with no external requests, so it can be emailed or kept next to your code.

### Connecting to a Railway database

Use the host and port from `DATABASE_PUBLIC_URL` in your Postgres service's Variables. Or open a private tunnel with the Railway CLI, and keep that window open while you work:

```bash
railway connect postgres --tunnel-only -P 5433
```

Then connect to host `127.0.0.1`, port `5433`, with the credentials the tunnel prints.

## Command line

When running from source, the `schemadoc` command documents tables without opening the window:

```bash
schemadoc --url sqlite:///sample.db --list
schemadoc --url sqlite:///sample.db --tables customers,orders,order_items -o shop.html
schemadoc --url "postgresql://me:secret@db.local/app" --schema billing --all -o billing.pdf
schemadoc --url "mssql://me:secret@sql01/Sales" --all -o sales.pdf
```

`--format` defaults to the output file's extension.

## Development

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -e .[dev]

python -m data_editor              # run the app
python scripts/make_sample_db.py   # creates sample.db, a small SQLite shop database to try it on
pytest                             # run tests
python build.py                    # build dist\DataEditor.exe
```

`tests/test_sql_server.py` runs against a real SQL Server. It creates and drops scratch tables in `tempdb`. To run it, set `$env:DATA_EDITOR_TEST_SERVER = "localhost"`; it signs in with Windows authentication.

### Project layout

```
src/data_editor/            the desktop app
  __main__.py               entry point
  connect_dialog.py         sign-in window, for every database type
  session.py                one connection shared by both tabs
  main_window.py            window: connection bar and the two tabs
  editor_page.py            Edit Data tab
  table_model.py            grid model that tracks pending changes
  db.py                     SQL Server reads and writes (pyodbc)
  document_page.py          Document Schema tab
  theme.py, widgets.py      colours and loading spinner
  worker.py                 runs database work off the UI thread
src/schemadoc/              schema documenting library and `schemadoc` command
  introspect.py             reads tables, columns, keys and indexes (SQLAlchemy)
  connection.py             database types and connection URLs
  models.py                 plain data classes
  report.py                 decides what the report says
  erd.py, canvas.py         diagram layout and drawing (SVG and PDF)
  render_html.py            HTML report
  render_pdf.py             PDF report (ReportLab)
  generate.py, cli.py       ties reading and rendering together, and the command line
scripts/make_sample_db.py
tests/
build.py                    PyInstaller build script
.github/workflows/release.yml
```

## Publishing a release

Push a version tag. GitHub Actions runs the tests, builds `DataEditor.exe` and attaches it to a new GitHub release:

```powershell
git tag v2.0.0
git push origin v2.0.0
```

The app's version number is taken from the tag. You can also run the workflow by hand from the **Actions** tab. That builds the exe as a downloadable workflow artifact without creating a release.

MIT licensed.
