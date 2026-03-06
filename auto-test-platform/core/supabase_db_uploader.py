"""Supabase PostgreSQL uploader using direct DATABASE_URL connection."""

import asyncio
import json
from typing import Sequence

from core.base_test import TestResult
from lib.supabase_connection import SupabaseDatabaseConnection


class SupabaseDbUploader:
    """Upload test run and result rows directly into Supabase Postgres."""

    def __init__(self, database_url: str, schema: str = "public", timeout_sec: float = 15.0):
        self._connection = SupabaseDatabaseConnection(
            database_url=database_url,
            schema=schema,
            timeout_sec=timeout_sec,
        )
        self._schema = schema

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
        conn = await self._connection.connect()
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
        conn = await self._connection.connect()
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
