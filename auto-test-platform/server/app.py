"""
server/app.py - Centralised result collection server + Dashboard.

Exposes a lightweight Flask web app that:
  * Accepts POST /results — stores incoming test result JSON payloads
  * Serves  GET  /         — HTML dashboard showing all collected results
  * Serves  GET  /api/results — returns all results as JSON
  * Serves  GET  /health   — liveness probe

Run
---
    python server/app.py
    # or via gunicorn:
    gunicorn -w 2 -b 0.0.0.0:5000 "server.app:create_app()"
"""

import logging
import os
import sys
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from time import monotonic
from typing import Dict

from flask import Flask, jsonify, request, Response

# Allow running `python server/app.py` from project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.station_simulator import StationSimulator
from lib.supabase_connection import SupabaseRestConnection

logger = logging.getLogger(__name__)

# In-memory store — replace with a database for production use
_MAX_RUNS = int(os.environ.get("ATP_MAX_RUNS", 100))
_results_store: deque = deque(maxlen=_MAX_RUNS)

# In-memory station telemetry simulation
_STATION_COUNT = int(os.environ.get("ATP_STATION_COUNT", 10))
_STATION_UPDATE_SEC = float(os.environ.get("ATP_STATION_UPDATE_SEC", 2.0))
_station_simulator = StationSimulator(station_count=_STATION_COUNT)
_station_lock = Lock()
_station_cache = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "stations": _station_simulator.snapshot(),
    "_last_tick": monotonic(),
}

# ---------------------------------------------------------------------------
# Dashboard HTML (single-file, no external CDN required)
# ---------------------------------------------------------------------------

_DASHBOARD_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Auto-Test Platform - Dashboard</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            margin: 0; padding: 0; background: #1a1a2e; color: #eee; }}
    header {{ background: #16213e; padding: 20px 32px;
              border-bottom: 2px solid #0f3460; }}
    header h1 {{ margin: 0; font-size: 1.6em; color: #e94560; }}
    main {{ padding: 24px 32px; }}
    .cards {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 28px; }}
    .card {{ background: #16213e; border-radius: 10px; padding: 16px 24px;
             min-width: 130px; text-align: center; }}
    .card .num {{ font-size: 2.2em; font-weight: bold; }}
    .card .lbl {{ font-size: .85em; color: #aaa; margin-top: 4px; }}
    .green {{ color: #2ecc71; }} .red {{ color: #e74c3c; }}
    .orange {{ color: #e67e22; }} .grey {{ color: #95a5a6; }}
    h2 {{ color: #e94560; margin-top: 0; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th {{ background: #0f3460; color: #eee; padding: 10px 14px; text-align: left; }}
    td {{ padding: 9px 14px; border-bottom: 1px solid #0f3460; font-size: .9em; }}
    tr:hover td {{ background: #16213e; }}
    .badge {{ display: inline-block; padding: 2px 10px; border-radius: 12px;
              font-size: .8em; font-weight: bold; }}
    .passed  {{ background: #1a5c38; color: #2ecc71; }}
    .failed  {{ background: #5c1a1a; color: #e74c3c; }}
    .error   {{ background: #5c3a1a; color: #e67e22; }}
    .skipped {{ background: #3a3a3a; color: #95a5a6; }}
    .idle    {{ background: #5a4a1b; color: #f1c40f; }}
    .running {{ background: #1a5c38; color: #2ecc71; }}
    .warning {{ background: #5c3a1a; color: #e67e22; }}
    .offline {{ background: #3a3a3a; color: #95a5a6; }}
    .refresh {{ float: right; color: #aaa; font-size: .85em; margin-top: 6px; }}
    .stations {{ margin-top: 32px; }}
    .stations-grid {{ display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); margin-bottom: 20px; }}
    .station-card {{ background: #16213e; border-radius: 10px; padding: 14px 16px; text-align: center; }}
    .station-card .num {{ font-size: 1.8em; font-weight: bold; }}
    .station-card .lbl {{ font-size: .8em; color: #aaa; margin-top: 4px; }}
    .status-idle {{ color: #f1c40f; }}
    .status-running {{ color: #2ecc71; }}
    .status-warning {{ color: #e67e22; }}
    .status-offline {{ color: #95a5a6; }}
    .muted {{ color: #aaa; font-size: .85em; }}
    @media (max-width: 740px) {{
      header, main {{ padding-left: 16px; padding-right: 16px; }}
      th, td {{ padding: 8px; }}
    }}
  </style>
  <script>
    // Auto-refresh every 30 seconds
    setTimeout(() => location.reload(), 30000);
  </script>
</head>
<body>
<header>
  <h1>🧪 Auto-Test Platform Dashboard</h1>
</header>
<main>
  <h2>Test Result Overview <span class="refresh">auto-refreshes every 30 s</span></h2>
  <div class="cards">
    <div class="card"><div class="num">{total}</div><div class="lbl">Total Runs</div></div>
    <div class="card"><div class="num green">{passed}</div><div class="lbl">Passed</div></div>
    <div class="card"><div class="num red">{failed}</div><div class="lbl">Failed</div></div>
    <div class="card"><div class="num orange">{error}</div><div class="lbl">Error</div></div>
    <div class="card"><div class="num grey">{skipped}</div><div class="lbl">Skipped</div></div>
  </div>

  <h2>Recent Results</h2>
  <table>
    <thead>
      <tr>
        <th>#</th><th>Test</th><th>Status</th>
        <th>Duration (s)</th><th>Received</th><th>Error</th>
      </tr>
    </thead>
    <tbody>
      {rows}
    </tbody>
  </table>

  <div class="stations">
    <h2>Station Monitoring <span class="muted">latest update: {station_generated_at}</span></h2>
    <div class="stations-grid">
      <div class="station-card"><div class="num">{station_total}</div><div class="lbl">Stations</div></div>
      <div class="station-card"><div class="num status-running">{station_running}</div><div class="lbl">Running</div></div>
      <div class="station-card"><div class="num status-idle">{station_idle}</div><div class="lbl">Idle</div></div>
      <div class="station-card"><div class="num status-warning">{station_warning}</div><div class="lbl">Warning</div></div>
      <div class="station-card"><div class="num status-offline">{station_offline}</div><div class="lbl">Offline</div></div>
    </div>
    <table>
      <thead>
        <tr>
          <th>Station</th><th>Line</th><th>Status</th><th>Current Test</th>
          <th>Temp (C)</th><th>Utilization (%)</th><th>Pass</th><th>Fail</th><th>Heartbeat</th>
        </tr>
      </thead>
      <tbody>
        {station_rows}
      </tbody>
    </table>
  </div>
</main>
</body>
</html>"""

_ROW = (
    "<tr>"
    "<td>{idx}</td>"
    "<td>{name}</td>"
    "<td><span class='badge {status}'>{status_upper}</span></td>"
    "<td>{duration}</td>"
    "<td>{received}</td>"
    "<td style='color:#aaa;font-style:italic'>{error}</td>"
    "</tr>"
)

_STATION_ROW = (
    "<tr>"
    "<td>{station_id}</td>"
    "<td>{line}</td>"
    "<td><span class='badge {status}'>{status_upper}</span></td>"
    "<td>{current_test}</td>"
    "<td>{temperature_c}</td>"
    "<td>{utilization_pct}</td>"
    "<td>{pass_count}</td>"
    "<td>{fail_count}</td>"
    "<td>{last_heartbeat}</td>"
    "</tr>"
)


def _supabase_config() -> Dict[str, str]:
  """Return Supabase REST config if available via environment variables."""
  url = os.environ.get("SUPABASE_URL", "").strip()
  key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
  schema = os.environ.get("SUPABASE_SCHEMA", "public").strip() or "public"
  if not url or not key:
    return {}
  return {
    "url": url.rstrip("/"),
    "key": key,
    "schema": schema,
  }


def _supabase_connection() -> SupabaseRestConnection | None:
  """Build Supabase REST connection object from environment config."""
  cfg = _supabase_config()
  if not cfg:
    return None
  return SupabaseRestConnection(
    supabase_url=cfg["url"],
    service_role_key=cfg["key"],
    schema=cfg["schema"],
  )


def _supabase_get(path: str, query: Dict[str, str]) -> list:
  """Perform a GET request to Supabase REST and return JSON list payload."""
  connection = _supabase_connection()
  if connection is None:
    raise RuntimeError("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is not configured")

  return connection.get_json(table=path, query=query, timeout_sec=10)


def _fetch_results_from_supabase(limit: int = 200) -> list:
  """Fetch recent test results from Supabase view and map to dashboard format."""
  rows = _supabase_get(
    "v_recent_test_results",
    {
      "select": "test_name,status,duration_sec,error_text,received_at",
      "order": "received_at.desc",
      "limit": str(limit),
    },
  )
  return [
    {
      "name": row.get("test_name", "-"),
      "status": row.get("status", "error"),
      "duration": float(row.get("duration_sec", 0) or 0),
      "error": row.get("error_text"),
      "_received_at": row.get("received_at", "-"),
    }
    for row in rows
  ]


def _fetch_stations_from_supabase(limit: int = 200) -> Dict:
  """Fetch latest station telemetry from Supabase view and map to API format."""
  rows = _supabase_get(
    "v_latest_station_status",
    {
      "select": (
        "station_id,line,status,current_test,temperature_c,"
        "utilization_pct,pass_count,fail_count,heartbeat_at"
      ),
      "order": "heartbeat_at.desc",
      "limit": str(limit),
    },
  )
  stations = [
    {
      "station_id": row.get("station_id", "-"),
      "line": row.get("line", "-"),
      "status": row.get("status", "offline"),
      "current_test": row.get("current_test", "-"),
      "temperature_c": row.get("temperature_c", "-"),
      "utilization_pct": row.get("utilization_pct", "-"),
      "pass_count": row.get("pass_count", 0),
      "fail_count": row.get("fail_count", 0),
      "last_heartbeat": row.get("heartbeat_at", "-"),
    }
    for row in rows
  ]
  return {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "stations": stations,
  }


def _load_results_for_dashboard() -> list:
  """Return results from Supabase when configured, otherwise from in-memory store."""
  try:
    return _fetch_results_from_supabase(limit=300)
  except Exception as exc:  # pylint: disable=broad-except
    if _supabase_config():
      logger.warning("Supabase results fetch failed, fallback to memory store — %s", exc)
    return list(_results_store)


def _load_stations_for_dashboard() -> Dict:
  """Return station telemetry from Supabase when configured, otherwise simulator."""
  try:
    return _fetch_stations_from_supabase(limit=200)
  except Exception as exc:  # pylint: disable=broad-except
    if _supabase_config():
      logger.warning("Supabase stations fetch failed, fallback to simulator — %s", exc)
    return _refresh_station_cache()


def _refresh_station_cache(force: bool = False) -> Dict:
    """Update station telemetry at a fixed interval and return latest cache."""
    with _station_lock:
        elapsed = monotonic() - _station_cache["_last_tick"]
        if force or elapsed >= _STATION_UPDATE_SEC:
            _station_cache["stations"] = _station_simulator.tick()
            _station_cache["generated_at"] = datetime.now(timezone.utc).isoformat()
            _station_cache["_last_tick"] = monotonic()

        return {
            "generated_at": _station_cache["generated_at"],
            "stations": [s.copy() for s in _station_cache["stations"]],
        }


# ---------------------------------------------------------------------------
# Flask application factory
# ---------------------------------------------------------------------------

def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)

    # ------------------------------------------------------------------ #
    #  Routes                                                             #
    # ------------------------------------------------------------------ #

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"}), 200

    @app.post("/results")
    def receive_results():
        """
        Accept a JSON payload of one or many test results.

        Expected body (single result):
            {"name": "...", "status": "passed", "duration": 0.5, "error": null}

        Expected body (run summary):
            {"results": [...], "summary": {...}}
        """
        payload = request.get_json(force=True, silent=True)
        if payload is None:
            return jsonify({"error": "Invalid JSON"}), 400

        received_at = datetime.now(timezone.utc).isoformat()

        # Accept both a list and a single run-summary dict
        if isinstance(payload, list):
            items = payload
        elif "results" in payload:
            items = payload["results"]
        else:
            items = [payload]

        for item in items:
            item["_received_at"] = received_at
            _results_store.append(item)

        logger.info("Received %d result(s)", len(items))
        return jsonify({"accepted": len(items)}), 201

    @app.get("/api/results")
    def api_results():
        """Return all stored results as JSON."""
        return jsonify(_load_results_for_dashboard()), 200

    @app.get("/api/stations")
    def api_stations():
        """Return simulated station telemetry for dashboard monitoring."""
        payload = _load_stations_for_dashboard()
        return jsonify(payload), 200

    @app.get("/")
    def dashboard():
        """Render the HTML dashboard."""
        results = _load_results_for_dashboard()
        station_payload = _load_stations_for_dashboard()
        stations = station_payload["stations"]

        counts = {"total": len(results), "passed": 0, "failed": 0, "error": 0, "skipped": 0}
        for r in results:
            s = r.get("status", "error")
            counts[s] = counts.get(s, 0) + 1

        station_counts = {"idle": 0, "running": 0, "warning": 0, "offline": 0, "total": len(stations)}
        for station in stations:
            station_counts[station.get("status", "offline")] = (
                station_counts.get(station.get("status", "offline"), 0) + 1
            )

        rows_html = ""
        for idx, r in enumerate(reversed(results), start=1):
            status = r.get("status", "error")
            rows_html += _ROW.format(
                idx=idx,
                name=r.get("name", "—"),
                status=status,
                status_upper=status.upper(),
                duration=f"{r.get('duration', 0):.4f}",
                received=r.get("_received_at", "—"),
                error=r.get("error") or "",
            )

        station_rows_html = ""
        for station in stations:
            status = station.get("status", "offline")
            station_rows_html += _STATION_ROW.format(
                station_id=station.get("station_id", "-"),
                line=station.get("line", "-"),
                status=status,
                status_upper=status.upper(),
                current_test=station.get("current_test", "-"),
                temperature_c=station.get("temperature_c", "-"),
                utilization_pct=station.get("utilization_pct", "-"),
                pass_count=station.get("pass_count", 0),
                fail_count=station.get("fail_count", 0),
                last_heartbeat=station.get("last_heartbeat", "-"),
            )

        html = _DASHBOARD_TEMPLATE.format(
            rows=rows_html,
            station_rows=station_rows_html,
            station_generated_at=station_payload["generated_at"],
            station_total=station_counts["total"],
            station_running=station_counts["running"],
            station_idle=station_counts["idle"],
            station_warning=station_counts["warning"],
            station_offline=station_counts["offline"],
            **counts,
        )
        return Response(html, mimetype="text/html")

    return app


# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    port = int(os.environ.get("PORT", 5000))
    app = create_app()
    app.run(host="0.0.0.0", port=port, debug=False)
