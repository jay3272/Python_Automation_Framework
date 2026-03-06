"""Unit tests for core.supabase_uploader."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from core.base_test import TestResult
from core.supabase_uploader import SupabaseUploader


class _FakeUploader(SupabaseUploader):
    def __init__(self):
        super().__init__(
            supabase_url="https://example.supabase.co",
            service_role_key="test-key",
        )
        self.calls = []

    def _post(self, table, rows, query=None, prefer="return=minimal"):
        self.calls.append(
            {
                "table": table,
                "rows": rows,
                "query": query,
                "prefer": prefer,
            }
        )
        if table == "test_runs":
            return [{"id": "run-uuid-1"}]
        return []


def test_upload_run_results_writes_runs_and_results():
    uploader = _FakeUploader()

    result = TestResult("sample")
    result.status = "passed"
    result.duration = 0.12

    db_run_id = uploader.upload_run_results(
        external_run_id="ext-run-1",
        station_id="ST-001",
        started_at="2026-03-06T10:00:00+00:00",
        ended_at="2026-03-06T10:00:01+00:00",
        summary={"passed": 1, "failed": 0, "error": 0, "skipped": 0, "total": 1},
        results=[result],
    )

    assert db_run_id == "run-uuid-1"
    assert len(uploader.calls) == 2
    assert uploader.calls[0]["table"] == "test_runs"
    assert uploader.calls[0]["rows"][0]["run_id"] == "ext-run-1"
    assert uploader.calls[1]["table"] == "test_results"
    assert uploader.calls[1]["rows"][0]["run_id"] == "run-uuid-1"


def test_upload_run_results_without_result_rows():
    uploader = _FakeUploader()

    db_run_id = uploader.upload_run_results(
        external_run_id="ext-run-2",
        station_id="ST-001",
        started_at="2026-03-06T10:00:00+00:00",
        ended_at="2026-03-06T10:00:01+00:00",
        summary={"passed": 0, "failed": 0, "error": 0, "skipped": 0, "total": 0},
        results=[],
    )

    assert db_run_id == "run-uuid-1"
    assert len(uploader.calls) == 1
    assert uploader.calls[0]["table"] == "test_runs"
