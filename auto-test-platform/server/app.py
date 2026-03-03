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

import json
import logging
import os
from collections import deque
from datetime import datetime, timezone
from typing import Dict, List

from flask import Flask, jsonify, request, Response

logger = logging.getLogger(__name__)

# In-memory store — replace with a database for production use
_MAX_RUNS = int(os.environ.get("ATP_MAX_RUNS", 100))
_results_store: deque = deque(maxlen=_MAX_RUNS)

# ---------------------------------------------------------------------------
# Dashboard HTML (single-file, no external CDN required)
# ---------------------------------------------------------------------------

_DASHBOARD_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Auto-Test Platform — Dashboard</title>
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
    .refresh {{ float: right; color: #aaa; font-size: .85em; margin-top: 6px; }}
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
  <div class="cards">
    <div class="card"><div class="num">{total}</div><div class="lbl">Total Runs</div></div>
    <div class="card"><div class="num green">{passed}</div><div class="lbl">Passed</div></div>
    <div class="card"><div class="num red">{failed}</div><div class="lbl">Failed</div></div>
    <div class="card"><div class="num orange">{error}</div><div class="lbl">Error</div></div>
    <div class="card"><div class="num grey">{skipped}</div><div class="lbl">Skipped</div></div>
  </div>

  <h2>Recent Results <span class="refresh">auto-refreshes every 30 s</span></h2>
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
        return jsonify(list(_results_store)), 200

    @app.get("/")
    def dashboard():
        """Render the HTML dashboard."""
        results = list(_results_store)
        counts = {"total": len(results), "passed": 0, "failed": 0, "error": 0, "skipped": 0}
        for r in results:
            s = r.get("status", "error")
            counts[s] = counts.get(s, 0) + 1

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

        html = _DASHBOARD_TEMPLATE.format(rows=rows_html, **counts)
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
