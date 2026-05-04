# API Design — memo-mcp MCP Tools (2026-05-01 09:00)

---

## Overview

Three MCP tools exposed via a FastMCP stdio server. The caller is Claude Desktop (the MCP host); the end user directs Claude in natural language. Tools are registered with `@mcp.tool(name="notes.<action>")` decorators; FastMCP derives JSON Schema from Python type hints + Pydantic `Field` annotations.

All timestamps are UTC ISO-8601 strings. All business-logic errors return `isError: true` in the tool result (not a JSON-RPC protocol error). There is no authentication — single-user local server.

---

## Style and conventions

| Dimension | Choice | Rationale |
|-----------|--------|-----------|
| Tool naming | `notes.<action>` dot-namespace | Groups tools visually in Claude Desktop; consistent with MCP community conventions |
| Error delivery | `isError: true` + plain-English message in `content[0].text` | FastMCP catches raised exceptions and sets `isError`; Claude reads the message |
| Success content | JSON-serialized Python dict/list in `content[0].text` | FastMCP default; Claude parses the JSON from the text block |
| Timestamps | `TEXT` in ISO-8601 UTC, e.g. `2026-05-01T09:01:23Z` | SQLite has no native timestamp type; ISO-8601 sorts lexicographically |
| Cursor | Opaque base64 string encoding `{"c": created_at, "i": id}` | Hides pagination internals; safe to transmit as a JSON string value |
| Validation | Pydantic `Annotated[str, Field(...)]` on inputs | FastMCP exposes constraints in the tool's JSON Schema, so Claude knows bounds before calling |

---

## Tool list

| Tool name | Purpose | Size |
|-----------|---------|------|
| `notes.add` | Append a new plain-text note | S |
| `notes.search` | Full-text search, ranked by relevance | S |
| `notes.list` | Paginated list of notes, newest first | S |

---

## Tool schemas

### `notes.add`

**Purpose:** Append a new plain-text note to the personal store.

**When Claude should call it:** When the user says "remember", "save", "note down", "store", or similar.

#### Python registration

```python
from typing import Annotated
from pydantic import Field
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(name="memo")

@mcp.tool(name="notes.add")
async def notes_add(
    body: Annotated[
        str,
        Field(
            description="The plain-text content to save as a note.",
            min_length=1,
            max_length=10_000,
        ),
    ],
) -> dict:
    """
    Add a new plain-text note to your personal store.

    Returns the assigned note ID and creation timestamp on success.
    Raises an error if body is empty or exceeds 10,000 characters.
    """
    ...
```

#### JSON Schema (as registered with MCP host)

```json
{
  "name": "notes.add",
  "description": "Add a new plain-text note to your personal store.\n\nReturns the assigned note ID and creation timestamp on success.\nRaises an error if body is empty or exceeds 10,000 characters.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "body": {
        "type": "string",
        "description": "The plain-text content to save as a note.",
        "minLength": 1,
        "maxLength": 10000
      }
    },
    "required": ["body"]
  }
}
```

#### Success response

`isError: false`; `content[0].text` contains JSON:

```json
{
  "id": 42,
  "created_at": "2026-05-01T09:01:23Z"
}
```

#### Error responses

| Condition | `isError` | Message |
|-----------|-----------|---------|
| `body` is empty or whitespace-only | `true` | `"Note body must contain at least one non-whitespace character."` |
| `body` exceeds 10,000 characters | `true` | `"Note body exceeds the 10,000-character limit (got 10,452 characters). Consider splitting into multiple notes."` |
| DB write failure | `true` | `"Failed to save note: <sqlite error message>"` |

#### Implementation note

FastMCP's `min_length=1` enforces the constraint at the schema layer, but the implementation must also `strip()` and check for whitespace-only strings, since `" "` (a space) has `len == 1` but violates BR-1.

---

### `notes.search`

**Purpose:** Full-text search across all stored notes, ranked by BM25 relevance.

**When Claude should call it:** When the user asks to find, look up, recall, or search notes — any retrieval intent with a topic or keyword.

#### Python registration

```python
@mcp.tool(name="notes.search")
async def notes_search(
    query: Annotated[
        str,
        Field(
            description="Search terms or phrase. Supports FTS5 syntax: prefix wildcards (term*), phrase (\"exact phrase\"), Boolean (term1 OR term2).",
            min_length=1,
        ),
    ],
    limit: Annotated[
        int,
        Field(
            description="Maximum number of results to return. Default 10, max 20.",
            default=10,
            ge=1,
            le=20,
        ),
    ] = 10,
) -> list:
    """
    Search notes by keyword or phrase using full-text search.

    Results are returned in relevance order (most relevant first).
    Returns an empty list when nothing matches — not an error.
    Raises an error only if the query is empty or causes an unrecoverable FTS5 parse error.
    """
    ...
```

#### JSON Schema

```json
{
  "name": "notes.search",
  "description": "Search notes by keyword or phrase using full-text search.\n\nResults are returned in relevance order (most relevant first).\nReturns an empty list when nothing matches — not an error.\nRaises an error only if the query is empty or causes an unrecoverable FTS5 parse error.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "Search terms or phrase. Supports FTS5 syntax: prefix wildcards (term*), phrase (\"exact phrase\"), Boolean (term1 OR term2).",
        "minLength": 1
      },
      "limit": {
        "type": "integer",
        "description": "Maximum number of results to return. Default 10, max 20.",
        "default": 10,
        "minimum": 1,
        "maximum": 20
      }
    },
    "required": ["query"]
  }
}
```

#### Success response

`isError: false`; `content[0].text` contains JSON — an array (may be empty):

```json
[
  {
    "id": 42,
    "body": "Docker Compose v2 sets the project name from the directory name by default.",
    "created_at": "2026-05-01T09:01:23Z"
  },
  {
    "id": 17,
    "body": "Use docker compose --project-name to override the name.",
    "created_at": "2026-04-28T14:30:00Z"
  }
]
```

#### Error responses

| Condition | `isError` | Message |
|-----------|-----------|---------|
| `query` is empty or whitespace-only | `true` | `"Search query must not be empty."` |
| FTS5 unrecoverable parse error (after sanitisation) | `true` | `"Invalid search query: <fts5 error>. Try simpler terms or remove special characters."` |

#### FTS5 query handling

FTS5 special characters (`"`, `*`, `-`, `(`, `)`, `OR`, `AND`, `NOT`) are valid FTS5 operators and should be passed through as-is — this gives Claude advanced search capability. Only catch `sqlite3.OperationalError` and surface it as a user-friendly error. Do not sanitise or escape by default.

---

### `notes.list`

**Purpose:** Paginated list of all notes, newest first.

**When Claude should call it:** When the user asks to browse, list, or review recent notes without a specific search term.

#### Python registration

```python
@mcp.tool(name="notes.list")
async def notes_list(
    limit: Annotated[
        int,
        Field(
            description="Number of notes per page. Default 20, max 100.",
            default=20,
            ge=1,
            le=100,
        ),
    ] = 20,
    cursor: Annotated[
        str | None,
        Field(
            description="Pagination cursor from a previous notes.list response. Omit to start from the beginning.",
            default=None,
        ),
    ] = None,
) -> dict:
    """
    List notes, newest first.

    Returns up to `limit` notes per page plus a `next_cursor` for the next page.
    When `next_cursor` is null, you have reached the last page.
    Pass the cursor from the previous response to retrieve the next page.
    Raises an error if the cursor is malformed or invalid.
    """
    ...
```

#### JSON Schema

```json
{
  "name": "notes.list",
  "description": "List notes, newest first.\n\nReturns up to `limit` notes per page plus a `next_cursor` for the next page.\nWhen `next_cursor` is null, you have reached the last page.\nPass the cursor from the previous response to retrieve the next page.\nRaises an error if the cursor is malformed or invalid.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "limit": {
        "type": "integer",
        "description": "Number of notes per page. Default 20, max 100.",
        "default": 20,
        "minimum": 1,
        "maximum": 100
      },
      "cursor": {
        "anyOf": [{"type": "string"}, {"type": "null"}],
        "description": "Pagination cursor from a previous notes.list response. Omit to start from the beginning.",
        "default": null
      }
    },
    "required": []
  }
}
```

#### Success response

`isError: false`; `content[0].text` contains JSON:

```json
{
  "notes": [
    {
      "id": 42,
      "body": "DB migration runs on Fridays at 18:00 UTC.",
      "created_at": "2026-05-01T09:01:23Z"
    },
    {
      "id": 41,
      "body": "Use docker compose --project-name to override the name.",
      "created_at": "2026-04-28T14:30:00Z"
    }
  ],
  "next_cursor": "eyJjIjogIjIwMjYtMDQtMjhUMTQ6MzA6MDBaIiwgImkiOiA0MX0="
}
```

When on the last page, `next_cursor` is `null`:

```json
{
  "notes": [...],
  "next_cursor": null
}
```

When the store is empty:

```json
{
  "notes": [],
  "next_cursor": null
}
```

#### Error responses

| Condition | `isError` | Message |
|-----------|-----------|---------|
| `cursor` is malformed (invalid base64 or JSON) | `true` | `"Invalid pagination cursor. Call notes.list without a cursor to start from the beginning."` |
| `cursor` references a position that no longer exists | `true` | `"Pagination cursor is no longer valid (the referenced note may have been deleted). Call notes.list without a cursor to start from the beginning."` |

#### Cursor encoding

```python
import base64, json

def encode_cursor(created_at: str, note_id: int) -> str:
    payload = json.dumps({"c": created_at, "i": note_id}, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode()).decode()

def decode_cursor(cursor: str) -> tuple[str, int]:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return payload["c"], int(payload["i"])
    except Exception:
        raise ValueError("Invalid pagination cursor.")
```

The cursor encodes the `created_at` and `id` of the **last note on the current page**. The next-page query fetches notes strictly older than that position.

---

## Error model

All errors are delivered as MCP tool results with `isError: true`. The error message is in `content[0].text` as a plain-English string (not a JSON envelope). This matches FastMCP's default exception-handling behaviour.

```
isError: true
content: [{ "type": "text", "text": "<human-readable error message>" }]
```

**Rationale for plain text over JSON error envelope:** Claude reads the error message directly. A JSON envelope (`{"code": "INVALID_BODY", "message": "..."}`) adds parsing burden without benefit for a single-user personal tool. If error codes are needed later (e.g., for a client library), they can be added as a prefix: `"INVALID_CURSOR: ..."`.

**No protocol-level JSON-RPC errors** are raised for business-logic failures. JSON-RPC errors are reserved for server-level failures (tool not found, malformed request).

---

## Versioning

There is no URL versioning (this is a local stdio MCP server, not a REST API). The version contract is:

- **Additive changes** (new optional input fields, new response fields) are backwards-compatible and do not require a version bump.
- **Breaking changes** (removing fields, changing types, renaming tools) require a minor version bump (`0.1.x → 0.2.0`) and a CHANGELOG entry.
- Tool names (`notes.add`, `notes.search`, `notes.list`) are part of the public contract and must not change without a major version bump.
- The `mcp` SDK is pinned to `>=1.27.0,<2.0` to prevent silent breaking changes from the upstream SDK.

---

## Cross-cutting concerns

**Tool descriptions as the primary contract:** FastMCP exposes the Python docstring as the MCP tool description. These descriptions are what Claude Desktop presents to the model. They must be accurate and complete — they are the API documentation.

**stdout is reserved for MCP framing.** No `print()` statements anywhere in the server code. All logging goes to stderr via structlog. Any stdout write corrupts the MCP wire protocol silently.

**No auth / rate limiting:** Single-user local server. The OS process boundary is the only isolation.

**Observability fields (stderr log per call):**
```json
{
  "event": "tool_call",
  "tool": "notes.search",
  "request_id": "abc123",
  "duration_ms": 12,
  "outcome": "ok",
  "result_count": 3
}
```

---

## Open questions

None. All questions from T2 are resolved. T3 (this document) is the input to T5 (generate-technical-design).
