"""
config.py - YAML-based configuration loader.

Loads ``config.yaml`` (or any YAML file) and exposes settings as a
typed, dot-accessible :class:`Config` object.

Usage
-----
from core.config import load_config

cfg = load_config()            # loads config.yaml in CWD
cfg = load_config("my.yaml")  # loads a custom path

print(cfg.runner.workers)
print(cfg.get("runner.workers", default=4))
"""

import os
import logging
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


class Config:
    """
    Wraps a parsed YAML dict, providing both attribute-style and
    dot-path access with optional defaults.
    """

    def __init__(self, data: dict):
        self._data = data or {}

    # ------------------------------------------------------------------
    # Attribute access  (cfg.runner  →  sub-Config)
    # ------------------------------------------------------------------

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            value = self._data[name]
        except KeyError:
            raise AttributeError(
                f"Configuration key {name!r} not found"
            ) from None
        return Config(value) if isinstance(value, dict) else value

    def __repr__(self) -> str:  # pragma: no cover
        return f"Config({self._data!r})"

    # ------------------------------------------------------------------
    # Dot-path access  (cfg.get("runner.workers", 4))
    # ------------------------------------------------------------------

    def get(self, path: str, default: Any = None) -> Any:
        """
        Retrieve a value by dot-separated *path*.

        Returns *default* when any key in the path is missing.
        """
        parts = path.split(".")
        node: Any = self._data
        for part in parts:
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    # ------------------------------------------------------------------
    # Raw dict access
    # ------------------------------------------------------------------

    def as_dict(self) -> dict:
        """Return the underlying dictionary."""
        return self._data


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------

def load_config(path: Optional[str] = None) -> Config:
    """
    Load a YAML configuration file and return a :class:`Config` instance.

    Parameters
    ----------
    path:
        File path to the YAML config.  If *None* the loader looks for
        ``config.yaml`` next to the project root.  The path may also be
        supplied via the ``ATP_CONFIG`` environment variable.
    """
    resolved = Path(
        path
        or os.environ.get("ATP_CONFIG", "")
        or _DEFAULT_CONFIG_PATH
    )

    if not resolved.exists():
        logger.warning("Config file not found at %s — using empty config", resolved)
        return Config({})

    with resolved.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    logger.debug("Loaded config from %s", resolved)
    return Config(data)
