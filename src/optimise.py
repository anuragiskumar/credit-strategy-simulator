"""Greedy optimiser, naive comparison, and swap-out analysis (REQUIREMENTS.md Section 10).

Finds an originations strategy that maximises approvals subject to business constraints
(Section 10.2). Also provides:
- naive cutoff reduction comparison (Section 10.2.3)
- swap-out analysis on currently approved book (Section 10.3)
- breakeven conservatism penalty calculation (Section 9.3)
"""
from __future__ import annotations

import argparse
import copy
import json
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import load_config
from src.contracts import OptimiserResult, ScenarioResult, SegmentExclusion, SegmentOverride, Strategy
from src.risk_model import INFERRED, NOT_MODELLED, OBSERVED, RiskModel, _wilson_ci, train_model
from src.rules import evaluate_strategy, strategy_from_config, with_exclusions, with_overrides, with_rule_params
from src.segments import band_label, band_series, cell_label, dimension_frame, dimensions_from_config
from src.simulate import blended_bad_rate, inferred_bad_rate, penalised_pd, simulate, simulate_detailed
from src.util import log, print_json


# --------------------------------------------------------------------------- constraints (10.2.1)
SUPPORTED_METRICS = {"blended_bad_rate"}


def evaluate_constraints(constraints: list[dict], metrics: dict[str, float]) -> tuple[bool, list[str]]:
    """Generic constraint evaluation.

    Returns (passed, list_of_failure_reasons).
    Unimplemented metrics named in config raise ValueError.
    """
    passed = True
    reasons = []
    for c in constraints:
        if not c.get("enabled", True):
            continue
        metric_name = c["metric"]
        if metric_name not in SUPPORTED_METRICS:
            raise ValueError(f"Unsupported constraint metric '{metric_name}'. Supported: {sorted(SUPPORTED_METRICS)}")
        if metric_name not in metrics:
            raise KeyError(f"Metric '{metric_name}' not provided for constraint evaluation")

        val = metrics[metric_name]
        thresh = float(c["threshold"])
        op = c.get("operator", "<=")

        ok = False
        if op == "<=":
            ok = val <= thresh
        elif op == "<":
            ok = val < thresh
        elif op == ">=":
            ok = val >= thresh
        elif op == ">":
            ok = val > thresh
        elif op == "==":
            ok = val == thresh
        else:
            raise ValueError(f"Unsupported constraint operator '{op}'")

        if not ok:
            passed = False
            reasons.append(f"breaches {c['name']} constraint: {val:.4f} {op} {thresh:.4f} is False")
    return passed, reasons


# --------------------------------------------------------------------------- breakeven penalty (9.3)
def calculate_breakeven_penalty(observed_bads: float, n_retained: int, modelled_pds: np.ndarray,
                                max_bad_rate: float) -> float:
    """Find the penalty at which blended_bad_rate first breaches max_bad_rate."""
    if len(modelled_pds) == 0:
        return float("nan")

    # If even at penalty 0 it breaches, breakeven is 0.0
    if blended_bad_rate(observed_bads, n_retained, modelled_pds, 0.0) > max_bad_rate:
        return 0.0

    # Binary search over [0, 10.0]
    lo, hi = 0.0, 10.0
    if blended_bad_rate(observed_bads, n_retained, modelled_pds, hi) <= max_bad_rate:
        return float("inf")

    for _ in range(35):
        mid = (lo + hi) / 2.0
        if blended_bad_rate(observed_bads, n_retained, modelled_pds, mid) <= max_bad_rate:
            lo = mid
        else:
            hi = mid
    return float(round((lo + hi) / 2.0, 4))


# --------------------------------------------------------------------------- candidate funnel
@dataclass
class CandidateFunnel:
    total_declines: int
    failed_only_relaxable: int
    inside_support: int
    in_viable_segments: int


# --------------------------------------------------------------------------- optimiser (10.2)
def _segment_condition(col: str, dim_type: str, val, edges: tuple | None) -> tuple[str, object]:
    """Map dimension cell value back to a SegmentOverride condition pair."""
    if dim_type == "band":
        # val is band label like '680–699' or '0.00–0.35'
        val_str = str(val)
        if val_str == band_label(-np.inf, edges[0]):
            return col, (-np.inf, float(edges[0]))
        if val_str == band_label(edges[-1], np.inf):
            return col, (float(edges[-1]), np.inf)
        for i in range(len(edges) - 1):
            lbl = band_label(edges[i], edges[i + 1])
            if lbl == val_str:
                return col, (float(edges[i]), float(edges[i + 1]))
        raise ValueError(f"Could not match band label '{val_str}' to edges {edges}")
    else:
        return col, [str(val)]


def optimise(df: pd.DataFrame, baseline: Strategy, model: RiskModel,
             config: dict, retained_booked: np.ndarray | None = None,
             comparison_baseline: Strategy | None = None) -> OptimiserResult:
    """Greedy segment optimiser (Section 10.2)."""
    min_segment_size = config["optimiser"]["min_segment_size"]
    max_segments_added = config["optimiser"]["max_segments_added"]
    penalty = config["model"]["inference_penalty"]
    relaxes = tuple(config["segment_overrides"]["default_relaxes"])
    active_constraints = [c for c in config["constraints"] if c.get("enabled", True)]

    # 1. Baseline state
    ev_base = evaluate_strategy(df, baseline)
    booked = df["booked"].to_numpy(dtype=bool)
    retained_booked = booked if retained_booked is None else np.asarray(retained_booked, dtype=bool)
    if retained_booked.shape != booked.shape or (retained_booked & ~booked).any():
        raise ValueError("retained_booked must be a subset of booked with the same shape")
    bad = df["bad_flag"].fillna(0).to_numpy(dtype=float)
    n_retained = int(retained_booked.sum())
    observed_bads = float(bad[retained_booked].sum())

    # 2. Candidate Funnel (Section 10.2)
    declined = ~booked
    total_declines = int(declined.sum())

    # Failed only among relaxable rules (R5_SCORE, R6_FOIR)
    mandatory_or_other_failed = np.zeros(len(df), dtype=bool)
    relaxable_failed = np.zeros(len(df), dtype=bool)
    for r in baseline.rules:
        f = ev_base[f"failed_{r.id}"].to_numpy(dtype=bool)
        if r.id in relaxes:
            relaxable_failed |= f
        else:
            mandatory_or_other_failed |= f

    eligible = declined & ~mandatory_or_other_failed & relaxable_failed
    if baseline.exclusions:
        from src.rules import override_condition_mask
        excluded_candidates = np.logical_or.reduce(
            [override_condition_mask(df, ex.conditions) for ex in baseline.exclusions])
        eligible &= ~excluded_candidates
    n_eligible = int(eligible.sum())

    # Inside training support
    support_mask = model.support_mask(df).to_numpy()
    candidates_mask = eligible & support_mask
    n_candidates = int(candidates_mask.sum())

    # 3. Segmentation along config dimensions (10.2.2)
    dims = dimensions_from_config(config)
    dim_cols = [d.column for d in dims]

    # Use band_series for candidate segmentation (out-of-range becomes NaN)
    seg_cols = {}
    for d in dims:
        if d.type == "band":
            seg_cols[d.column] = band_series(df[d.column], d.edges)
        else:
            col = df[d.column]
            cats = [str(c) for c in col.cat.categories] if isinstance(col.dtype, pd.CategoricalDtype) else sorted(
                str(v) for v in col.dropna().unique())
            seg_cols[d.column] = pd.Categorical(col.astype(str), categories=cats)
    seg_df = pd.DataFrame(seg_cols, index=df.index)

    # Valid candidates must have non-null segmentation dimensions
    valid_dim_mask = seg_df.notna().all(axis=1).to_numpy()
    candidates_mask &= valid_dim_mask

    # Raw model PDs for all candidates
    cand_indices = np.where(candidates_mask)[0]
    cand_df = df.iloc[cand_indices]
    cand_pds = model.predict_pd(cand_df).to_numpy()
    cand_penalised_pds = penalised_pd(cand_pds, penalty)
    cand_cells = model.cell_support(cand_df).to_numpy()

    # Group candidate rows by dimension categories
    cand_seg_df = seg_df.iloc[cand_indices].copy()
    cand_seg_df["_idx"] = np.arange(len(cand_indices))
    cand_seg_df["_pd"] = cand_pds
    cand_seg_df["_inf_pd"] = cand_penalised_pds
    cand_seg_df["_cell"] = cand_cells

    grouped = cand_seg_df.groupby(dim_cols, observed=True)

    segment_candidates = []
    n_in_viable = 0
    for group_key, grp in grouped:
        size = len(grp)
        if size < min_segment_size:
            continue
        n_in_viable += size

        # Build condition dict
        conditions = {}
        for d, k in zip(dims, group_key if isinstance(group_key, tuple) else (group_key,)):
            c_name, c_val = _segment_condition(d.column, d.type, k, d.edges)
            conditions[c_name] = c_val

        inf_rate = float(grp["_inf_pd"].mean())
        booked_in_cell = int(grp["_cell"].iloc[0])
        thin = bool(model.is_thin(booked_in_cell))

        # Human-readable rule label
        rule_desc = "Approve " + " AND ".join(
            f"{c} {v}" if not isinstance(v, tuple) else f"{c} {band_label(v[0], v[1])}"
            for c, v in conditions.items()
        )

        segment_candidates.append({
            "conditions": conditions,
            "rule_description": rule_desc,
            "count": size,
            "inferred_bad_rate": inf_rate,
            "booked_in_cell": booked_in_cell,
            "thin": thin,
            "row_indices": cand_indices[grp["_idx"].to_numpy()],
            "pds": grp["_pd"].to_numpy(),
        })

    # Sort deterministic: ascending by inferred bad rate, then descending count, then rule description
    segment_candidates.sort(key=lambda s: (s["inferred_bad_rate"], -s["count"], s["rule_description"]))

    # Candidate funnel
    funnel = CandidateFunnel(
        total_declines=total_declines,
        failed_only_relaxable=n_eligible,
        inside_support=n_candidates,
        in_viable_segments=n_in_viable,
    )

    # 4. Greedy selection respecting constraints
    added_list = []
    rejected_list = []
    current_swap_pds = []
    current_bads = observed_bads
    current_n_modelled = 0

    for seg in segment_candidates:
        if len(added_list) >= max_segments_added:
            rejected_list.append({
                "conditions": seg["conditions"],
                "rule_description": seg["rule_description"],
                "count": seg["count"],
                "inferred_bad_rate": seg["inferred_bad_rate"],
                "reason": f"reached max_segments_added ({max_segments_added})",
            })
            continue

        test_pds = np.concatenate([current_swap_pds, seg["pds"]]) if len(current_swap_pds) else seg["pds"]
        test_blended = blended_bad_rate(observed_bads, n_retained, test_pds, penalty)

        metrics = {"blended_bad_rate": test_blended}
        ok, reasons = evaluate_constraints(active_constraints, metrics)

        if ok:
            current_swap_pds = test_pds
            current_n_modelled = len(test_pds)
            added_list.append({
                "conditions": seg["conditions"],
                "rule_description": seg["rule_description"],
                "count": seg["count"],
                "inferred_bad_rate": seg["inferred_bad_rate"],
                "cumulative_bad_rate": test_blended,
                "booked_in_cell": seg["booked_in_cell"],
                "thin": seg["thin"],
            })
        else:
            rejected_list.append({
                "conditions": seg["conditions"],
                "rule_description": seg["rule_description"],
                "count": seg["count"],
                "inferred_bad_rate": seg["inferred_bad_rate"],
                "reason": "; ".join(reasons),
            })

    # Construct proposed Strategy with overrides from candidate segments
    overrides = tuple(
        SegmentOverride(conditions=s["conditions"], relaxes=relaxes)
        for s in added_list
    )
    proposed_strategy = with_overrides(baseline, overrides)

    # 5. Full simulation of proposed strategy
    headline = simulate(df, comparison_baseline or baseline, proposed_strategy, model, config)

    # Calculate THIN share of incremental approvals
    thin_count = sum(s["count"] for s in added_list if s.get("thin") is True)
    evaluated_swap_ins = sum(s["count"] for s in added_list)
    thin_share = float(thin_count / evaluated_swap_ins) if evaluated_swap_ins else 0.0
    thin_share_of_total = float(thin_count / headline.swap_in_count) if headline.swap_in_count else 0.0

    # Reconcile added segments table to headline swap-ins:
    # If the overrides approved applicants outside training support, add a NOT_MODELLED row
    n_not_modelled = headline.not_modelled_count
    if n_not_modelled > 0:
        added_list.append({
            "conditions": None,
            "rule_description": "NOT_MODELLED (outside training support)",
            "count": n_not_modelled,
            "inferred_bad_rate": np.nan,
            "cumulative_bad_rate": headline.blended_bad_rate,
            "booked_in_cell": pd.NA,
            "thin": pd.NA,
        })

    # Breakeven penalty
    max_br = next((float(c["threshold"]) for c in active_constraints if c["metric"] == "blended_bad_rate"), 0.035)
    breakeven_p = calculate_breakeven_penalty(observed_bads, n_retained, np.asarray(current_swap_pds), max_br)

    # 6. Naive comparison (10.2.3)
    naive_cutoff, naive_result = _find_naive_comparison(
        df, baseline, model, config, observed_bads, n_retained, penalty, active_constraints,
        comparison_baseline=comparison_baseline
    )

    added_df = pd.DataFrame(added_list) if added_list else pd.DataFrame(
        columns=["conditions", "rule_description", "count", "inferred_bad_rate",
                 "cumulative_bad_rate", "booked_in_cell", "thin"]
    )
    rejected_df = pd.DataFrame(rejected_list) if rejected_list else pd.DataFrame(
        columns=["conditions", "rule_description", "count", "inferred_bad_rate", "reason"]
    )

    has_appetite_rejection = any("breaches" in r["reason"] for r in rejected_list)
    has_slot_rejection = any("reached max_segments_added" in r["reason"] for r in rejected_list)

    if has_appetite_rejection:
        binding_constraint = "bad_rate"
    elif has_slot_rejection:
        binding_constraint = "max_segments_added"
    else:
        binding_constraint = "none"

    return OptimiserResult(
        headline=headline,
        added_segments=added_df,
        rejected_segments=rejected_df,
        naive_cutoff=float(naive_cutoff),
        naive_result=naive_result,
        breakeven_penalty=breakeven_p,
        strategy=proposed_strategy,
        thin_share=thin_share,
        thin_share_of_total=thin_share_of_total,
        binding_constraint=binding_constraint,
        candidate_funnel=funnel,
    )


# --------------------------------------------------------------------------- naive comparison (10.2.3)
def _find_naive_comparison(df: pd.DataFrame, baseline: Strategy, model: RiskModel, config: dict,
                           observed_bads: float, n_retained: int, penalty: float,
                           active_constraints: list[dict],
                           comparison_baseline: Strategy | None = None) -> tuple[float, ScenarioResult]:
    """Find lowest score cutoff keeping portfolio within constraints, costed on exact same basis."""
    start = int(config["optimiser"]["naive_cutoff_start"])
    stop = int(config["optimiser"]["naive_cutoff_stop"])
    step = int(config["optimiser"]["naive_cutoff_step"])

    # Identify candidate pool for naive reduction:
    # applicants who pass all other baseline rules, failed R5_SCORE, and were not booked
    ev = evaluate_strategy(df, baseline)
    booked = df["booked"].to_numpy(dtype=bool)
    other_failed = np.zeros(len(df), dtype=bool)
    for r in baseline.rules:
        if r.id != "R5_SCORE":
            other_failed |= ev[f"failed_{r.id}"].to_numpy(dtype=bool)

    pool_mask = (~booked) & (~other_failed) & (df["bureau_score"].notna()) & (df["bureau_score"] < start)
    if baseline.exclusions:
        from src.rules import override_condition_mask
        pool_mask &= ~np.logical_or.reduce(
            [override_condition_mask(df, ex.conditions) for ex in baseline.exclusions])
    pool_idx = np.where(pool_mask)[0]
    pool_df = df.iloc[pool_idx]
    pool_scores = pool_df["bureau_score"].to_numpy(dtype=float)
    pool_pds = model.predict_pd(pool_df).to_numpy()

    # Pre-sort candidate pool descending by bureau_score for fast sweep
    order = np.argsort(-pool_scores)
    sorted_scores = pool_scores[order]
    sorted_pds = pool_pds[order]
    is_modelled = ~np.isnan(sorted_pds)

    best_cutoff = float(start)
    # Search from start down to stop
    cutoffs = range(start - step, stop - 1, -step)
    for c in cutoffs:
        # Swap-ins are candidates with bureau_score >= c
        idx_end = np.searchsorted(-sorted_scores, -c, side="right")
        cand_pds = sorted_pds[:idx_end]
        mod_pds = cand_pds[is_modelled[:idx_end]]

        test_blended = blended_bad_rate(observed_bads, n_retained, mod_pds, penalty)
        metrics = {"blended_bad_rate": test_blended}
        ok, _ = evaluate_constraints(active_constraints, metrics)
        if ok:
            best_cutoff = float(c)
        else:
            break

    # Construct naive scenario and simulate fully
    naive_strategy = with_rule_params(baseline, {"R5_SCORE": {"cutoff": int(best_cutoff)}})
    naive_result = simulate(df, comparison_baseline or baseline, naive_strategy, model, config)
    return best_cutoff, naive_result


# --------------------------------------------------------------------------- swap-out analysis (10.3)
def swap_out_analysis(df: pd.DataFrame, baseline: Strategy, config: dict) -> pd.DataFrame:
    """OBSERVED-only ranking of currently approved segments by bad contribution (Section 10.3).

    Ignores segments below min_segment_size, ranks by contribution to total bads descending,
    and reports 95% Wilson confidence intervals beside each rate.
    """
    min_segment_size = config["optimiser"]["min_segment_size"]
    booked = df["booked"].to_numpy(dtype=bool)
    bk_df = df[booked].copy()
    total_booked = len(bk_df)
    bad_flags = bk_df["bad_flag"].fillna(0).to_numpy(dtype=float)
    total_bads = float(bad_flags.sum())

    dims = dimensions_from_config(config)
    dim_cols = [d.column for d in dims]
    frame, _ = dimension_frame(bk_df, dims)
    frame["_bads"] = bad_flags

    grouped = frame.groupby(dim_cols, observed=True)
    rows = []
    excluded_count = 0
    excluded_booked = 0
    excluded_bads = 0.0

    for key, grp in grouped:
        n = len(grp)
        if n == 0:
            continue
        bads = float(grp["_bads"].sum())
        if n < min_segment_size:
            excluded_count += 1
            excluded_booked += n
            excluded_bads += bads
            continue

        rate = bads / n if n else 0.0
        ci_lo, ci_hi = _wilson_ci(int(bads), n)

        key_tuple = key if isinstance(key, tuple) else (key,)
        row_dict = {col: str(v) for col, v in zip(dim_cols, key_tuple)}
        row_dict.update({
            "segment": cell_label(pd.DataFrame([row_dict]))[0],
            "count": n,
            "bads": bads,
            "observed_bad_rate": rate,
            "ci_lower": ci_lo,
            "ci_upper": ci_hi,
            "share_of_booked": n / total_booked if total_booked else 0.0,
            "share_of_bads": bads / total_bads if total_bads else 0.0,
            "provenance": OBSERVED,
        })
        rows.append(row_dict)

    res = pd.DataFrame(rows)
    if not res.empty:
        # Rank by contribution to total bads descending (Section 10.3)
        res = res.sort_values(by=["share_of_bads", "observed_bad_rate"], ascending=[False, False]).reset_index(drop=True)
        res["cumulative_bads_share"] = res["share_of_bads"].cumsum()

    res.attrs = {
        "excluded_segments_count": excluded_count,
        "excluded_booked_count": excluded_booked,
        "excluded_booked_share": excluded_booked / total_booked if total_booked else 0.0,
        "excluded_bads": excluded_bads,
    }
    return res


# --------------------------------------------------------------------------- combined trade (10.3)
def candidate_declines(df: pd.DataFrame, baseline: Strategy, config: dict) -> tuple[pd.DataFrame, float]:
    """Identify segments eligible for decline (observed rate and CI lower bound above portfolio rate).

    Returns (eligible_segments_df, portfolio_observed_bad_rate).
    """
    diagnostic = swap_out_analysis(df, baseline, config)
    booked = df["booked"].to_numpy(dtype=bool)
    bad = df["bad_flag"].fillna(0).to_numpy(dtype=float)
    n_booked = int(booked.sum())
    portfolio_rate = float(bad[booked].sum() / n_booked) if n_booked else float("nan")
    eligible = diagnostic.loc[
        (diagnostic["observed_bad_rate"] > portfolio_rate)
        & (diagnostic["ci_lower"] > portfolio_rate)
    ].copy()
    eligible["excess_bads"] = eligible["count"] * (eligible["observed_bad_rate"] - portfolio_rate)
    eligible = eligible.sort_values(["excess_bads", "segment"], ascending=[False, True]).reset_index(drop=True)
    return eligible, portfolio_rate


def combined_trade(df: pd.DataFrame, baseline: Strategy, model: RiskModel,
                   config: dict, n_worst_segments: int | None = None,
                   base_result: OptimiserResult | None = None) -> dict:
    """Decline statistically worse booked cells, then optimise and simulate the strategy."""
    n = config["optimiser"].get("swap_out_decline_count", 3) if n_worst_segments is None else n_worst_segments
    if n < 0:
        raise ValueError("swap_out_decline_count must be non-negative")
    eligible, portfolio_rate = candidate_declines(df, baseline, config)
    worst = eligible.head(n)
    booked = df["booked"].to_numpy(dtype=bool)
    bad = df["bad_flag"].fillna(0).to_numpy(dtype=float)
    n_booked = int(booked.sum())
    dims = dimensions_from_config(config)
    exclusions = []
    for _, row in worst.iterrows():
        conditions = dict(_segment_condition(d.column, d.type, row[d.column], d.edges)
                          for d in dims)
        exclusions.append(SegmentExclusion(conditions, f"Segment exclusion: {row['segment']}"))
    excluded_strategy = with_exclusions(baseline, baseline.exclusions + tuple(exclusions))
    baseline_approved = (evaluate_strategy(df, baseline)["decision"] == "approve").to_numpy()
    excluded_decisions = evaluate_strategy(df, excluded_strategy)
    excluded_approved = (excluded_decisions["decision"] == "approve").to_numpy()
    retained = booked & ~(baseline_approved & ~excluded_approved)
    result = optimise(df, excluded_strategy, model, config, retained_booked=retained,
                      comparison_baseline=baseline)
    headline = result.headline
    lost = headline.swap_out_count
    gained = headline.swap_in_count

    if base_result is not None:
        base_binding = base_result.binding_constraint
    else:
        base_res = optimise(df, baseline, model, config)
        base_binding = base_res.binding_constraint

    constraints_differ = (base_binding != result.binding_constraint)

    return {
        "n_worst_segments_declined": len(worst),
        "portfolio_observed_bad_rate": portfolio_rate,
        "declined_segments": worst[["segment", "count", "bads", "observed_bad_rate",
                                    "ci_lower", "ci_upper", "excess_bads", "share_of_bads"]].to_dict(orient="records"),
        "approvals_lost": lost,
        "bads_removed": float(bad[booked & ~retained].sum()),
        "retained_observed_bad_rate": headline.observed_bad_rate,
        "approvals_gained": gained,
        "added_segments": result.added_segments.to_dict(orient="records"),
        "rejected_segments": result.rejected_segments.to_dict(orient="records"),
        "binding_constraint": result.binding_constraint,
        "base_binding_constraint": base_binding,
        "constraints_differ": constraints_differ,
        "candidate_funnel": vars(result.candidate_funnel),
        "not_modelled_count": headline.not_modelled_count,
        "net_approval_count": headline.approval_count,
        "net_approval_rate": headline.approval_rate,
        "net_approval_delta": headline.approval_count - n_booked,
        "net_blended_bad_rate": headline.blended_bad_rate,
        "baseline_approval_count": n_booked,
        "baseline_approval_rate": n_booked / len(df) if len(df) else float("nan"),
        "baseline_observed_bad_rate": portfolio_rate,
        "strategy": result.strategy,
        "headline": headline,
    }


# --------------------------------------------------------------------------- CLI (11.1)
def optimiser_result_to_dict(result: OptimiserResult, config: dict) -> dict:
    h = result.headline
    penalties = config["model"]["sensitivity_penalties"]
    thin_share_eval = result.thin_share
    thin_share_tot = result.thin_share_of_total

    out = {
        "headline": {
            "approval_count": h.approval_count,
            "approval_rate": h.approval_rate,
            "swap_in_count": h.swap_in_count,
            "swap_out_count": h.swap_out_count,
            "not_modelled_count": h.not_modelled_count,
            "observed_bad_rate": h.observed_bad_rate,
            "model_basis_baseline": h.model_basis_baseline,
            "inferred_bad_rate": h.inferred_bad_rate,
            "blended_bad_rate": h.blended_bad_rate,
            "inferred_share": h.inferred_share,
            "thin_share": thin_share_eval,
            "thin_share_of_evaluated": thin_share_eval,
            "thin_share_of_total": thin_share_tot,
            "binding_constraint": result.binding_constraint,
        },
        "binding_constraint": result.binding_constraint,
        "thin_share": thin_share_eval,
        "thin_share_of_evaluated": thin_share_eval,
        "thin_share_of_total": thin_share_tot,
        "added_segments": result.added_segments.to_dict(orient="records"),
        "rejected_segments": result.rejected_segments.to_dict(orient="records"),
        "naive_comparison": {
            "naive_cutoff": result.naive_cutoff,
            "approval_count": result.naive_result.approval_count,
            "approval_rate": result.naive_result.approval_rate,
            "blended_bad_rate": result.naive_result.blended_bad_rate,
        },
        "breakeven_penalty": result.breakeven_penalty,
        "sensitivity": h.sensitivity.to_dict(orient="records"),
    }
    if result.candidate_funnel is not None:
        cf = result.candidate_funnel
        out["candidate_funnel"] = {
            "total_declines": cf.total_declines,
            "failed_only_relaxable": cf.failed_only_relaxable,
            "inside_support": cf.inside_support,
            "in_viable_segments": cf.in_viable_segments,
        }
    return out


def main(argv: list[str] | None = None) -> int:
    from src.loader import load_applications

    ap = argparse.ArgumentParser(description="Run the credit strategy optimiser.")
    ap.add_argument("--data", help="parquet path (default: config data_path)")
    ap.add_argument("--config", help="config.yaml path")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    df = load_applications(args.data, cfg)
    baseline = strategy_from_config(cfg)

    t0 = time.perf_counter()
    model = train_model(df, cfg)
    train_s = time.perf_counter() - t0

    t1 = time.perf_counter()
    result = optimise(df, baseline, model, cfg)
    opt_s = time.perf_counter() - t1

    swap_out = swap_out_analysis(df, baseline, cfg)
    trade = combined_trade(df, baseline, model, cfg, base_result=result)

    out = optimiser_result_to_dict(result, cfg)
    out["swap_out_analysis"] = swap_out.to_dict(orient="records")
    out["swap_out_exclusions"] = swap_out.attrs
    out["combined_trade"] = {k: v for k, v in trade.items() if k not in {"strategy", "headline"}}
    from src.strategy_io import export_strategy
    from src.validation import oracle_available, validate_trade_oracle
    out["combined_trade"]["strategy_export"] = export_strategy(
        trade["strategy"], trade["headline"], cfg["constraints"])
    if oracle_available(df):
        out["combined_trade"]["oracle_validation"] = validate_trade_oracle(df, baseline, trade, model)
    out["timing"] = {"train_seconds": train_s, "optimise_seconds": opt_s}

    h = result.headline
    thin_eval = out["headline"]["thin_share_of_evaluated"]
    thin_tot = out["headline"]["thin_share_of_total"]
    log(f"\n--- Optimiser Result ---")
    log(f"Approvals:       {h.approval_count:,} ({h.approval_rate:.2%})  [+{h.swap_in_count:,} incremental]  [bound: {result.binding_constraint}]  THIN share: {thin_eval:.1%} of evaluated ({thin_tot:.1%} of total)")
    log(f"Blended Bad Rate:{h.blended_bad_rate:.2%} [constraint <= {cfg['constraints'][0]['threshold']:.2%}]")
    log(f"Binding Constr:  {result.binding_constraint}")
    log(f"Inferred Share:  {h.inferred_share:.2%}")
    log(f"Breakeven Pen:   {result.breakeven_penalty:.2f} (default: {cfg['model']['inference_penalty']})")

    if result.candidate_funnel is not None:
        cf = result.candidate_funnel
        log(f"\nCandidate Funnel:")
        log(f"  Total Declines:               {cf.total_declines:,}")
        log(f"  -> Failed Only R5/R6:         {cf.failed_only_relaxable:,}")
        log(f"  -> Inside Training Support:   {cf.inside_support:,}")
        log(f"  -> In Viable Segments:        {cf.in_viable_segments:,}")

    log(f"\nAdded Segments ({len(result.added_segments)}):")
    if not result.added_segments.empty:
        log(result.added_segments[["rule_description", "count", "inferred_bad_rate", "cumulative_bad_rate", "thin"]].to_string(index=False))
    log(f"\nRejected Segments ({len(result.rejected_segments)}):")
    if not result.rejected_segments.empty:
        log(result.rejected_segments[["rule_description", "count", "inferred_bad_rate", "reason"]].head(5).to_string(index=False))
    log(f"\nNaive Comparison (Cutoff {result.naive_cutoff:.0f}):")
    log(f"Naive Approvals: {result.naive_result.approval_count:,} ({result.naive_result.approval_rate:.2%}), Bad Rate: {result.naive_result.blended_bad_rate:.2%}")

    log(f"\nSwap-Out Analysis (Top 5 Approved Segments by Contribution to Total Bads):")
    if not swap_out.empty:
        log(swap_out[["segment", "count", "bads", "observed_bad_rate", "share_of_bads", "cumulative_bads_share"]].head(5).to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    if swap_out.attrs.get("excluded_segments_count", 0) > 0:
        log(f"  (Excluded {swap_out.attrs['excluded_segments_count']} segments with < {cfg['optimiser']['min_segment_size']} obs, covering {swap_out.attrs['excluded_booked_share']:.2%} of booked book)")

    log(f"\nCombined Trade (Decline Worst {trade['n_worst_segments_declined']} Above-Portfolio Segments; portfolio OBSERVED bad rate {trade['portfolio_observed_bad_rate']:.2%}; bound: {trade['binding_constraint']}):")
    for segment in trade["declined_segments"]:
        log(f"  {segment['segment']}: +{segment['excess_bads']:,.0f} excess bads")
    log(f"  Approvals Lost:       {trade['approvals_lost']:,} (bads removed: {trade['bads_removed']:,.0f})")
    log(f"  Freed Headroom:       retained bad rate drops to {trade['retained_observed_bad_rate']:.2%}")
    log(f"  Approvals Gained:     {trade['approvals_gained']:,} ({len(trade['strategy'].overrides)} segments)")
    if trade["constraints_differ"]:
        log(f"  Net Approvals:        {trade['net_approval_count']:,} ({trade['net_approval_rate']:.2%})  [bound: {trade['binding_constraint']}]  (binding constraints differ: base is {trade['base_binding_constraint']}, trade is {trade['binding_constraint']}; comparison not like-for-like, delta omitted)")
    else:
        log(f"  Net Approvals:        {trade['net_approval_count']:,} ({trade['net_approval_rate']:.2%})  [{trade['net_approval_delta']:+,} net change]  [bound: {trade['binding_constraint']}]")
    log(f"  Net Blended Bad Rate: {trade['net_blended_bad_rate']:.2%}")

    print_json(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
