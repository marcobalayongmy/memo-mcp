# Code Review — T-01 through T-08 source files (2026-05-03)

**Scope:** `src/memo_mcp/__init__.py`, `storage.py`, `logging.py`, `server.py`, `tools.py`, `cli.py` + `pyproject.toml`
**Stack detected:** Python 3.11+, FastMCP (MCP framework), SQLite + FTS5, structlog, Typer, Pydantic

---

## Should fix

### 1. `tools.py:28,52,74` — `_conn` unguarded; produces unhelpful `AttributeError` if injection is missed

`_conn` is `None` at module load. All three tool functions call `storage.*(_conn, ...)` directly without a guard. If `cli.py serve` ever fails to inject it before `asyncio.run(mcp.run())`, FastMCP catches the resulting `AttributeError: 'NoneType' object has no attribute 'execute'` and surfaces it as an opaque `isError: true` response — with no hint that the problem is server initialization, not a bad request.

**Suggested fix:** add a one-line guard at the top of each tool (or a shared getter):

```python
def _get_conn() -> sqlite3.Connection:
    if _conn is None:
        raise RuntimeError("database connection not initialized")
    return _conn
```

Then replace each `_conn` argument with `_get_conn()`. Four lines total across the three tools.

---

### 2. `pyproject.toml:13-18` — `pydantic` not declared as a direct dependency

`tools.py:8` does `from pydantic import Field`. Pydantic is not listed in `[project].dependencies`; it arrives transitively through `mcp` (FastMCP requires Pydantic). This works today but is fragile: if `mcp` ever reorganizes its extras or FastMCP moves to a Pydantic-optional model, `tools.py` silently breaks. Explicit imports should have explicit dependencies.

**Suggested fix:** add `"pydantic>=2.0"` to `[project].dependencies`.

---

## Nit / suggestion

- **`storage.py:105`** — `except Exception` in `decode_cursor` is broader than necessary. All realistic decode-path failures (`base64.Error` → subclass of `ValueError`; `json.JSONDecodeError` → subclass of `ValueError`; missing key → `KeyError`; bad int cast → `ValueError`) are covered by `except (ValueError, KeyError)`. The bare `except Exception` hides unexpected errors (e.g., an OOM during JSON parse) that should probably propagate.

- **`logging.py:29`** — `get_logger()` has no return type annotation. `-> structlog.stdlib.BoundLogger` (or the more precise `structlog.BoundLogger`) would help IDEs and type checkers downstream.

- **`pyproject.toml:23`** — `dev` extras only declare `pytest>=8.0`. The upcoming test tasks (T-11/T-12/T-13) use the FastMCP async test client, which will need `pytest-asyncio` or `anyio[trio]` (depending on how FastMCP's `Client` runs its event loop). Flag this before running `generate-tests` so the right runner is added from the start.

---

## What's correct and well-done

- **Schema SQL:** `CREATE TABLE/VIRTUAL TABLE/TRIGGER/INDEX IF NOT EXISTS` guards are all present; `executescript` + `commit` on `open_db()` is idempotent and safe.
- **FTS5 sync:** All three triggers (`notes_ai`, `notes_ad`, `notes_au`) correctly use the external-content delete + re-insert pattern for updates.
- **Cursor encoding:** The `(-len(cursor) % 4)` padding formula is correct; `decode_cursor` raises `ValueError` on any malformed input — no silent fallback.
- **`list_notes` pagination:** `fetch limit+1` to detect next page with no `COUNT(*)` is correct. Row-value comparison `(created_at, id) < (?, ?)` works on SQLite ≥ 3.15 (Python 3.11 ships ≥ 3.39).
- **`search_notes` ordering:** `ORDER BY bm25(notes_fts) ASC` is correct — bm25 returns negative values, more negative = better match.
- **Logging discipline:** Tools log `query_len` and `result_count` only — never raw query text or body. All log output goes to `sys.stderr`. stdout is kept clean for MCP wire framing.
- **UNC path rejection:** `open_db()` rejects `\\` and `//` prefixes after `pathlib.Path` normalization, which is the right layer to check (Path normalizes `//server/share` → `\\server\share` on Windows, caught by the `\\\\` guard).
- **`RETURNING id, created_at`:** Used correctly; no `last_insert_rowid()`.
- **`reindex()`:** Uses `INSERT INTO notes_fts(notes_fts) VALUES('rebuild')` — not DROP+recreate — correct per FTS5 spec.

---

## Verdict

**approve-with-comments** — no blockers; two should-fix items (unguarded `_conn` and implicit pydantic dependency) worth addressing before the test phase to avoid confusing failures during T-11/T-12/T-13.
