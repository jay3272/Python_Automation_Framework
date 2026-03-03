"""
Unit tests for core.runner
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
from core.base_test import BaseTest
from core.runner import Runner


class QuickPass(BaseTest):
    name = "quick_pass"
    def execute(self):
        assert True


class QuickFail(BaseTest):
    name = "quick_fail"
    def execute(self):
        assert False, "expected failure"


def test_runner_all_pass():
    runner = Runner(workers=2)
    results = runner.run([QuickPass, QuickPass])
    assert all(r.status == "passed" for r in results)


def test_runner_mixed_results():
    runner = Runner(workers=2)
    results = runner.run([QuickPass, QuickFail])
    statuses = {r.status for r in results}
    assert "passed" in statuses
    assert "failed" in statuses


def test_runner_summary():
    runner = Runner(workers=2)
    results = runner.run([QuickPass, QuickFail])
    summary = runner.summary(results)
    assert summary["total"] == 2
    assert summary["passed"] == 1
    assert summary["failed"] == 1


def test_runner_on_result_callback():
    received = []
    runner = Runner(workers=1, on_result=received.append)
    runner.run([QuickPass])
    assert len(received) == 1
    assert received[0].status == "passed"


def test_runner_empty_list():
    runner = Runner()
    results = runner.run([])
    assert results == []
