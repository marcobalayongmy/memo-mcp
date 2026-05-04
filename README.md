# memo-mcp

Personal notes MCP server for Claude Desktop. Save, search, and list notes from inside any Claude conversation. Notes are stored locally in SQLite with full-text search powered by FTS5.

**Requires Python 3.11+**

## Installation

```bash
pip install memo-mcp
```

## Claude Desktop setup

Add the following to your Claude Desktop config file:

**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`  
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "memo": {
      "command": "memo-mcp",
      "args": ["serve"]
    }
  }
}
```

> If `memo-mcp` is not on your PATH (e.g. installed in a virtualenv), use the full path to the executable, or install with [uv](https://github.com/astral-sh/uv) and use `uvx` instead:
>
> ```json
> {
>   "mcpServers": {
>     "memo": {
>       "command": "uvx",
>       "args": ["memo-mcp", "serve"]
>     }
>   }
> }
> ```

Restart Claude Desktop after editing the config.

## Tools

Once connected, Claude can use three tools:

| Tool | Description |
|------|-------------|
| `notes.add` | Save a note (plain text, max 10,000 characters) |
| `notes.search` | Full-text search across all notes (FTS5 syntax supported) |
| `notes.list` | List notes newest-first with cursor-based pagination |

## Custom database path

By default notes are stored at `~/.memo-mcp/notes.db`. Override with the `MEMO_MCP_DB_PATH` environment variable:

```json
{
  "mcpServers": {
    "memo": {
      "command": "memo-mcp",
      "args": ["serve"],
      "env": {
        "MEMO_MCP_DB_PATH": "/path/to/your/notes.db"
      }
    }
  }
}
```

## Rebuilding the search index

If search results seem incomplete after a crash or manual database edit, rebuild the FTS5 index:

```bash
memo-mcp reindex
# Reindexed 42 notes in 0.03s
```

Pass `--db` to target a non-default database:

```bash
memo-mcp reindex --db /path/to/notes.db
```

### Scheduling nightly reindex

**macOS / Linux** — add to crontab (`crontab -e`):

```
0 3 * * * memo-mcp reindex >> ~/.memo-mcp/reindex.log 2>&1
```

**Windows** — run once in an elevated PowerShell to create a daily Task Scheduler job:

```powershell
schtasks /create /tn "memo-mcp reindex" /tr "memo-mcp reindex" /sc daily /st 03:00 /f
```

## Developer notes

**Log level** — set `MEMO_MCP_LOG_LEVEL=debug` to enable verbose structured JSON logging to stderr. Default is `info`. This is a developer-only knob; normal users do not need to set it.

```json
{
  "mcpServers": {
    "memo": {
      "command": "memo-mcp",
      "args": ["serve"],
      "env": {
        "MEMO_MCP_LOG_LEVEL": "debug"
      }
    }
  }
}
```

## License

MIT
