"""
runner.py - Parallel test runner using a thread / process pool.

Supports:
  * Concurrent execution via ThreadPoolExecutor or ProcessPoolExecutor
  * Per-test timeout
  * Progress callbacks
"""

import logging
import concurrent.futures
from typing import Callable, List, Optional, Sequence, Type

from core.base_test import BaseTest, TestResult

logger = logging.getLogger(__name__)


class Runner:
    """
    Execute a collection of :class:`~core.base_test.BaseTest` subclasses
    in parallel and aggregate their results.

    Parameters
    ----------
    workers:
        Maximum number of parallel workers (default: 4).
    timeout:
        Per-test timeout in seconds.  ``None`` means no timeout.
    use_processes:
        When *True* use ``ProcessPoolExecutor``; otherwise ``ThreadPoolExecutor``.
    on_result:
        Optional callback invoked with each :class:`~core.base_test.TestResult`
        as soon as it is available.
    """

    def __init__(
        self,
        workers: int = 4,
        timeout: Optional[float] = None,
        use_processes: bool = False,
        on_result: Optional[Callable[[TestResult], None]] = None,
    ):
        self.workers = workers
        self.timeout = timeout
        self.use_processes = use_processes
        self.on_result = on_result

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, test_classes: Sequence[Type[BaseTest]]) -> List[TestResult]:
        """
        Instantiate and run each test class, returning all results.

        Parameters
        ----------
        test_classes:
            An iterable of :class:`~core.base_test.BaseTest` *subclasses*
            (not instances).
        """
        results: List[TestResult] = []

        executor_cls = (
            concurrent.futures.ProcessPoolExecutor
            if self.use_processes
            else concurrent.futures.ThreadPoolExecutor
        )

        with executor_cls(max_workers=self.workers) as executor:
            future_to_cls = {
                executor.submit(_run_test, cls): cls for cls in test_classes
            }

            for future in concurrent.futures.as_completed(
                future_to_cls, timeout=self.timeout
            ):
                cls = future_to_cls[future]
                try:
                    result = future.result(timeout=self.timeout)
                except concurrent.futures.TimeoutError:
                    result = TestResult(cls.__name__)
                    result.status = "error"
                    result.error = f"Test timed out after {self.timeout}s"
                    logger.error("[TIMEOUT] %s", cls.__name__)
                except Exception as exc:  # pylint: disable=broad-except
                    result = TestResult(cls.__name__)
                    result.status = "error"
                    result.error = f"{type(exc).__name__}: {exc}"
                    logger.error("[RUNNER ERROR] %s — %s", cls.__name__, exc)

                results.append(result)
                if self.on_result:
                    self.on_result(result)

        return results

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def summary(self, results: List[TestResult]) -> dict:
        """Return a dict with pass / fail / error / skipped counts."""
        counts: dict = {"passed": 0, "failed": 0, "error": 0, "skipped": 0, "total": len(results)}
        for r in results:
            counts[r.status] = counts.get(r.status, 0) + 1
        return counts


# ---------------------------------------------------------------------------
# Module-level helper (must be picklable for ProcessPoolExecutor)
# ---------------------------------------------------------------------------

def _run_test(cls: Type[BaseTest]) -> TestResult:
    """Instantiate *cls* and call its ``run()`` method."""
    return cls().run()
