from __future__ import annotations

import json
import sqlite3
import time
from typing import Annotated

from pydantic import Field

from memo_mcp import storage
from memo_mcp.logging import get_logger
from memo_mcp.server import mcp

_conn: sqlite3.Connection | None = None


def _get_conn() -> sqlite3.Connection:
    if _conn is None:
        raise RuntimeError("database connection not initialized")
    return _conn


@mcp.tool(name="notes.add")
async def notes_add(
    body: Annotated[
        str,
        Field(description="The note text to save. Plain text, max 10,000 characters.", max_length=10000),
    ],
) -> str:
    t0 = time.perf_counter()
    body = body.strip()
    if not body:
        raise ValueError("body must not be empty")
    result = storage.add_note(_get_conn(), body)
    get_logger().info(
        "notes.add",
        note_id=result["id"],
        duration_ms=int((time.perf_counter() - t0) * 1000),
    )
    return f"Note {result['id']} saved ({result['created_at']})"


@mcp.tool(name="notes.search")
async def notes_search(
    query: Annotated[
        str,
        Field(description="Full-text search query. FTS5 syntax is supported.", max_length=500),
    ],
    limit: Annotated[
        int,
        Field(description="Maximum number of results to return.", ge=1, le=20),
    ] = 10,
) -> str:
    t0 = time.perf_counter()
    query = query.strip()
    if not query:
        raise ValueError("query must not be empty")
    result = storage.search_notes(_get_conn(), query, limit)
    get_logger().info(
        "notes.search",
        query_len=len(query),
        result_count=result["count"],
        duration_ms=int((time.perf_counter() - t0) * 1000),
    )
    return json.dumps(result)


@mcp.tool(name="notes.list")
async def notes_list(
    limit: Annotated[
        int,
        Field(description="Maximum number of notes to return.", ge=1, le=100),
    ] = 20,
    cursor: Annotated[
        str | None,
        Field(description="Pagination cursor returned by a previous notes.list call."),
    ] = None,
) -> str:
    t0 = time.perf_counter()
    result = storage.list_notes(_get_conn(), limit, cursor)
    get_logger().info(
        "notes.list",
        result_count=len(result["notes"]),
        has_cursor=cursor is not None,
        has_next_cursor=result["next_cursor"] is not None,
        duration_ms=int((time.perf_counter() - t0) * 1000),
    )
    return json.dumps(result)
