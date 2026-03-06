"""Modular Supabase connection helpers for REST and Postgres access.

This module is intentionally independent from `core/` so it can be validated
before replacing existing uploader implementations.

Quick usage:

REST connection helper:
    >>> import json
    >>> from lib.supabase_connection import SupabaseRestConnection
    >>> conn = SupabaseRestConnection(
    ...     supabase_url="https://xxx.supabase.co",
    ...     service_role_key="your-service-role-key",
    ... )
    >>> payload = json.dumps([{"run_id": "run-1"}]).encode("utf-8")
    >>> request = conn.build_post_request("test_runs", payload)

Database connection helper:
    >>> from lib.supabase_connection import SupabaseDatabaseConnection
    >>> db = SupabaseDatabaseConnection(
    ...     database_url="postgresql://postgres:pw@host:5432/postgres",
    ... )
    >>> db.ping()  # raises on connectivity or schema/table issues
"""

from __future__ import annotations

import asyncio
import re
import urllib.parse
import urllib.request

try:
    import asyncpg
except ImportError:  # pragma: no cover
    asyncpg = None


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class SupabaseRestConnection:
    """Build REST API endpoints and headers for Supabase PostgREST."""

    def __init__(
        self,
        supabase_url: str,
        service_role_key: str,
        schema: str = "public",
        timeout_sec: float = 10.0,
    ):
        if not supabase_url:
            raise ValueError("supabase_url is required")
        if not service_role_key:
            raise ValueError("service_role_key is required")
        # Restrict schema format to avoid SQL/header injection from config values.
        _validate_schema(schema)

        self.base_url = supabase_url.rstrip("/") + "/rest/v1"
        self.service_role_key = service_role_key
        self.schema = schema
        self.timeout_sec = timeout_sec

    def table_endpoint(self, table: str, query: dict | None = None) -> str:
        """Return table endpoint URL, optionally including query string."""
        if not table:
            raise ValueError("table is required")

        endpoint = f"{self.base_url}/{table}"
        if query:
            endpoint += "?" + urllib.parse.urlencode(query)
        return endpoint

    def headers(self, prefer: str = "return=minimal") -> dict:
        """Return standard Supabase REST headers for authenticated requests."""
        return {
            "Content-Type": "application/json",
            "apikey": self.service_role_key,
            "Authorization": f"Bearer {self.service_role_key}",
            "Prefer": prefer,
            "Accept-Profile": self.schema,
            "Content-Profile": self.schema,
        }

    def build_post_request(self, table: str, payload: bytes, query: dict | None = None, prefer: str = "return=minimal"):
        """Create a configured POST request object for Supabase REST."""
        return urllib.request.Request(
            self.table_endpoint(table=table, query=query),
            data=payload,
            method="POST",
            headers=self.headers(prefer=prefer),
        )


class SupabaseDatabaseConnection:
    """Manage direct Postgres connectivity for Supabase DATABASE_URL usage."""

    def __init__(self, database_url: str, schema: str = "public", timeout_sec: float = 15.0):
        if asyncpg is None:
            raise RuntimeError("asyncpg is required for DATABASE_URL connections. Install asyncpg first.")
        if not database_url:
            raise ValueError("database_url is required")
        # Keep schema strict since it will be interpolated into SQL identifier slots.
        _validate_schema(schema)

        self.database_url = database_url
        self.schema = schema
        self.timeout_sec = timeout_sec

    async def connect(self):
        """Create and return an asyncpg connection."""
        return await asyncpg.connect(dsn=self.database_url, timeout=self.timeout_sec)

    async def ping_async(self) -> None:
        """Validate DB reachability and target schema visibility."""
        conn = await self.connect()
        try:
            # Basic connectivity check.
            await conn.execute("SELECT 1;")
            # Early signal if expected table/schema is not present.
            await conn.execute(f"SELECT 1 FROM {self.schema}.test_runs LIMIT 1;")
        finally:
            await conn.close()

    def ping(self) -> None:
        """Synchronous wrapper around ping_async for CLI use."""
        asyncio.run(self.ping_async())


def _validate_schema(schema: str) -> None:
    """Validate SQL identifier-like schema names (letters, numbers, underscore)."""
    if not _IDENTIFIER_RE.match(schema):
        raise ValueError(f"Invalid schema name: {schema!r}")
