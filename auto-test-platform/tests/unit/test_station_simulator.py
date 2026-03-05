"""Unit tests for core.station_simulator."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest

from core.station_simulator import StationSimulator


def test_station_simulator_defaults_to_10_stations():
    sim = StationSimulator(seed=42)
    stations = sim.snapshot()

    assert len(stations) == 10
    assert stations[0]["station_id"] == "ST-001"
    assert stations[-1]["station_id"] == "ST-010"


def test_station_simulator_tick_keeps_expected_schema():
    sim = StationSimulator(station_count=10, seed=7)
    stations = sim.tick()

    assert len(stations) == 10
    sample = stations[0]
    assert set(sample.keys()) == {
        "station_id",
        "line",
        "status",
        "current_test",
        "temperature_c",
        "utilization_pct",
        "pass_count",
        "fail_count",
        "last_heartbeat",
    }


def test_station_simulator_invalid_count_raises():
    with pytest.raises(ValueError):
        StationSimulator(station_count=0)
