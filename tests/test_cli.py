from __future__ import annotations

import re
from unittest.mock import MagicMock, patch

import pytest
from filelock import FileLock
from typer.testing import CliRunner

from memo_mcp import storage
from memo_mcp.cli import app

runner = CliRunner()


class TestReindex:
    def test_exit_1_db_not_found(self, tmp_path):
        result = runner.invoke(app, ["reindex", "--db", str(tmp_path / "missing.db")])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_exit_3_unc_path(self):
        result = runner.invoke(app, ["reindex", "--db", r"\\server\share\notes.db"])
        assert result.exit_code == 3
        assert "UNC" in result.output

    def test_exit_4_already_running(self, tmp_path):
        db_path = tmp_path / "notes.db"
        conn = storage.open_db(str(db_path))
        conn.close()
        lock_path = tmp_path / ".memo-mcp-reindex.lock"
        with FileLock(str(lock_path)):
            result = runner.invoke(app, ["reindex", "--db", str(db_path)])
        assert result.exit_code == 4
        assert "already running" in result.output

    def test_exit_0_success_and_output_format(self, tmp_path):
        db_path = tmp_path / "notes.db"
        conn = storage.open_db(str(db_path))
        storage.add_note(conn, "hello")
        storage.add_note(conn, "world")
        conn.close()
        result = runner.invoke(app, ["reindex", "--db", str(db_path)])
        assert result.exit_code == 0
        assert re.search(r"Reindexed 2 notes in \d+\.\d{2}s", result.output)

    def test_exit_2_corrupt_db(self, tmp_path):
        db_path = tmp_path / "notes.db"
        db_path.write_bytes(b"this is not a sqlite database")
        result = runner.invoke(app, ["reindex", "--db", str(db_path)])
        assert result.exit_code == 2
        assert "Error" in result.output

    def test_reindex_is_idempotent(self, tmp_path):
        db_path = tmp_path / "notes.db"
        conn = storage.open_db(str(db_path))
        storage.add_note(conn, "idempotent check")
        conn.close()
        result1 = runner.invoke(app, ["reindex", "--db", str(db_path)])
        result2 = runner.invoke(app, ["reindex", "--db", str(db_path)])
        assert result1.exit_code == 0
        assert result2.exit_code == 0

    def test_uses_memo_mcp_db_path_env_var(self, tmp_path, monkeypatch):
        db_path = tmp_path / "notes.db"
        conn = storage.open_db(str(db_path))
        conn.close()
        monkeypatch.setenv("MEMO_MCP_DB_PATH", str(db_path))
        result = runner.invoke(app, ["reindex"])
        assert result.exit_code == 0


class TestServe:
    def test_serve_help_exits_0(self):
        result = runner.invoke(app, ["serve", "--help"])
        assert result.exit_code == 0
        assert "stdio" in result.output.lower()

    def test_initializes_logging_db_and_runs(self):
        from memo_mcp.server import mcp

        mock_conn = MagicMock()
        with (
            patch("memo_mcp.cli.configure_logging") as mock_log,
            patch("memo_mcp.cli.storage.open_db", return_value=mock_conn),
            patch("memo_mcp.cli.asyncio.run") as mock_asyncio_run,
            patch.object(mcp, "run") as mock_mcp_run,
        ):
            result = runner.invoke(app, ["serve"])
            mock_log.assert_called_once()
            mock_mcp_run.assert_called_once()
            mock_asyncio_run.assert_called_once()
            assert result.exit_code == 0
