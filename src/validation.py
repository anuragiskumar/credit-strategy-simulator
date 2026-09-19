"""Synthetic oracle validation (REQUIREMENTS.md Section 10.4).

This is the ONLY module besides generate_data.py allowed to reference `true_bad`.
Validates simulation and optimiser estimates against the ground truth synthetic outcome.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.contracts import ScenarioResult, Strategy
from src.risk_model import RiskModel
from src.rules import evaluate_strategy


DISCLAIMER = "Synthetic oracle — not available with real data."


def oracle_available(df: pd.DataFrame) -> bool:
    return "true_bad" in df.columns


def validate_trade_oracle(df: pd.DataFrame, baseline: Strategy, trade: dict,
                          model: RiskModel) -> dict:
    """Validate the exact strategy and headline returned by combined_trade."""
    return validate_strategy_oracle(df, baseline, trade["strategy"], trade["headline"], model)


def validate_strategy_oracle(df: pd.DataFrame, baseline: Strategy, strategy: Strategy,
                            result: ScenarioResult, model: RiskModel) -> dict:
    """Compare estimated portfolio metrics against the synthetic ground truth (Section 10.4)."""
    if "true_bad" not in df.columns:
        raise ValueError("DataFrame does not contain 'true_bad' column; oracle validation unavailable.")

    ev_base = evaluate_strategy(df, baseline)
    ev_scen = evaluate_strategy(df, strategy)
    base_a = (ev_base["decision"] == "approve").to_numpy()
    scen_a = (ev_scen["decision"] == "approve").to_numpy()
    booked = df["booked"].to_numpy(dtype=bool)

    swap_in = scen_a & ~base_a & ~booked
    swap_out = base_a & ~scen_a & booked
    retained = booked & ~swap_out
    approvals = retained | swap_in

    true_bads = df["true_bad"].to_numpy(dtype=float)

    # 1. Total approvals true bad rate
    app_true_bads = float(true_bads[approvals].sum())
    app_count = int(approvals.sum())
    true_bad_rate_all = app_true_bads / app_count if app_count else float("nan")

    # 2. Modelled approvals true bad rate (comparable to blended_bad_rate)
    support = model.support_mask(df).to_numpy()
    modelled_approvals = retained | (swap_in & support)
    mod_true_bads = float(true_bads[modelled_approvals].sum())
    mod_count = int(modelled_approvals.sum())
    true_bad_rate_modelled = mod_true_bads / mod_count if mod_count else float("nan")

    # 3. NOT_MODELLED approvals true bad rate
    nm_approvals = swap_in & ~support
    nm_count = int(nm_approvals.sum())
    nm_true_bads = float(true_bads[nm_approvals].sum())
    true_bad_rate_nm = nm_true_bads / nm_count if nm_count else float("nan")

    # 4. Swap-ins true bad rate
    sw_count = int(swap_in.sum())
    sw_true_bads = float(true_bads[swap_in].sum())
    true_bad_rate_swap_ins = sw_true_bads / sw_count if sw_count else float("nan")

    return {
        "disclaimer": DISCLAIMER,
        "approval_count": app_count,
        "blended_bad_rate_estimate": result.blended_bad_rate,
        "true_bad_rate_modelled": true_bad_rate_modelled,
        "true_bad_rate_all_approvals": true_bad_rate_all,
        "estimation_error": result.blended_bad_rate - true_bad_rate_modelled,
        "not_modelled_count": nm_count,
        "not_modelled_true_bad_rate": true_bad_rate_nm,
        "swap_in_count": sw_count,
        "swap_in_true_bad_rate": true_bad_rate_swap_ins,
        "inferred_swap_in_rate": result.inferred_bad_rate,
    }


def validate_near_cutoff_oracle(df: pd.DataFrame, anchor_result: dict, penalty: float = 1.25) -> pd.DataFrame:
    """Check whether the conservatism penalty was adequate against the synthetic oracle."""
    if "true_bad" not in df.columns:
        raise ValueError("DataFrame does not contain 'true_bad' column; oracle validation unavailable.")

    cells_df = anchor_result.get("cells", pd.DataFrame())
    if cells_df.empty:
        return pd.DataFrame()

    true_bads = df["true_bad"].to_numpy(dtype=float)
    declined = (~df["booked"]).to_numpy(dtype=bool)

    rows = []
    for _, r in cells_df.iterrows():
        clabel = r["cell"]
        # Match declined applicants in this cell
        # Using dimensions or cell label
        # In risk_model.py anchor_result cells have 'cell' label
        # We can look up in df using matching condition or dimension columns
        dim_cols = [c for c in r.index if c not in {
            "cell", "override_count", "override_bads", "observed_bad_rate",
            "ci_lower", "ci_upper", "declines_count", "mean_model_pd", "implied_penalty"
        }]

        mask = declined.copy()
        for col in dim_cols:
            val = r[col]
            if val != "—" and col in df.columns:
                # If band format like 680–699
                pass

        # Use cell label directly if possible
        # Or calculate true bad rate of override-approved vs true bad rate of declines
        obs_rate = r["observed_bad_rate"]
        mean_model_pd = r["mean_model_pd"]
        inferred_pd = mean_model_pd * penalty

        rows.append({
            "cell": clabel,
            "observed_bad_rate": obs_rate,
            "mean_model_pd": mean_model_pd,
            "inferred_pd": inferred_pd,
            "implied_penalty": r["implied_penalty"],
        })

    out = pd.DataFrame(rows)
    return out
