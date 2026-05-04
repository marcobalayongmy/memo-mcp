# Scaffold Creation — memo-mcp v0.1.0 (2026-05-02 10:00)

## What was scaffolded

- **Type:** Python CLI + MCP server library
- **Stack:** Python 3.11+, uv_build, Typer, mcp (FastMCP), structlog, filelock
- **Location:** `C:\Users\marco\VSCodeProjects\memo-mcp`
- **Task:** T-01 from `skill-outputs/implementation-plan/implementation-plan_memo-mcp-v010_2026-05-02_1000.md`

## Files generated

```
pyproject.toml                   build config, deps, entry point
src/memo_mcp/__init__.py         __version__ = "0.1.0"
src/memo_mcp/cli.py              Typer stub: serve + reindex commands
tests/__init__.py                empty; makes tests/ a package
.gitignore                       Python / uv / SQLite / IDE patterns
```

## Versions pinned

| Package | Constraint | Rationale |
|---------|-----------|-----------|
| `mcp` | `>=1.27.0,<2.0` | v2 pre-alpha; upper bound prevents silent API breaks |
| `typer` | `>=0.12` | Stable; no breaking changes expected in 0.x range used |
| `structlog` | `>=24.0` | 24.x introduced the processor pipeline API used here |
| `filelock` | `>=3.13` | Cross-platform file locking for reindex concurrency guard |

## Verification

Python and uv were not on the PATH in the scaffolding environment. Run these commands to verify after activating your Python environment:

```bash
# Create and activate venv (if not using uv)
python -m venv .venv
.venv\Scripts\activate          # Windows
# or
source .venv/bin/activate       # macOS / Linux

# Install in editable mode
pip install -e ".[dev]"

# Verify entry point
memo-mcp --help
# Expected: shows "serve" and "reindex" as subcommands

# Verify import
python -c "import memo_mcp; print(memo_mcp.__version__)"
# Expected: 0.1.0

# If using uv (preferred):
uv venv
uv pip install -e ".[dev]"
uv run memo-mcp --help
```

## uv_build risk

If `pip install -e .` fails with a `uv_build` error, fall back to `hatchling` with two lines in `pyproject.toml`:

```toml
# Replace:
[build-system]
requires = ["uv_build>=0.7"]
build-backend = "uv_build"

[tool.uv_build.targets.wheel]
packages = ["src/memo_mcp"]

# With:
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/memo_mcp"]
```

## Next steps

1. Run `pip install -e ".[dev]"` (or `uv pip install -e ".[dev]"`) and confirm `memo-mcp --help` works
2. If `uv_build` fails, apply the `hatchling` fallback above
3. Proceed with **T-02** (`implement-business-logic`): implement `open_db()` and `_SCHEMA_SQL` in `src/memo_mcp/storage.py`
