# Implement Business Logic — storage.open_db + _SCHEMA_SQL (2026-05-02 11:00)

## Requirement
T-02: Implement `open_db()` and `_SCHEMA_SQL` in `src/memo_mcp/storage.py`.
Inputs: technical design §4 (schema SQL) and §8 (open_db sequence).

## Files created / modified
- **new:** `src/memo_mcp/storage.py` — `_SCHEMA_SQL` constant (full DDL) and `open_db()` function (62 LOC)

## Key design decisions
- `_SCHEMA_SQL` contains all DDL in dependency order: `notes` table → `notes_fts` virtual table → 3 sync triggers → composite index. All statements guarded with `IF NOT EXISTS` for idempotency.
- `open_db()` follows the exact sequence from technical design §8: resolve path → reject UNC → mkdir → connect → row_factory → WAL pragma → busy_timeout pragma → executescript → commit → return.
- UNC path check uses `startswith("\\\\") or startswith("//")` — covers both Windows and POSIX network share notations.
- `executescript` commits any pending transaction internally; the trailing `conn.commit()` is a no-op but kept for clarity.

## Tests added / run
- Manual verification via inline Python script:
  - `_SCHEMA_SQL` runs against an in-memory SQLite DB without error
  - All expected objects confirmed present: `notes` table, `notes_fts` virtual table, `notes_ai/notes_ad/notes_au` triggers, `idx_notes_created_at_id` index
  - `open_db()` creates a real DB file in a temp directory; journal_mode confirmed `wal`
- Result: all checks passed

## Manual verification
Not applicable — no UI or API surface in this task.

## Deferred items
- `add_note()`, `search_notes()`, `list_notes()`, `encode_cursor()`, `decode_cursor()`, `reindex()` — deferred to T-03 and T-04 per implementation plan.

## Open questions
None. All decisions locked in from technical design and database design documents.
