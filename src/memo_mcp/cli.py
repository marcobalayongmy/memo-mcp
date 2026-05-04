from __future__ import annotations

import asyncio
import pathlib
import sqlite3
import time

import typer
from filelock import FileLock, Timeout

from memo_mcp import storage
from memo_mcp.logging import configure_logging
from memo_mcp.server import mcp

app = typer.Typer(name="memo-mcp", add_completion=False)


@app.command()
def serve() -> None:
    """Start the MCP server on stdio."""
    configure_logging()
    conn = storage.open_db()
    import memo_mcp.tools as _tools  # local import keeps injection intent explicit
    _tools._conn = conn
    asyncio.run(mcp.run())


@app.command()
def reindex(
    db: str | None = typer.Option(
        None,
        "--db",
        envvar="MEMO_MCP_DB_PATH",
        help="Path to the SQLite database. Defaults to ~/.memo-mcp/notes.db.",
        show_default=False,
    ),
) -> None:
    """Rebuild the FTS5 full-text search index from the notes table.

    Safe to run at any time. Use after manual DB edits, interrupted writes,
    or memo-mcp upgrades.
    """
    path = (
        pathlib.Path(db)
        if db
        else pathlib.Path.home() / ".memo-mcp" / "notes.db"
    )

    path_str = str(path)
    if path_str.startswith("\\\\") or path_str.startswith("//"):
        typer.echo(f"Error: UNC/network paths are not supported: {path}", err=True)
        raise typer.Exit(code=3)

    if not path.exists():
        typer.echo(f"Error: database not found: {path}", err=True)
        raise typer.Exit(code=1)

    lock_path = path.parent / ".memo-mcp-reindex.lock"
    try:
        with FileLock(str(lock_path), timeout=0):
            t0 = time.perf_counter()
            try:
                conn = storage.open_db(str(path))
                count = storage.reindex(conn)
                conn.close()
            except sqlite3.Error as exc:
                typer.echo(f"Error: {exc}", err=True)
                raise typer.Exit(code=2)
            elapsed = time.perf_counter() - t0
            typer.echo(f"Reindexed {count} notes in {elapsed:.2f}s")
    except Timeout:
        typer.echo("Error: reindex already running.", err=True)
        raise typer.Exit(code=4)


if __name__ == "__main__":
    app()
