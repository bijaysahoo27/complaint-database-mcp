"""MCP tools for the PostgreSQL Complaint Database."""

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .database import (
    change_complaint_status,
    get_complaint,
    list_complaints,
    update_complaint_owner,
)


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

mcp = FastMCP(
    "complaint-database",
    instructions="Read complaint records and update a complaint's current status in PostgreSQL.",
)

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
