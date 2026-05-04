from __future__ import annotations

import pytest

import memo_mcp.tools as _tools
from memo_mcp import storage
from memo_mcp.logging import configure_logging


@pytest.fixture(scope="session", autouse=True)
def setup_logging():
    """Direct structlog to stderr for the whole test session, matching production."""
    configure_logging()


@pytest.fixture
def db():
    conn = storage.open_db(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def mcp_client(db):
    """Inject in-memory DB into the tool layer and yield the connection."""
    old = _tools._conn
    _tools._conn = db
    yield db
    _tools._conn = old
