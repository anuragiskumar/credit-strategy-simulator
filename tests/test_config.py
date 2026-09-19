"""Config resolution, and the guard that keeps the suite off the 1M-row dataset (Section 13)."""
from __future__ import annotations

import os
from pathlib import Path

import yaml

from src.config import DATA_PATH_ENV, DEFAULT_CONFIG_PATH, load_config, resolve_path


def test_env_overrides_data_path(monkeypatch, tmp_path):
    target = tmp_path / "elsewhere.parquet"
    monkeypatch.setenv(DATA_PATH_ENV, str(target))
    assert load_config()["data_path"] == str(target)


def test_explicit_override_beats_env(monkeypatch, tmp_path):
    monkeypatch.setenv(DATA_PATH_ENV, str(tmp_path / "from_env.parquet"))
    cfg = load_config(overrides={"data_path": "from_argument.parquet"})
    assert cfg["data_path"] == "from_argument.parquet"


def test_env_absent_falls_back_to_config_file(monkeypatch):
    monkeypatch.delenv(DATA_PATH_ENV, raising=False)
    on_disk = yaml.safe_load(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
    assert load_config()["data_path"] == on_disk["data_path"]


def test_suite_never_reads_the_1m_dataset(app_dataset: Path):
    """The whole suite must run on a fresh clone, where `data/` does not exist at all.

    `data/` is gitignored, so a test that reads `config.data_path` passes only on the machine that
    happened to generate the 1M build. The `app_dataset` fixture repoints every consumer at a
    generated dataset; this asserts the redirect is actually in force, because the failure it
    guards against is invisible locally and total on a fresh clone.
    """
    default_path = resolve_path(yaml.safe_load(
        DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))["data_path"])
    assert os.environ[DATA_PATH_ENV] == str(app_dataset)
    assert resolve_path(load_config()["data_path"]) != default_path
    assert app_dataset.exists()
