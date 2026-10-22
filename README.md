# Data Editor

A simple Windows desktop app for viewing and editing rows in Microsoft SQL Server tables.
Sign in with your own SQL Server or Windows credentials. The database's own permissions decide what you can see and change.

## Features

- Sign in with **SQL Server Authentication** or **Windows Authentication**. The app remembers the server, username and database, but never your password.
- Switch between databases and browse tables, with a search box to filter the table list.
- Load rows with an optional `WHERE` clause and a row limit. You can also search the rows you've loaded and sort by any column.
- **Edit cells** in place, **add rows**, **delete rows** and **set values to NULL**.
- Copy and paste cells to and from Excel.
- Changes stay pending until you click **Save**:
  - 🟩 new rows · 🟨 changed cells (hover to see the original value) · 🟥 rows to be deleted
  - All changes are saved in **one transaction**. If any part fails, nothing is saved.
  - Values are checked against the column type before saving.
- Identity, computed, rowversion and binary columns are read-only.
- Tables without a primary key are insert-only, because there's no safe way to identify a row to change or delete.

### Keyboard shortcuts

| Action | Shortcut |
|---|---|
| Save changes | `Ctrl+S` |
| Add row | `Ctrl+N` |
| Delete / undelete selected rows | `Ctrl+D` |
| Set selected cells to NULL | `Ctrl+0` |
| Refresh | `F5` |
| Copy / paste | `Ctrl+C` / `Ctrl+V` |

## Install (for users)

1. Install the **[Microsoft ODBC Driver 18 for SQL Server](https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server)** if you don't already have it. Driver 17 also works.
2. Download `DataEditor.exe` from the [latest release](../../releases/latest) and run it. You don't need to install anything else.

> Windows SmartScreen may warn about an unsigned app. Click **More info → Run anyway**.

## Development

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -e .[dev]

python -m data_editor     # run the app
pytest                    # run tests
python build.py           # build dist\DataEditor.exe
```

### Project layout

```
src/data_editor/
  __main__.py       entry point
  db.py             connecting, table/column info, reading and saving rows (pyodbc)
  table_model.py    Qt table model that tracks pending changes
  login_dialog.py   connect / sign-in dialog
  main_window.py    main window
tests/              unit tests
build.py            PyInstaller build script
.github/workflows/release.yml
```

## Publishing a release

Push a version tag. GitHub Actions runs the tests, builds `DataEditor.exe` and attaches it to a new GitHub release:

```powershell
git tag v1.0.0
git push origin v1.0.0
```

The app's version number is taken from the tag. You can also run the workflow by hand from the **Actions** tab. That builds the exe as a downloadable workflow artifact without creating a release.
