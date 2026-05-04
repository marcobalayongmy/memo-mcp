from __future__ import annotations

import base64
import json
import os
import pathlib
import sqlite3

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS notes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    body       TEXT    NOT NULL
                       CHECK(length(trim(body)) > 0)
                       CHECK(length(body) <= 10000),
    tags       TEXT,
    created_at TEXT    NOT NULL
                       DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts
    USING fts5(
        body,
        content='notes',
        content_rowid='id'
    );

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

CREATE INDEX IF NOT EXISTS idx_notes_created_at_id
    ON notes(created_at DESC, id DESC);
"""


def open_db(db_path: str | None = None) -> sqlite3.Connection:
    raw_path = db_path or os.environ.get("MEMO_MCP_DB_PATH")
    path = (
        pathlib.Path(raw_path)
        if raw_path
        else pathlib.Path.home() / ".memo-mcp" / "notes.db"
    )

    path_str = str(path)
    if path_str.startswith("\\\\") or path_str.startswith("//"):
        raise ValueError(
            f"MEMO_MCP_DB_PATH must be a local filesystem path, "
            f"not a network share: {path}"
        )

    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")

    conn.executescript(_SCHEMA_SQL)
    conn.commit()
    return conn


def add_note(conn: sqlite3.Connection, body: str) -> dict:
    if not body.strip():
        raise ValueError("body must not be empty")
    if len(body) > 10000:
        raise ValueError("body must not exceed 10,000 characters")
    row = conn.execute(
        "INSERT INTO notes(body) VALUES(?) RETURNING id, created_at",
        (body,),
    ).fetchone()
    conn.commit()
    return {"id": row["id"], "created_at": row["created_at"]}


def encode_cursor(created_at: str, id: int) -> str:
    payload = json.dumps({"c": created_at, "i": id}, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode()).decode()


def decode_cursor(cursor: str) -> tuple[str, int]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded).decode())
        return data["c"], int(data["i"])
    except Exception:
        raise ValueError("invalid cursor")


def list_notes(
    conn: sqlite3.Connection,
    limit: int = 20,
    cursor: str | None = None,
) -> dict:
    if limit > 100:
        raise ValueError("limit must not exceed 100")
    if cursor is not None:
        cursor_created_at, cursor_id = decode_cursor(cursor)
        rows = conn.execute(
            """
            SELECT id, body, created_at FROM notes
            WHERE (created_at, id) < (?, ?)
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (cursor_created_at, cursor_id, limit + 1),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, body, created_at FROM notes
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (limit + 1,),
        ).fetchall()
    notes = [dict(row) for row in rows[:limit]]
    next_cursor = None
    if len(rows) > limit:
        last = notes[-1]
        next_cursor = encode_cursor(last["created_at"], last["id"])
    return {"notes": notes, "next_cursor": next_cursor}


def search_notes(
    conn: sqlite3.Connection,
    query: str,
    limit: int = 10,
) -> dict:
    if limit > 20:
        raise ValueError("limit must not exceed 20")
    rows = conn.execute(
        """
        SELECT n.id, n.body, n.created_at
        FROM notes_fts
        JOIN notes n ON notes_fts.rowid = n.id
        WHERE notes_fts MATCH ?
        ORDER BY bm25(notes_fts) ASC, n.created_at DESC
        LIMIT ?
        """,
        (query, limit),
    ).fetchall()
    notes = [dict(row) for row in rows]
    return {"notes": notes, "count": len(notes)}


def reindex(conn: sqlite3.Connection) -> int:
    conn.execute("INSERT INTO notes_fts(notes_fts) VALUES('rebuild')")
    conn.commit()
    return conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
