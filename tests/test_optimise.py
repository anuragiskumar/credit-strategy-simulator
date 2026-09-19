"""Phase 3 tests: optimiser, naive comparison, near-cutoff anchor, swap-out analysis, strategy I/O."""
import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.contracts import OptimiserResult, Rule, ScenarioResult, SegmentOverride, Strategy
from src.optimise import (calculate_breakeven_penalty, evaluate_constraints, optimise,
                          swap_out_analysis)
from src.risk_model import RiskModel, near_cutoff_anchor
from src.rules import strategy_from_config, with_overrides, with_rule_params
from src.simulate import simulate
from src.strategy_io import export_strategy, import_strategy
from tests.conftest import make_applicants


class StubModel:
    """Hand-set PDs, cell counts, and support mask."""

    def __init__(self, pds: dict, cells: dict | None = None, support: dict | None = None):
        self.pds = pds
        self.cells = cells or {}
        self.support = support or {}
        self.cfg = {"model": {"min_cell_obs": 100, "min_anchor_obs": 1, "inference_penalty": 1.25}}

    def predict_pd(self, df):
        return pd.Series(df["application_id"].map(self.pds).astype(float).to_numpy(), index=df.index)

    def cell_support(self, df):
        return pd.Series(df["application_id"].map(self.cells).fillna(0).astype(int).to_numpy(), index=df.index)

    def support_mask(self, df):
        if self.support:
            return pd.Series(df["application_id"].map(self.support).fillna(True).astype(bool).to_numpy(), index=df.index)
        return pd.Series(~df["application_id"].map(self.pds).isna().to_numpy(), index=df.index)

    def is_thin(self, booked_in_cell):
        return np.asarray(booked_in_cell) < 100


# --------------------------------------------------------------------------- near-cutoff anchor test (9.4)
def test_anchor_comparison_within_cells_vs_naive_opposite_signs(cfg):
    """Assert Simpson's paradox: within matched FOIR cells, override applicants look better (penalty < 1),
    while measured across the entire score band, override applicants look worse (naive penalty > 1).
    """
    rows = []
    pds = {}
    app_id = 0

    # Low FOIR cell: score 680-699, FOIR 0.20, salaried
    # Overrides: 100 obs, 2 bads (2.0%). Declines: 900 obs, model PD = 0.03 (3.0%).
    # In-cell: 0.02 < 0.03 -> penalty = 0.67 (< 1)
    for _ in range(100):
        aid = f"a{app_id}"
        app_id += 1
        is_bad = 1 if _ < 2 else 0
        rows.append(dict(application_id=aid, bureau_score=690.0, foir=0.20, employment_type="salaried",
                         booked=True, manual_override=True, bad_flag=is_bad))
        pds[aid] = 0.025
    for _ in range(900):
        aid = f"a{app_id}"
        app_id += 1
        rows.append(dict(application_id=aid, bureau_score=690.0, foir=0.20, employment_type="salaried",
                         booked=False, manual_override=False, bad_flag=None))
        pds[aid] = 0.03

    # High FOIR cell: score 680-699, FOIR 0.55, salaried
    # Overrides: 200 obs, 12 bads (6.0%). Declines: 100 obs, model PD = 0.08 (8.0%).
    # In-cell: 0.06 < 0.08 -> penalty = 0.75 (< 1)
    for _ in range(200):
        aid = f"a{app_id}"
        app_id += 1
        is_bad = 1 if _ < 12 else 0
        rows.append(dict(application_id=aid, bureau_score=690.0, foir=0.55, employment_type="salaried",
                         booked=True, manual_override=True, bad_flag=is_bad))
        pds[aid] = 0.065
    for _ in range(100):
        aid = f"a{app_id}"
        app_id += 1
        rows.append(dict(application_id=aid, bureau_score=690.0, foir=0.55, employment_type="salaried",
                         booked=False, manual_override=False, bad_flag=None))
        pds[aid] = 0.08

    df = make_applicants(rows)
    df["application_id"] = [r["application_id"] for r in rows]
    df["booked"] = [r["booked"] for r in rows]
    df["manual_override"] = [r["manual_override"] for r in rows]
    df["bad_flag"] = pd.array([r["bad_flag"] for r in rows], dtype="Int8")

    stub = StubModel(pds)
    test_cfg = copy.deepcopy(cfg)
    test_cfg["model"]["min_anchor_obs"] = 50

    anchor = near_cutoff_anchor(df, stub, test_cfg)

    # In-cell volume weighted penalty must be < 1.0 (override is better within cells)
    vw_penalty = anchor["volume_weighted"]["implied_penalty"]
    assert vw_penalty < 1.0

    # Naive penalty across score band must be > 1.0 (override is worse across whole band due to FOIR mix)
    # Naive override observed: (2 + 12) / 300 = 4.67%
    # Naive declines mean PD: (900 * 0.03 + 100 * 0.08) / 1000 = 3.50%
    # 0.0467 / 0.0350 = 1.33 > 1.0
    naive_penalty = anchor["naive_total"]["implied_penalty"]
    assert naive_penalty > 1.0

    # Must detect and flag the direction conflict!
    assert anchor["direction_conflict"] is True
    assert any("FOIR mix effect detected" in w for w in anchor["warnings"])


# --------------------------------------------------------------------------- optimiser tests (10.2)
def test_optimiser_on_synthetic_data(synthetic, model, cfg, strategy):
    """End-to-end optimiser test on synthetic population."""
    res = optimise(synthetic, strategy, model, cfg)

    # 1. Headline respects constraints
    max_br = float(cfg["constraints"][0]["threshold"])
    assert res.headline.blended_bad_rate <= max_br

    # 2. More approvals than baseline
    assert res.headline.approval_count > res.headline.approval_count - res.headline.swap_in_count
    assert res.headline.swap_in_count > 0

    # 3. Incremental approvals between 3% and 12% of total population (Section 14)
    swap_in_share = res.headline.swap_in_count / len(synthetic)
    assert 0.03 <= swap_in_share <= 0.12

    # 4. Constraint binds: at least 1 segment rejected (Section 14)
    assert len(res.rejected_segments) >= 1

    # 5. Targeted beats or matches naive comparison
    assert res.headline.approval_count >= res.naive_result.approval_count

    # 6. Determinism: identical run produces identical segment list
    res2 = optimise(synthetic, strategy, model, cfg)
    assert res.headline.approval_count == res2.headline.approval_count
    assert res.headline.blended_bad_rate == pytest.approx(res2.headline.blended_bad_rate)
    assert res.added_segments["rule_description"].tolist() == res2.added_segments["rule_description"].tolist()

    # 7. Added segments carry joint-support count and thin flag for candidate rules
    evaluated = res.added_segments[res.added_segments["conditions"].notna()]
    assert "booked_in_cell" in evaluated.columns
    assert "thin" in evaluated.columns
    assert evaluated["booked_in_cell"].notna().all()

    # 8. Added segments table reconciles exactly to headline swap-ins (including NOT_MODELLED)
    assert res.added_segments["count"].sum() == res.headline.swap_in_count

    # 9. THIN share is populated and between 0 and 1
    assert 0.0 <= res.thin_share <= 1.0

    # 10. Candidate funnel is populated
    assert res.candidate_funnel is not None
    assert res.candidate_funnel.total_declines > 0
    assert res.candidate_funnel.failed_only_relaxable > 0
    assert res.candidate_funnel.inside_support > 0
    assert res.candidate_funnel.in_viable_segments > 0


def test_swap_ins_never_include_thin_file_or_mandatory_failures(synthetic, model, cfg, strategy):
    """Swap-ins must never include thin-file or mandatory-rule failures (Section 13)."""
    res = optimise(synthetic, strategy, model, cfg)
    ev = res.headline.waterfall

    # Evaluate the proposed strategy
    from src.rules import evaluate_strategy
    ev_scen = evaluate_strategy(synthetic, res.strategy)

    # All approved rows must pass mandatory rules R1_AGE and R2_FRAUD
    approved = ev_scen["decision"] == "approve"
    assert not ev_scen.loc[approved, "failed_R1_AGE"].any()
    assert not ev_scen.loc[approved, "failed_R2_FRAUD"].any()

    # Modelled swap-ins must have a score and vintage >= 6
    booked = synthetic["booked"].to_numpy(dtype=bool)
    base_ev = evaluate_strategy(synthetic, strategy)
    base_a = (base_ev["decision"] == "approve").to_numpy()
    swap_in = (ev_scen["decision"] == "approve").to_numpy() & ~base_a & ~booked
    sw_df = synthetic[swap_in]

    assert sw_df["bureau_score"].notna().all()
    assert (sw_df["bureau_vintage_months"] >= cfg["model"]["min_vintage_months"]).all()


def test_naive_comparison_costed_on_same_basis(synthetic, model, cfg, strategy):
    """Naive comparison is costed on exactly the same basis (Section 10.2.3)."""
    res = optimise(synthetic, strategy, model, cfg)
    max_br = float(cfg["constraints"][0]["threshold"])

    # Naive result must satisfy the constraint
    assert res.naive_result.blended_bad_rate <= max_br
    # Naive cutoff should be <= 700
    assert res.naive_cutoff <= 700.0


def test_swap_out_analysis(synthetic, cfg, strategy):
    """Swap-out analysis ranks currently approved segments by bad contribution descending (Section 10.3)."""
    sw_df = swap_out_analysis(synthetic, strategy, cfg)

    assert not sw_df.empty
    assert "observed_bad_rate" in sw_df.columns
    assert "provenance" in sw_df.columns
    assert (sw_df["provenance"] == "OBSERVED").all()
    assert "ci_lower" in sw_df.columns
    assert "ci_upper" in sw_df.columns

    # Must filter out segments with count < min_segment_size
    assert (sw_df["count"] >= cfg["optimiser"]["min_segment_size"]).all()

    # Must be sorted descending by contribution to total bads (share_of_bads)
    bads_shares = sw_df["share_of_bads"].tolist()
    assert bads_shares == sorted(bads_shares, reverse=True)


def test_combined_trade(synthetic, model, cfg, strategy):
    """Combined trade declines worst N segments, freeing headroom for optimiser (Section 10.3)."""
    from src.optimise import combined_trade

    trade = combined_trade(synthetic, strategy, model, cfg, n_worst_segments=3)

    assert trade["approvals_lost"] > 0
    assert trade["bads_removed"] > 0
    # Declining worst segments frees headroom: retained observed bad rate is lower than baseline
    assert trade["retained_observed_bad_rate"] < trade["baseline_observed_bad_rate"]
    assert trade["approvals_gained"] > 0
    # Net blended bad rate remains within constraint
    max_br = float(cfg["constraints"][0]["threshold"])
    assert trade["net_blended_bad_rate"] <= max_br
    assert "binding_constraint" in trade
    assert "base_binding_constraint" in trade
    assert "constraints_differ" in trade


def test_optimiser_reports_binding_constraint(synthetic, model, cfg, strategy):
    """The optimiser reports which constraint stopped it: max_segments_added when the slot limit
    binds and bad_rate when appetite does (Section 10.2 / Section 13)."""
    # 1. Slot limit binds with budget left
    cfg_slot = copy.deepcopy(cfg)
    cfg_slot["optimiser"]["max_segments_added"] = 1
    cfg_slot["constraints"][0]["threshold"] = 0.50
    res_slot = optimise(synthetic, strategy, model, cfg_slot)
    assert res_slot.binding_constraint == "max_segments_added"

    # 2. Appetite limit binds
    cfg_appetite = copy.deepcopy(cfg)
    cfg_appetite["optimiser"]["max_segments_added"] = 50
    cfg_appetite["constraints"][0]["threshold"] = 0.035
    res_appetite = optimise(synthetic, strategy, model, cfg_appetite)
    assert res_appetite.binding_constraint == "bad_rate"

    # 3. Neither binds (every candidate added)
    cfg_none = copy.deepcopy(cfg)
    cfg_none["optimiser"]["max_segments_added"] = 50
    cfg_none["constraints"][0]["threshold"] = 1.0
    res_none = optimise(synthetic, strategy, model, cfg_none)
    assert res_none.binding_constraint == "none"


def test_trade_strategy_full_simulation_and_exclusion_round_trip(synthetic, model, cfg, strategy, tmp_path):
    from src.optimise import combined_trade
    from src.validation import validate_strategy_oracle

    trade = combined_trade(synthetic, strategy, model, cfg)
    proposed = trade["strategy"]
    assert len(proposed.exclusions) == cfg["optimiser"]["swap_out_decline_count"]
    full = simulate(synthetic, strategy, proposed, model, cfg)
    assert trade["net_approval_count"] == full.approval_count
    assert trade["approvals_gained"] == full.swap_in_count
    assert trade["approvals_lost"] == full.swap_out_count
    assert trade["net_blended_bad_rate"] == pytest.approx(full.blended_bad_rate)
    assert trade["not_modelled_count"] == full.not_modelled_count
    assert trade["retained_observed_bad_rate"] == pytest.approx(full.observed_bad_rate)
    assert "Removed by segment exclusions" in full.waterfall["label"].tolist()

    path = tmp_path / "trade.json"
    exported = export_strategy(proposed, full, cfg["constraints"], path=path)
    assert len(exported["segment_exclusions"]) == len(proposed.exclusions)
    assert "Infinity" not in path.read_text()
    imported, _ = import_strategy(path, strategy, cfg)
    assert imported.exclusions == proposed.exclusions
    replay = simulate(synthetic, strategy, imported, model, cfg)
    assert replay.approval_count == full.approval_count
    assert replay.blended_bad_rate == pytest.approx(full.blended_bad_rate)
    assert validate_strategy_oracle(synthetic, strategy, imported, replay, model)["approval_count"] == full.approval_count



def test_strategy_export_round_trip(synthetic, model, cfg, strategy, tmp_path):
    """Exporting and importing a strategy reproduces the same headline numbers (Section 10.5)."""
    res = optimise(synthetic, strategy, model, cfg)

    export_file = tmp_path / "strategy.json"
    exported = export_strategy(res.strategy, res, cfg.get("constraints"), path=export_file)

    # Verify JSON file exists and is valid
    assert export_file.exists()
    data = json.loads(export_file.read_text())
    assert "strategy_id" in data
    assert "segment_overrides" in data
    assert len(data["segment_overrides"]) == len(res.strategy.overrides)

    # Import strategy
    imported_strat, meta = import_strategy(export_file, strategy, cfg)
    assert len(imported_strat.overrides) == len(res.strategy.overrides)

    # Re-simulate imported strategy
    re_res = simulate(synthetic, strategy, imported_strat, model, cfg)

    assert re_res.approval_count == res.headline.approval_count
    assert re_res.approval_rate == pytest.approx(res.headline.approval_rate)
    assert re_res.blended_bad_rate == pytest.approx(res.headline.blended_bad_rate)
    assert re_res.inferred_share == pytest.approx(res.headline.inferred_share)


def test_constraint_evaluation_unsupported_metric_raises():
    """Unimplemented constraint metric named in config must raise ValueError (Section 10.2.1)."""
    with pytest.raises(ValueError, match="Unsupported constraint metric"):
        evaluate_constraints([{"name": "loss", "metric": "expected_loss", "threshold": 0.05}],
                             {"blended_bad_rate": 0.03})


def test_breakeven_penalty_edge_cases():
    """Breakeven penalty handles empty, already breached, and very safe cases."""
    # Empty swap-ins -> NaN
    assert np.isnan(calculate_breakeven_penalty(10, 100, np.array([]), 0.05))

    # Already breached at penalty 0.0 -> 0.0
    # 10 bads in 100 retained = 10%, threshold is 5%
    assert calculate_breakeven_penalty(10, 100, np.array([0.01, 0.02]), 0.05) == 0.0

    # Never breached even at penalty 10.0 -> inf
    # 1 bad in 1000 retained = 0.1%, swap-in PD 0.001, threshold 5%
    assert calculate_breakeven_penalty(1, 1000, np.array([0.001]), 0.05) == float("inf")


def test_validation_oracle(synthetic, model, cfg, strategy):
    """Synthetic oracle validation module computes true bad rates (Section 10.4)."""
    from src.validation import validate_strategy_oracle

    res = optimise(synthetic, strategy, model, cfg)
    oracle = validate_strategy_oracle(synthetic, strategy, res.strategy, res.headline, model)

    assert "disclaimer" in oracle
    assert "Synthetic oracle" in oracle["disclaimer"]
    assert "true_bad_rate_modelled" in oracle
    assert 0.0 <= oracle["true_bad_rate_modelled"] <= 1.0
    assert "estimation_error" in oracle
