"""
retry.py - Retry mechanism with exponential back-off and jitter.

Usage as a decorator
--------------------
from core.retry import retry

@retry(max_attempts=3, delay=0.5, exceptions=(ValueError, IOError))
def flaky_operation():
    ...

Usage as a context helper
-------------------------
from core.retry import RetryPolicy

policy = RetryPolicy(max_attempts=5, delay=1.0, backoff=2.0)
result = policy.execute(flaky_operation, arg1, kwarg=value)
"""

import functools
import logging
import random
import time
from typing import Callable, Optional, Tuple, Type

logger = logging.getLogger(__name__)

# Default exception types that trigger a retry
_DEFAULT_EXCEPTIONS: Tuple[Type[Exception], ...] = (Exception,)


def retry(
    max_attempts: int = 3,
    delay: float = 0.5,
    backoff: float = 2.0,
    jitter: float = 0.1,
    exceptions: Tuple[Type[Exception], ...] = _DEFAULT_EXCEPTIONS,
) -> Callable:
    """
    Decorator that retries the wrapped function on failure.

    Parameters
    ----------
    max_attempts:
        Total number of attempts (including the first).
    delay:
        Initial sleep time in seconds between attempts.
    backoff:
        Multiplier applied to *delay* after each failure.
    jitter:
        Random fraction of *delay* added to avoid thundering-herd.
    exceptions:
        Tuple of exception types that should trigger a retry.
        All other exceptions propagate immediately.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            policy = RetryPolicy(
                max_attempts=max_attempts,
                delay=delay,
                backoff=backoff,
                jitter=jitter,
                exceptions=exceptions,
            )
            return policy.execute(func, *args, **kwargs)
        return wrapper
    return decorator


class RetryPolicy:
    """
    Encapsulates retry configuration and execution logic.

    Can be used stand-alone (without the decorator) when the policy
    itself needs to be passed around or reconfigured at runtime.
    """

    def __init__(
        self,
        max_attempts: int = 3,
        delay: float = 0.5,
        backoff: float = 2.0,
        jitter: float = 0.1,
        exceptions: Tuple[Type[Exception], ...] = _DEFAULT_EXCEPTIONS,
    ):
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        self.max_attempts = max_attempts
        self.delay = delay
        self.backoff = backoff
        self.jitter = jitter
        self.exceptions = exceptions

    def execute(self, func: Callable, *args, **kwargs):
        """
        Call *func* with the given arguments, retrying on allowed exceptions.

        Raises the last encountered exception if all attempts are exhausted.
        """
        current_delay = self.delay
        last_exc: Optional[Exception] = None

        for attempt in range(1, self.max_attempts + 1):
            try:
                return func(*args, **kwargs)
            except self.exceptions as exc:
                last_exc = exc
                if attempt == self.max_attempts:
                    break
                sleep_time = current_delay + random.uniform(0, self.jitter * current_delay)
                logger.warning(
                    "[RETRY] %s attempt %d/%d failed (%s: %s) — retrying in %.2fs",
                    getattr(func, "__name__", repr(func)),
                    attempt,
                    self.max_attempts,
                    type(exc).__name__,
                    exc,
                    sleep_time,
                )
                time.sleep(sleep_time)
                current_delay *= self.backoff

        logger.error(
            "[RETRY EXHAUSTED] %s failed after %d attempts",
            getattr(func, "__name__", repr(func)),
            self.max_attempts,
        )
        raise last_exc  # type: ignore[misc]
