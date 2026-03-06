"""Integration tests for dashboard Supabase-backed API behavior."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import server.app as app_module


def test_api_results_uses_supabase_when_env_present(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "dummy-key")

    def _fake_fetch(limit=200):
        return [
            {
                "name": "db_test_case",
                "status": "passed",
                "duration": 0.1,
                "error": None,
                "_received_at": "2026-03-06T00:00:00Z",
            }
        ]

    monkeypatch.setattr(app_module, "_fetch_results_from_supabase", _fake_fetch)

    app = app_module.create_app()
    client = app.test_client()

    response = client.get("/api/results")
    assert response.status_code == 200
    payload = response.get_json()
    assert isinstance(payload, list)
    assert payload[0]["name"] == "db_test_case"
    assert payload[0]["status"] == "passed"
