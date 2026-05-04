# implement-business-logic — logging.py + server.py + tools.py (T-06/T-07/T-08)

## Requirement
T-06: `configure_logging()` / `get_logger()` — structlog JSON to stderr only.
T-07: `mcp = FastMCP(name="memo")` — shared FastMCP instance.
T-08: Three MCP tool handlers (`notes.add`, `notes.search`, `notes.list`) wired to storage.

## Files created
- `src/memo_mcp/logging.py` — `configure_logging()` + `get_logger()`; structlog JSON to stderr
- `src/memo_mcp/server.py` — `mcp = FastMCP(name="memo")`; tool registrations live in tools.py
- `src/memo_mcp/tools.py` — `notes_add`, `notes_search`, `notes_list`; `_conn` injected by cli.py

## Key design decisions

| Decision | Rationale |
|---|---|
| `PrintLoggerFactory(file=sys.stderr)` — captured at `configure_logging()` call time | Fixed reference ensures all log writes always go to the original stderr, even if `sys.stderr` is reassigned later |
| `make_filtering_bound_logger(level)` as `wrapper_class` | Modern structlog (21.2+) level filtering without requiring stdlib integration; avoids two-layer indirection |
| `logging.basicConfig(stream=sys.stderr)` kept as first layer | Catches any transitive dependency using stdlib logging (structlog doesn't intercept those) |
| Unknown `MEMO_MCP_LOG_LEVEL` silently falls back to `INFO` via `getattr(..., logging.INFO)` | Matches spec: no error on bad env value |
| Tool handlers use `pydantic.Field` in `Annotated` for `ge`/`le`/`max_length`/`description` | FastMCP uses Pydantic for arg validation + JSON schema generation; constraints visible in MCP tool manifest |
| `_conn: sqlite3.Connection \| None = None` module-level | Injected by `cli.py` before `asyncio.run(mcp.run())` — the invariant is guaranteed by startup ordering |
| `body = body.strip()` before `storage.add_note()` | Strips at the tool boundary so stored notes never have leading/trailing whitespace |
| `json.dumps(result)` for list/search returns | Tools return `str`; JSON is the natural serialization for structured results |
| Event key = tool name (e.g. `"notes.add"`) | Unique, greppable event names; no separate `tool=` field needed for routing |

## Tests / verification
Smoke-tested inline:
- `configure_logging()` → `get_logger().info("test", x=1)` → JSON line in stderr buffer ✓
- `MEMO_MCP_LOG_LEVEL=BADLEVEL` → falls back to `info` silently ✓
- stdout untouched after log call ✓
- `mcp.name == "memo"` ✓
- After importing `tools`, `mcp._tool_manager.list_tools()` returns all three tool names ✓

## Deferred
- `cli.py` serve/reindex commands (T-09/T-10) — wire `_conn` injection and `asyncio.run`
- Tests for tool error paths (T-11/T-12)
- Logging in `reindex` CLI command (T-10)
