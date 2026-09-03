# Complaint Database MCP chatbot

This project includes a Streamlit chatbot powered by OpenAI and a LangChain
agent. The agent connects to PostgreSQL only through the local stdio MCP server.

The MCP server exposes six tools:

- `get_complaint_by_id`
- `search_complaints`
- `list_recent_complaints`
- `update_complaint_status`
- `get_customer_complaint_history`
- `assign_complaint`

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
# Edit .env and provide PostgreSQL credentials and OPENAI_API_KEY.
uv sync
```

Start the chatbot:

```powershell
uv run streamlit run app.py
```

Open the local URL printed by Streamlit (normally `http://localhost:8501`).
The OpenAI model decides when to call the MCP tools; the MCP server performs the actual
PostgreSQL reads and updates.

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
