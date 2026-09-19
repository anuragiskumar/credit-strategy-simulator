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
    """'680–699' for integer edges, '0.30–0.40' for fractional ones, '760+' / '<640' for open-ended."""
    if np.isneginf(lo):
        return f"<{hi:g}"
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


# --------------------------------------------------------------------------- cells
def open_band_series(values: pd.Series, edges) -> pd.Series:
    """Like `band_series`, but with an open-ended band below the first edge and above the last.

    Config edges usually only cover the region the optimiser explores (e.g. 640-700). Evidence counts
    still have to be defined for every applicant, so values outside the edges land in '<640' / '700+'
    rather than NaN. Only NaN values stay NaN.
    """
    e = [-np.inf, *[float(x) for x in edges], np.inf]
    labels = [band_label(e[i], e[i + 1]) for i in range(len(e) - 1)]
    return pd.cut(values.astype(float), bins=e, labels=labels, right=False, ordered=True)


def dimension_frame(df: pd.DataFrame, dims: list[Dimension],
                    levels: dict[str, list] | None = None) -> tuple[pd.DataFrame, dict[str, list]]:
    """Segmentation-cell labels, one categorical column per dimension.

    `levels` fixes the categories of categorical dimensions (as returned by an earlier call), so a
    cell coded at fit time can be looked up on new data. Values not in `levels` become NaN.
    Returns (frame, levels-by-column).
    """
    out, used = {}, {}
    for d in dims:
        if d.type == "band":
            cat = open_band_series(df[d.column], d.edges)
        else:
            col = df[d.column]
            if levels is not None and d.column in levels:
                cats = list(levels[d.column])
            elif isinstance(col.dtype, pd.CategoricalDtype):
                cats = [str(c) for c in col.cat.categories]
            else:
                cats = sorted(str(v) for v in col.dropna().unique())
            cat = pd.Categorical(col.astype(object).where(col.notna(), None).map(
                lambda v: None if v is None else str(v)), categories=cats)
            cat = pd.Series(cat, index=df.index)
        out[d.column] = cat
        used[d.column] = [str(c) for c in cat.cat.categories]
    return pd.DataFrame(out, index=df.index), used


def cell_codes(frame: pd.DataFrame) -> np.ndarray:
    """One int64 per row identifying its cell (mixed radix over the dimension categories).
    -1 where any dimension is undefined."""
    code = np.zeros(len(frame), dtype=np.int64)
    undefined = np.zeros(len(frame), dtype=bool)
    for col in frame.columns:
        c = frame[col].cat.codes.to_numpy().astype(np.int64)
        undefined |= c < 0
        code = code * len(frame[col].cat.categories) + np.maximum(c, 0)
    return np.where(undefined, -1, code)


def cell_label(frame: pd.DataFrame) -> pd.Series:
    """Human-readable cell name, e.g. 'bureau_score 680–699 | foir 0.00–0.35 | employment_type salaried'."""
    parts = [col + " " + frame[col].astype(object).astype(str) for col in frame.columns]
    out = parts[0]
    for p in parts[1:]:
        out = out + " | " + p
    return out
