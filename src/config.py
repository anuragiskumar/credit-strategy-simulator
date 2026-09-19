"""Config loading. The single place that reads config.yaml."""
from __future__ import annotations

import copy
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = ROOT / "config.yaml"


def load_config(path: str | Path | None = None, overrides: dict | None = None) -> dict:
    """Load config.yaml. `overrides` is a shallow top-level merge, e.g. {"n_rows": 5000}."""
    with open(path or DEFAULT_CONFIG_PATH, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    cfg = copy.deepcopy(cfg)
    for key, value in (overrides or {}).items():
        cfg[key] = value
    return cfg


def resolve_path(cfg_path: str | Path) -> Path:
    """Resolve a config-relative path against the project root."""
    p = Path(cfg_path)
    return p if p.is_absolute() else ROOT / p
