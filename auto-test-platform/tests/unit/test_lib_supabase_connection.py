"""Unit tests for lib.supabase_connection."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import lib.supabase_connection as mod


class _FakeConn:
    def __init__(self):
        self.executed = []

    async def execute(self, sql):
        self.executed.append(sql)
        return "OK"

    async def close(self):
        self.executed.append("__closed__")


class _FakeAsyncPg:
    def __init__(self, conn):
        self.conn = conn

    async def connect(self, dsn, timeout):
        return self.conn


def test_rest_connection_builds_endpoint_and_headers():
    conn = mod.SupabaseRestConnection(
        supabase_url="https://example.supabase.co/",
        service_role_key="test-key",
        schema="public",
    )

    endpoint = conn.table_endpoint("test_runs", {"on_conflict": "run_id"})
    headers = conn.headers(prefer="return=representation")

    assert endpoint == "https://example.supabase.co/rest/v1/test_runs?on_conflict=run_id"
    assert headers["apikey"] == "test-key"
    assert headers["Authorization"] == "Bearer test-key"
    assert headers["Accept-Profile"] == "public"


def test_rest_connection_rejects_invalid_input():
    try:
        mod.SupabaseRestConnection("", "key")
        assert False, "Expected ValueError for supabase_url"
    except ValueError:
        assert True

    try:
        mod.SupabaseRestConnection("https://example.supabase.co", "", schema="public")
        assert False, "Expected ValueError for service_role_key"
    except ValueError:
        assert True

    try:
        mod.SupabaseRestConnection("https://example.supabase.co", "key", schema="public;drop")
        assert False, "Expected ValueError for invalid schema"
    except ValueError:
        assert True


def test_database_ping_uses_schema_and_closes_connection(monkeypatch):
    fake_conn = _FakeConn()
    monkeypatch.setattr(mod, "asyncpg", _FakeAsyncPg(fake_conn))

    db = mod.SupabaseDatabaseConnection(
        database_url="postgresql://postgres:pw@db.example:5432/postgres",
        schema="public",
    )
    db.ping()

    assert fake_conn.executed[0] == "SELECT 1;"
    assert fake_conn.executed[1] == "SELECT 1 FROM public.test_runs LIMIT 1;"
    assert fake_conn.executed[2] == "__closed__"


def test_database_connection_rejects_invalid_schema(monkeypatch):
    fake_conn = _FakeConn()
    monkeypatch.setattr(mod, "asyncpg", _FakeAsyncPg(fake_conn))

    try:
        mod.SupabaseDatabaseConnection(
            database_url="postgresql://postgres:pw@db.example:5432/postgres",
            schema="public;drop",
        )
        assert False, "Expected ValueError"
    except ValueError:
        assert True
