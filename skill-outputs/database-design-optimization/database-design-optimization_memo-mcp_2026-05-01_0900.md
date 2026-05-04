# Database Design / Optimization — memo-mcp v0.1.0 (2026-05-01 09:00)

---

## Engine

**SQLite** — version bundled with CPython:
- Python 3.11 → SQLite 3.39.2 (2022-07-21)
- Python 3.12 → SQLite 3.41.2 (2023-03-22)

Features used and their minimum SQLite version:
| Feature | Min version | Available |
|---------|-------------|-----------|
| FTS5 | 3.9.0 (2015) | ✓ |
| `RETURNING` clause | 3.35.0 (2021) | ✓ |
| WAL journal mode | 3.7.0 (2010) | ✓ |
| `IF NOT EXISTS` on virtual tables | 3.7.0 | ✓ |
| `CREATE TRIGGER IF NOT EXISTS` | 3.7.11 | ✓ |

No migration tooling is needed for v0.1.0 — the DB is created fresh on first write with `IF NOT EXISTS` guards.

---

## Schema

### `notes` table

```sql
CREATE TABLE IF NOT EXISTS notes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    body       TEXT    NOT NULL
                       CHECK(length(trim(body)) > 0)
                       CHECK(length(body) <= 10000),
    tags       TEXT,                          -- reserved; not exposed in v0.1.0
    created_at TEXT    NOT NULL
                       DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
```

**Field notes:**

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | INTEGER | PK, AUTOINCREMENT | Surrogate key; AUTOINCREMENT prevents ID reuse after deletion (safe for cursors) |
| `body` | TEXT | NOT NULL, CHECK trim > 0, CHECK len ≤ 10000 | DB-layer enforcement is defence-in-depth; app layer validates first |
| `tags` | TEXT | NULL | Reserved for v0.1.1; never read or written in v0.1.0 |
| `created_at` | TEXT | NOT NULL, DEFAULT UTC | ISO-8601 UTC string; lexicographic sort equals chronological sort |

**Why `AUTOINCREMENT`?** Without it, SQLite may reuse IDs from deleted rows. Since v0.1.1 will add soft-delete, reused IDs could cause cursor confusion. `AUTOINCREMENT` adds a minor overhead (one extra write to `sqlite_sequence`) but guarantees monotone IDs.

**Why two `CHECK` constraints instead of one?** Separating them produces a cleaner error message: a whitespace-only body fails `trim(body) > 0` with a distinct error from a body that is too long.

---

### FTS5 virtual table

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts
    USING fts5(
        body,
        content='notes',
        content_rowid='id'
    );
```

**Configuration:**
- `content='notes'` — external-content mode: FTS5 stores only the index, not the body text; source of truth is always `notes.body`.
- `content_rowid='id'` — maps FTS rowid to `notes.id`.
- Default tokenizer: `unicode61` — handles accented characters and non-ASCII scripts correctly (covers CJK, Arabic, etc.).
- No `tokenize=` override needed for v0.1.0.

**Why external-content instead of storing body in FTS?** Avoids body duplication on disk. The tradeoff is that the triggers below are required to keep the index in sync; `reindex` recovers from any sync drift.

---

### Sync triggers

These three triggers keep `notes_fts` in sync with `notes` automatically. Without them, external-content FTS5 goes stale silently.

```sql
CREATE TRIGGER IF NOT EXISTS notes_ai
    AFTER INSERT ON notes
BEGIN
    INSERT INTO notes_fts(rowid, body) VALUES (new.id, new.body);
END;

CREATE TRIGGER IF NOT EXISTS notes_ad
    AFTER DELETE ON notes
BEGIN
    INSERT INTO notes_fts(notes_fts, rowid, body)
        VALUES ('delete', old.id, old.body);
END;

CREATE TRIGGER IF NOT EXISTS notes_au
    AFTER UPDATE ON notes
BEGIN
    INSERT INTO notes_fts(notes_fts, rowid, body)
        VALUES ('delete', old.id, old.body);
    INSERT INTO notes_fts(rowid, body)
        VALUES (new.id, new.body);
END;
```

**v0.1.0 note:** `notes.add` is the only write tool; UPDATE and DELETE triggers are not exercised in v0.1.0 but are included so the schema is correct for v0.1.1 soft-delete from day one.

---

### Index

```sql
CREATE INDEX IF NOT EXISTS idx_notes_created_at_id
    ON notes(created_at DESC, id DESC);
```

**Purpose:** Supports the `notes.list` cursor pagination query. Without this index, the `ORDER BY created_at DESC, id DESC` forces a full table scan + sort on every page.

**Why a composite index on (created_at, id) and not just (created_at)?** Two notes added within the same second share a `created_at` value. The `id` suffix provides a deterministic tiebreaker and prevents gaps or duplicates between pages.

**notes.search index:** FTS5 maintains its own inverted index internally. No additional index is needed for search queries.

---

## Initialization sequence

Run once per connection open, in this order:

```python
import sqlite3, pathlib, os

def open_db(db_path: str | None = None) -> sqlite3.Connection:
    path = pathlib.Path(db_path or os.environ.get("MEMO_MCP_DB_PATH") or
                        pathlib.Path.home() / ".memo-mcp" / "notes.db")

    # Reject network shares (WAL does not work on UNC paths)
    raw = str(path)
    if raw.startswith("\\\\") or raw.startswith("//"):
        raise ValueError(
            f"MEMO_MCP_DB_PATH must be a local filesystem path, not a network share: {path}"
        )

    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row

    # Must be set before any transaction; not persistent across connections
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")

    # Schema creation (idempotent)
    conn.executescript(_SCHEMA_SQL)
    conn.commit()
    return conn
```

`_SCHEMA_SQL` contains all the `CREATE TABLE / VIRTUAL TABLE / TRIGGER / INDEX IF NOT EXISTS` statements above, in dependency order: table first, then virtual table, then triggers, then index.

**Server process:** call `open_db()` once at startup; reuse the connection for all tool calls (SQLite handles concurrent reads safely in WAL mode).

**reindex CLI:** call `open_db()` as its own connection; it shares the WAL with the server connection.

---

## Query patterns

### `notes.add`

```python
async def add_note(conn: sqlite3.Connection, body: str) -> dict:
    row = conn.execute(
        "INSERT INTO notes(body) VALUES (?) RETURNING id, created_at",
        (body,)
    ).fetchone()
    conn.commit()
    return {"id": row["id"], "created_at": row["created_at"]}
```

`RETURNING` eliminates the `last_insert_rowid()` call. The INSERT trigger fires inside the same transaction before `RETURNING` returns, so FTS is in sync before the commit.

---

### `notes.search`

```python
async def search_notes(conn: sqlite3.Connection, query: str, limit: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT n.id, n.body, n.created_at
        FROM   notes_fts
        JOIN   notes n ON notes_fts.rowid = n.id
        WHERE  notes_fts MATCH ?
        ORDER  BY bm25(notes_fts) ASC   -- negative scores; ASC = best first
        LIMIT  ?
        """,
        (query, limit),
    ).fetchall()
    return [dict(r) for r in rows]
```

**bm25 sort direction:** SQLite's `bm25()` returns negative values (more negative = better match). `ORDER BY bm25(notes_fts) ASC` puts the best match first.

**FTS5 special characters:** Pass `query` directly to MATCH — this enables FTS5 syntax (`term*`, `"phrase"`, `term1 OR term2`). Catch `sqlite3.OperationalError` and re-raise as a user-facing error.

**No score in response:** bm25 value is not included in the returned rows (BR-16). Log it to stderr if needed for debugging.

---

### `notes.list`

```python
async def list_notes(
    conn: sqlite3.Connection,
    limit: int,
    cursor: str | None,
) -> dict:
    fetch_n = limit + 1  # fetch one extra to detect next page

    if cursor is None:
        rows = conn.execute(
            """
            SELECT id, body, created_at
            FROM   notes
            ORDER  BY created_at DESC, id DESC
            LIMIT  ?
            """,
            (fetch_n,),
        ).fetchall()
    else:
        cur_created_at, cur_id = decode_cursor(cursor)  # raises ValueError on bad cursor
        rows = conn.execute(
            """
            SELECT id, body, created_at
            FROM   notes
            WHERE  (created_at < ? OR (created_at = ? AND id < ?))
            ORDER  BY created_at DESC, id DESC
            LIMIT  ?
            """,
            (cur_created_at, cur_created_at, cur_id, fetch_n),
        ).fetchall()

    notes = [dict(r) for r in rows[:limit]]
    next_cursor = None
    if len(rows) == fetch_n:
        last = rows[limit - 1]
        next_cursor = encode_cursor(last["created_at"], last["id"])

    return {"notes": notes, "next_cursor": next_cursor}
```

**Fetch-N+1 pattern:** Fetching `limit + 1` rows tells us whether a next page exists without a separate `COUNT(*)` query. We return exactly `limit` rows to the caller.

**Cursor position:** The cursor encodes the **last row returned on the current page** (index `limit - 1`, not `limit`). The next-page query uses `<` / `=` to fetch rows strictly after that position.

**Why `(created_at < ? OR (created_at = ? AND id < ?))`?** SQLite row-value comparisons (`(created_at, id) < (?, ?)`) are supported since 3.15.0 (2016), but the explicit form is more readable and equally efficient with the composite index.

---

### `memo-mcp reindex`

```python
def reindex(conn: sqlite3.Connection) -> int:
    """Rebuild notes_fts from notes. Returns the note count."""
    conn.execute("INSERT INTO notes_fts(notes_fts) VALUES('rebuild')")
    conn.commit()
    count = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
    return count
```

**`'rebuild'` command:** FTS5 built-in command that atomically drops and rebuilds the index from the content table. Simpler and safer than `DROP VIRTUAL TABLE` + recreate.

**Does not auto-create DB:** `reindex` is called only when a DB already exists (enforced at the CLI level before calling this function). If the DB file is absent, the CLI prints an error and exits 1.

**Concurrency safety:** In WAL mode, `reindex` takes a write lock for the duration of the rebuild. The server's reads proceed concurrently. Any server write that arrives during rebuild waits up to 5,000 ms (`busy_timeout`) then raises an error (extremely unlikely in practice for a personal tool).

---

## WAL and concurrency summary

| Scenario | Behaviour |
|----------|-----------|
| Server serving a tool call + server concurrently receiving another | Read-write or write-write: SQLite queues the second write; `busy_timeout=5000` prevents instant error |
| Server running + `reindex` CLI running | `reindex` holds a write lock during rebuild; server reads proceed; server writes wait up to 5s |
| Two `reindex` runs at once | Second process waits up to 5s for the write lock; succeeds after first completes |
| DB path on a network share (UNC path) | Rejected at startup with a clear error; WAL requires kernel shared-memory, unavailable on SMB/NFS |

---

## Migration plan

### v0.1.0 (initial)
No migration tooling. DB created fresh on first write via `executescript` with `IF NOT EXISTS` guards.

### v0.1.1 (soft-delete — planned)
```sql
ALTER TABLE notes ADD COLUMN deleted_at TEXT;  -- NULL = not deleted
```
SQLite `ALTER TABLE ADD COLUMN` is an online operation (no table rewrite). The FTS triggers need updating to exclude soft-deleted rows from results — handled by modifying the `notes.search` query to `WHERE notes_fts MATCH ? AND n.deleted_at IS NULL`.

No migration tool is needed for v0.1.1 either — a single `ALTER TABLE` statement run at server startup (guarded by checking `PRAGMA table_info(notes)`) is sufficient.

---

## Findings summary

| Category | Finding | Action |
|----------|---------|--------|
| Schema | Body constraints at both app and DB layers | Both CHECK constraints included (defence in depth) |
| Schema | `tags` column present but unused | Documented; no access in v0.1.0 |
| Index | Full table scan on `notes.list` without composite index | `idx_notes_created_at_id ON notes(created_at DESC, id DESC)` added |
| FTS | External-content table requires trigger maintenance | All three triggers (INSERT/UPDATE/DELETE) included |
| FTS | `bm25()` returns negative scores | `ORDER BY bm25(notes_fts) ASC` (best first) |
| WAL | Network share paths silently fail | Startup path check rejects UNC paths with clear error |
| reindex | DROP + recreate is fragile | Use FTS5 `'rebuild'` command instead |
| Soft-delete | Not in v0.1.0 but schema should accommodate it | `AUTOINCREMENT` on `id` prevents ID reuse; `deleted_at` column added in v0.1.1 via safe `ALTER TABLE` |

---

## Open questions

None. All schema decisions are locked in from T1 (technical-research) and T2 (functional-design). This document is the input to T5 (generate-technical-design) alongside T3 (api-design).
