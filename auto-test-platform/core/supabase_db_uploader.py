"""Supabase PostgreSQL uploader using direct DATABASE_URL connection."""

import asyncio
import json
import re
from typing import Sequence

from core.base_test import TestResult

try:
    import asyncpg
except ImportError:  # pragma: no cover
    asyncpg = None


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class SupabaseDbUploader:
    """Upload test run and result rows directly into Supabase Postgres."""

    def __init__(self, database_url: str, schema: str = "public", timeout_sec: float = 15.0):
        if asyncpg is None:
            raise RuntimeError("asyncpg is required for DATABASE_URL uploads. Install asyncpg first.")
        if not _IDENTIFIER_RE.match(schema):
            raise ValueError(f"Invalid schema name: {schema!r}")
        self._database_url = database_url
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
        """Synchronously upload one run and all test results."""
        return asyncio.run(
            self._upload_run_results(
                external_run_id=external_run_id,
                station_id=station_id,
                started_at=started_at,
                ended_at=ended_at,
                summary=summary,
                results=results,
            )
        )

    def ping(self) -> None:
        """Validate database connectivity and schema accessibility."""
        asyncio.run(self._ping())

    async def _ping(self) -> None:
        conn = await asyncpg.connect(dsn=self._database_url, timeout=self._timeout_sec)
        try:
            await conn.execute("SELECT 1;")
            await conn.execute(f"SELECT 1 FROM {self._schema}.test_runs LIMIT 1;")
        finally:
            await conn.close()

    async def _upload_run_results(
        self,
        external_run_id: str,
        station_id: str,
        started_at: str,
        ended_at: str,
        summary: dict,
        results: Sequence[TestResult],
    ) -> str:
        conn = await asyncpg.connect(dsn=self._database_url, timeout=self._timeout_sec)
        run_sql = f"""
            INSERT INTO {self._schema}.test_runs (run_id, station_id, started_at, ended_at, summary_json)
            VALUES ($1, $2, $3::timestamptz, $4::timestamptz, $5::jsonb)
            ON CONFLICT (run_id) DO UPDATE SET
                station_id = EXCLUDED.station_id,
                started_at = EXCLUDED.started_at,
                ended_at = EXCLUDED.ended_at,
                summary_json = EXCLUDED.summary_json
            RETURNING id;
        """
        result_sql = f"""
            INSERT INTO {self._schema}.test_results (run_id, test_name, status, duration_sec, error_text, received_at)
            VALUES ($1::uuid, $2, $3, $4::numeric, $5, now());
        """
        try:
            row = await conn.fetchrow(
                run_sql,
                external_run_id,
                station_id,
                started_at,
                ended_at,
                json.dumps(summary),
            )
            if row is None:
                raise RuntimeError("Upsert test_runs failed and returned no row")

            run_uuid = str(row["id"])
            if results:
                await conn.executemany(
                    result_sql,
                    [
                        (
                            run_uuid,
                            item.name,
                            item.status,
                            round(item.duration, 4),
                            item.error,
                        )
                        for item in results
                    ],
                )
            return run_uuid
        finally:
            await conn.close()
