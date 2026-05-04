# Generate Tests — memo-mcp full suite (2026-05-03)

## Targets
`src/memo_mcp/storage.py`, `src/memo_mcp/tools.py`, `src/memo_mcp/cli.py`

## Framework detected
- Python 3.13, pytest 9.0.3, anyio 4.13.0 (auto-discovered pytest plugin, installed transitively via `mcp`)
- Async tool tests: `@pytest.mark.anyio` via module-level `pytestmark`
- CLI tests: `typer.testing.CliRunner`
- No new test runner package needed; added `anyio>=4.0` to dev extras for explicit declaration

## New files

| File | Cases | Notes |
|------|-------|-------|
| `tests/conftest.py` | 2 fixtures | `db` (in-memory conn), `mcp_client` (injects conn + yields it) |
| `tests/test_storage.py` | 25 cases | `add_note`, `search_notes`, `list_notes`, cursor encode/decode, `reindex` |
| `tests/test_tools.py` | 13 cases | `notes.add`, `notes.search`, `notes.list` via `mcp.call_tool()`; `_get_conn()` guard |
| `tests/test_cli.py` | 7 cases | All 5 reindex exit codes + env-var resolution + serve mock |

## Run result
```
45 passed in 0.17s
```

## Key decisions

### Async test approach
Used `mcp.call_tool(name, args)` directly on the FastMCP server object — no wire transport needed. `anyio`'s pytest plugin (already installed) handles `@pytest.mark.anyio` without adding `pytest-asyncio`.

### serve test strategy
`mcp.run()` is a sync wrapper calling `anyio.run()` directly — it runs as an argument before `asyncio.run` can be intercepted. Fix: `patch.object(mcp, "run")` stops the transport from starting; `patch("memo_mcp.cli.asyncio.run")` verifies the call chain. Both mocks asserted.

### CLI output capture
Typer's `CliRunner` default captures stdout and stderr separately. Error messages (`typer.echo(..., err=True)`) appear in `result.output` for the Typer runner (which mixes streams by default at output level). All assertions verified against actual output.

### exit code 2 (corrupt DB)
Created a file with garbage bytes; `open_db()` connects successfully but `executescript()` raises `sqlite3.DatabaseError` (subclass of `sqlite3.Error`) → caught → exit 2.

## Skipped
- `serve` end-to-end (real MCP stdio loop) — would require a subprocess with stdin/stdout plumbing; not worth the complexity for a unit test suite.
