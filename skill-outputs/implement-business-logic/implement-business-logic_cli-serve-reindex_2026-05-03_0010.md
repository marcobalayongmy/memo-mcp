# Implement Business Logic — T-09 + T-10: cli.py serve & reindex (2026-05-03)

## Requirement
Implement the real `serve` and `reindex` commands in `src/memo_mcp/cli.py` (both were `raise NotImplementedError` stubs).

## Files modified
- `src/memo_mcp/cli.py` — replaced both stubs with full implementations (~40 LOC added)

## Key design decisions

### serve
- `configure_logging()` is called first so all subsequent errors (including `open_db()` failures) are captured in structured JSON on stderr.
- `import memo_mcp.tools as _tools` is a local import inside `serve()` — keeps the `_conn` injection pattern explicit and defers tool registration until the server is actually starting.
- `asyncio.run(mcp.run())` — no try/except; if the MCP run loop crashes, the process exits non-zero and the error goes to stderr (not stdout, which is the MCP wire channel).

### reindex
- Path resolution mirrors `open_db()` logic: `--db` / `MEMO_MCP_DB_PATH` env var (via Typer's `envvar=`) / default `~/.memo-mcp/notes.db`.
- UNC check (`startswith("\\\\") or startswith("//")`) is applied on `str(pathlib.Path(...))` — same normalization used by `open_db()` — so the two guards stay in sync.
- Existence check fires before `open_db()` so the DB is never auto-created by this command.
- `FileLock(timeout=0)` wraps the entire work block; `Timeout` caught outside the `with` statement.
- `sqlite3.Error` is caught inside the lock block and exits with code 2; any other unexpected exception propagates naturally.
- Timing uses `time.perf_counter()` started after the lock is acquired and before `open_db()` — includes DB open time in the reported elapsed time, which is accurate from the user's perspective.

## Exit codes verified

| Code | Scenario | Verified |
|------|----------|---------|
| 0 | Success (2 notes reindexed) | ✓ `Reindexed 2 notes in 0.01s` |
| 1 | DB not found | ✓ error to stderr |
| 3 | UNC path (`\\server\share\notes.db`) | ✓ error to stderr |
| 4 | Lock already held | ✓ error to stderr |

Exit code 2 (sqlite3.Error) not exercised manually — covered by unit tests in T-11/T-12.

## Tests
None yet — T-11/T-12/T-13 (`generate-tests`) is the next phase.

## Deferred / follow-up
- Exit code 2 path (`sqlite3.Error` during open/reindex) will be covered in `test_cli.py` (T-13).
- `serve` error paths (e.g. corrupt DB at startup) are not explicitly handled — they propagate and crash the process, which is the correct behavior for an MCP server startup failure.
