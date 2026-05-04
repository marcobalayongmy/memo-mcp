# memo-mcp

Personal notes MCP server for Claude Desktop. Ships as `memo-mcp` on PyPI. Python 3.11+, SQLite + FTS5 backend, stdio MCP transport via FastMCP.

## Commands

```bash
# Install deps (dev)
pip install -e ".[dev]"

# Run MCP server (stdio)
memo-mcp serve

# Rebuild FTS5 index
memo-mcp reindex

# Tests
pytest

# Build wheel
python -m build
```

## Project layout

```
src/memo_mcp/
  __init__.py    # version string + public re-exports
  server.py      # FastMCP instance; tool registration
  tools.py       # MCP tool handlers (notes.add / notes.search / notes.list)
  storage.py     # SQLite layer: open_db, queries, cursor encode/decode, reindex
  cli.py         # Typer CLI: serve + reindex commands; entry point
  logging.py     # structlog config bound to stderr; get_logger()
tests/
  conftest.py    # shared fixtures: in-memory DB, FastMCP test client
  test_tools.py  # tool-level integration tests via FastMCP test client
  test_storage.py
  test_cli.py
skill-outputs/   # design documents (not part of the installable package)
```

## Architecture decisions

### Transport
- stdio MCP transport — **stdout is reserved for MCP wire framing**. No `print()`, no logging to stdout, ever. All logging goes to stderr via structlog.
- No `multiprocessing` — hangs under stdio transport (mcp-sdk issue #817). `subprocess` is fine.

### MCP framework
- **FastMCP** (`@mcp.tool()` decorator, not the low-level `Server` class). Tool docstrings are the MCP tool descriptions — keep them accurate.
- `mcp` pinned to `>=1.27.0,<2.0` to prevent silent breaks from the in-development v2.

### Database
- Single shared `sqlite3.Connection` opened at `serve` startup, injected into `tools.py` as `_tools._conn` before `asyncio.run(mcp.run())`.
- DB path: `MEMO_MCP_DB_PATH` env var → `~/.memo-mcp/notes.db`. UNC/network paths are rejected at startup.
- Per-connection PRAGMAs (non-persistent): `PRAGMA journal_mode=WAL`, `PRAGMA busy_timeout=5000`.
- Schema created idempotently with `IF NOT EXISTS` guards on every `open_db()` call.
- `RETURNING id, created_at` on INSERT — no `last_insert_rowid()`.

### FTS5
- External-content virtual table (`content='notes'`). Body text is not duplicated in FTS shadow tables.
- Three sync triggers (`notes_ai`, `notes_ad`, `notes_au`) keep `notes_fts` current.
- Search order: `ORDER BY bm25(notes_fts) ASC` (negative scores; more negative = better match). Ties broken by `created_at DESC`.
- FTS5 special chars (`"`, `*`, `-`, `OR`, `AND`, `NOT`) are passed through as-is — do not sanitise.
- `reindex` uses `INSERT INTO notes_fts(notes_fts) VALUES('rebuild')` — not DROP+recreate.

### Pagination (`notes.list`)
- Cursor-based: opaque base64 encoding of `{"c": created_at, "i": id}` for the last row on the current page.
- Fetch `limit + 1` rows to detect next page — no `COUNT(*)`.
- Invalid cursor → `ValueError` → `isError: true`. No silent fallback to page 1.

### Error model
- All business-logic errors: raise an exception in the tool handler → FastMCP converts to `isError: true` with plain-English text in `content[0].text`. No JSON error envelope.
- Protocol-level JSON-RPC errors are reserved for server failures (tool not found, malformed request).

### reindex command
- **CLI-only** — never called from within the MCP server process.
- Does not auto-create the DB. If DB absent → print error to stderr, `exit 1`.
- Exit codes: 0 success, 1 DB not found, 2 DB error, 3 UNC path, 4 already running.
- Concurrency guard: `filelock>=3.13`, lock file at `<db_dir>/.memo-mcp-reindex.lock`, non-blocking `timeout=0`.
- Timing: `time.perf_counter()`. Final stdout line: `Reindexed {N} notes in {X.XX}s`. All errors to stderr (`typer.echo(..., err=True)`).

### Logging
- structlog JSON lines to stderr. One line per tool call and per reindex.
- `MEMO_MCP_LOG_LEVEL` env var: `debug` or `info` (default `info`).
- **Never log** raw query text or note body (PII). Log `query_len` and `result_count` instead.

## Key constraints

| Constraint | Detail |
|---|---|
| Max note body | 10,000 chars (Claude context window bound) |
| `notes.search` limit | default 10, max 20 |
| `notes.list` limit | default 20, max 100 |
| `notes.add` fields | `body` only — no tags in v0.1.0 |
| Soft-delete | Deferred to v0.1.1; must use `deleted_at` column (not hard delete) |
| Tags column | Present in schema, NULL for all v0.1.0 rows, not exposed |

## Packaging

- Build backend: `uv_build`. Entry point: `memo-mcp = "memo_mcp.cli:app"`.
- PyPI name `memo-mcp` confirmed available.
- Publish via OIDC trusted publishing on `v*` tags (`.github/workflows/publish.yml`).
- First publish: dry-run to TestPyPI at `0.0.1a0`, then cut `v0.1.0` tag for real PyPI.

## Current status

**GitHub repo:** https://github.com/marcobalayongmy/memo-mcp

**T-01 through T-15 complete.** All automated tasks done; only manual release steps remain.

### All files implemented

| File | Status |
|------|--------|
| `src/memo_mcp/storage.py` | `open_db`, `add_note`, `search_notes`, `list_notes`, `encode_cursor`, `decode_cursor`, `reindex` |
| `src/memo_mcp/logging.py` | `configure_logging`, `get_logger` |
| `src/memo_mcp/server.py` | `mcp = FastMCP(name="memo")` |
| `src/memo_mcp/tools.py` | `notes.add`, `notes.search`, `notes.list`; `_get_conn()` guard |
| `src/memo_mcp/cli.py` | `serve` + `reindex`; all exit codes (0–4) verified |
| `tests/conftest.py` | `db`, `mcp_client`, `setup_logging` fixtures |
| `tests/test_storage.py` | 25 cases |
| `tests/test_tools.py` | 17 cases (async via `@pytest.mark.anyio`; stdout-leak assertions) |
| `tests/test_cli.py` | 10 cases (all exit codes, idempotent reindex, serve mock, `--help`) |
| `README.md` | Install, Claude Desktop config JSON, env vars, reindex scheduling |
| `.github/workflows/publish.yml` | `test` → `publish` (OIDC, `environment: publish`, no secrets) |

**Test suite: 52 tests, all passing.**

### Key decisions made during build (not in original design)
- `_get_conn()` guard in `tools.py` — `None` produces `RuntimeError`, not cryptic `AttributeError`
- `pydantic>=2.11` (not `>=2.0`) — `mcp` itself requires 2.11+; old bound was misleading
- `typer>=0.12,<1.0` — safety upper bound; typer is pre-1.0
- `anyio>=4.0` added to dev extras — already transitive via `mcp`, made explicit
- `configure_logging()` session fixture in `conftest.py` — directs structlog to stderr in tests, enabling stdout-leak assertions
- `serve` test uses `patch.object(mcp, "run")` — `mcp.run()` is a sync wrapper calling `anyio.run()` directly, so patching `asyncio.run` alone is insufficient

### Remaining (manual)

**Next: T-16** — Register trusted publisher on pypi.org and test.pypi.org:
- GitHub repo, workflow file `publish.yml`, environment name `publish`
- Push `v0.0.1a0` tag → confirm TestPyPI dry-run succeeds
- `pip install -i https://test.pypi.org/simple/ memo-mcp==0.0.1a0` and verify `memo-mcp --help`

**Then: T-17** — Cut `v0.1.0` tag → real PyPI publish

**Final automated passes:** `code-review` → `security-analysis`
