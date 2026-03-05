"""
station_simulator.py - Simulate test-station telemetry for dashboard monitoring.

The simulator maintains a small in-memory state for each station and updates
metrics over time to mimic a live production line.
"""

from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Dict, List, Optional


_STATUSES = ("idle", "running", "warning", "offline")


class StationSimulator:
    """Generate and update station telemetry snapshots."""

    def __init__(self, station_count: int = 10, seed: Optional[int] = None):
        if station_count <= 0:
            raise ValueError("station_count must be > 0")

        self._rng = random.Random(seed)
        self._stations: Dict[str, Dict] = {}

        for idx in range(1, station_count + 1):
            station_id = f"ST-{idx:03d}"
            self._stations[station_id] = {
                "station_id": station_id,
                "line": f"LINE-{((idx - 1) // 5) + 1}",
                "status": self._rng.choices(_STATUSES, weights=(20, 65, 10, 5), k=1)[0],
                "current_test": f"TEST-{self._rng.randint(1000, 9999)}",
                "temperature_c": round(self._rng.uniform(31.0, 52.0), 1),
                "utilization_pct": self._rng.randint(20, 95),
                "pass_count": self._rng.randint(20, 120),
                "fail_count": self._rng.randint(0, 10),
                "last_heartbeat": _utc_now_iso(),
            }

    def snapshot(self) -> List[Dict]:
        """Return a stable station list for API/dashboard consumption."""
        return [self._stations[key].copy() for key in sorted(self._stations.keys())]

    def tick(self) -> List[Dict]:
        """Advance station state and return the latest snapshot."""
        for station in self._stations.values():
            station["status"] = self._next_status(station["status"])

            if station["status"] == "running":
                station["current_test"] = f"TEST-{self._rng.randint(1000, 9999)}"
                station["utilization_pct"] = _clamp(
                    station["utilization_pct"] + self._rng.randint(-5, 8), 0, 100
                )
                station["temperature_c"] = round(
                    _clamp(station["temperature_c"] + self._rng.uniform(-1.5, 2.5), 20.0, 85.0),
                    1,
                )
                if self._rng.random() < 0.86:
                    station["pass_count"] += 1
                else:
                    station["fail_count"] += 1

            elif station["status"] == "idle":
                station["utilization_pct"] = _clamp(
                    station["utilization_pct"] + self._rng.randint(-8, 4), 0, 100
                )
                station["temperature_c"] = round(
                    _clamp(station["temperature_c"] + self._rng.uniform(-2.0, 1.0), 20.0, 85.0),
                    1,
                )

            elif station["status"] == "warning":
                station["current_test"] = f"TEST-{self._rng.randint(1000, 9999)}"
                station["utilization_pct"] = _clamp(
                    station["utilization_pct"] + self._rng.randint(-3, 6), 0, 100
                )
                station["temperature_c"] = round(
                    _clamp(station["temperature_c"] + self._rng.uniform(0.8, 3.5), 20.0, 95.0),
                    1,
                )
                station["fail_count"] += 1

            else:  # offline
                station["current_test"] = "-"
                station["utilization_pct"] = _clamp(station["utilization_pct"] - self._rng.randint(5, 12), 0, 100)
                station["temperature_c"] = round(
                    _clamp(station["temperature_c"] + self._rng.uniform(-2.5, -0.5), 20.0, 85.0),
                    1,
                )

            station["last_heartbeat"] = _utc_now_iso()

        return self.snapshot()

    def _next_status(self, current: str) -> str:
        if current == "running":
            return self._rng.choices(_STATUSES, weights=(18, 70, 9, 3), k=1)[0]
        if current == "idle":
            return self._rng.choices(_STATUSES, weights=(50, 40, 7, 3), k=1)[0]
        if current == "warning":
            return self._rng.choices(_STATUSES, weights=(15, 65, 15, 5), k=1)[0]
        return self._rng.choices(_STATUSES, weights=(30, 45, 10, 15), k=1)[0]



def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()



def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
