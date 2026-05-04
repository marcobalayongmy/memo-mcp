# memo-mcp — Kickoff

A personal-notes MCP server that exposes search / add / list tools to Claude.
Used as the test bed for the `.copilot/skills` library — exercises ~20 of 28 skills end-to-end.

**Stack (proposed; confirm in Phase 1):**
- Python 3.12 + `mcp` SDK
- SQLite + FTS5 for search
- Typer for CLI
- structlog for JSON logs
- pytest for tests
- GitHub Actions → PyPI for release

**Outcome:** a working `memo-mcp` v0.1.0 published to PyPI, runnable from Claude Desktop via stdio.

---

## The skill chain

| Phase | Skills (in order) |
|-------|-------------------|
| 1. Frame | `task-analyzer` → `technical-research` → `generate-functional-design` |
| 2. Design | `api-design` → `database-design-optimization` → `generate-technical-design` → `batch-job-design` → `implementation-plan` |
| 3. Build | `scaffold-creation` → `implement-business-logic` (per task) → `generate-tests` |
| 4. Operate | `observability-setup` → `code-review` → `security-analysis` |
| 5. Ship | `dependency-management` → `release-prep` → `devops-deployment` |
| 6. Iterate | `debugging-troubleshooting` / `performance-optimization` / `refactoring` / `code-explanation` as needed |

---

## Start here

Open this folder in VS Code, open a Claude Code session in it, and paste the prompt below. That kicks off Phase 1 and routes the rest.

```
task-analyzer build a personal notes MCP server in Python: tools to search/add/list notes, SQLite + FTS5 backend, nightly reindex batch job, structured logs, ship as a PyPI package; goal is to run locally with Claude Desktop within ~1 week of evenings
```

After `task-analyzer` finishes, follow its recommended chain. Each skill saves its output under `skill-outputs/<skill-name>/...` in this directory, so you can come back to any phase later and re-read the artifacts.

---

## Acceptance for v0.1.0

- [ ] `pip install memo-mcp` works
- [ ] `memo-mcp` command starts an MCP server on stdio
- [ ] All three tools (`notes.search`, `notes.add`, `notes.list`) callable from Claude Desktop
- [ ] Nightly reindex job runnable via `memo-mcp reindex`
- [ ] Structured JSON logs to stderr
- [ ] Tests passing in CI
- [ ] Released as a tagged GitHub release + PyPI package
