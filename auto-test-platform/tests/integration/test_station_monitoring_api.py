"""Integration tests for station monitoring API."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from server.app import create_app


def test_station_api_returns_10_stations_and_fields():
    app = create_app()
    client = app.test_client()

    response = client.get("/api/stations")

    assert response.status_code == 200
    data = response.get_json()
    assert "generated_at" in data
    assert "stations" in data
    assert len(data["stations"]) == 10

    first = data["stations"][0]
    assert first["station_id"].startswith("ST-")
    assert first["status"] in {"idle", "running", "warning", "offline"}
    assert "last_heartbeat" in first
