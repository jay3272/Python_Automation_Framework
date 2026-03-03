"""
base_test.py - Template Method Pattern for test execution lifecycle.

Defines the abstract base class that all tests should inherit from.
Subclasses override hook methods; the `run` method enforces the sequence.
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class TestResult:
    """Holds the outcome of a single test case."""

    def __init__(self, name: str):
        self.name = name
        self.status: str = "pending"   # pending | passed | failed | error | skipped
        self.duration: float = 0.0
        self.error: Optional[str] = None
        self.details: Dict[str, Any] = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "duration": round(self.duration, 4),
            "error": self.error,
            "details": self.details,
        }

    def __repr__(self) -> str:  # pragma: no cover
        return f"<TestResult name={self.name!r} status={self.status!r}>"


class BaseTest(ABC):
    """
    Abstract base class implementing the Template Method Pattern.

    Template method: `run()`
    Override hooks:  setup / teardown / execute / skip_condition
    """

    #: Human-readable name; defaults to the class name.
    name: str = ""

    def __init__(self):
        self._result = TestResult(self.name or self.__class__.__name__)

    # ------------------------------------------------------------------
    # Template method – do NOT override this in subclasses
    # ------------------------------------------------------------------

    def run(self) -> TestResult:
        """Execute the full test lifecycle and return a TestResult."""
        result = self._result
        start = time.monotonic()

        try:
            if self.skip_condition():
                result.status = "skipped"
                logger.info("[SKIP] %s", result.name)
                return result

            logger.info("[START] %s", result.name)
            self.setup()
            self.execute()
            result.status = "passed"
            logger.info("[PASS]  %s", result.name)

        except AssertionError as exc:
            result.status = "failed"
            result.error = str(exc)
            logger.warning("[FAIL]  %s — %s", result.name, exc)

        except Exception as exc:  # pylint: disable=broad-except
            result.status = "error"
            result.error = f"{type(exc).__name__}: {exc}"
            logger.error("[ERROR] %s — %s", result.name, exc, exc_info=True)

        finally:
            try:
                self.teardown()
            except Exception as exc:  # pylint: disable=broad-except
                logger.error("[TEARDOWN ERROR] %s — %s", result.name, exc)
            result.duration = time.monotonic() - start

        return result

    # ------------------------------------------------------------------
    # Hook methods – override in subclasses as needed
    # ------------------------------------------------------------------

    def setup(self) -> None:
        """Prepare the test environment (optional)."""

    @abstractmethod
    def execute(self) -> None:
        """Core test logic – must be implemented by every subclass."""

    def teardown(self) -> None:
        """Clean up after the test (optional)."""

    def skip_condition(self) -> bool:
        """Return True to skip this test entirely (optional)."""
        return False
