"""Segment definitions and banding (config-driven, Section 10.2.2)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Dimension:
    column: str
    type: str                    # "band" | "categorical"
    edges: tuple | None = None   # band edges, ascending; bands are [e_i, e_{i+1})


def dimensions_from_config(cfg: dict) -> list[Dimension]:
    dims = []
    for d in cfg["segmentation"]:
        if d["type"] not in ("band", "categorical"):
            raise ValueError(f"Unknown segmentation type '{d['type']}'")
        if d["type"] == "band" and not d.get("edges"):
            raise ValueError(f"Band dimension '{d['column']}' needs edges")
        dims.append(Dimension(d["column"], d["type"], tuple(d["edges"]) if d.get("edges") else None))
    return dims


def band_label(lo: float, hi: float) -> str:
    """'680–699' for integer edges, '0.30–0.40' for fractional ones, '760+' for open-ended."""
    if np.isinf(hi):
        return f"{lo:g}+"
    if float(lo).is_integer() and float(hi).is_integer():
        return f"{int(lo)}–{int(hi) - 1}"
    return f"{lo:.2f}–{hi:.2f}"


def band_series(values: pd.Series, edges) -> pd.Series:
    """Ordered categorical band labels; NaN or out-of-range values become NaN."""
    edges = [float(e) for e in edges]
    labels = [band_label(edges[i], edges[i + 1]) for i in range(len(edges) - 1)]
    return pd.cut(values.astype(float), bins=edges, labels=labels, right=False, ordered=True)
