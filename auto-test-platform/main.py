"""
main.py - Entry point for the Auto-Test Platform.

Discovers and runs all tests found under the ``tests/`` directory,
generates an HTML report, and optionally posts results to the
collection server.

Usage
-----
    python main.py
    python main.py --workers 8 --timeout 60
    python main.py --server-url http://localhost:5000
"""

import argparse
import importlib
import inspect
import logging
import os
import pkgutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Type
from uuid import uuid4

# Allow absolute imports from the project root
sys.path.insert(0, str(Path(__file__).parent))

from core.base_test import BaseTest
from core.config import load_config
from core.supabase_db_uploader import SupabaseDbUploader
from core.report import Reporter
from core.runner import Runner
from core.supabase_uploader import SupabaseUploader

logger = logging.getLogger(__name__)


def _is_postgres_dsn(value: str) -> bool:
    """Return True when value looks like a PostgreSQL DSN."""
    lowered = value.lower()
    return lowered.startswith("postgresql://") or lowered.startswith("postgres://")


def _format_db_error_hint(exc: Exception) -> str:
    """Return actionable hint text for common DB connectivity errors."""
    text = str(exc)
    lowered = text.lower()
    if "network is unreachable" in lowered or "no route to host" in lowered:
        return (
            f"{text}. Hint: current runtime likely cannot reach port 5432. "
            "Use Supabase Pooler connection string (usually port 6543), "
            "or run from a network that allows outbound access to the DB host."
        )
    if "password authentication failed" in lowered:
        return f"{text}. Hint: verify DB password and ensure special characters are URL-encoded."
    if "name or service not known" in lowered or "temporary failure in name resolution" in lowered:
        return f"{text}. Hint: DNS cannot resolve DB host from current environment."
    return text


# ---------------------------------------------------------------------------
# Test discovery
# ---------------------------------------------------------------------------

def discover_tests(root: str = "tests") -> List[Type[BaseTest]]:
    """
    Recursively find all :class:`~core.base_test.BaseTest` subclasses
    inside *root*.
    """
    classes: List[Type[BaseTest]] = []
    root_path = Path(root)

    for finder, module_name, _ in pkgutil.walk_packages(
        path=[str(root_path)],
        prefix=root_path.name + ".",
        onerror=lambda name: logger.warning("Cannot import %s", name),
    ):
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Skipping %s — %s", module_name, exc)
            continue

        for _, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, BaseTest)
                and obj is not BaseTest
                and obj.__module__ == module.__name__
            ):
                classes.append(obj)

    logger.info("Discovered %d test class(es)", len(classes))
    return classes


# ---------------------------------------------------------------------------
# Optional: post results to the collection server
# ---------------------------------------------------------------------------

def post_results(server_url: str, results) -> None:
    """Send results JSON to the centralised collection server."""
    try:
        import urllib.request
        import json

        payload = json.dumps([r.to_dict() for r in results]).encode()
        req = urllib.request.Request(
            f"{server_url.rstrip('/')}/results",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            logger.info("Server response: %s", resp.status)
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("Could not post results to server — %s", exc)


def upload_results_to_supabase(
    supabase_url: str,
    supabase_key: str,
    results,
    station_id: str,
    started_at: str,
    ended_at: str,
    summary: dict,
    schema: str = "public",
) -> None:
    """Upload one run summary and all test results to Supabase."""
    try:
        uploader = SupabaseUploader(
            supabase_url=supabase_url,
            service_role_key=supabase_key,
            schema=schema,
        )
        external_run_id = str(uuid4())
        uploader.upload_run_results(
            external_run_id=external_run_id,
            station_id=station_id,
            started_at=started_at,
            ended_at=ended_at,
            summary=summary,
            results=results,
        )
        logger.info(
            "Uploaded %d result(s) to Supabase. external_run_id=%s",
            len(results),
            external_run_id,
        )
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("Could not upload results to Supabase — %s", exc)


def upload_results_to_supabase_db(
    database_url: str,
    results,
    station_id: str,
    started_at: str,
    ended_at: str,
    summary: dict,
    schema: str = "public",
) -> bool:
    """Upload test results using direct PostgreSQL connection."""
    try:
        uploader = SupabaseDbUploader(
            database_url=database_url,
            schema=schema,
        )
        external_run_id = str(uuid4())
        uploader.upload_run_results(
            external_run_id=external_run_id,
            station_id=station_id,
            started_at=started_at,
            ended_at=ended_at,
            summary=summary,
            results=results,
        )
        logger.info(
            "Uploaded %d result(s) to Supabase DB. external_run_id=%s",
            len(results),
            external_run_id,
        )
        return True
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("Could not upload results via DATABASE_URL — %s", _format_db_error_hint(exc))
        return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Auto-Test Platform runner",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--config", default=None, help="Path to config.yaml")
    p.add_argument("--workers", type=int, default=None, help="Parallel worker count")
    p.add_argument("--timeout", type=float, default=None, help="Per-test timeout (seconds)")
    p.add_argument("--report-dir", default=None, help="Output directory for reports")
    p.add_argument("--server-url", default=None, help="URL of the result-collection server")
    p.add_argument("--supabase-url", default=None, help="Supabase project URL")
    p.add_argument("--database-url", default=None, help="Direct PostgreSQL connection string")
    p.add_argument("--ping-db", action="store_true", help="Only validate DATABASE_URL connectivity and exit")
    p.add_argument("--tests-dir", default="tests", help="Root directory of test modules")
    return p


def main(argv=None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    )

    args = build_parser().parse_args(argv)

    cfg = load_config(args.config)

    workers = args.workers or cfg.get("runner.workers", default=4)
    timeout = args.timeout or cfg.get("runner.timeout", default=None)
    report_dir = args.report_dir or cfg.get("report.output_dir", default="reports")
    server_url = args.server_url or cfg.get("server.url", default=None)
    supabase_url = args.supabase_url or cfg.get("supabase.url", default=None)
    supabase_schema = cfg.get("supabase.schema", default="public")
    supabase_key_env = cfg.get("supabase.service_role_key_env", default="SUPABASE_SERVICE_ROLE_KEY")
    database_url = (
        args.database_url
        or os.environ.get(cfg.get("supabase.database_url_env", default="DATABASE_URL"), None)
        or cfg.get("supabase.database_url", default=None)
    )
    station_id = cfg.get("supabase.station_id", default="ST-UNKNOWN")

    if args.ping_db:
        if not database_url:
            logger.error("DATABASE_URL is not set")
            return 2
        if not _is_postgres_dsn(database_url):
            logger.error("DATABASE_URL is invalid. Expected postgresql:// or postgres://")
            return 2
        try:
            SupabaseDbUploader(database_url=database_url, schema=supabase_schema).ping()
            logger.info("DATABASE_URL connection check passed")
            return 0
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("DATABASE_URL connection check failed — %s", _format_db_error_hint(exc))
            return 2

    test_classes = discover_tests(args.tests_dir)
    if not test_classes:
        logger.warning("No tests found in %s", args.tests_dir)
        return 0

    runner = Runner(workers=workers, timeout=timeout)
    started_at = datetime.now(timezone.utc).isoformat()
    results = runner.run(test_classes)
    ended_at = datetime.now(timezone.utc).isoformat()

    reporter = Reporter(output_dir=report_dir)
    reporter.generate(results)

    if server_url:
        post_results(server_url, results)

    summary = runner.summary(results)

    if database_url and _is_postgres_dsn(database_url):
        db_uploaded = upload_results_to_supabase_db(
            database_url=database_url,
            results=results,
            station_id=station_id,
            started_at=started_at,
            ended_at=ended_at,
            summary=summary,
            schema=supabase_schema,
        )
        if not db_uploaded and supabase_url:
            logger.info("Falling back to Supabase REST upload")
            supabase_key = os.environ.get(supabase_key_env)
            if not supabase_key:
                logger.warning(
                    "Supabase key is missing. Set environment variable %s", supabase_key_env
                )
            else:
                upload_results_to_supabase(
                    supabase_url=supabase_url,
                    supabase_key=supabase_key,
                    results=results,
                    station_id=station_id,
                    started_at=started_at,
                    ended_at=ended_at,
                    summary=summary,
                    schema=supabase_schema,
                )
    elif database_url and not _is_postgres_dsn(database_url):
        logger.warning(
            "DATABASE_URL does not look like PostgreSQL DSN; skipping direct DB upload: %s",
            database_url,
        )
        if supabase_url:
            supabase_key = os.environ.get(supabase_key_env)
            if not supabase_key:
                logger.warning(
                    "Supabase key is missing. Set environment variable %s", supabase_key_env
                )
            else:
                upload_results_to_supabase(
                    supabase_url=supabase_url,
                    supabase_key=supabase_key,
                    results=results,
                    station_id=station_id,
                    started_at=started_at,
                    ended_at=ended_at,
                    summary=summary,
                    schema=supabase_schema,
                )
    elif supabase_url:
        supabase_key = os.environ.get(supabase_key_env)
        if not supabase_key:
            logger.warning(
                "Supabase key is missing. Set environment variable %s", supabase_key_env
            )
        else:
            upload_results_to_supabase(
                supabase_url=supabase_url,
                supabase_key=supabase_key,
                results=results,
                station_id=station_id,
                started_at=started_at,
                ended_at=ended_at,
                summary=summary,
                schema=supabase_schema,
            )

    return 0 if summary["failed"] == 0 and summary["error"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
