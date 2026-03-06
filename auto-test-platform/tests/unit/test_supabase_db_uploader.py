"""Unit tests for core.supabase_db_uploader."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import core.supabase_db_uploader as mod
from core.base_test import TestResult


class _FakeConn:
    def __init__(self):
        self.executed = []

    async def fetchrow(self, sql, *params):
        self.executed.append(("fetchrow", sql, params))
        return {"id": "00000000-0000-0000-0000-000000000001"}

    async def executemany(self, sql, params):
        self.executed.append(("executemany", sql, params))

    async def close(self):
        self.executed.append(("close", None, None))

    async def execute(self, sql):
        self.executed.append(("execute", sql, None))
        return "SELECT 1"


class _FakeDbConnection:
    def __init__(self, database_url, schema="public", timeout_sec=15.0, conn=None):
        self.database_url = database_url
        self.schema = schema
        self.timeout_sec = timeout_sec
        self._conn = conn

    async def connect(self):
        return self._conn


def test_upload_run_results_with_direct_db(monkeypatch):
    conn = _FakeConn()

    class _ConnectionFactory(_FakeDbConnection):
        def __init__(self, database_url, schema="public", timeout_sec=15.0):
            super().__init__(database_url, schema, timeout_sec, conn=conn)

    monkeypatch.setattr(mod, "SupabaseDatabaseConnection", _ConnectionFactory)

    uploader = mod.SupabaseDbUploader(
        database_url="postgresql://postgres:pw@db.example:5432/postgres",
        schema="public",
    )

    result = TestResult("smoke")
    result.status = "passed"
    result.duration = 0.4567

    run_id = uploader.upload_run_results(
        external_run_id="ext-001",
        station_id="ST-001",
        started_at="2026-03-06T10:00:00+00:00",
        ended_at="2026-03-06T10:00:05+00:00",
        summary={"total": 1, "passed": 1, "failed": 0, "error": 0, "skipped": 0},
        results=[result],
    )

    assert run_id == "00000000-0000-0000-0000-000000000001"
    assert conn.executed[0][0] == "fetchrow"
    assert conn.executed[1][0] == "executemany"


def test_invalid_schema_rejected(monkeypatch):
    class _RejectSchemaDbConnection(_FakeDbConnection):
        def __init__(self, database_url, schema="public", timeout_sec=15.0):
            if ";" in schema:
                raise ValueError("Invalid schema name")
            super().__init__(database_url, schema, timeout_sec)

    monkeypatch.setattr(mod, "SupabaseDatabaseConnection", _RejectSchemaDbConnection)

    try:
        mod.SupabaseDbUploader(
            database_url="postgresql://postgres:pw@db.example:5432/postgres",
            schema="public;drop",
        )
        assert False, "Expected ValueError"
    except ValueError:
        assert True


def test_ping_checks_connection_and_table(monkeypatch):
    conn = _FakeConn()

    class _ConnectionFactory(_FakeDbConnection):
        def __init__(self, database_url, schema="public", timeout_sec=15.0):
            super().__init__(database_url, schema, timeout_sec, conn=conn)

    monkeypatch.setattr(mod, "SupabaseDatabaseConnection", _ConnectionFactory)

    uploader = mod.SupabaseDbUploader(
        database_url="postgresql://postgres:pw@db.example:5432/postgres",
        schema="public",
    )

    uploader.ping()

    assert conn.executed[0][0] == "execute"
    assert "SELECT 1;" in conn.executed[0][1]
    assert conn.executed[1][0] == "execute"
    assert "public.test_runs" in conn.executed[1][1]
