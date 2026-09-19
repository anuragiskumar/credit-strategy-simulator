"""Decline waterfall, single-rule declines and the score x FOIR heatmap (Section 8)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.contracts import Strategy
from src.rules import evaluate_strategy
from src.segments import band_series


def build_waterfall(df: pd.DataFrame, strategy: Strategy, evaluation: pd.DataFrame | None = None,
                    adjustment: str | None = "historical") -> pd.DataFrame:
    """Sequential waterfall: applications -> removed by each rule in order -> approved.

    adjustment:
      "historical"        add a final step reconciling the written strategy to actual hist_decision
                          (manual override decline->approve / approve->decline)
      "segment_overrides" add a final step for approvals created by the strategy's segment overrides
      None                stop at the base-rule approvals

    Columns: step, label, kind, delta, delta_pct, remaining, remaining_pct.
    `kind` is start | rule | subtotal | adjustment | end. The frame reconciles by construction and
    the function raises if it does not.
    """
    ev = evaluate_strategy(df, strategy) if evaluation is None else evaluation
    n = len(df)
    first = ev["first_failed_rule"]
    rows: list[tuple] = [("Applications", "start", n)]

    for rule in strategy.rules:
        removed = int((first == rule.id).sum()) if rule.enabled else 0
        label = f"Removed by {rule.id}" + ("" if rule.enabled else " (off)")
        rows.append((label, "rule", -removed))

    base_approved = n + sum(d for _, k, d in rows if k == "rule")
    rows.append(("Approved by written strategy", "subtotal", None))

    if adjustment == "historical":
        engine_approve = (ev["decision"] == "approve").to_numpy()
        hist_approve = (df["hist_decision"] == "approve").to_numpy()
        rows.append(("Manual override: decline → approve", "adjustment",
                     int((~engine_approve & hist_approve).sum())))
        rows.append(("Manual override: approve → decline", "adjustment",
                     -int((engine_approve & ~hist_approve).sum())))
        rows.append(("Approved (actual)", "end", None))
        final_expected = int(hist_approve.sum())
    elif adjustment == "segment_overrides":
        rows.append(("Approved by segment overrides", "adjustment", int(ev["approved_by_override"].sum())))
        rows.append(("Approved (scenario)", "end", None))
        final_expected = int((ev["decision"] == "approve").sum())
    elif adjustment is None:
        final_expected = base_approved
    else:
        raise ValueError(f"Unknown adjustment '{adjustment}'")

    out, remaining = [], 0
    for i, (label, kind, delta) in enumerate(rows):
        if kind == "start":
            remaining, d = n, n
        elif kind in ("subtotal", "end"):
            d = None
        else:
            remaining += delta
            d = delta
        out.append({"step": i, "label": label, "kind": kind, "delta": d, "remaining": remaining})
    wf = pd.DataFrame(out)
    wf["delta_pct"] = wf["delta"] / n
    wf["remaining_pct"] = wf["remaining"] / n

    if int(wf["remaining"].iloc[-1]) != final_expected:
        raise AssertionError(
            f"Waterfall does not reconcile: ends at {wf['remaining'].iloc[-1]}, expected {final_expected}")
    if adjustment is None and int(wf.loc[wf["kind"] == "subtotal", "remaining"].iloc[0]) != base_approved:
        raise AssertionError("Waterfall subtotal does not reconcile")
    return wf


def single_rule_declines(df: pd.DataFrame, strategy: Strategy,
                         evaluation: pd.DataFrame | None = None) -> pd.DataFrame:
    """Declines that failed exactly one rule, by rule — the near-miss opportunity."""
    ev = evaluate_strategy(df, strategy) if evaluation is None else evaluation
    cols = [f"failed_{r.id}" for r in strategy.rules]
    failed = ev[cols].to_numpy()
    n_failed = failed.sum(axis=1)
    n = len(df)
    rows = []
    for j, rule in enumerate(strategy.rules):
        single = int((failed[:, j] & (n_failed == 1)).sum())
        rows.append({
            "rule_id": rule.id,
            "mandatory": rule.mandatory,
            "failed_any": int(failed[:, j].sum()),
            "single_rule_declines": single,
            "single_rule_pct_of_applications": single / n,
        })
    return pd.DataFrame(rows)


def decline_heatmap(df: pd.DataFrame, cfg: dict, strategy: Strategy,
                    evaluation: pd.DataFrame | None = None) -> pd.DataFrame:
    """Declined volume by bureau-score band (rows) x FOIR band (columns), per the written strategy.
    Applicants with no bureau score get their own 'No score' row."""
    ev = evaluate_strategy(df, strategy) if evaluation is None else evaluation
    declined = df.loc[(ev["decision"] == "decline").to_numpy()]
    score_band = band_series(declined["bureau_score"], cfg["waterfall"]["heatmap_score_edges"]).astype(object)
    score_band = score_band.where(declined["bureau_score"].notna(), "No score")
    foir_band = band_series(declined["foir"], cfg["waterfall"]["heatmap_foir_edges"])

    s_edges = cfg["waterfall"]["heatmap_score_edges"]
    s_labels = list(band_series(pd.Series([s_edges[0]]), s_edges).cat.categories) + ["No score"]
    f_labels = list(foir_band.cat.categories)
    table = pd.crosstab(pd.Categorical(score_band, categories=s_labels, ordered=True),
                        foir_band, dropna=False)
    table.index.name, table.columns.name = "score_band", "foir_band"
    return table.reindex(index=s_labels, columns=f_labels, fill_value=0)
