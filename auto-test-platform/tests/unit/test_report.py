"""
Unit tests for core.report
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import json
import tempfile
from pathlib import Path

import pytest
from core.base_test import TestResult
from core.report import Reporter


def _make_result(name, status, duration=0.1, error=None):
    r = TestResult(name)
    r.status = status
    r.duration = duration
    r.error = error
    return r


def test_reporter_creates_html_file(tmp_path):
    reporter = Reporter(output_dir=str(tmp_path))
    results = [
        _make_result("test_a", "passed"),
        _make_result("test_b", "failed", error="assertion failed"),
    ]
    html_path = reporter.generate(results)
    assert html_path.exists()
    content = html_path.read_text(encoding="utf-8")
    assert "test_a" in content
    assert "test_b" in content
    assert "PASSED" in content
    assert "FAILED" in content


def test_reporter_creates_json_file(tmp_path):
    reporter = Reporter(output_dir=str(tmp_path))
    results = [_make_result("test_x", "passed")]
    reporter.generate(results)
    json_path = tmp_path / "report.json"
    assert json_path.exists()
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["summary"]["total"] == 1
    assert data["summary"]["passed"] == 1
    assert len(data["results"]) == 1


def test_reporter_summary_counts():
    results = [
        _make_result("a", "passed"),
        _make_result("b", "failed"),
        _make_result("c", "error"),
        _make_result("d", "skipped"),
    ]
    counts = Reporter._counts(results)
    assert counts == {"passed": 1, "failed": 1, "error": 1, "skipped": 1, "total": 4}
