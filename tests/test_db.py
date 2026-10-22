import datetime as dt
from decimal import Decimal

import pytest

from data_editor.db import Column, ConnectionInfo, _where, coerce, format_value, quote_ident


def col(name="c", data_type="int", **kw):
    return Column(name, data_type, kw.get("nullable", True), False, False, kw.get("pk", False))


def test_quote_ident_escapes_brackets():
    assert quote_ident("Orders") == "[Orders]"
    assert quote_ident("bad]name") == "[bad]]name]"


def test_connection_string_sql_auth_escapes_password():
    info = ConnectionInfo(server="srv", database="db", username="u", password="p}w;d")
    cs = info.connection_string()
    assert "UID=u" in cs
    assert "PWD={p}}w;d}" in cs
    assert "Trusted_Connection" not in cs


def test_connection_string_windows_auth():
    cs = ConnectionInfo(server="srv", windows_auth=True, username="ignored").connection_string()
    assert "Trusted_Connection=yes" in cs
    assert "UID" not in cs


@pytest.mark.parametrize(
    "text, data_type, expected",
    [
        ("42", "int", 42),
        ("3.50", "decimal", Decimal("3.50")),
        ("1.5", "float", 1.5),
        ("true", "bit", True),
        ("0", "bit", False),
        ("2024-03-01", "date", dt.date(2024, 3, 1)),
        ("2024-03-01 13:45:00.123", "datetime", dt.datetime(2024, 3, 1, 13, 45, 0, 123000)),
        ("hello", "nvarchar", "hello"),
    ],
)
def test_coerce(text, data_type, expected):
    assert coerce(text, col(data_type=data_type)) == expected


def test_coerce_rejects_bad_values():
    with pytest.raises(ValueError, match="not a valid int"):
        coerce("abc", col(data_type="int"))


def test_format_value_round_trips_datetime():
    value = dt.datetime(2024, 3, 1, 13, 45, 0, 123000)
    assert coerce(format_value(value), col(data_type="datetime2")) == value


def test_where_handles_null_keys():
    clause, params = _where({"a": 1, "b": None})
    assert clause == "[a] = ? AND [b] IS NULL"
    assert params == [1]
