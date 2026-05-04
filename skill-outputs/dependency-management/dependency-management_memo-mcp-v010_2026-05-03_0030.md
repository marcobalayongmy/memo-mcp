# Dependency Audit — memo-mcp v0.1.0 pre-release (2026-05-03)

**Manager:** pyproject.toml (uv_build backend), no lockfile
**Scope:** all direct + transitive runtime and dev dependencies
**Tool:** pip-audit (OSV database), pip index, importlib.metadata

---

## Summary

| Class | Count | Notes |
|-------|-------|-------|
| CVE (app deps) | 0 | Clean — only CVE found is in pip itself (not a dep) |
| Outdated | 0 | Every direct dep is at its latest published version |
| Lower-bound mismatch | 1 | `pydantic>=2.0` misleading; mcp requires `>=2.11` |
| Pre-1.0 safety bound | 1 | `typer` has no upper bound; added `<1.0` |
| Unused | 0 | All declared deps are imported in source |
| Conflicts | 0 | Transitive graph resolves cleanly |

---

## Applied changes

### 1. `pydantic>=2.0` → `pydantic>=2.11` (correctness)

`mcp>=1.27.0` itself requires `pydantic>=2.11.0,<3.0.0` (confirmed from wheel metadata). Declaring `>=2.0` in pyproject.toml implies pydantic 2.0–2.10 would work, but a fresh `pip install memo-mcp` would never install anything below 2.11 because mcp's constraint is stricter. The old bound was misleading to users reading the manifest.

### 2. `typer>=0.12` → `typer>=0.12,<1.0` (safety bound)

Typer is currently at 0.25.1 (pre-1.0). A future 1.0 release may introduce breaking API changes (e.g., argument handling, `CliRunner` interface changes we saw during testing). The `<1.0` upper bound prevents a silent break when Typer eventually ships its 1.0. Review and remove this bound when memo-mcp is tested against Typer 1.0.

---

## Installed vs latest (all current)

| Package | Lower bound | Installed | Latest | Status |
|---------|------------|-----------|--------|--------|
| mcp | `>=1.27.0,<2.0` | 1.27.0 | 1.27.0 | ✓ at latest; `<2.0` intentional |
| pydantic | `>=2.11` (updated) | 2.13.3 | 2.13.3 | ✓ at latest |
| typer | `>=0.12,<1.0` (updated) | 0.25.1 | 0.25.1 | ✓ at latest |
| structlog | `>=24.0` | 25.5.0 | 25.5.0 | ✓ at latest |
| filelock | `>=3.13` | 3.29.0 | 3.29.0 | ✓ at latest |
| pytest (dev) | `>=8.0` | 9.0.3 | 9.0.3 | ✓ at latest |
| anyio (dev) | `>=4.0` | 4.13.0 | 4.13.0 | ✓ at latest |

---

## CVE scan

```
pip-audit result: No known vulnerabilities found, 1 ignored
Ignored: CVE-2026-3219 — affects pip 26.0.1 (the package manager itself, not a dep)
```

No CVEs in any runtime or dev dependency.

---

## Platform notes

- `pywin32>=310` is pulled in by `mcp` with marker `sys_platform == 'win32'` — correctly conditional, won't install on Linux/Mac.
- `uvicorn>=0.31.1` has marker `sys_platform != 'emscripten'` — installs on all target platforms.
- No other platform-specific transitive deps found. Cross-platform installs on Python 3.11–3.13 are clean.

---

## Dev extras completeness

| Package | Purpose | Status |
|---------|---------|--------|
| pytest>=8.0 | test runner | ✓ |
| anyio>=4.0 | async test support via `@pytest.mark.anyio` | ✓ (also transitive via mcp) |
| pytest-asyncio | not needed — anyio plugin used directly | n/a |

Dev extras are complete for the current test suite.

---

## No action needed

- `structlog>=24.0` lower bound is intentionally loose — structlog has a stable API across 24.x–25.x. No upper bound needed.
- `filelock>=3.13` lower bound is fine — `FileLock(timeout=0)` API unchanged since 3.x.
- `mcp>=1.27.0,<2.0` — correct; `<2.0` intentionally guards against the in-development v2 breaking changes.
