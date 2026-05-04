# implement-business-logic — storage query functions (T-03)

## Requirement
Implement the remaining query functions in `src/memo_mcp/storage.py`:
`add_note`, `encode_cursor`, `decode_cursor`, `list_notes`, `search_notes`, `reindex`.

## Files modified
- `src/memo_mcp/storage.py` — added `import base64`, `import json`; added all six functions after `open_db`

## Key decisions

| Decision | Rationale |
|---|---|
| Strip body before empty-check; measure `len(body)` before stripping | Matches schema constraints: `CHECK(length(trim(body))>0)` and `CHECK(length(body)<=10000)` |
| `RETURNING id, created_at` on INSERT | No `last_insert_rowid()` — design constraint |
| `base64.urlsafe_b64encode/decode` + padding fix (`-len % 4`) | urlsafe variant avoids `+/` characters in JSON fields; padding is stripped by some encoders so restore it defensively |
| `decode_cursor` catches all exceptions → single `ValueError("invalid cursor")` | Spec: invalid cursor = MCP error, no silent fallback |
| `WHERE (created_at, id) < (?, ?)` — SQLite row-value comparison | Correct keyset pagination for `ORDER BY created_at DESC, id DESC`; supported since SQLite 3.15 (2016) |
| Fetch `limit+1` rows, slice `[:limit]` for response | Detects next page without COUNT(*) |
| `INSERT INTO notes_fts(notes_fts) VALUES('rebuild')` + commit | FTS5 full rebuild; not DROP+recreate |
| No logging in storage.py | Logging added in T-05 observability pass |

## Test results
Smoke-tested manually via inline Python against an in-memory SQLite DB:
- `add_note` happy path, empty body, too-long body ✓
- `encode_cursor` / `decode_cursor` round-trip, bad cursor ✓
- `list_notes` three-page walk (limit=2 over 5 notes), limit>100 error ✓
- `search_notes` FTS match, limit>20 error ✓
- `reindex` returns correct count ✓

All assertions passed.

## Deferred / follow-ups
- Logging (query_len, result_count) added in T-05 observability
- `server.py`, `tools.py` wire these functions in T-04 (next implement-business-logic pass)
