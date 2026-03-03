"""
Unit tests for core.config
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import tempfile
import textwrap
from pathlib import Path

import pytest
from core.config import Config, load_config


SAMPLE_YAML = textwrap.dedent("""\
    runner:
      workers: 8
      timeout: 30
    report:
      output_dir: reports
    feature_flags:
      debug: true
""")


def test_config_attribute_access():
    cfg = Config({"runner": {"workers": 4}})
    assert cfg.runner.workers == 4


def test_config_get_dot_path():
    cfg = Config({"runner": {"workers": 4, "timeout": 60}})
    assert cfg.get("runner.workers") == 4
    assert cfg.get("runner.timeout") == 60


def test_config_get_missing_returns_default():
    cfg = Config({})
    assert cfg.get("runner.workers", default=2) == 2


def test_config_missing_attribute_raises():
    cfg = Config({})
    with pytest.raises(AttributeError):
        _ = cfg.nonexistent_key


def test_load_config_from_file():
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as fh:
        fh.write(SAMPLE_YAML)
        tmp_path = fh.name

    try:
        cfg = load_config(tmp_path)
        assert cfg.runner.workers == 8
        assert cfg.get("report.output_dir") == "reports"
        assert cfg.get("feature_flags.debug") is True
    finally:
        os.unlink(tmp_path)


def test_load_config_nonexistent_returns_empty():
    cfg = load_config("/tmp/nonexistent_config_xyz.yaml")
    assert cfg.as_dict() == {}


def test_config_as_dict():
    data = {"key": "value"}
    cfg = Config(data)
    assert cfg.as_dict() == data
