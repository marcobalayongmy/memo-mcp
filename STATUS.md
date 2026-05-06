# memo-mcp — Project Status

## Current goal
Publish `memo-mcp` to PyPI as a production release.

## Tasks
- [x] T-01 to T-15: Full implementation (storage, tools, server, CLI, tests, CI/CD pipeline)
- [x] All 52 tests passing
- [x] Initial commit pushed to GitHub (https://github.com/marcobalayongmy/memo-mcp)
- [ ] T-16: Register OIDC trusted publisher on pypi.org and test.pypi.org, push `v0.0.1a0` tag, verify TestPyPI install
- [ ] T-17: Cut `v0.1.0` tag for real PyPI publish
- [ ] Final passes: `code-review` → `security-analysis`

## Last session (2026-05-06)
- Fixed Stop hook JSON validation error: replaced invalid `hookSpecificOutput`/`hookEventName: 'Stop'` with correct `reason` field in `~/.claude/settings.json`
- Clarified Stop hook behavior: fires per Claude response turn, not on window close — must end session with a final message to trigger it reliably

## Blockers
- T-16 is a manual step requiring pypi.org account access (OIDC trusted publisher registration)

## Notes
- stdout is reserved for MCP wire framing — never log to stdout, always stderr
- `multiprocessing` banned under stdio transport (mcp-sdk issue #817)
- PyPI package name `memo-mcp` confirmed available
