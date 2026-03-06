"""Supabase uploader for test run and test result records."""

import json
from typing import Sequence
import urllib.parse
import urllib.request

from core.base_test import TestResult


class SupabaseUploader:
    """Upload test run summary and detailed results via Supabase REST API."""

    def __init__(
        self,
        supabase_url: str,
        service_role_key: str,
        schema: str = "public",
        timeout_sec: float = 10.0,
    ):
        self._base_url = supabase_url.rstrip("/") + "/rest/v1"
        self._service_role_key = service_role_key
        self._schema = schema
        self._timeout_sec = timeout_sec

    def upload_run_results(
        self,
        external_run_id: str,
        station_id: str,
        started_at: str,
        ended_at: str,
        summary: dict,
        results: Sequence[TestResult],
    ) -> str:
        """Insert or upsert one run and bulk-insert its test results."""
        run_row = {
            "run_id": external_run_id,
            "station_id": station_id,
            "started_at": started_at,
            "ended_at": ended_at,
            "summary_json": summary,
        }

        run_resp = self._post(
            table="test_runs",
            rows=[run_row],
            query={"on_conflict": "run_id"},
            prefer="resolution=merge-duplicates,return=representation",
        )
        if not run_resp:
            raise RuntimeError("Supabase test_runs upsert returned empty response")

        db_run_id = run_resp[0]["id"]
        if not results:
            return db_run_id

        result_rows = [
            {
                "run_id": db_run_id,
                "test_name": item.name,
                "status": item.status,
                "duration_sec": round(item.duration, 4),
                "error_text": item.error,
            }
            for item in results
        ]
        self._post(table="test_results", rows=result_rows, prefer="return=minimal")
        return db_run_id

    def _post(self, table: str, rows: list, query: dict | None = None, prefer: str = "return=minimal"):
        endpoint = f"{self._base_url}/{table}"
        if query:
            endpoint += "?" + urllib.parse.urlencode(query)

        payload = json.dumps(rows).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "apikey": self._service_role_key,
                "Authorization": f"Bearer {self._service_role_key}",
                "Prefer": prefer,
                "Accept-Profile": self._schema,
                "Content-Profile": self._schema,
            },
        )

        with urllib.request.urlopen(req, timeout=self._timeout_sec) as response:
            body = response.read().decode("utf-8").strip()
            return json.loads(body) if body else []
