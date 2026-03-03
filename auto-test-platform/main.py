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
from pathlib import Path
from typing import List, Type

# Allow absolute imports from the project root
sys.path.insert(0, str(Path(__file__).parent))

from core.base_test import BaseTest
from core.config import load_config
from core.report import Reporter
from core.runner import Runner

logger = logging.getLogger(__name__)


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

    test_classes = discover_tests(args.tests_dir)
    if not test_classes:
        logger.warning("No tests found in %s", args.tests_dir)
        return 0

    runner = Runner(workers=workers, timeout=timeout)
    results = runner.run(test_classes)

    reporter = Reporter(output_dir=report_dir)
    reporter.generate(results)

    if server_url:
        post_results(server_url, results)

    summary = runner.summary(results)
    return 0 if summary["failed"] == 0 and summary["error"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
