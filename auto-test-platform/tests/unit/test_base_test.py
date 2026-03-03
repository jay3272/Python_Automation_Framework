"""
Unit tests for core.base_test
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
from core.base_test import BaseTest, TestResult


# ---------------------------------------------------------------------------
# Concrete test implementations for testing purposes
# ---------------------------------------------------------------------------

class PassingTest(BaseTest):
    name = "passing_test"

    def execute(self):
        assert 1 + 1 == 2


class FailingTest(BaseTest):
    name = "failing_test"

    def execute(self):
        assert False, "intentional failure"


class ErrorTest(BaseTest):
    name = "error_test"

    def execute(self):
        raise RuntimeError("unexpected error")


class SkippedTest(BaseTest):
    name = "skipped_test"

    def skip_condition(self):
        return True

    def execute(self):
        raise AssertionError("should never run")


class SetupTeardownTest(BaseTest):
    name = "setup_teardown_test"

    def __init__(self):
        super().__init__()
        self.log = []

    def setup(self):
        self.log.append("setup")

    def execute(self):
        self.log.append("execute")

    def teardown(self):
        self.log.append("teardown")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_passing_test_returns_passed():
    result = PassingTest().run()
    assert result.status == "passed"
    assert result.error is None
    assert result.duration >= 0


def test_failing_test_returns_failed():
    result = FailingTest().run()
    assert result.status == "failed"
    assert "intentional failure" in result.error


def test_error_test_returns_error():
    result = ErrorTest().run()
    assert result.status == "error"
    assert "RuntimeError" in result.error


def test_skipped_test_returns_skipped():
    result = SkippedTest().run()
    assert result.status == "skipped"


def test_setup_and_teardown_called_in_order():
    test = SetupTeardownTest()
    test.run()
    assert test.log == ["setup", "execute", "teardown"]


def test_teardown_called_even_on_failure():
    class TeardownOnFailure(BaseTest):
        name = "teardown_on_failure"
        teardown_called = False

        def execute(self):
            assert False, "fail"

        def teardown(self):
            TeardownOnFailure.teardown_called = True

    TeardownOnFailure().run()
    assert TeardownOnFailure.teardown_called


def test_result_name_defaults_to_class_name():
    class UnnamedTest(BaseTest):
        def execute(self):
            pass

    result = UnnamedTest().run()
    assert result.name == "UnnamedTest"


def test_result_to_dict():
    result = PassingTest().run()
    d = result.to_dict()
    assert d["name"] == "passing_test"
    assert d["status"] == "passed"
    assert "duration" in d
    assert "error" in d
