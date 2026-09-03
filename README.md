# Complaint Database MCP server

This stdio MCP server connects to PostgreSQL and exposes four tools:

- `get_complaint_by_id`
- `search_complaints`
- `list_recent_complaints`
- `update_complaint_status`

The default database is `Complaint Database`, and the default relation is
`public.complaints`. Override the schema or table with `POSTGRES_SCHEMA` and
`POSTGRES_TABLE`.

The table is expected to contain `complaint_id`, `created_at`, and the filter
columns `status`, `severity`, `owner`, `region`, `customer`, `service`,
`category`, and `channel`. It may contain additional columns; tools return the
complete latest row for each complaint ID.

## Setup

```powershell
Copy-Item .env.example .env
# Edit .env and provide the actual credentials.
uv sync
```

Load the environment and run the server:

```powershell
Get-Content .env | Where-Object { $_ -match '^[^#].*=' } | ForEach-Object {
    $key, $value = $_ -split '=', 2
    Set-Item -Path "Env:$key" -Value $value
}
uv run complaint-db-mcp
```

Example Codex MCP registration after setting the PostgreSQL variables in the
environment:

```powershell
codex mcp add complaint-database -- uv --directory "C:\AI\Ai_project\My_project" run complaint-db-mcp
```

Restart or open a new Codex session after registering a local MCP server so its
tools can be discovered.
