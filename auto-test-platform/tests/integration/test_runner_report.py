"""
Integration test: full runner → report pipeline.

Verifies that running multiple tests end-to-end produces a valid HTML
report and correct summary counts.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import json
from pathlib import Path

import pytest
from core.base_test import BaseTest
from core.runner import Runner
from core.report import Reporter


class SamplePass(BaseTest):
    name = "sample_pass"
    def execute(self):
        assert 2 * 2 == 4


class SampleFail(BaseTest):
    name = "sample_fail"
    def execute(self):
        assert 1 == 2, "math is broken"


class SampleSkip(BaseTest):
    name = "sample_skip"
    def skip_condition(self):
        return True
    def execute(self):
        pass


def test_runner_report_integration(tmp_path):
    runner = Runner(workers=2)
    results = runner.run([SamplePass, SampleFail, SampleSkip])

    reporter = Reporter(output_dir=str(tmp_path))
    html_path = reporter.generate(results)

    # HTML exists and contains test names
    assert html_path.exists()
    html = html_path.read_text(encoding="utf-8")
    assert "sample_pass" in html
    assert "sample_fail" in html
    assert "sample_skip" in html

    # JSON summary is accurate
    json_data = json.loads((tmp_path / "report.json").read_text())
    summary = json_data["summary"]
    assert summary["total"] == 3
    assert summary["passed"] == 1
    assert summary["failed"] == 1
    assert summary["skipped"] == 1
