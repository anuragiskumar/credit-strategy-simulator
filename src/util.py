"""Small shared helpers for the headless entry points."""
from __future__ import annotations

import json
import math
import sys
from dataclasses import asdict, is_dataclass

import numpy as np
import pandas as pd


def jsonable(obj):
    """Recursively convert numpy / pandas / dataclass objects to plain JSON types. NaN -> null."""
    if isinstance(obj, pd.DataFrame):
        return [jsonable(r) for r in obj.to_dict(orient="records")]
    if isinstance(obj, pd.Series):
        return jsonable(obj.to_dict())
    if is_dataclass(obj) and not isinstance(obj, type):
        return jsonable(asdict(obj))
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [jsonable(v) for v in obj]
    if obj is pd.NA or obj is None:
        return None
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return None if math.isnan(f) or math.isinf(f) else f
    if isinstance(obj, (pd.Timestamp,)):
        return obj.isoformat()
    return str(obj) if not isinstance(obj, str) else obj


def print_json(payload) -> None:
    """Machine-readable JSON on stdout."""
    json.dump(jsonable(payload), sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


def log(*parts) -> None:
    """Human-readable output goes to stderr so stdout stays valid JSON."""
    print(*parts, file=sys.stderr)
