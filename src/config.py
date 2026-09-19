"""Config loading. The single place that reads config.yaml."""
from __future__ import annotations

import copy
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = ROOT / "config.yaml"

DATA_PATH_ENV = "ORIGSIM_DATA_PATH"
"""Environment override for `data_path`.

Every consumer resolves the dataset through config, so one variable repoints the CLIs and the
Streamlit app at a different build. The test suite uses it to stay off the 1M-row dataset
(Section 13), and a deployment uses it to keep the data location out of the config file.
"""


def load_config(path: str | Path | None = None, overrides: dict | None = None) -> dict:
    """Load config.yaml. `overrides` is a shallow top-level merge, e.g. {"n_rows": 5000}.

    Precedence, lowest first: config.yaml, the ORIGSIM_DATA_PATH environment variable,
    explicit `overrides`.
    """
    with open(path or DEFAULT_CONFIG_PATH, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    cfg = copy.deepcopy(cfg)
    env_data_path = os.environ.get(DATA_PATH_ENV)
    if env_data_path:
        cfg["data_path"] = env_data_path
    for key, value in (overrides or {}).items():
        cfg[key] = value
    return cfg


def resolve_path(cfg_path: str | Path) -> Path:
    """Resolve a config-relative path against the project root."""
    p = Path(cfg_path)
    return p if p.is_absolute() else ROOT / p
