# Technical Research — memo-mcp stack confirmation (2026-05-01 07:35)

> **Research date matters.** The `mcp` SDK is on a fast release cadence (v1.27.0 as of April 2026; v2 pre-alpha in development). Re-run this research if more than 4 weeks have passed before you start T10.

---

## Question
- **For use case:** Confirm the exact APIs, patterns, and configuration needed to build and ship memo-mcp — a Python stdio MCP server backed by SQLite/FTS5 — without hitting avoidable dead-ends during implementation.
- **Constraints:** Python 3.11/3.12, single-writer local SQLite on Windows, Typer CLI, pip-installable PyPI package, no long-lived secrets in CI.
- **Criteria:** correctness (does it actually work as documented), sharp edges (what will break silently), recency (version-locked evidence, not old blog posts).

---

## Area 1 — Python `mcp` SDK

### Findings

**Current version:** `1.27.0` (released 2026-04-02). v2 pre-alpha is in development; do not use it.

**Two APIs available:**

| API | Import | Verbosity | Recommendation |
|-----|--------|-----------|----------------|
| Low-level `Server` | `mcp.server.lowlevel.Server` | Verbose; manual `list_tools` + `call_tool` decorators, explicit `run()` + `stdio_server()` context manager | Use only if you need fine-grained control |
| High-level `FastMCP` | `mcp.server.fastmcp.FastMCP` | Minimal boilerplate; tools registered with `@mcp.tool()` | **Use this for memo-mcp** |

**Minimal FastMCP stdio server:**
```python
from mcp.server.fastmcp import FastMCP
import asyncio

mcp = FastMCP(name="memo")

@mcp.tool()
async def add_note(body: str) -> str:
    """Add a note."""
    # ... storage call ...
    return "Note added."

# Entry point
asyncio.run(mcp.run())  # defaults to stdio transport
```

**Typer + asyncio.run pattern — confirmed working:**
```python
import typer, asyncio
from mcp.server.fastmcp import FastMCP

app = typer.Typer()
mcp_server = FastMCP(name="memo")

@mcp_server.tool()
async def add_note(body: str) -> str: ...

@app.command()
def serve():
    """Start the MCP server on stdio."""
    asyncio.run(mcp_server.run())

@app.command()
def reindex():
    """Rebuild the FTS5 index."""
    ...  # synchronous; no asyncio needed
```

**Sharp edges:**

| Edge | Impact | Mitigation |
|------|--------|------------|
| Any `print()` or stray stdout write corrupts the MCP framing | Silent parse failure in Claude Desktop | Bind all loggers to stderr; assert in tests that stdout is empty during a tool call |
| `multiprocessing` hangs under stdio transport ([#817](https://github.com/modelcontextprotocol/python-sdk/issues/817)) | N/A for memo-mcp (no multiprocessing planned) | Don't use `multiprocessing`; `subprocess` is fine |
| `stdio_client` can hang on init on some systems ([#1452](https://github.com/modelcontextprotocol/python-sdk/issues/1452)) | Intermittent test flakiness | Use in-process integration tests via the FastMCP test client rather than spawning a subprocess |

**Sources:**
- https://github.com/modelcontextprotocol/python-sdk/releases/tag/v1.27.0
- https://github.com/modelcontextprotocol/python-sdk/issues/817
- https://github.com/modelcontextprotocol/python-sdk/issues/1452

---

## Area 2 — SQLite FTS5 (external-content + WAL)

### Findings

**Schema (memo-mcp has `body` only, no `title`):**
```sql
CREATE TABLE notes (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    body      TEXT    NOT NULL,
    tags      TEXT,                    -- reserved, not exposed in v0.1.0
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE VIRTUAL TABLE notes_fts
    USING fts5(body, content='notes', content_rowid='id');

-- Keep FTS in sync with notes
CREATE TRIGGER notes_ai AFTER INSERT ON notes BEGIN
    INSERT INTO notes_fts(rowid, body) VALUES (new.id, new.body);
END;

CREATE TRIGGER notes_ad AFTER DELETE ON notes BEGIN
    INSERT INTO notes_fts(notes_fts, rowid, body) VALUES ('delete', old.id, old.body);
END;

CREATE TRIGGER notes_au AFTER UPDATE ON notes BEGIN
    INSERT INTO notes_fts(notes_fts, rowid, body) VALUES ('delete', old.id, old.body);
    INSERT INTO notes_fts(rowid, body) VALUES (new.id, new.body);
END;
```

**bm25 ranking query:**

SQLite's `bm25()` returns **negative** values (more negative = better match). Order `ASC` for best-first:
```sql
SELECT n.id, n.body, n.created_at, bm25(notes_fts) AS rank
FROM notes_fts
JOIN notes n ON notes_fts.rowid = n.id
WHERE notes_fts MATCH ?
ORDER BY rank ASC
LIMIT ?;
```

**WAL mode — confirmed safe on Windows:**
- WAL uses shared-memory primitives supported by the Windows VFS.
- Only one writer at a time; readers never block writers.
- **Hard caveat:** WAL does not work over network shares (UNC paths). `MEMO_MCP_DB_PATH` must point to a local filesystem path.
- Set on every connection open (not persistent across restarts):
```python
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA busy_timeout=5000")  # 5 s retry window
```

**busy_timeout=5000 — confirmed appropriate:**
- Default is 0 (instant `SQLITE_BUSY`); 5 000 ms is a standard production choice for a local single-writer scenario.
- **Must be set per connection** — it does not persist.
- Caveat: `BEGIN IMMEDIATE` transactions cannot benefit from busy_timeout retry; use plain `BEGIN` (deferred) for reads and rely on the write lock being acquired naturally.

**Sources:**
- https://www.sqlite.org/fts5.html
- https://www.sqlite.org/wal.html
- https://www.sqlite.org/c3ref/busy_timeout.html
- https://abdus.dev/posts/quick-full-text-search-using-sqlite/

---

## Area 3 — PyPI OIDC Trusted Publishing

### Findings

**`pyproject.toml` (minimal required fields):**
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "memo-mcp"
version = "0.1.0"
description = "A personal notes MCP server for Claude Desktop"
readme = "README.md"
requires-python = ">=3.11"
license = { text = "MIT" }
authors = [{ name = "Marco", email = "marcobalayong@gmail.com" }]
dependencies = [
    "mcp>=1.27.0",
    "typer>=0.12",
    "structlog>=24.0",
]

[project.scripts]
memo-mcp = "memo_mcp.cli:app"

[tool.hatch.build.targets.wheel]
packages = ["src/memo_mcp"]
```

**GitHub Actions publish workflow (OIDC, no stored token):**
```yaml
name: publish

on:
  push:
    tags: ["v*"]

jobs:
  build-and-publish:
    runs-on: ubuntu-latest
    environment: publish          # optional but adds a manual approval gate
    permissions:
      id-token: write             # required for OIDC
      contents: read

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.x"
      - run: pip install build
      - run: python -m build
      - uses: pypa/gh-action-pypi-publish@release/v1
        # No `password:` needed — OIDC handles auth
```

**PyPI side setup (one-time, before first tag):**
1. Log in to pypi.org → Your projects → "Add project" (or publish manually once to claim the name).
2. Go to the project → **Publishing** → **Add a new publisher**.
3. Set: Publisher = GitHub, Repository = `<user>/memo-mcp`, Workflow = `publish.yml`, Environment = `publish`.

**First-publish gotcha:** PyPI trusted publishing cannot create a *new* project — only publish to an existing one. You must either (a) publish a `0.0.1a0` manually via `twine` or `uv publish` to claim the name first, or (b) use the "pending publisher" feature (pypi.org supports registering a trusted publisher before the project exists — check current docs at `docs.pypi.org/trusted-publishers/`).

**Recommended approach for T15:** publish `0.0.1a0` to TestPyPI first via the same workflow pointed at `repository-url: https://test.pypi.org/legacy/` to prove the pipeline, then cut `v0.1.0` to real PyPI.

**Sources:**
- https://docs.pypi.org/trusted-publishers/
- https://github.com/pypa/gh-action-pypi-publish
- https://docs.github.com/en/actions/security-for-github-actions/security-hardening-your-deployments/configuring-openid-connect-in-pypi

---

## Area 4 — Packaging: build backend recommendation

### Findings

| Backend | Status (2026) | Recommendation |
|---------|--------------|----------------|
| `hatchling` | Mature, stable, explicit `src/` layout support | Good default; more community examples |
| `uv_build` | New default for `uv init` since mid-2025; zero-config for pure Python | **Preferred for new projects** |

**Decision: use `uv_build`** — it is the pragmatic 2026 default for new pure-Python CLI packages, integrates tightly with `uv` for lockfile management, and requires no extra config for a `src/` layout.

**`pyproject.toml` with `uv_build`:**
```toml
[build-system]
requires = ["uv_build"]
build-backend = "uv_build"

[project.scripts]
memo-mcp = "memo_mcp.cli:app"    # Typer app object
```

**Note:** `pypa/gh-action-pypi-publish` works with any PEP 517 backend; no workflow change needed between hatchling and uv_build.

**Sources:**
- https://docs.astral.sh/uv/concepts/build-backend/
- https://packaging.python.org/en/latest/guides/writing-pyproject-toml/

---

## Consolidated decisions for memo-mcp

| Decision | Choice | Rationale |
|----------|--------|-----------|
| MCP API style | `FastMCP` (high-level) | 80% less boilerplate; same capability |
| Typer + asyncio | `asyncio.run(mcp_server.run())` in Typer command | Confirmed working |
| FTS5 approach | External-content + 3 triggers | Keeps FTS and source table in sync; standard pattern |
| bm25 sort | `ORDER BY bm25(notes_fts) ASC` | Negative score; ascending = best-first |
| WAL | `PRAGMA journal_mode=WAL` + `PRAGMA busy_timeout=5000` per connection | Safe on local Windows filesystem; not on network shares |
| Build backend | `uv_build` | 2026 default for new pure-Python packages |
| PyPI publish | OIDC trusted publishing via `pypa/gh-action-pypi-publish` | No stored secrets |
| First publish | TestPyPI dry-run at `0.0.1a0`, then real PyPI at `v0.1.0` | Shakes out OIDC pipeline before the real tag |

## Risks of these choices

- **FastMCP v2 API break:** the SDK team is building v2; FastMCP's interface may change. Mitigation: pin `mcp>=1.27.0,<2.0` in `pyproject.toml`.
- **uv_build immaturity:** `uv_build` is newer than hatchling. If it causes unexpected issues (e.g., editable install quirks during dev), fallback to `hatchling` — the switch is two lines in `pyproject.toml`.
- **WAL on network path:** if the user ever moves `MEMO_MCP_DB_PATH` to a network share, WAL will silently fail. Add a startup check: `if not os.path.isabs(db_path) or not pathlib.Path(db_path).drive: warn`.
- **stdout corruption is silent:** Claude Desktop will simply stop calling tools without a useful error. The test coverage in T13 (assert stdout empty during tool call) is the only safety net.

## Sources (index)
1. https://github.com/modelcontextprotocol/python-sdk/releases/tag/v1.27.0
2. https://github.com/modelcontextprotocol/python-sdk/issues/817
3. https://github.com/modelcontextprotocol/python-sdk/issues/1452
4. https://www.sqlite.org/fts5.html
5. https://www.sqlite.org/wal.html
6. https://www.sqlite.org/c3ref/busy_timeout.html
7. https://abdus.dev/posts/quick-full-text-search-using-sqlite/
8. https://docs.pypi.org/trusted-publishers/
9. https://github.com/pypa/gh-action-pypi-publish
10. https://docs.astral.sh/uv/concepts/build-backend/
11. https://packaging.python.org/en/latest/guides/writing-pyproject-toml/
