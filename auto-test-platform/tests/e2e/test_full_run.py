"""
E2E test: simulate a real test run driven by config.yaml.

Loads the project config, creates a runner with the configured worker
count, runs a small test suite, and asserts the report is produced.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import json
from pathlib import Path

import pytest
from core.base_test import BaseTest
from core.config import load_config
from core.runner import Runner
from core.report import Reporter


class E2ETest1(BaseTest):
    name = "e2e_test_1"
    def execute(self):
        assert "hello".upper() == "HELLO"


class E2ETest2(BaseTest):
    name = "e2e_test_2"
    def execute(self):
        data = {"key": "value"}
        assert data["key"] == "value"


def test_end_to_end_with_config(tmp_path):
    cfg = load_config()  # loads config.yaml from project root

    workers = cfg.get("runner.workers", default=2)
    runner = Runner(workers=workers)
    results = runner.run([E2ETest1, E2ETest2])

    reporter = Reporter(output_dir=str(tmp_path))
    html_path = reporter.generate(results)

    assert html_path.exists()
    json_path = tmp_path / "report.json"
    assert json_path.exists()

    data = json.loads(json_path.read_text())
    assert data["summary"]["passed"] == 2
    assert data["summary"]["failed"] == 0
