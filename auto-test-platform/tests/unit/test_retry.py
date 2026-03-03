"""
Unit tests for core.retry
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
from core.retry import retry, RetryPolicy


def test_retry_succeeds_on_first_attempt():
    calls = []

    @retry(max_attempts=3)
    def ok():
        calls.append(1)
        return "ok"

    result = ok()
    assert result == "ok"
    assert len(calls) == 1


def test_retry_retries_on_failure_then_succeeds():
    calls = []

    @retry(max_attempts=3, delay=0, exceptions=(ValueError,))
    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise ValueError("not yet")
        return "done"

    result = flaky()
    assert result == "done"
    assert len(calls) == 3


def test_retry_raises_after_max_attempts():
    @retry(max_attempts=2, delay=0, exceptions=(ValueError,))
    def always_fails():
        raise ValueError("always")

    with pytest.raises(ValueError, match="always"):
        always_fails()


def test_retry_does_not_catch_unexpected_exception():
    @retry(max_attempts=3, delay=0, exceptions=(ValueError,))
    def type_error():
        raise TypeError("wrong type")

    with pytest.raises(TypeError):
        type_error()


def test_retry_policy_execute():
    policy = RetryPolicy(max_attempts=2, delay=0, exceptions=(OSError,))
    calls = []

    def fn():
        calls.append(1)
        if len(calls) == 1:
            raise OSError("first")
        return "success"

    result = policy.execute(fn)
    assert result == "success"
    assert len(calls) == 2


def test_retry_policy_invalid_max_attempts():
    with pytest.raises(ValueError):
        RetryPolicy(max_attempts=0)
