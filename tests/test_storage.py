from __future__ import annotations

import base64
import json

import pytest

from memo_mcp import storage


class TestAddNote:
    def test_returns_id_and_created_at(self, db):
        result = storage.add_note(db, "hello world")
        assert isinstance(result["id"], int)
        assert result["id"] >= 1
        assert "T" in result["created_at"]

    def test_empty_body_raises(self, db):
        with pytest.raises(ValueError, match="empty"):
            storage.add_note(db, "")

    def test_whitespace_only_raises(self, db):
        with pytest.raises(ValueError, match="empty"):
            storage.add_note(db, "   ")

    def test_body_too_long_raises(self, db):
        with pytest.raises(ValueError, match="10,000"):
            storage.add_note(db, "x" * 10001)

    def test_body_at_max_length_succeeds(self, db):
        result = storage.add_note(db, "x" * 10000)
        assert result["id"] >= 1

    def test_ids_increment(self, db):
        r1 = storage.add_note(db, "first")
        r2 = storage.add_note(db, "second")
        assert r2["id"] == r1["id"] + 1


class TestSearchNotes:
    def test_finds_matching_notes(self, db):
        storage.add_note(db, "cats are great")
        storage.add_note(db, "dogs are loyal")
        result = storage.search_notes(db, "cats")
        assert result["count"] == 1
        assert "cats" in result["notes"][0]["body"]

    def test_returns_required_fields(self, db):
        storage.add_note(db, "test note")
        note = storage.search_notes(db, "test")["notes"][0]
        assert "id" in note
        assert "body" in note
        assert "created_at" in note

    def test_no_match_returns_empty(self, db):
        storage.add_note(db, "cats are great")
        result = storage.search_notes(db, "elephants")
        assert result["count"] == 0
        assert result["notes"] == []

    def test_limit_exceeded_raises(self, db):
        with pytest.raises(ValueError, match="20"):
            storage.search_notes(db, "cats", limit=21)

    def test_higher_match_density_ranks_first(self, db):
        storage.add_note(db, "cats cats cats")
        storage.add_note(db, "cats and dogs")
        result = storage.search_notes(db, "cats")
        assert result["count"] == 2
        assert "cats cats cats" in result["notes"][0]["body"]


class TestListNotes:
    def test_empty_db_returns_empty(self, db):
        result = storage.list_notes(db)
        assert result["notes"] == []
        assert result["next_cursor"] is None

    def test_returns_newest_first(self, db):
        storage.add_note(db, "first")
        storage.add_note(db, "second")
        bodies = [n["body"] for n in storage.list_notes(db)["notes"]]
        assert bodies[0] == "second"
        assert bodies[1] == "first"

    def test_returns_required_fields(self, db):
        storage.add_note(db, "check fields")
        note = storage.list_notes(db)["notes"][0]
        assert "id" in note
        assert "body" in note
        assert "created_at" in note

    def test_pagination_cursor(self, db):
        for i in range(3):
            storage.add_note(db, f"note {i}")

        page1 = storage.list_notes(db, limit=2)
        assert len(page1["notes"]) == 2
        assert page1["next_cursor"] is not None

        page2 = storage.list_notes(db, limit=2, cursor=page1["next_cursor"])
        assert len(page2["notes"]) == 1
        assert page2["next_cursor"] is None

    def test_pages_cover_all_notes_without_overlap(self, db):
        for i in range(4):
            storage.add_note(db, f"note {i}")

        page1 = storage.list_notes(db, limit=2)
        page2 = storage.list_notes(db, limit=2, cursor=page1["next_cursor"])
        ids1 = {n["id"] for n in page1["notes"]}
        ids2 = {n["id"] for n in page2["notes"]}
        assert ids1.isdisjoint(ids2)
        assert len(ids1 | ids2) == 4

    def test_invalid_cursor_raises(self, db):
        with pytest.raises(ValueError, match="invalid cursor"):
            storage.list_notes(db, cursor="!!!notvalid!!!")

    def test_limit_exceeded_raises(self, db):
        with pytest.raises(ValueError, match="100"):
            storage.list_notes(db, limit=101)


class TestCursorEncoding:
    def test_roundtrip(self):
        created_at = "2026-05-03T00:00:00Z"
        cursor = storage.encode_cursor(created_at, 42)
        assert storage.decode_cursor(cursor) == (created_at, 42)

    def test_invalid_base64_raises(self):
        with pytest.raises(ValueError, match="invalid cursor"):
            storage.decode_cursor("!!!not-base64!!!")

    def test_missing_keys_raises(self):
        bad = base64.urlsafe_b64encode(json.dumps({"x": 1}).encode()).decode()
        with pytest.raises(ValueError, match="invalid cursor"):
            storage.decode_cursor(bad)

    def test_non_int_id_raises(self):
        bad = base64.urlsafe_b64encode(
            json.dumps({"c": "2026-05-03T00:00:00Z", "i": "abc"}).encode()
        ).decode()
        with pytest.raises(ValueError, match="invalid cursor"):
            storage.decode_cursor(bad)


class TestReindex:
    def test_empty_db_returns_zero(self, db):
        assert storage.reindex(db) == 0

    def test_returns_note_count(self, db):
        storage.add_note(db, "one")
        storage.add_note(db, "two")
        assert storage.reindex(db) == 2

    def test_search_works_after_reindex(self, db):
        storage.add_note(db, "findable note")
        storage.reindex(db)
        result = storage.search_notes(db, "findable")
        assert result["count"] == 1
