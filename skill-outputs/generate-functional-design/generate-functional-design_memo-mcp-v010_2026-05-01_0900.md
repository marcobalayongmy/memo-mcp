# Functional Design — memo-mcp v0.1.0 (2026-05-01 09:00)

---

## 1. Problem and goal

**Problem:** When working in Claude Desktop, there is no persistent memory across sessions. Notes, decisions, reminders, and snippets that come up during a conversation disappear when the session ends. Copying them into a separate app breaks the flow, and no existing tool lets Claude itself store and retrieve plain-text notes on the user's behalf without leaving the chat.

**Goal (user):** Be able to say "remember this" or "what did I note about X?" inside Claude Desktop and have it work — reliably and without leaving the interface.

**Goal (business/project):** Publish `pip install memo-mcp` as a self-contained stdio MCP server that Claude Desktop can launch locally, backed by a personal SQLite database, with no external dependencies or authentication.

**Success metric:** After `pip install memo-mcp` and one config line in Claude Desktop, the user can add a note, search it back up, and list recent notes — all within a Claude conversation — with zero data loss across restarts.

---

## 2. Scope

### In scope (v0.1.0)
- `notes.add` — append a plain-text note to the local store
- `notes.search` — full-text search across all stored notes, ranked by relevance
- `notes.list` — paginated list of stored notes, newest first
- `memo-mcp reindex` — CLI command to rebuild the FTS5 index from the source table
- Single-user, local-only storage (SQLite on the user's machine)
- Structured JSON logs to stderr for each tool call
- Ships as a PyPI package (`memo-mcp`), runnable as a stdio MCP server

### Out of scope (v0.1.0)
- Editing or deleting notes
- Tagging / categorising notes (schema column reserved; not exposed)
- Semantic / embedding-based search
- Multi-user or shared storage
- Web UI, desktop GUI, or mobile
- Authentication or encryption
- Sync across devices
- Offset-based pagination
- Attachments / binary content
- Export / import (e.g., JSON dump)
- Windows installer or tray app

---

## 3. Users and personas

**Primary — Marco (the note-taker):** A developer using Claude Desktop as a daily AI assistant. Wants to offload transient thoughts, decisions, and snippets into a searchable store without switching apps. Technically comfortable (can run `pip install` and edit a JSON config); does not want to manage a database manually.

**Secondary — Claude (the MCP client):** The AI model that calls the MCP tools on Marco's behalf. Claude is the caller of `notes.add`, `notes.search`, and `notes.list` — it translates natural-language requests ("remember this", "find my note about X") into structured tool calls. Claude must receive clear, machine-readable responses to incorporate into its replies.

**Operator — Claude Desktop:** The process that launches `memo-mcp serve` via stdio and routes tool calls. Its config (`claude_desktop_config.json`) determines the server launch command and environment.

---

## 4. User flows

### 4.1 Add a note

**Trigger:** Marco tells Claude to save something (e.g., "remember that the DB migration runs on Fridays").

```
1. Marco sends a message to Claude asking it to remember something.
2. Claude calls notes.add with the note body.
3. The server writes the note to the SQLite notes table; triggers update notes_fts.
4. The server returns a confirmation with the assigned note ID.
5. Claude relays the confirmation to Marco ("Got it, I've saved that as note #42.").
```

**Variations:**
- Empty body → tool returns an error; Claude tells Marco it needs content to save.
- Body exceeds maximum length → tool returns an error with the limit; Claude offers to split it.
- DB file does not exist yet → server creates it automatically on first write.

---

### 4.2 Search notes

**Trigger:** Marco asks Claude to find something he noted previously (e.g., "what did I save about Docker Compose?").

```
1. Marco sends a message to Claude asking about a past note.
2. Claude calls notes.search with a query string (e.g., "Docker Compose").
3. The server runs an FTS5 MATCH query, ranks results by bm25, returns top matches.
4. Claude presents the matching notes to Marco.
```

**Variations:**
- Empty/whitespace-only query → tool returns an error; Claude asks Marco what to search for.
- No matches → tool returns an empty list; Claude tells Marco nothing was found.
- Many matches → tool returns the top N results (default 10, caller may specify limit); Marco can ask Claude to narrow the search.
- Query contains FTS5 special characters (e.g., `"`, `*`, `-`) → server sanitises or escapes before passing to FTS5; never returns a 500.

---

### 4.3 List recent notes

**Trigger:** Marco asks Claude to show recent notes (e.g., "what have I saved this week?").

```
1. Marco asks Claude to list recent notes.
2. Claude calls notes.list (no cursor → first page; default limit 20).
3. The server returns the newest notes, each with id, body, created_at, plus a next_cursor if more pages exist.
4. Claude presents the notes to Marco.
5. If Marco wants more, Claude calls notes.list again with the next_cursor from the previous response.
6. Repeat until next_cursor is null (last page reached).
```

**Variations:**
- No notes in DB → returns empty list, no cursor; Claude tells Marco no notes have been saved yet.
- Caller passes an invalid/expired cursor → tool returns an error with a clear message; Claude starts a fresh list call without a cursor.
- Custom limit requested → caller passes limit; server caps at BR-5 maximum.

---

### 4.4 Rebuild the FTS index (reindex)

**Trigger:** Marco suspects search is returning stale or missing results (e.g., after manually editing the DB, or after a crash mid-write).

```
1. Marco runs: memo-mcp reindex  (in a terminal or scheduled task)
2. The CLI drops and rebuilds notes_fts from the notes table.
3. On success: exits 0, prints a summary line to stdout (note count, duration).
4. On error (e.g., DB not found): exits 1, prints an error line to stdout.
```

**Variations:**
- `memo-mcp serve` is running concurrently → WAL mode allows the rebuild to proceed; busy_timeout=5000 ms prevents hard lock errors.
- DB path set via `MEMO_MCP_DB_PATH` → CLI respects the same env var as the server.
- Run twice in a row → idempotent; result is the same; no duplicate rows.

---

## 5. User stories

### US-1 — Add a note
**As a** note-taker, **I want** to save a plain-text note by telling Claude, **so that** I can retrieve it in a future session.

**Acceptance criteria:**

- **AC-1.1 (happy path):** Given a non-empty body string (≤ max length), when `notes.add` is called, then the note is persisted, a confirmation is returned containing the new note's `id` and `created_at`, and the note is immediately findable via `notes.search`.
- **AC-1.2 (empty body):** Given an empty or whitespace-only body, when `notes.add` is called, then an error is returned with a message indicating the body is required; no record is written.
- **AC-1.3 (oversized body):** Given a body exceeding the maximum length (BR-2), when `notes.add` is called, then an error is returned stating the limit; no partial record is written.
- **AC-1.4 (FTS sync):** Given a note that was just added, when `notes.search` is called with a distinctive word from that note's body, then the note appears in the results without running `reindex`.

**Size:** S

---

### US-2 — Search notes by keyword
**As a** note-taker, **I want** to search my notes by keyword or phrase, **so that** I can find what I saved without scrolling through everything.

**Acceptance criteria:**

- **AC-2.1 (happy path):** Given at least one note containing the word "Docker", when `notes.search("Docker")` is called, then results include that note, ordered by bm25 relevance score (best match first).
- **AC-2.2 (relevance order):** Given multiple notes where one body is entirely about "Docker" and another mentions it in passing, when `notes.search("Docker")` is called, then the more relevant note ranks higher.
- **AC-2.3 (empty query):** Given a query that is empty or whitespace-only, when `notes.search` is called, then an error is returned; no results are returned.
- **AC-2.4 (no results):** Given a query that matches no notes, when `notes.search` is called, then an empty list is returned with no error.
- **AC-2.5 (limit respected):** Given `limit=3`, when `notes.search` is called with multiple matching notes, then at most 3 results are returned.
- **AC-2.6 (FTS special characters):** Given a query containing FTS5 special characters (e.g., `"hello*`), when `notes.search` is called, then the server returns a result or an empty list — never an unhandled SQLite error.

**Size:** S

---

### US-3 — List recent notes
**As a** note-taker, **I want** to browse my most recently saved notes, **so that** I can review what I've captured recently.

**Acceptance criteria:**

- **AC-3.1 (happy path):** Given notes exist in the DB, when `notes.list` is called without a cursor, then the first page is returned (newest first, default 20 per page), each entry containing `id`, `body`, and `created_at`.
- **AC-3.2 (next page):** Given a response that included a `next_cursor`, when `notes.list` is called with that cursor, then the next page of older notes is returned with no overlap or gaps.
- **AC-3.3 (last page):** Given the last page of results, when `notes.list` returns it, then `next_cursor` is null (or absent).
- **AC-3.4 (empty DB):** Given no notes in the DB, when `notes.list` is called, then an empty list is returned with no `next_cursor` and no error.
- **AC-3.5 (custom limit):** Given `limit=5`, when `notes.list` is called, then at most 5 notes are returned per page.
- **AC-3.6 (invalid cursor):** Given a cursor that is malformed or refers to a deleted note, when `notes.list` is called, then an error is returned indicating the cursor is invalid; the caller may retry without a cursor to start from the beginning.

**Size:** S

---

### US-4 — Rebuild the FTS index
**As a** note-taker, **I want** to run `memo-mcp reindex` from the terminal, **so that** full-text search works correctly after data migration, manual edits, or a crash.

**Acceptance criteria:**

- **AC-4.1 (happy path):** Given a valid DB at `MEMO_MCP_DB_PATH` (or default), when `memo-mcp reindex` is run, then `notes_fts` is rebuilt from `notes`, the command exits 0, and a summary line is printed to stdout (e.g., `Reindexed 42 notes in 0.12s`).
- **AC-4.2 (idempotent):** Given `memo-mcp reindex` is run twice in succession with no changes to `notes`, then the second run exits 0 and produces the same row count as the first.
- **AC-4.3 (concurrent server):** Given `memo-mcp serve` is running and actively taking calls, when `memo-mcp reindex` is run, then both complete without data corruption or a hard lock error (relies on WAL + busy_timeout=5000 ms).
- **AC-4.4 (DB not found):** Given `MEMO_MCP_DB_PATH` points to a path where no DB file exists (and the default location has no DB either), when `memo-mcp reindex` is run, then the command exits 1 with a clear error message; it does not create an empty DB.
- **AC-4.5 (stale search corrected):** Given a note was added while FTS was out of sync (simulated by directly deleting a row from `notes_fts`), when `memo-mcp reindex` is run and `notes.search` is called, then the previously missing note is now returned.

**Size:** S

---

## 6. Business rules

| Rule ID | Rule | Source / owner |
|---------|------|----------------|
| BR-1 | A note body must contain at least 1 non-whitespace character | Product decision / Marco |
| BR-2 | A note body must not exceed 10,000 characters — keeps individual search results from consuming excessive Claude context window | Product decision / Marco |
| BR-3 | Notes are append-only in v0.1.0; there are no edit or delete MCP tools | v0.1.0 scope decision |
| BR-4 | `created_at` is set by the database at insert time using UTC; callers cannot supply or override it | Engineering convention |
| BR-5 | `notes.list` `limit` may not exceed 100; values above 100 are clamped to 100 | Product decision / Marco |
| BR-6 | `notes.search` results are ordered by bm25 relevance, ascending (most relevant first); ties broken by `created_at DESC` | Technical convention (SQLite bm25 returns negative scores) |
| BR-7 | `notes.list` results are ordered by `created_at DESC, id DESC` (newest first) | Product decision |
| BR-8 | The pagination cursor for `notes.list` is opaque to the caller; its internal encoding (created_at + id) is an implementation detail | API design convention |
| BR-9 | `MEMO_MCP_DB_PATH` must resolve to a local filesystem path; UNC/network paths are rejected at startup with a clear error | SQLite WAL limitation on network shares |
| BR-10 | The `tags` column exists in the `notes` schema but is not exposed via any MCP tool or CLI output in v0.1.0 | Scope decision; reserved for v0.2.0 |
| BR-11 | FTS5 index updates are maintained automatically by INSERT/UPDATE/DELETE triggers on the `notes` table; callers need not manage the index during normal operation | Technical convention |
| BR-12 | `memo-mcp reindex` is the only operation that drops and rebuilds `notes_fts`; it should not be called from within the MCP server process | Correctness / locking safety |
| BR-13 | All MCP tool responses that represent errors must use the MCP error response format (not a success response with an error field) | MCP protocol conformance |
| BR-14 | The server auto-creates the DB file and parent directories on first write if they do not exist; `reindex` does not auto-create (see AC-4.4) | Usability vs. correctness trade-off |
| BR-15 | `notes.search` `limit` defaults to 10 and may not exceed 20; values above 20 are clamped to 20 — bounds chosen to protect Claude's context window | Product decision / Marco |
| BR-16 | `notes.search` responses do not include the raw bm25 score; relevance is communicated by result order only. Scores are written to the stderr JSON log for debugging | Product decision / Marco |
| BR-17 | `notes.list` with a malformed or unresolvable cursor returns an MCP error; it does not silently restart from page 1 | Product decision / Marco |
| BR-18 | `memo-mcp reindex` prints a single summary line to stdout on completion (e.g., `Reindexed 42 notes in 0.12s`); no per-note progress output | Product decision / Marco |
| BR-19 | Edit and delete tools are deferred to v0.1.1; when `notes.delete` is added it must use soft-delete (`deleted_at` timestamp) to prevent accidental data loss through misunderstood Claude instructions | Product decision / Marco |

---

## 7. Screens / views

*memo-mcp has no graphical UI. Claude Desktop's chat interface is the only surface. The "views" here describe the structured data returned to Claude for each tool.*

### 7.1 notes.add response

**Information returned:**
- `id` — integer, the assigned note ID
- `created_at` — ISO-8601 UTC timestamp string

**States:**
- Success: `{ "id": 42, "created_at": "2026-05-01T09:01:23Z" }`
- Error (empty body): MCP error with code and human-readable message
- Error (oversized): MCP error with max length in the message

---

### 7.2 notes.search response

**Information returned (per result):**
- `id` — integer
- `body` — full note text
- `created_at` — ISO-8601 UTC timestamp string

**States:**
- Results found: array of note objects, ordered by relevance
- No results: empty array `[]` (not an error)
- Invalid query: MCP error

---

### 7.3 notes.list response

**Information returned:**
- `notes` — array of `{ id, body, created_at }`, newest first
- `next_cursor` — opaque string, or null if no further pages

**States:**
- Notes exist, more pages: array + non-null `next_cursor`
- Notes exist, last page: array + `next_cursor: null`
- No notes: `{ "notes": [], "next_cursor": null }`
- Invalid cursor: MCP error

---

## 8. Non-functional expectations

**Performance (from the user's perspective):**
- `notes.add`: completes in under 200 ms for any valid note body (local SQLite write + trigger).
- `notes.search`: returns first page in under 500 ms for a personal DB of up to 10,000 notes.
- `notes.list`: returns first page in under 200 ms regardless of total note count.
- `memo-mcp reindex`: completes in under 10 s for up to 10,000 notes on a modern laptop.

**Permissions / access control:**
- Single-user personal tool; no authentication in v0.1.0.
- DB file permissions are whatever the OS assigns to the user's home directory; no additional restriction layer.
- No network access; all data stays local.

**Audit / observability:**
- Every tool call produces a structured JSON log line to stderr: `tool_name`, `request_id`, `duration_ms`, and outcome (`ok` / `error`).
- Nothing is logged to stdout (would corrupt MCP framing).
- `reindex` logs its run to the same stderr stream when invoked.

**Accessibility / i18n:**
- No GUI; not applicable to accessibility guidelines.
- Note bodies are stored as UTF-8; FTS5 `unicode61` tokenizer handles non-ASCII scripts (accented characters, CJK, etc.).
- Timestamps are stored and returned as UTC ISO-8601 strings; display formatting is Claude's responsibility.

**Reliability:**
- WAL mode + `busy_timeout=5000` ensures concurrent reads and a single writer do not produce hard errors under normal use.
- Trigger-driven FTS sync ensures the index is current after every write without manual intervention.

---

## 9. Resolved decisions (formerly open questions)

All questions resolved 2026-05-01.

| ID | Question | Decision |
|----|----------|----------|
| Q-1 | Max note body length? | **10,000 chars** — a 50k note would consume ~12,500 tokens of Claude's context per result; 10k is generous for a personal note and safe for search responses → BR-2 |
| Q-2 | Should `notes.search` support a `limit` param? | **Yes — default 10, max 20** — Claude needs to control result count to avoid flooding context; cap 20 keeps worst-case response bounded → BR-15 |
| Q-3 | Include bm25 score in search response? | **No** — score is noise in Claude's context; ranked order communicates relevance; score logged to stderr for debugging → BR-16 |
| Q-4 | Invalid cursor: silent fallback to page 1 or error? | **Return an error** — silent fallback would cause Claude to present duplicate results as a continuation, a subtle lie; explicit error lets Claude restart cleanly → BR-17, AC-3.6 |
| Q-5 | `reindex` output: per-note progress or summary only? | **Final summary only** (`Reindexed N notes in X.XXs`) — per-note lines are spam at any real volume → BR-18, AC-4.1 |
| Q-6 | `notes.delete` / `notes.update` in v0.1.1? | **Defer to v0.1.1; use soft-delete** — hard delete risks accidental data loss through misunderstood Claude instructions; `deleted_at` column is the safe pattern; UPDATE trigger already wired so it's a scope unlock → BR-19 |
