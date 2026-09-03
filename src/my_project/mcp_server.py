"""MCP tools for the PostgreSQL Complaint Database."""

from __future__ import annotations

import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import psycopg
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from psycopg import sql
from psycopg.rows import dict_row
from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[2] / ".env")


READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

WRITE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=True,
    openWorldHint=False,
)

mcp = MCPServer(
    "complaint-database",
    title="Complaint Database",
    description="Read and update current PostgreSQL complaint records.",
    instructions="Read complaint records and update a complaint's current status in PostgreSQL.",
    version="0.1.3",
)

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
    """Update and return the newest row for a complaint ID."""
    statement = sql.SQL(
        "UPDATE {} SET status = %s WHERE ctid = ("
        " SELECT ctid FROM {} WHERE UPPER(complaint_id) = UPPER(%s)"
        " ORDER BY created_at DESC LIMIT 1"
        ") RETURNING *"
    ).format(_table(), _table())
    with _connection(read_only=False) as connection:
        return connection.execute(statement, (status, complaint_id.strip())).fetchone()


def update_complaint_owner(
    complaint_id: str,
    owner: str,
) -> dict[str, Any] | None:
    """Update and return the newest row for a complaint ID."""
    statement = sql.SQL(
        "UPDATE {} SET owner = %s WHERE ctid = ("
        " SELECT ctid FROM {} WHERE UPPER(complaint_id) = UPPER(%s)"
        " ORDER BY created_at DESC LIMIT 1"
        ") RETURNING *"
    ).format(_table(), _table())
    with _connection(read_only=False) as connection:
        return connection.execute(statement, (owner, complaint_id.strip())).fetchone()


@mcp.tool(annotations=READ_ONLY)
def get_complaint_by_id(complaint_id: str) -> dict:
    """Get the latest database record for one complaint ID, such as CMP-1001."""
    normalized_id = complaint_id.strip().upper()
    return get_complaint(normalized_id) or {
        "error": "Complaint not found",
        "complaint_id": normalized_id,
    }


@mcp.tool(annotations=READ_ONLY)
def search_complaints(
    status: str = "",
    severity: str = "",
    owner: str = "",
    region: str = "",
    customer: str = "",
    service: str = "",
    category: str = "",
    channel: str = "",
) -> list[dict]:
    """Search current complaint records. Every non-empty argument is combined as a filter."""
    return list_complaints({
        "status": status,
        "severity": severity,
        "owner": owner,
        "region": region,
        "customer": customer,
        "service": service,
        "category": category,
        "channel": channel,
    })


@mcp.tool(annotations=READ_ONLY)
def list_recent_complaints(limit: int = 10) -> list[dict]:
    """List the newest complaint records, ordered by creation time descending."""
    safe_limit = max(1, min(limit, 100))
    return list_complaints()[:safe_limit]

#Customer complaint history
@mcp.tool(annotations=READ_ONLY)
def get_customer_complaint_history(
    customer: str,
    limit: int = 20,
) -> list[dict]:
    """Return the latest complaints registered for a customer."""

    safe_limit = max(1, min(limit, 100))

    return list_complaints({
        "customer": customer,
    })[:safe_limit]


#Change complaint status
@mcp.tool(annotations=WRITE)
def update_complaint_status(
    complaint_id: str,
    status: str,
) -> dict:
    """Change the status of a complaint."""

    allowed_statuses = {
        "Open",
        "In Progress",
        "Pending Customer",
        "Resolved",
        "Closed",
    }

    normalized_status = status.strip().title()

    if normalized_status not in allowed_statuses:
        return {
            "error": "Invalid status",
            "allowed_statuses": sorted(allowed_statuses),
        }

    normalized_id = complaint_id.strip().upper()
    return change_complaint_status(
        complaint_id,
        normalized_status,
    ) or {
        "error": "Complaint not found",
        "complaint_id": normalized_id,
    }

#Assign complaint
@mcp.tool(annotations=WRITE)
def assign_complaint(
    complaint_id: str,
    owner: str,
) -> dict:
    """Assign an open complaint to a support owner."""

    if not owner.strip():
        return {"error": "Owner cannot be empty"}

    normalized_id = complaint_id.strip().upper()
    return update_complaint_owner(
        complaint_id=complaint_id,
        owner=owner.strip(),
    ) or {
        "error": "Complaint not found",
        "complaint_id": normalized_id,
    }
    
def main() -> None:
    mcp.run(transport="stdio")
