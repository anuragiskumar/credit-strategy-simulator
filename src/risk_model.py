"""PD model, training support and provenance labelling (REQUIREMENTS.md Sections 6 and 9).

The model is trained on booked customers only. It knows two things about where it may speak:

* marginal support  — per-feature decile bins / categorical levels with enough booked observations.
                      Decides whether a PD is produced at all (NaN otherwise -> NOT_MODELLED).
* joint support     — booked observations in the applicant's segmentation cell. An evidence count that
                      travels beside the PD; it never changes a PD or a decision.

Nothing here reads the synthetic outcome column; only `bad_flag` (booked customers) is used.
"""
from __future__ import annotations

import argparse
import itertools
import time

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

from src.config import load_config
from src.segments import cell_codes, cell_label, dimension_frame, dimensions_from_config
from src.util import log, print_json

# ---- provenance labels (Section 6)
OBSERVED = "OBSERVED"          # actual bad_flag of booked applicants
PREDICTED = "PREDICTED"        # model PD for booked applicants
INFERRED = "INFERRED"          # model PD x conservatism penalty for historically declined applicants
NOT_MODELLED = "NOT_MODELLED"  # outside training support: no PD is produced

SCORE_COL = "bureau_score"
VINTAGE_COL = "bureau_vintage_months"
MAX_CELLS_ENUMERATED = 50_000


class ModelQualityError(AssertionError):
    """The holdout AUC is below `model.min_auc`: the pipeline is broken, not the data."""


def _native(v):
    return v.item() if hasattr(v, "item") else v


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def _bin_index(x: np.ndarray, edges: np.ndarray) -> np.ndarray:
    """Bin i is [edges[i], edges[i+1]); the last bin also includes its upper edge.
    -1 for NaN or values outside the population range the edges were built from."""
    x = np.asarray(x, dtype=float)
    idx = np.searchsorted(edges, x, side="right") - 1
    idx = np.where(x == edges[-1], len(edges) - 2, idx)
    invalid = np.isnan(x) | (x < edges[0]) | (x > edges[-1])
    return np.where(invalid, -1, idx).astype(np.int64)


def _decile_edges(values: np.ndarray, n_bins: int) -> np.ndarray:
    """Quantile edges of the non-null values. Ties collapse, so discrete features get fewer bins."""
    v = values[~np.isnan(values)]
    edges = np.unique(np.quantile(v, np.linspace(0.0, 1.0, n_bins + 1)))
    if len(edges) < 2:
        edges = np.array([edges[0], edges[0]])
    return edges


class RiskModel:
    """Logistic PD model with explicit training support."""

    def __init__(self, cfg: dict | None = None):
        self.cfg = cfg or load_config()
        m = self.cfg["model"]
        self.numeric: list[str] = list(m["features"]["numeric"])
        self.categorical: list[str] = list(m["features"]["categorical"])
        self.dimensions = dimensions_from_config(self.cfg)
        self.fitted = False

    # ------------------------------------------------------------------ fit
    def fit(self, booked: pd.DataFrame, population: pd.DataFrame | None = None) -> "RiskModel":
        """Train on booked customers only.

        `population` is the full application population (approved + declined). Numeric support bins
        are deciles of that population (Section 9.2). If omitted, deciles come from `booked` and
        `population_source` says so — fine for unit tests, wrong for a real run.

        Training protocol: fit on a 70/30 split and report AUC / calibration on the 30%; the model
        that is kept is then refit on all supported booked rows with the same settings, so the support
        counts describe exactly the data it saw.
        """
        m = self.cfg["model"]
        pop = booked if population is None else population
        self.population_source = "booked only" if population is None else "full application population"
        self.n_pop_ = int(len(pop))

        # 1. Gate: no bureau score or a thin file -> outside the model altogether (9.1).
        booked = booked[self._gate(booked)]
        if booked["bad_flag"].isna().any():
            raise ValueError("booked rows must all carry a bad_flag")

        # 2. Categorical levels: drop any level with fewer than min_level_obs booked observations.
        booked_in = booked
        self._fit_levels(booked, pop, m["min_level_obs"])
        booked = booked[self._levels_ok(booked)]

        # 3. Numeric support: deciles of the full population, supported at >= min_support_obs booked obs.
        self._fit_numeric_support(booked, pop, m["support_bins"], m["min_support_obs"])
        train = booked[self._bins_ok(booked, with_range=False)]
        self.n_train_rows = int(len(train))
        # A dense bin can still span values no booked customer has (a wide tail decile). Support also
        # requires the value to sit inside the booked range of the rows the model was fitted on.
        self.range_ = {c: (float(train[c].min()), float(train[c].max())) for c in self.numeric}
        self._summarise_support(booked, pop, m)

        # 4. Coefficients: holdout fit for the metrics, final fit on everything supported.
        # Say why the training set is empty before sklearn says "n_samples=0". Pointing the app at a
        # small extract is a normal mistake (ORIGSIM_DATA_PATH, --data, a trimmed client sample), and
        # the support filters above are what emptied it, not the split.
        if len(train) == 0:
            raise ModelQualityError(
                f"no booked rows survive the training-support filters: {len(booked_in):,} booked rows in, "
                f"{len(booked):,} after dropping categorical levels below min_level_obs="
                f"{m['min_level_obs']}, 0 after dropping numeric bins below min_support_obs="
                f"{m['min_support_obs']}. The dataset is too small to fit a PD model — generate a "
                f"larger one, or lower those thresholds in config.yaml."
            )
        y = train["bad_flag"].to_numpy(dtype=int)
        X = self._design(train)
        tr, te = train_test_split(np.arange(len(train)), test_size=m["test_size"],
                                  random_state=m["random_state"], stratify=y)
        hold = self._fit_logit(X[tr], y[tr])
        p_te = _sigmoid(hold["intercept"] + X[te] @ hold["coef"])
        if len(np.unique(y[te])) < 2:
            raise ValueError("holdout set has a single outcome class; cannot compute AUC")
        self.metrics = {
            "auc": float(roc_auc_score(y[te], p_te)),
            "n_train": int(len(tr)),
            "n_test": int(len(te)),
            "test_bad_rate": float(y[te].mean()),
            "calibration": self._calibration(p_te, y[te]),
        }
        final = self._fit_logit(X, y)
        self.intercept_, self.coef_, self.coef_std_ = final["intercept"], final["coef"], final["coef_std"]

        # 5. Joint support: booked training observations per segmentation cell (9.2).
        frame, self._cell_levels = dimension_frame(train, self.dimensions)
        codes = cell_codes(frame)
        keys, counts = np.unique(codes[codes >= 0], return_counts=True)
        self._cell_keys, self._cell_counts = keys, counts
        self.fitted = True
        return self

    def assert_quality(self) -> None:
        auc, floor = self.metrics["auc"], self.cfg["model"]["min_auc"]
        if auc < floor:
            raise ModelQualityError(
                f"holdout AUC {auc:.4f} < {floor}: the pipeline is broken, not the data")

    # -- fit helpers
    def _gate(self, df: pd.DataFrame) -> pd.Series:
        return df[SCORE_COL].notna() & (df[VINTAGE_COL] >= self.cfg["model"]["min_vintage_months"])

    def _fit_levels(self, booked: pd.DataFrame, pop: pd.DataFrame, min_level_obs: int) -> None:
        self.levels_: dict[str, list] = {}       # surviving levels
        self.reference_: dict[str, object] = {}  # baseline level (most frequent survivor)
        self.dropped_levels_: list[dict] = []
        self._level_stats: dict[str, pd.DataFrame] = {}
        for col in self.categorical:
            universe = sorted({_native(v) for v in pop[col].dropna().astype(object).unique()}
                              | {_native(v) for v in booked[col].dropna().astype(object).unique()})
            b_counts = booked[col].astype(object).value_counts()
            p_counts = pop[col].astype(object).value_counts()
            rows = [{"level": lv, "booked_obs": int(b_counts.get(lv, 0)),
                     "applications": int(p_counts.get(lv, 0))} for lv in universe]
            stats = pd.DataFrame(rows)
            stats["supported"] = stats["booked_obs"] >= min_level_obs
            self._level_stats[col] = stats
            keep = stats[stats["supported"]]
            if keep.empty:
                raise ValueError(f"no level of '{col}' has >= {min_level_obs} booked observations")
            self.levels_[col] = list(keep["level"])
            self.reference_[col] = keep.loc[keep["booked_obs"].idxmax(), "level"]
            for _, r in stats[~stats["supported"]].iterrows():
                self.dropped_levels_.append({"feature": col, "level": r["level"],
                                             "booked_obs": int(r["booked_obs"]),
                                             "applications": int(r["applications"])})

    def _levels_ok(self, df: pd.DataFrame) -> np.ndarray:
        ok = np.ones(len(df), dtype=bool)
        for col in self.categorical:
            ok &= df[col].isin(self.levels_[col]).to_numpy()
        return ok

    def _fit_numeric_support(self, booked: pd.DataFrame, pop: pd.DataFrame, n_bins: int,
                             min_support_obs: int) -> None:
        self.edges_: dict[str, np.ndarray] = {}
        self.bin_booked_: dict[str, np.ndarray] = {}
        self.bin_pop_: dict[str, np.ndarray] = {}
        self.bin_supported_: dict[str, np.ndarray] = {}
        self.pop_null_: dict[str, int] = {}
        for col in self.numeric:
            edges = _decile_edges(pop[col].to_numpy(dtype=float), n_bins)
            k = len(edges) - 1
            self.edges_[col] = edges
            bidx = _bin_index(booked[col].to_numpy(dtype=float), edges)
            self.bin_booked_[col] = np.bincount(bidx[bidx >= 0], minlength=k)
            pidx = _bin_index(pop[col].to_numpy(dtype=float), edges)
            self.bin_pop_[col] = np.bincount(pidx[pidx >= 0], minlength=k)
            self.bin_supported_[col] = self.bin_booked_[col] >= min_support_obs
            self.pop_null_[col] = int(pop[col].isna().sum())

    def _bins_ok(self, df: pd.DataFrame, with_range: bool = True) -> np.ndarray:
        ok = np.ones(len(df), dtype=bool)
        for col in self.numeric:
            x = df[col].to_numpy(dtype=float)
            idx = _bin_index(x, self.edges_[col])
            ok &= (idx >= 0) & self.bin_supported_[col][idx.clip(min=0)]
            if with_range:
                lo, hi = self.range_[col]
                ok &= (x >= lo) & (x <= hi)
        return ok

    def _summarise_support(self, booked: pd.DataFrame, pop: pd.DataFrame, m: dict) -> None:
        rows = []
        self.pop_inside_: dict[str, int] = {}
        for col in self.numeric:
            edges = self.edges_[col]
            x = pop[col].to_numpy(dtype=float)
            pidx = _bin_index(x, edges)
            lo, hi = self.range_[col]
            in_range = (x >= lo) & (x <= hi)
            self.pop_inside_[col] = int((in_range & (pidx >= 0) & self.bin_supported_[col][pidx.clip(min=0)]).sum())
            for i in range(len(edges) - 1):
                last = i == len(edges) - 2
                rows.append({
                    "feature": col, "kind": "bin",
                    "label": f"[{edges[i]:g}, {edges[i + 1]:g}{']' if last else ')'}",
                    "lo": float(edges[i]), "hi": float(edges[i + 1]),
                    "booked_obs": int(self.bin_booked_[col][i]),
                    "applications": int(self.bin_pop_[col][i]),
                    "applications_in_booked_range": int((in_range & (pidx == i)).sum()),
                    "supported": bool(self.bin_supported_[col][i]),
                    "threshold": m["min_support_obs"]})
            rows.append({"feature": col, "kind": "gate", "label": "null", "lo": np.nan, "hi": np.nan,
                         "booked_obs": 0, "applications": self.pop_null_[col],
                         "supported": False, "threshold": np.nan})
        for col in self.categorical:
            for _, r in self._level_stats[col].iterrows():
                rows.append({"feature": col, "kind": "level", "label": str(r["level"]),
                             "lo": np.nan, "hi": np.nan, "booked_obs": int(r["booked_obs"]),
                             "applications": int(r["applications"]),
                             "supported": bool(r["supported"]), "threshold": m["min_level_obs"]})
        v_min = m["min_vintage_months"]
        pop_ok = pop[VINTAGE_COL] >= v_min
        rows.append({"feature": VINTAGE_COL, "kind": "gate", "label": f">= {v_min} (thin-file gate)",
                     "lo": float(v_min), "hi": np.inf, "booked_obs": int(len(booked)),
                     "applications": int(pop_ok.sum()), "supported": True, "threshold": np.nan})
        rows.append({"feature": VINTAGE_COL, "kind": "gate", "label": f"< {v_min} (thin file)",
                     "lo": -np.inf, "hi": float(v_min), "booked_obs": 0,
                     "applications": int((~pop_ok).sum()), "supported": False, "threshold": np.nan})
        s = pd.DataFrame(rows)
        s["applications_in_booked_range"] = s["applications_in_booked_range"].fillna(s["applications"])
        s["headroom"] = s["booked_obs"] / s["threshold"] - 1.0   # +0.06 = 6% above the threshold
        self._support_summary = s

    def _design(self, df: pd.DataFrame, mask: np.ndarray | None = None) -> np.ndarray:
        """Numeric columns, then one 0/1 column per non-reference surviving level."""
        cols = []
        for col in self.numeric:
            x = df[col].to_numpy(dtype=float)
            cols.append(x if mask is None else x[mask])
        for col in self.categorical:
            v = df[col]
            for lv in self.levels_[col]:
                if lv == self.reference_[col]:
                    continue
                d = (v == lv).to_numpy(dtype=float)
                cols.append(d if mask is None else d[mask])
        return np.column_stack(cols)

    def _terms(self) -> list[tuple[str, str]]:
        terms = [(c, "numeric") for c in self.numeric]
        for col in self.categorical:
            terms += [(f"{col}={lv}", "level") for lv in self.levels_[col] if lv != self.reference_[col]]
        return terms

    def _fit_logit(self, X: np.ndarray, y: np.ndarray) -> dict:
        """L2 logistic regression on standardised numerics; coefficients are returned in raw units."""
        k = len(self.numeric)
        mu, sd = np.zeros(X.shape[1]), np.ones(X.shape[1])
        mu[:k], sd[:k] = X[:, :k].mean(axis=0), X[:, :k].std(axis=0)
        sd[:k] = np.where(sd[:k] > 0, sd[:k], 1.0)
        lr = LogisticRegression(C=self.cfg["model"]["l2_C"], max_iter=1000,
                                random_state=self.cfg["model"]["random_state"])
        lr.fit((X - mu) / sd, y)
        coef_std = lr.coef_[0]
        coef = coef_std / sd
        return {"intercept": float(lr.intercept_[0] - np.sum(coef_std * mu / sd)),
                "coef": coef, "coef_std": coef_std}

    @staticmethod
    def _calibration(p: np.ndarray, y: np.ndarray, n_bins: int = 10) -> pd.DataFrame:
        d = pd.DataFrame({"p": p, "y": y})
        d["decile"] = pd.qcut(d["p"].rank(method="first"), n_bins, labels=False) + 1
        g = d.groupby("decile")
        cal = pd.DataFrame({"n": g.size(), "mean_predicted": g["p"].mean(),
                            "observed_bad_rate": g["y"].mean(), "bads": g["y"].sum()}).reset_index()
        cal["ratio_obs_to_pred"] = cal["observed_bad_rate"] / cal["mean_predicted"]
        return cal

    # ------------------------------------------------------------------ predict
    def _require_fit(self) -> None:
        if not self.fitted:
            raise RuntimeError("RiskModel is not fitted")

    def support_mask(self, df: pd.DataFrame) -> pd.Series:
        """True where the model is entitled to produce a PD (marginal support, Section 9.2)."""
        self._require_fit()
        ok = (df[SCORE_COL].notna() & (df[VINTAGE_COL] >= self.cfg["model"]["min_vintage_months"])
              ).to_numpy(copy=True)
        ok &= self._levels_ok(df)
        ok &= self._bins_ok(df)
        return pd.Series(ok, index=df.index, name="model_support")

    def predict_pd(self, df: pd.DataFrame) -> pd.Series:
        """Model PD. NaN — never zero — for rows outside training support."""
        mask = self.support_mask(df).to_numpy()
        out = np.full(len(df), np.nan)
        if mask.any():
            out[mask] = _sigmoid(self.intercept_ + self._design(df, mask) @ self.coef_)
        return pd.Series(out, index=df.index, name="model_pd")

    def cell_support(self, df: pd.DataFrame) -> pd.Series:
        """Booked training observations in each row's segmentation cell (Section 9.2).

        An evidence count only — it never changes a decision or a PD. Independent of `support_mask`.
        Values outside the configured band edges fall into open-ended outer bands; a row with an
        undefined dimension (e.g. no score) or an unseen categorical level has no cell and gets 0.
        """
        self._require_fit()
        frame, _ = dimension_frame(df, self.dimensions, self._cell_levels)
        codes = cell_codes(frame)
        pos = np.searchsorted(self._cell_keys, codes).clip(max=max(len(self._cell_keys) - 1, 0))
        if len(self._cell_keys):
            hit = (codes >= 0) & (self._cell_keys[pos] == codes)
            out = np.where(hit, self._cell_counts[pos], 0)
        else:
            out = np.zeros(len(df), dtype=np.int64)
        return pd.Series(out.astype(np.int64), index=df.index, name="booked_in_cell")

    def is_thin(self, booked_in_cell) -> np.ndarray:
        return np.asarray(booked_in_cell) < self.cfg["model"]["min_cell_obs"]

    # ------------------------------------------------------------------ reporting
    def coefficients(self) -> pd.DataFrame:
        """Coefficients in raw units (explainability), with the standardised value for numerics."""
        self._require_fit()
        terms = self._terms()
        rows = [{"term": "intercept", "kind": "intercept", "coefficient": self.intercept_,
                 "odds_ratio": np.nan, "std_coefficient": np.nan, "reference": ""}]
        for (name, kind), c, cs in zip(terms, self.coef_, self.coef_std_):
            ref = ""
            if kind == "level":
                col = name.split("=")[0]
                ref = f"vs {self.reference_[col]}"
            rows.append({"term": name, "kind": kind, "coefficient": float(c),
                         "odds_ratio": float(np.exp(c)),
                         "std_coefficient": float(cs) if kind == "numeric" else np.nan,
                         "reference": ref})
        return pd.DataFrame(rows)

    def support_summary(self) -> pd.DataFrame:
        """Per feature bin / level: booked observations, applications and whether it is supported.

        `headroom` is booked_obs / threshold - 1, so a bin 6% above its threshold shows 0.06 — a
        boolean alone would hide how close the classification is to flipping.
        """
        self._require_fit()
        return self._support_summary.copy()

    def support_ranges(self) -> pd.DataFrame:
        """Per feature: the supported range or levels, and applications inside / outside it (counts).

        Numeric support = dense decile bin AND inside the booked min-max of the training rows."""
        self._require_fit()
        s = self._support_summary
        n_pop = self.n_pop_
        rows = []
        for col in self.numeric:
            b = s[(s["feature"] == col) & (s["kind"] == "bin")].reset_index(drop=True)
            inside = self.pop_inside_[col]
            lo, hi = self.range_[col]
            rows.append({"feature": col, "kind": "numeric", "supported": self._range_text(b, lo, hi),
                         "bins_supported": f"{int(b['supported'].sum())} of {len(b)}",
                         "booked_min": lo, "booked_max": hi,
                         "booked_obs_inside": int(b.loc[b["supported"], "booked_obs"].sum()),
                         "applications_inside": inside, "applications_outside": n_pop - inside,
                         "share_outside": (n_pop - inside) / n_pop})
        for col in self.categorical:
            lv = s[(s["feature"] == col) & (s["kind"] == "level")]
            inside = int(lv.loc[lv["supported"], "applications"].sum())
            rows.append({"feature": col, "kind": "categorical",
                         "supported": ", ".join(lv.loc[lv["supported"], "label"]),
                         "bins_supported": f"{int(lv['supported'].sum())} of {len(lv)}",
                         "booked_obs_inside": int(lv.loc[lv["supported"], "booked_obs"].sum()),
                         "applications_inside": inside, "applications_outside": n_pop - inside,
                         "share_outside": (n_pop - inside) / n_pop})
        g = s[(s["feature"] == VINTAGE_COL) & (s["kind"] == "gate")]
        inside = int(g.loc[g["supported"], "applications"].sum())
        rows.append({"feature": VINTAGE_COL, "kind": "gate", "supported": g.iloc[0]["label"],
                     "bins_supported": "1 of 2", "booked_obs_inside": int(g.iloc[0]["booked_obs"]),
                     "applications_inside": inside, "applications_outside": n_pop - inside,
                     "share_outside": (n_pop - inside) / n_pop})
        return pd.DataFrame(rows)

    @staticmethod
    def _range_text(bins: pd.DataFrame, lo: float, hi: float) -> str:
        """Supported bins merged into spans and clipped to the booked range [lo, hi]."""
        spans, cur = [], None
        for _, r in bins.iterrows():
            if r["supported"]:
                cur = [r["lo"], r["hi"]] if cur is None else [cur[0], r["hi"]]
            elif cur is not None:
                spans.append(cur)
                cur = None
        if cur is not None:
            spans.append(cur)
        spans = [(max(a, lo), min(b, hi)) for a, b in spans if max(a, lo) <= min(b, hi)]
        return ", ".join(f"{a:g}–{b:g}" for a, b in spans) if spans else "none"

    def cell_support_table(self, candidates: pd.DataFrame | None = None) -> pd.DataFrame:
        """Booked training observations per segmentation cell, empty cells included (Section 9.2).

        If `candidates` (e.g. declines the optimiser could approve) is given, adds how many of them
        sit in each cell — the cells that matter most for the recommendation.
        """
        self._require_fit()
        levels = [self._cell_levels[d.column] for d in self.dimensions]
        n_cells = int(np.prod([len(v) for v in levels]))
        cols = [d.column for d in self.dimensions]
        if n_cells > MAX_CELLS_ENUMERATED:
            raise ValueError(f"{n_cells} cells is too many to enumerate")
        grid = pd.DataFrame(list(itertools.product(*levels)), columns=cols)
        for d in self.dimensions:
            grid[d.column] = pd.Categorical(grid[d.column], categories=self._cell_levels[d.column])
        codes = cell_codes(grid)
        pos = np.searchsorted(self._cell_keys, codes).clip(max=max(len(self._cell_keys) - 1, 0))
        hit = (self._cell_keys[pos] == codes) if len(self._cell_keys) else np.zeros(len(codes), bool)
        grid["booked_obs"] = np.where(hit, self._cell_counts[pos] if len(self._cell_keys) else 0, 0)
        grid["thin"] = self.is_thin(grid["booked_obs"])
        if candidates is not None:
            cf, _ = dimension_frame(candidates, self.dimensions, self._cell_levels)
            cc = cell_codes(cf)
            k, n = np.unique(cc[cc >= 0], return_counts=True)
            lookup = dict(zip(k.tolist(), n.tolist()))
            grid["candidates"] = [lookup.get(int(c), 0) for c in codes]
        grid.insert(0, "cell", cell_label(grid))
        return grid


# --------------------------------------------------------------------------- provenance
def label_applicants(df: pd.DataFrame, model: RiskModel, penalty: float | None = None) -> pd.DataFrame:
    """Row-level provenance for every applicant (Section 6).

    performance_provenance   OBSERVED (booked) | INFERRED (declined, has a PD) | NOT_MODELLED
    pd                       model PD, x penalty for declined applicants (INFERRED); NaN if NOT_MODELLED
    pd_provenance            PREDICTED (booked) | INFERRED | NOT_MODELLED
    """
    penalty = model.cfg["model"]["inference_penalty"] if penalty is None else penalty
    raw = model.predict_pd(df)
    booked = df["booked"].to_numpy(dtype=bool)
    has_pd = raw.notna().to_numpy()
    perf = np.where(booked, OBSERVED, np.where(has_pd, INFERRED, NOT_MODELLED))
    pd_prov = np.where(has_pd, np.where(booked, PREDICTED, INFERRED), NOT_MODELLED)
    final = np.where(booked, raw.to_numpy(), np.minimum(raw.to_numpy() * penalty, 1.0))
    return pd.DataFrame({"performance_provenance": perf, "pd": final, "pd_provenance": pd_prov},
                        index=df.index)


def train_model(df: pd.DataFrame, cfg: dict | None = None) -> RiskModel:
    """Train on the booked rows of `df`, with deciles from all of `df`, and enforce the AUC floor."""
    cfg = cfg or load_config()
    model = RiskModel(cfg).fit(df[df["booked"]], population=df)
    model.assert_quality()
    return model


# --------------------------------------------------------------------------- near-cutoff anchor (9.4)
def _wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    denom = 1.0 + (z ** 2) / n
    center = (p + (z ** 2) / (2 * n)) / denom
    spread = (z * np.sqrt((p * (1 - p) + (z ** 2) / (4 * n)) / n)) / denom
    return max(0.0, float(center - spread)), min(1.0, float(center + spread))


def near_cutoff_anchor(df: pd.DataFrame, model: RiskModel, config: dict | None = None) -> dict:
    """Near-cutoff inference anchor (Section 9.4).

    Compares observed performance of override-approved applicants with model PDs of declines
    within the same segmentation cells (score band x FOIR band x employment_type).
    Also computes the naive version (score band alone) to demonstrate the FOIR mix effect.
    """
    cfg = config or model.cfg
    min_anchor_obs = cfg.get("model", {}).get("min_anchor_obs", 200)

    booked = df["booked"].to_numpy(dtype=bool)
    override = df["manual_override"].to_numpy(dtype=bool)
    override_approved = booked & override
    declined = ~booked

    dims = dimensions_from_config(cfg)
    dim_cols = [d.column for d in dims]
    frame, _ = dimension_frame(df, dims, getattr(model, "_cell_levels", None))
    frame["_cell_label"] = cell_label(frame[dim_cols])

    pds = model.predict_pd(df).to_numpy()
    bad_flags = df["bad_flag"].fillna(0).to_numpy(dtype=float)

    # 1. Cell-matched analysis
    df_ov = frame[override_approved].copy()
    ov_counts = df_ov["_cell_label"].value_counts()
    eligible_cells = set(ov_counts[ov_counts >= min_anchor_obs].index)

    cell_rows = []
    total_ov_count = 0
    total_ov_bads = 0.0
    total_dec_count = 0
    sum_weighted_model_pd = 0.0

    for clabel in sorted(eligible_cells):
        m_ov = override_approved & (frame["_cell_label"] == clabel).to_numpy()
        m_dec = declined & (frame["_cell_label"] == clabel).to_numpy() & ~np.isnan(pds)

        n_ov = int(m_ov.sum())
        bads_ov = float(bad_flags[m_ov].sum())
        rate_ov = bads_ov / n_ov if n_ov else float("nan")
        ci_lo, ci_hi = _wilson_ci(int(bads_ov), n_ov)

        n_dec = int(m_dec.sum())
        mean_pd_dec = float(pds[m_dec].mean()) if n_dec else float("nan")
        imp_penalty = rate_ov / mean_pd_dec if (mean_pd_dec and np.isfinite(mean_pd_dec)) else float("nan")

        first_row = frame[frame["_cell_label"] == clabel].iloc[0]
        row_dict = {col: str(first_row[col]) for col in dim_cols}
        row_dict.update({
            "cell": clabel,
            "override_count": n_ov,
            "override_bads": bads_ov,
            "observed_bad_rate": rate_ov,
            "ci_lower": ci_lo,
            "ci_upper": ci_hi,
            "declines_count": n_dec,
            "mean_model_pd": mean_pd_dec,
            "implied_penalty": imp_penalty,
        })
        cell_rows.append(row_dict)

        total_ov_count += n_ov
        total_ov_bads += bads_ov
        total_dec_count += n_dec
        if np.isfinite(mean_pd_dec):
            sum_weighted_model_pd += n_ov * mean_pd_dec

    cells_df = pd.DataFrame(cell_rows)

    vw_obs_rate = total_ov_bads / total_ov_count if total_ov_count else float("nan")
    vw_model_pd = sum_weighted_model_pd / total_ov_count if total_ov_count else float("nan")
    vw_penalty = vw_obs_rate / vw_model_pd if (vw_model_pd and np.isfinite(vw_model_pd)) else float("nan")

    volume_weighted = {
        "override_count": total_ov_count,
        "override_bads": total_ov_bads,
        "observed_bad_rate": vw_obs_rate,
        "declines_count": total_dec_count,
        "mean_model_pd": vw_model_pd,
        "implied_penalty": vw_penalty,
    }

    # 2. Naive version (score band alone)
    naive_rows = []
    total_naive_ov_count = 0
    total_naive_ov_bads = 0.0
    total_naive_dec_count = 0
    sum_naive_weighted_pd = 0.0

    if "bureau_score" in frame.columns:
        score_bands = frame["bureau_score"].dropna().unique()
        for sb in sorted(score_bands, key=lambda x: str(x)):
            m_sb_ov = override_approved & (frame["bureau_score"] == sb).to_numpy()
            n_sb_ov = int(m_sb_ov.sum())
            if n_sb_ov < min_anchor_obs:
                continue
            bads_sb_ov = float(bad_flags[m_sb_ov].sum())
            rate_sb_ov = bads_sb_ov / n_sb_ov if n_sb_ov else float("nan")
            ci_lo, ci_hi = _wilson_ci(int(bads_sb_ov), n_sb_ov)

            m_sb_dec = declined & (frame["bureau_score"] == sb).to_numpy() & ~np.isnan(pds)
            n_sb_dec = int(m_sb_dec.sum())
            mean_sb_pd = float(pds[m_sb_dec].mean()) if n_sb_dec else float("nan")
            imp_sb_penalty = rate_sb_ov / mean_sb_pd if (mean_sb_pd and np.isfinite(mean_sb_pd)) else float("nan")

            naive_rows.append({
                "score_band": str(sb),
                "override_count": n_sb_ov,
                "override_bads": bads_sb_ov,
                "observed_bad_rate": rate_sb_ov,
                "ci_lower": ci_lo,
                "ci_upper": ci_hi,
                "declines_count": n_sb_dec,
                "mean_model_pd": mean_sb_pd,
                "implied_penalty": imp_sb_penalty,
            })
            total_naive_ov_count += n_sb_ov
            total_naive_ov_bads += bads_sb_ov
            total_naive_dec_count += n_sb_dec
            if np.isfinite(mean_sb_pd):
                sum_naive_weighted_pd += n_sb_ov * mean_sb_pd

    naive_df = pd.DataFrame(naive_rows)
    naive_vw_obs = total_naive_ov_bads / total_naive_ov_count if total_naive_ov_count else float("nan")
    naive_vw_pd = sum_naive_weighted_pd / total_naive_ov_count if total_naive_ov_count else float("nan")
    naive_vw_penalty = naive_vw_obs / naive_vw_pd if (naive_vw_pd and np.isfinite(naive_vw_pd)) else float("nan")

    naive_total = {
        "override_count": total_naive_ov_count,
        "override_bads": total_naive_ov_bads,
        "observed_bad_rate": naive_vw_obs,
        "declines_count": total_naive_dec_count,
        "mean_model_pd": naive_vw_pd,
        "implied_penalty": naive_vw_penalty,
    }

    # 3. Direction validation
    cell_gap = vw_obs_rate - vw_model_pd if (np.isfinite(vw_obs_rate) and np.isfinite(vw_model_pd)) else 0.0
    naive_gap = naive_vw_obs - naive_vw_pd if (np.isfinite(naive_vw_obs) and np.isfinite(naive_vw_pd)) else 0.0
    direction_conflict = bool((cell_gap * naive_gap < 0) or ((vw_penalty - 1.0) * (naive_vw_penalty - 1.0) < 0))

    warnings = [
        "Override approvals were human-selected and are therefore favourably biased within their cell: "
        "the observed rate is a lower bound on that cell's true rate, so the implied penalty is a lower "
        "bound on the penalty you should use (not a direct selection estimate)."
    ]
    if direction_conflict:
        warnings.append(
            f"FOIR mix effect detected: measured across the whole score band, the naive implied penalty is {naive_vw_penalty:.3f} "
            f"({'penalty > 1' if naive_vw_penalty > 1 else 'penalty < 1'}), "
            f"while within matched cells the volume-weighted implied penalty is {vw_penalty:.3f} "
            f"({'penalty > 1' if vw_penalty > 1 else 'penalty < 1'}). "
            f"The two comparisons disagree in direction; always condition on FOIR as well."
        )

    return {
        "cells": cells_df,
        "volume_weighted": volume_weighted,
        "naive": naive_df,
        "naive_total": naive_total,
        "direction_conflict": direction_conflict,
        "warnings": warnings,
    }


# --------------------------------------------------------------------------- CLI
def _pct(x: float) -> str:
    return f"{100 * x:.2f}%"


def main(argv: list[str] | None = None) -> int:
    from src.loader import load_applications

    ap = argparse.ArgumentParser(description="Train the PD model; print AUC, calibration, coefficients, support.")
    ap.add_argument("--data", help="parquet path (default: config data_path)")
    ap.add_argument("--config", help="config.yaml path")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    df = load_applications(args.data, cfg)
    t0 = time.perf_counter()
    model = RiskModel(cfg).fit(df[df["booked"]], population=df)
    elapsed = time.perf_counter() - t0

    labels = label_applicants(df, model)
    prov_counts = labels["performance_provenance"].value_counts().to_dict()
    n_declined = int((~df["booked"]).sum())
    nm_declines = int(prov_counts.get(NOT_MODELLED, 0))
    cal, coefs = model.metrics["calibration"], model.coefficients()
    ranges, summary = model.support_ranges(), model.support_summary()

    log(f"\nHoldout AUC {model.metrics['auc']:.4f}  (floor {cfg['model']['min_auc']}; "
        f"train {model.metrics['n_train']:,} / test {model.metrics['n_test']:,}; fit {elapsed:.1f}s)")
    log("\nCalibration by decile of predicted PD (holdout):")
    log(cal.assign(mean_predicted=cal["mean_predicted"].map(_pct),
                   observed_bad_rate=cal["observed_bad_rate"].map(_pct)).to_string(index=False))
    log("\nCoefficients (raw units; levels vs reference):")
    log(coefs.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    if model.dropped_levels_:
        log("\nDropped categorical levels (too few booked observations, so NOT_MODELLED):")
        log(pd.DataFrame(model.dropped_levels_).to_string(index=False))
    log("\nSupported ranges (applications counted over the full population):")
    log(ranges.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    log("\nSupport bins (headroom = booked_obs / threshold - 1):")
    log(summary.drop(columns=["lo", "hi"]).to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    log("\nProvenance of every application: " + ", ".join(f"{k} {v:,}" for k, v in prov_counts.items()))
    log(f"NOT_MODELLED = {nm_declines / n_declined:.1%} of the {n_declined:,} declined applications: "
        f"a ceiling on what any inferred approval can reach.")

    # Near-cutoff inference anchor (Section 9.4)
    anchor = near_cutoff_anchor(df, model, cfg)
    log("\nNear-cutoff inference anchor (Section 9.4):")
    if not anchor["cells"].empty:
        log(anchor["cells"][["cell", "override_count", "observed_bad_rate", "declines_count", "mean_model_pd", "implied_penalty"]].to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    vw = anchor["volume_weighted"]
    log(f"\nVolume-weighted matched cells: observed {vw['observed_bad_rate']:.2%}, declines mean PD {vw['mean_model_pd']:.2%}, implied penalty {vw['implied_penalty']:.3f}")
    nt = anchor["naive_total"]
    log(f"Naive (score band alone):      observed {nt['observed_bad_rate']:.2%}, declines mean PD {nt['mean_model_pd']:.2%}, implied penalty {nt['implied_penalty']:.3f}")
    for w in anchor["warnings"]:
        log(f"WARNING: {w}")

    model.assert_quality()

    print_json({
        "auc": model.metrics["auc"],
        "min_auc": cfg["model"]["min_auc"],
        "auc_ok": model.metrics["auc"] >= cfg["model"]["min_auc"],
        "n_train_rows": model.n_train_rows,
        "n_holdout_train": model.metrics["n_train"],
        "n_holdout_test": model.metrics["n_test"],
        "fit_seconds": elapsed,
        "support_deciles_from": model.population_source,
        "calibration_holdout": cal,
        "coefficients": coefs,
        "dropped_levels": model.dropped_levels_,
        "support_ranges": ranges,
        "support_summary": summary,
        "application_provenance": prov_counts,
        "not_modelled_share_of_declines": nm_declines / n_declined,
        "near_cutoff_anchor": {
            "volume_weighted": anchor["volume_weighted"],
            "naive_total": anchor["naive_total"],
            "direction_conflict": anchor["direction_conflict"],
            "warnings": anchor["warnings"],
            "cells": anchor["cells"].to_dict(orient="records"),
            "naive": anchor["naive"].to_dict(orient="records"),
        },
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
