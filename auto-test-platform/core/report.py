"""
report.py - HTML report generator and CI-friendly summary printer.

Generates:
  * A self-contained HTML report (``report.html`` by default)
  * A plain-text CI summary printed to stdout / stderr

Usage
-----
from core.report import Reporter

reporter = Reporter(output_dir="reports")
reporter.generate(results)
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Sequence

from core.base_test import TestResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# HTML template (single-file, no external dependencies)
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Test Report — {timestamp}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            margin: 0; padding: 20px; background: #f5f5f5; color: #333; }}
    h1   {{ color: #2c3e50; }}
    .summary {{ display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }}
    .badge {{ padding: 10px 20px; border-radius: 8px; font-weight: bold;
              color: #fff; font-size: 1.1em; }}
    .passed  {{ background: #27ae60; }}
    .failed  {{ background: #e74c3c; }}
    .error   {{ background: #e67e22; }}
    .skipped {{ background: #95a5a6; }}
    table {{ width: 100%; border-collapse: collapse; background: #fff;
             border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,.1); }}
    th {{ background: #2c3e50; color: #fff; padding: 12px; text-align: left; }}
    td {{ padding: 10px 12px; border-bottom: 1px solid #eee; }}
    tr:last-child td {{ border-bottom: none; }}
    .status-passed  {{ color: #27ae60; font-weight: bold; }}
    .status-failed  {{ color: #e74c3c; font-weight: bold; }}
    .status-error   {{ color: #e67e22; font-weight: bold; }}
    .status-skipped {{ color: #95a5a6; font-weight: bold; }}
    .error-msg {{ font-size: .85em; color: #777; font-style: italic; }}
  </style>
</head>
<body>
  <h1>🧪 Test Report</h1>
  <p>Generated: {timestamp} &nbsp;|&nbsp; Duration: {total_duration:.2f}s</p>
  <div class="summary">
    <div class="badge passed">✔ Passed: {passed}</div>
    <div class="badge failed">✘ Failed: {failed}</div>
    <div class="badge error">⚠ Error: {error}</div>
    <div class="badge skipped">⊘ Skipped: {skipped}</div>
  </div>
  <table>
    <thead>
      <tr><th>Test</th><th>Status</th><th>Duration (s)</th><th>Details</th></tr>
    </thead>
    <tbody>
      {rows}
    </tbody>
  </table>
</body>
</html>
"""

_ROW_TEMPLATE = """\
<tr>
  <td>{name}</td>
  <td class="status-{status}">{status_upper}</td>
  <td>{duration:.4f}</td>
  <td class="error-msg">{error}</td>
</tr>"""


class Reporter:
    """
    Generates an HTML report and prints a CI-friendly summary.

    Parameters
    ----------
    output_dir:
        Directory where ``report.html`` (and ``report.json``) are written.
        Created automatically if it does not exist.
    filename:
        Base filename for the HTML report (default: ``report.html``).
    """

    def __init__(self, output_dir: str = "reports", filename: str = "report.html"):
        self.output_dir = Path(output_dir)
        self.filename = filename

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self, results: Sequence[TestResult]) -> Path:
        """
        Write the HTML report and return its path.

        Also writes a companion ``report.json`` and prints a CI summary.
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)

        counts = self._counts(results)
        total_duration = sum(r.duration for r in results)
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        # --- HTML ---
        rows = "\n".join(
            _ROW_TEMPLATE.format(
                name=r.name,
                status=r.status,
                status_upper=r.status.upper(),
                duration=r.duration,
                error=r.error or "",
            )
            for r in results
        )
        html = _HTML_TEMPLATE.format(
            timestamp=timestamp,
            total_duration=total_duration,
            rows=rows,
            **counts,
        )
        html_path = self.output_dir / self.filename
        html_path.write_text(html, encoding="utf-8")
        logger.info("HTML report written to %s", html_path)

        # --- JSON (for CI / server ingestion) ---
        json_path = self.output_dir / "report.json"
        payload = {
            "timestamp": timestamp,
            "summary": counts,
            "total_duration": round(total_duration, 4),
            "results": [r.to_dict() for r in results],
        }
        json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        logger.info("JSON report written to %s", json_path)

        # --- CI summary ---
        self._print_ci_summary(counts, total_duration)

        return html_path

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _counts(results: Sequence[TestResult]) -> dict:
        counts = {"passed": 0, "failed": 0, "error": 0, "skipped": 0, "total": len(results)}
        for r in results:
            counts[r.status] = counts.get(r.status, 0) + 1
        return counts

    @staticmethod
    def _print_ci_summary(counts: dict, duration: float) -> None:
        line = "=" * 60
        print(line)
        print("TEST SUMMARY")
        print(line)
        print(f"  Total   : {counts['total']}")
        print(f"  Passed  : {counts['passed']}")
        print(f"  Failed  : {counts['failed']}")
        print(f"  Error   : {counts['error']}")
        print(f"  Skipped : {counts['skipped']}")
        print(f"  Duration: {duration:.2f}s")
        print(line)
        if counts["failed"] or counts["error"]:
            print("RESULT: ❌ FAILED")
        else:
            print("RESULT: ✅ PASSED")
        print(line)
