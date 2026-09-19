"""What-if simulation (Section 10.1): accounting, provenance, blended bad rate, mandatory rules."""
import json

import numpy as np
import pandas as pd
import pytest

from src.contracts import Rule, Strategy
from src.rules import (evaluate_strategy, strategy_from_config, with_overrides, with_rule_enabled,
                       with_rule_params)
from src.simulate import (blended_bad_rate, blended_statement, check_mandatory_unchanged,
                          load_scenario_spec, scenario_from_dict, simulate, simulate_detailed)
from tests.conftest import make_applicants


class StubModel:
    """Hand-set PDs and cell counts keyed by application_id; NaN PD = outside support."""

    def __init__(self, pds: dict, cells: dict | None = None):
        self.pds, self.cells = pds, cells or {}

    def predict_pd(self, df):
        return pd.Series(df["application_id"].map(self.pds).astype(float).to_numpy(), index=df.index)

    def cell_support(self, df):
        return pd.Series(df["application_id"].map(self.cells).fillna(0).astype(int).to_numpy(), index=df.index)


def _book(rows: list[dict]) -> pd.DataFrame:
    """Applicants with the columns the simulator needs. `booked` defaults to False; `bad` sets bad_flag."""
    df = make_applicants(rows)
    df["application_id"] = [f"a{i}" for i in range(len(df))]
    df["booked"] = [bool(r.get("booked", False)) for r in rows]
    df["manual_override"] = [bool(r.get("manual_override", False)) for r in rows]
    df["bad_flag"] = pd.array([r.get("bad", None) for r in rows], dtype="Int8")
    return df.drop(columns=[c for c in ("booked_", "bad_") if c in df.columns])


def _fixture():
    """4 booked (1 bad) at score 750; 3 modelled declines + 2 unmodelled declines at score 690."""
    rows = [dict(booked=True, bad=b, bureau_score=750.0) for b in (1, 0, 0, 0)]
    rows += [dict(bureau_score=690.0) for _ in range(5)]
    df = _book(rows)
    stub = StubModel({"a0": 0.05, "a1": 0.03, "a2": 0.03, "a3": 0.03,       # booked: PREDICTED
                      "a4": 0.02, "a5": 0.04, "a6": 0.06,                    # modelled swap-ins
                      "a7": np.nan, "a8": np.nan},                           # NOT_MODELLED swap-ins
                     cells={"a4": 40, "a5": 40, "a6": 40, "a7": 0, "a8": 0})
    return df, stub


@pytest.fixture()
def base(cfg):
    return strategy_from_config(cfg)


# ------------------------------------------------------------------ formula (Section 6 / 10.1)
def test_blended_bad_rate_formula_on_a_hand_built_fixture(cfg, base):
    df, stub = _fixture()
    scen = with_rule_params(base, {"R5_SCORE": {"cutoff": 680}})
    res, det = simulate_detailed(df, base, scen, stub, cfg, penalty=1.25)

    # observed: 1 bad in 4 retained. inferred: mean(0.02, 0.04, 0.06) * 1.25 = 0.05.
    # blended = (1 + 1.25 * 0.12) / (4 + 3) — the two NOT_MODELLED swap-ins are in neither term.
    assert res.observed_bad_rate == pytest.approx(0.25)
    assert res.inferred_bad_rate == pytest.approx(0.05)
    assert res.blended_bad_rate == pytest.approx((1 + 1.25 * 0.12) / 7)
    assert res.blended_bad_rate != pytest.approx((1 + 1.25 * 0.12) / 9)       # not diluted by unmodelled rows

    assert (res.approval_count, res.swap_in_count, res.swap_out_count) == (9, 5, 0)
    assert res.not_modelled_count == 2                       # counted as approvals...
    assert res.inferred_share == pytest.approx(3 / 9)        # ...but not as inferred
    assert det.not_modelled_share == pytest.approx(2 / 9)
    assert res.model_basis_baseline == pytest.approx(0.035)  # mean of the booked PDs, unpenalised
    assert det.baseline_observed_bad_rate == pytest.approx(0.25)
    assert "excludes 2 approvals with no model support" in blended_statement(res)
    assert any("2 of these approvals cannot be scored by the model" in w for w in det.warnings)


def test_blended_bad_rate_refuses_nan_pds():
    with pytest.raises(ValueError, match="NOT_MODELLED"):
        blended_bad_rate(1, 4, [0.02, np.nan], 1.25)


def test_unmodelled_rows_are_never_imputed_as_zero(cfg, base):
    df, stub = _fixture()
    scen = with_rule_params(base, {"R5_SCORE": {"cutoff": 680}})
    res = simulate(df, base, scen, stub, cfg)
    imputed_zero = (1 + 1.25 * 0.12) / 9
    assert res.blended_bad_rate > imputed_zero


def test_swap_out_and_retained_accounting(cfg, base):
    df, stub = _fixture()
    strict = with_rule_params(base, {"R5_SCORE": {"cutoff": 800}})          # booked 750s no longer pass
    res = simulate(df, base, strict, stub, cfg)
    assert (res.swap_out_count, res.swap_in_count, res.approval_count) == (4, 0, 0)
    assert np.isnan(res.observed_bad_rate) and np.isnan(res.blended_bad_rate)   # nobody left to measure


def test_unchanged_scenario_reproduces_the_book_with_no_swaps(synthetic, model, cfg, base):
    res, det = simulate_detailed(synthetic, base, base, model, cfg)
    n_book = int(synthetic["booked"].sum())
    assert (res.swap_in_count, res.swap_out_count, res.not_modelled_count) == (0, 0, 0)
    assert res.approval_count == n_book
    assert res.observed_bad_rate == pytest.approx(synthetic.loc[synthetic["booked"], "bad_flag"].mean())
    assert res.blended_bad_rate == pytest.approx(res.observed_bad_rate)
    assert np.isnan(res.inferred_bad_rate)                                   # undefined, not zero
    # the model-basis baseline sits close to the observed one when the model is unbiased
    assert abs(det.model_bias_ratio) < cfg["model"]["bias_warning_ratio"]


def test_waterfall_reconciles_to_the_scenario_approvals(synthetic, model, cfg, base):
    scen = scenario_from_dict(base, {"rules": {"R5_SCORE": {"cutoff": 680}}}, cfg)
    res = simulate(synthetic, base, scen, model, cfg)
    wf = res.waterfall
    assert wf["remaining"].iloc[0] == len(synthetic)
    assert wf["remaining"].iloc[-1] == res.approval_count
    steps = wf[wf["kind"].isin(["rule", "adjustment"])]["delta"].sum()
    assert len(synthetic) + steps == res.approval_count


# ------------------------------------------------------------------ real model
def test_lowering_the_cutoff_adds_inferred_approvals(synthetic, model, cfg, base):
    scen = scenario_from_dict(base, {"rules": {"R5_SCORE": {"cutoff": 680}}}, cfg)
    res, det = simulate_detailed(synthetic, base, scen, model, cfg)
    assert res.swap_in_count > 0 and res.swap_out_count == 0
    assert res.inferred_bad_rate > res.observed_bad_rate                # swap-ins are riskier than the book
    assert res.blended_bad_rate > res.observed_bad_rate
    assert 0 < res.inferred_share < 1 and res.approval_rate > det.baseline_approval_rate


def test_relaxing_r4_produces_not_modelled_swap_ins_excluded_from_the_blend(synthetic, model, cfg, base):
    # DPD 60 / 90 have no booked customers, so every swap-in from relaxing the DPD limit is unscorable.
    scen = scenario_from_dict(base, {"rules": {"R4_BUREAU_HIST": {"dpd_lt": 100}}}, cfg)
    res, det = simulate_detailed(synthetic, base, scen, model, cfg)
    assert res.swap_in_count > 0
    assert res.not_modelled_count == res.swap_in_count > 0
    assert res.approval_count > int(synthetic["booked"].sum())            # they still count as approvals
    assert res.inferred_share == 0
    assert res.blended_bad_rate == pytest.approx(res.observed_bad_rate)   # excluded, not zero-imputed
    assert any("cannot be scored by the model" in w for w in det.warnings)
    nm = res.swap_in_breakdown.query("provenance == 'NOT_MODELLED'")
    assert len(nm) == 1 and nm["count"].iloc[0] == res.not_modelled_count


def test_relaxing_r3_thin_file_is_not_modelled(synthetic, model, cfg, base):
    scen = scenario_from_dict(base, {"enabled": {"R3_THIN_FILE": False}}, cfg)
    res = simulate(synthetic, base, scen, model, cfg)
    assert res.not_modelled_count > 0
    swap_pd = model.predict_pd(synthetic[(evaluate_strategy(synthetic, scen)["decision"] == "approve")
                                         & ~synthetic["booked"]])
    assert res.not_modelled_count == int(swap_pd.isna().sum())


def test_swap_in_breakdown_carries_joint_support_and_thin_flag(synthetic, model, cfg, base):
    override = {"conditions": {"bureau_score": [680, 700], "foir_max": 0.35, "employment_type": ["salaried"]}}
    scen = scenario_from_dict(base, {"overrides": [override]}, cfg)
    res = simulate(synthetic, base, scen, model, cfg)
    bd = res.swap_in_breakdown
    assert {"booked_in_cell", "thin", "inferred_bad_rate", "segment", "count", "provenance"} <= set(bd.columns)
    cell = bd[bd["provenance"] == "INFERRED"]
    assert len(cell) == 1 and cell["segment"].iloc[0].endswith("salaried")
    assert cell["booked_in_cell"].iloc[0] < cfg["model"]["min_cell_obs"] and bool(cell["thin"].iloc[0])
    # the evidence count agrees with what the model reports for the same applicants
    scen_a = (evaluate_strategy(synthetic, scen)["decision"] == "approve").to_numpy()
    base_a = (evaluate_strategy(synthetic, base)["decision"] == "approve").to_numpy()
    sw = synthetic[scen_a & ~base_a & ~synthetic["booked"].to_numpy()]
    assert cell["booked_in_cell"].iloc[0] == model.cell_support(sw).iloc[0]
    assert cell["count"].iloc[0] == len(sw)


def test_breakdown_counts_reconcile_to_swap_ins(synthetic, model, cfg, base):
    scen = scenario_from_dict(base, {"rules": {"R5_SCORE": {"cutoff": 660}, "R6_FOIR": {"cap": 0.55}}}, cfg)
    res = simulate(synthetic, base, scen, model, cfg)
    assert res.swap_in_breakdown["count"].sum() == res.swap_in_count
    assert res.swap_in_breakdown["share_of_swap_ins"].sum() == pytest.approx(1.0)


def test_sensitivity_strip_covers_every_penalty_and_matches_the_headline(synthetic, model, cfg, base):
    scen = scenario_from_dict(base, {"rules": {"R5_SCORE": {"cutoff": 680}}}, cfg)
    res = simulate(synthetic, base, scen, model, cfg)
    s = res.sensitivity
    assert s["penalty"].tolist() == cfg["model"]["sensitivity_penalties"]
    assert s["blended_bad_rate"].is_monotonic_increasing and s["blended_bad_rate"].nunique() == len(s)
    default = s.loc[s["penalty"] == cfg["model"]["inference_penalty"], "blended_bad_rate"].iloc[0]
    assert default == pytest.approx(res.blended_bad_rate)


def test_penalty_argument_changes_the_headline(synthetic, model, cfg, base):
    scen = scenario_from_dict(base, {"rules": {"R5_SCORE": {"cutoff": 680}}}, cfg)
    lo = simulate_detailed(synthetic, base, scen, model, cfg, penalty=1.0)[0]
    hi = simulate_detailed(synthetic, base, scen, model, cfg, penalty=2.0)[0]
    assert hi.blended_bad_rate > lo.blended_bad_rate
    assert hi.inferred_bad_rate == pytest.approx(2 * lo.inferred_bad_rate)


# ------------------------------------------------------------------ mandatory rules
def test_mandatory_rules_cannot_be_relaxed_through_the_helpers(base):
    with pytest.raises(ValueError, match="mandatory"):
        with_rule_params(base, {"R1_AGE": {"min_age": 18}})
    with pytest.raises(ValueError, match="mandatory"):
        with_rule_enabled(base, {"R2_FRAUD": False})


def test_simulator_rejects_a_scenario_that_relaxes_a_mandatory_rule(synthetic, model, cfg, base):
    """Even a hand-built Strategy that bypasses the helpers is refused."""
    rules = tuple(Rule(r.id, {**r.params, "min_age": 18} if r.id == "R1_AGE" else r.params, r.mandatory)
                  for r in base.rules)
    with pytest.raises(ValueError, match="R1_AGE is mandatory"):
        simulate(synthetic, base, Strategy(rules=rules), model, cfg)
    rules = tuple(Rule(r.id, r.params, r.mandatory, enabled=r.id != "R2_FRAUD") for r in base.rules)
    with pytest.raises(ValueError, match="R2_FRAUD is mandatory"):
        check_mandatory_unchanged(base, Strategy(rules=rules))
    with pytest.raises(KeyError):
        scenario_from_dict(base, {"mandatory": {}}, cfg)


def test_scenario_override_cannot_relax_a_mandatory_rule(cfg, base):
    spec = {"overrides": [{"conditions": {"bureau_score": [600, 700]}, "relaxes": ["R5_SCORE", "R1_AGE"]}]}
    scen = scenario_from_dict(base, spec, cfg)
    with pytest.raises(ValueError, match="mandatory"):
        evaluate_strategy(make_applicants([dict(bureau_score=650.0)]), scen)


def test_swap_ins_never_include_age_or_fraud_failures(synthetic, model, cfg, base):
    # Switch off every relaxable rule and add a catch-all override: mandatory failures must still decline.
    spec = {"enabled": {"R3_THIN_FILE": False, "R4_BUREAU_HIST": False, "R5_SCORE": False, "R6_FOIR": False}}
    scen = scenario_from_dict(base, spec, cfg)
    ev = evaluate_strategy(synthetic, scen)
    approved = (ev["decision"] == "approve").to_numpy()
    assert not (approved & (ev["failed_R1_AGE"] | ev["failed_R2_FRAUD"]).to_numpy()).any()
    res = simulate(synthetic, base, scen, model, cfg)
    assert res.swap_in_count > 0
    mandatory_fail = (ev["failed_R1_AGE"] | ev["failed_R2_FRAUD"]).to_numpy()
    assert res.approval_count <= int((~mandatory_fail).sum()) + int((mandatory_fail & synthetic["booked"]).sum())


# ------------------------------------------------------------------ scenario spec / CLI
def test_scenario_spec_builds_range_tuples_and_default_relaxes(cfg, base):
    spec = {"overrides": [{"conditions": {"bureau_score": [680, 700], "foir_max": 0.35,
                                          "employment_type": ["salaried", "other"]}}]}
    ov = scenario_from_dict(base, spec, cfg).overrides[0]
    assert ov.conditions["bureau_score"] == (680, 700)
    assert ov.conditions["employment_type"] == ["salaried", "other"]
    assert ov.relaxes == tuple(cfg["segment_overrides"]["default_relaxes"])


def test_load_scenario_spec_accepts_inline_json_or_a_file(tmp_path):
    inline = '{"rules": {"R5_SCORE": {"cutoff": 690}}}'
    f = tmp_path / "s.json"
    f.write_text(inline)
    assert load_scenario_spec(inline) == load_scenario_spec(str(f)) == json.loads(inline)
    assert load_scenario_spec(None) == {}


def test_cli_entry_points_emit_valid_json(synthetic, tmp_path, capsys):
    from src import risk_model, simulate as sim
    path = tmp_path / "apps.parquet"
    synthetic.to_parquet(path)

    assert risk_model.main(["--data", str(path)]) == 0
    rm = json.loads(capsys.readouterr().out)
    assert rm["auc_ok"] and rm["auc"] >= 0.60 and len(rm["calibration_holdout"]) == 10
    assert {"coefficients", "support_ranges", "support_summary", "dropped_levels"} <= set(rm)

    scenario = '{"rules": {"R5_SCORE": {"cutoff": 680}}}'
    assert sim.main(["--data", str(path), "--scenario", scenario]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["approvals"]["swap_in_count"] > 0
    assert out["bad_rate"]["baseline_observed"]["provenance"] == "OBSERVED"
    assert out["bad_rate"]["model_basis_baseline"]["provenance"] == "PREDICTED"
    assert out["bad_rate"]["scenario_inferred_swap_ins"]["provenance"] == "INFERRED"
    assert len(out["sensitivity"]) == 4 and out["statement"].startswith("blended bad rate")


# ------------------------------------------------------------------ waterfall carry-over is checked, not plugged
def test_carry_over_step_equals_the_override_effect_and_is_checked(synthetic, model, cfg, base):
    scen = scenario_from_dict(base, {"rules": {"R5_SCORE": {"cutoff": 680}}}, cfg)
    wf = simulate(synthetic, base, scen, model, cfg).waterfall
    step = wf.loc[wf["label"].str.startswith("Historical manual overrides"), "delta"].iloc[0]
    # On override rows the final decision is the historical one, so the step is
    # sum(historical approve - scenario engine approve) over exactly those rows.
    ov = synthetic[synthetic["manual_override"]]
    expected = int((ov["hist_decision"] == "approve").sum()
                   - (evaluate_strategy(ov, scen)["decision"] == "approve").sum())
    assert step == expected


def test_scenario_waterfall_raises_if_a_non_override_row_disagrees(cfg, base):
    from src.simulate import _scenario_waterfall
    df, _ = _fixture()
    ev = evaluate_strategy(df, base)
    final = (ev["decision"] == "approve").to_numpy().copy()
    final[5] = True                                   # a non-override row the rules decline
    with pytest.raises(AssertionError, match="non-override rows differ"):
        _scenario_waterfall(df, base, ev, final)
    df.loc[5, "manual_override"] = True               # flagged as an override: now it is explained
    wf = _scenario_waterfall(df, base, ev, final)
    assert wf["delta"].iloc[-2] == 1 and wf["remaining"].iloc[-1] == int(final.sum())


def test_unknown_parameter_in_a_scenario_is_rejected(cfg, base):
    with pytest.raises(KeyError, match="enquiries_lt"):
        scenario_from_dict(base, {"rules": {"R4_BUREAU_HIST": {"enquiries_lt": 12}}}, cfg)


def test_relaxing_enquiries_beyond_the_booked_range_is_not_modelled(synthetic, model, cfg, base):
    """Booked customers never exceed 6 enquiries, so relaxing the cap must not produce scored swap-ins."""
    assert synthetic.loc[synthetic["booked"], "enquiries_6m"].max() == cfg["strategy"]["rules"][3]["params"]["max_enquiries"]
    scen = scenario_from_dict(base, {"rules": {"R4_BUREAU_HIST": {"max_enquiries": 12}}}, cfg)
    res = simulate(synthetic, base, scen, model, cfg)
    assert res.swap_in_count > 0
    assert res.not_modelled_count == res.swap_in_count
    assert res.inferred_share == 0
