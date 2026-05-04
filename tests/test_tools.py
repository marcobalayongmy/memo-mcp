from __future__ import annotations

import json

import pytest
from mcp.server.fastmcp.exceptions import ToolError

import memo_mcp.tools as _tools
from memo_mcp import storage
from memo_mcp.server import mcp

pytestmark = pytest.mark.anyio


class TestNotesAdd:
    async def test_saves_note_and_returns_confirmation(self, mcp_client):
        result, _ = await mcp.call_tool("notes.add", {"body": "hello world"})
        text = result[0].text
        assert text.startswith("Note ")
        assert "saved" in text

    async def test_strips_whitespace_before_saving(self, mcp_client):
        result, _ = await mcp.call_tool("notes.add", {"body": "  trimmed  "})
        assert "saved" in result[0].text
        note = storage.list_notes(mcp_client)["notes"][0]
        assert note["body"] == "trimmed"

    async def test_empty_body_raises_tool_error(self, mcp_client):
        with pytest.raises(ToolError, match="body must not be empty"):
            await mcp.call_tool("notes.add", {"body": "   "})

    async def test_body_too_long_raises_tool_error(self, mcp_client):
        with pytest.raises(ToolError):
            await mcp.call_tool("notes.add", {"body": "x" * 10001})


class TestNotesSearch:
    async def test_finds_matching_notes(self, mcp_client):
        storage.add_note(mcp_client, "cats are wonderful")
        storage.add_note(mcp_client, "dogs are loyal")
        result, _ = await mcp.call_tool("notes.search", {"query": "cats"})
        data = json.loads(result[0].text)
        assert data["count"] == 1
        assert "cats" in data["notes"][0]["body"]

    async def test_returns_count_and_notes_keys(self, mcp_client):
        storage.add_note(mcp_client, "searchable content")
        result, _ = await mcp.call_tool("notes.search", {"query": "searchable"})
        data = json.loads(result[0].text)
        assert "count" in data
        assert "notes" in data

    async def test_no_results_returns_empty_list(self, mcp_client):
        result, _ = await mcp.call_tool("notes.search", {"query": "dragons"})
        data = json.loads(result[0].text)
        assert data["count"] == 0
        assert data["notes"] == []

    async def test_empty_query_raises_tool_error(self, mcp_client):
        with pytest.raises(ToolError, match="query must not be empty"):
            await mcp.call_tool("notes.search", {"query": "  "})

    async def test_malformed_fts_query_raises_tool_error(self, mcp_client):
        with pytest.raises(ToolError):
            await mcp.call_tool("notes.search", {"query": '"unclosed'})


class TestNotesList:
    async def test_empty_db_returns_empty_list(self, mcp_client):
        result, _ = await mcp.call_tool("notes.list", {})
        data = json.loads(result[0].text)
        assert data["notes"] == []
        assert data["next_cursor"] is None

    async def test_returns_notes_and_cursor_keys(self, mcp_client):
        storage.add_note(mcp_client, "a note")
        result, _ = await mcp.call_tool("notes.list", {})
        data = json.loads(result[0].text)
        assert "notes" in data
        assert "next_cursor" in data

    async def test_pagination(self, mcp_client):
        for i in range(3):
            storage.add_note(mcp_client, f"note {i}")

        result1, _ = await mcp.call_tool("notes.list", {"limit": 2})
        page1 = json.loads(result1[0].text)
        assert len(page1["notes"]) == 2
        assert page1["next_cursor"] is not None

        result2, _ = await mcp.call_tool(
            "notes.list", {"limit": 2, "cursor": page1["next_cursor"]}
        )
        page2 = json.loads(result2[0].text)
        assert len(page2["notes"]) == 1
        assert page2["next_cursor"] is None

    async def test_invalid_cursor_raises_tool_error(self, mcp_client):
        with pytest.raises(ToolError, match="invalid cursor"):
            await mcp.call_tool("notes.list", {"cursor": "!!!invalid!!!"})


class TestNoStdoutLeaks:
    async def test_notes_add_writes_nothing_to_stdout(self, mcp_client, capsys):
        await mcp.call_tool("notes.add", {"body": "stdout check"})
        assert capsys.readouterr().out == ""

    async def test_notes_search_writes_nothing_to_stdout(self, mcp_client, capsys):
        storage.add_note(mcp_client, "stdout check note")
        await mcp.call_tool("notes.search", {"query": "stdout"})
        assert capsys.readouterr().out == ""

    async def test_notes_list_writes_nothing_to_stdout(self, mcp_client, capsys):
        await mcp.call_tool("notes.list", {})
        assert capsys.readouterr().out == ""


class TestGetConn:
    def test_raises_when_conn_is_none(self):
        old = _tools._conn
        _tools._conn = None
        try:
            with pytest.raises(RuntimeError, match="database connection not initialized"):
                _tools._get_conn()
        finally:
            _tools._conn = old

    def test_returns_conn_when_set(self, db):
        old = _tools._conn
        _tools._conn = db
        try:
            assert _tools._get_conn() is db
        finally:
            _tools._conn = old
