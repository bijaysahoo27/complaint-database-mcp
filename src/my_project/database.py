"""PostgreSQL access layer for complaint records."""

from __future__ import annotations

import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import psycopg
from dotenv import load_dotenv
from psycopg import sql
from psycopg.rows import dict_row


load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=True)

FILTER_COLUMNS = (
    "status",
    "severity",
    "owner",
    "region",
    "customer",
    "service",
    "category",
    "channel",
)
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _identifier_setting(name: str, default: str) -> str:
    value = os.getenv(name, default)
    if not _IDENTIFIER.fullmatch(value):
        raise RuntimeError(f"{name} must be a simple PostgreSQL identifier")
    return value


def _table() -> sql.Composed:
    schema = _identifier_setting("POSTGRES_SCHEMA", "public")
    table = _identifier_setting("POSTGRES_TABLE", "complaints")
    return sql.SQL("{}.{}").format(sql.Identifier(schema), sql.Identifier(table))


def _connection_kwargs() -> dict[str, Any]:
    if connection_url := os.getenv("POSTGRES_URL"):
        return {"conninfo": connection_url}

    password = os.getenv("POSTGRES_PASSWORD")
    if not password:
        raise RuntimeError("Set POSTGRES_URL or POSTGRES_PASSWORD before starting the server")

    return {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "dbname": os.getenv("POSTGRES_DB", "Complaint Database"),
        "user": os.getenv("POSTGRES_USER", "postgres"),
        "password": password,
    }


@contextmanager
def _connection(*, read_only: bool = True) -> Iterator[psycopg.Connection[dict[str, Any]]]:
    kwargs = _connection_kwargs()
    conninfo = kwargs.pop("conninfo", "")
    with psycopg.connect(
        conninfo,
        **kwargs,
        connect_timeout=int(os.getenv("POSTGRES_CONNECT_TIMEOUT", "10")),
        row_factory=dict_row,
    ) as connection:
        if read_only:
            connection.execute("SET TRANSACTION READ ONLY")
        yield connection


def get_complaint(complaint_id: str) -> dict[str, Any] | None:
    statement = sql.SQL(
        "SELECT * FROM {} WHERE UPPER(complaint_id) = UPPER(%s) "
        "ORDER BY created_at DESC LIMIT 1"
    ).format(_table())
    with _connection() as connection:
        return connection.execute(statement, (complaint_id.strip(),)).fetchone()


def list_complaints(filters: dict[str, str] | None = None) -> list[dict[str, Any]]:
    filters = {key: value.strip() for key, value in (filters or {}).items() if value.strip()}
    unknown = set(filters) - set(FILTER_COLUMNS)
    if unknown:
        raise ValueError(f"Unsupported complaint filters: {', '.join(sorted(unknown))}")

    conditions: list[sql.Composed] = []
    parameters: list[str] = []
    for column, value in filters.items():
        conditions.append(sql.SQL("{} = %s").format(sql.Identifier(column)))
        parameters.append(value)

    where = sql.SQL("")
    if conditions:
        where = sql.SQL(" AND ") + sql.SQL(" AND ").join(conditions)

    statement = sql.SQL(
        "WITH current_complaints AS ("
        " SELECT *, ROW_NUMBER() OVER (PARTITION BY complaint_id ORDER BY created_at DESC) AS _row_number"
        " FROM {}"
        ") SELECT * FROM current_complaints WHERE _row_number = 1{} "
        "ORDER BY created_at DESC"
    ).format(_table(), where)

    with _connection() as connection:
        rows = connection.execute(statement, parameters).fetchall()

    for row in rows:
        row.pop("_row_number", None)
    return rows


def change_complaint_status(complaint_id: str, status: str) -> dict[str, Any] | None:
    statement = sql.SQL(
        "UPDATE {} SET status = %s WHERE ctid = ("
        " SELECT ctid FROM {} WHERE UPPER(complaint_id) = UPPER(%s)"
        " ORDER BY created_at DESC LIMIT 1"
        ") RETURNING *"
    ).format(_table(), _table())
    with _connection(read_only=False) as connection:
        return connection.execute(statement, (status, complaint_id.strip())).fetchone()


def update_complaint_owner(complaint_id: str, owner: str) -> dict[str, Any] | None:
    statement = sql.SQL(
        "UPDATE {} SET owner = %s WHERE ctid = ("
        " SELECT ctid FROM {} WHERE UPPER(complaint_id) = UPPER(%s)"
        " ORDER BY created_at DESC LIMIT 1"
        ") RETURNING *"
    ).format(_table(), _table())
    with _connection(read_only=False) as connection:
        return connection.execute(statement, (owner, complaint_id.strip())).fetchone()
