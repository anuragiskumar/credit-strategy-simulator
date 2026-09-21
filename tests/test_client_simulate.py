"""Simulator, swap sets and goal-seek (step 4).

Several of these are regression tests for bugs that produced plausible-looking wrong answers
rather than errors — a threshold move that silently retuned a second field, and a "relaxation"
that tightened rules testing the same number the other way round. Both showed up as approvals
falling when the user had loosened something.
"""
from pathlib import Path

import pandas as pd
import pytest

from src import client_analysis as A, client_optimise as O, client_simulate as S
from src.client_generate import generate, load_client_config
from src.rule_inventory import build_inventory

REPO = Path(__file__).resolve().parents[1]
HAS_RULES = bool(list(REPO.glob("business-rules-*.xlsx")))
pytestmark = pytest.mark.skipif(not HAS_RULES, reason="client rule files not present")


@pytest.fixture(scope="module")
def inv():
    return build_inventory(REPO)


@pytest.fixture(scope="module")
def cfg():
    return load_client_config(overrides={"n_rows": 20_000})


@pytest.fixture(scope="module")
def base(cfg, inv):
    return S.build_baseline(generate(cfg), inv, cfg)


# --------------------------------------------------------------------------- levers
def test_a_lever_must_change_something():
    with pytest.raises(ValueError):
        S.Lever(label="nothing", overrides={})


def test_field_lever_refuses_a_move_that_would_only_tighten(inv):
    """Every TWQR rule at CRIF 605 declines below it, so raising it can only tighten."""
    with pytest.raises(ValueError, match="tighten"):
        S.field_lever(inv, "crifscore", 605, 640, product="TWQR")


def test_a_gt_rule_is_loosened_by_raising_its_threshold(inv):
    """simahcreditscore 650 is tested both ways; raising it loosens the `gt` arm only."""
    lever = S.field_lever(inv, "simahcreditscore", 650, 680, product="TWQR")
    assert len(lever.overrides) >= 1
    assert lever.skipped_wrong_direction >= 1


def test_a_pass_rule_moves_with_the_fail_rule_it_mirrors(inv):
    """simati writes `<3500` Fail and `>=3500` Pass as a pair; both must move together."""
    lever = S.field_lever(inv, "income", 3500, 3000, product="TWQR")
    assert "simati_chk_IAF#004" in lever.overrides   # the Fail arm
    assert "simati_chk_IAF#005" in lever.overrides   # the Pass arm


def test_field_lever_skips_conditions_pointing_the_other_way(inv):
    """simahcreditscore 650 is tested by both a `lte` and a `gt` rule."""
    lever = S.field_lever(inv, "simahcreditscore", 650, 620, product="TWQR")
    assert lever.skipped_wrong_direction >= 1
    assert len(lever.overrides) >= 1


def test_a_threshold_move_names_the_field_it_applies_to(inv):
    """Regression: a rule tests CRIF and SIMAH; moving one must not move the other."""
    lever = S.field_lever(inv, "simahcreditscore", 650, 620, product="TWQR")
    for patch in lever.overrides.values():
        assert patch["field"] == "simahcreditscore"


def test_income_lever_covers_both_names_for_income(inv):
    """`income` and `netIncome.totalIncome` are the same thing in different files."""
    assert "netincome.totalincome" in S.field_aliases("income")
    lever = S.field_lever(inv, "income", 3500, 3000, product="TWQR")
    fields = {p["field"] for p in lever.overrides.values()}
    assert "netincome.totalincome" in fields


def test_retuning_a_rule_requires_the_field_name():
    with pytest.raises(ValueError, match="field_name"):
        S.rule_lever("racAndPolicies#012", value_low=600)


# --------------------------------------------------------------------------- simulation
@pytest.mark.parametrize("field_name, frm, to", [
    ("simahcreditscore", 600, 560),
    ("simahcreditscore", 650, 620),
    ("crifscore", 605, 580),
    ("income", 3500, 3000),
])
def test_loosening_never_declines_someone_it_previously_approved(base, inv, field_name, frm, to):
    """A pure relaxation has no swap-outs. Any is a sign the move went the wrong way."""
    result = S.simulate(base, inv, S.field_lever(inv, field_name, frm, to, product="TWQR"))
    assert result["swap_out"] == 0, result["lever"]
    assert result["approval_rate"] >= result["approval_rate_before"]


def test_switching_off_a_decline_rule_only_adds_approvals(base, inv):
    blocking = base.res.rules[base.res.rules["kind"] == "block"]
    top = blocking.nlargest(1, "matched")["rule_id"].iloc[0]
    result = S.simulate(base, inv, S.rule_lever(top, enabled=False))
    assert result["swap_out"] == 0
    assert result["swap_in"] > 0


def test_swap_ins_were_all_previously_declined(base, inv):
    result = S.simulate(base, inv, S.rule_lever("yknBasicCheckValidation#016", enabled=False))
    swapped = result["_swap_in"]
    assert not base.outcome.loc[swapped, "booked"].any()
    assert result["_outcome"].loc[swapped, "booked"].all()


def test_swap_set_profile_splits_the_movers(base, inv):
    result = S.simulate(base, inv, S.rule_lever("yknBasicCheckValidation#016", enabled=False))
    profile = S.swap_set_profile(base, result, "channel")
    assert profile["swap_in"].sum() == result["swap_in"]
    assert set(profile.columns) == {"swap_in", "swap_out", "net"}


def test_the_risk_verdict_is_honest_about_what_it_cannot_know(base, inv):
    result = S.simulate(base, inv, S.field_lever(inv, "income", 3500, 3000, product="TWQR"))
    if not result["expected_bad_rate_known"]:
        assert result["expected_bad_rate_after"] is None
        assert "unknown" in result["risk_verdict"]
    else:
        assert result["expected_bad_rate_after"] is not None


def test_sweep_reports_a_cutoff_curve(base, inv):
    curve = S.sweep(base, inv, "simahcreditscore", 600, [600, 580, 560], product="TWQR")
    assert len(curve) == 3
    current = curve[curve["note"] == "current"].iloc[0]
    assert current["cutoff"] == 600 and current["approval_change_pp"] == 0.0
    # Loosening further approves at least as many.
    ordered = curve.sort_values("cutoff", ascending=False)["approval_rate"].tolist()
    assert ordered == sorted(ordered)


# --------------------------------------------------------------------------- goal-seek
@pytest.fixture(scope="module")
def fast_cfg(cfg):
    """A smaller search, so the suite does not spend two minutes proving the same thing."""
    return {**cfg, "optimise": {**cfg["optimise"], "beam_width": 2, "max_depth": 2,
                                "max_rule_candidates": 4, "field_moves": []}}


def test_candidates_never_include_a_regulatory_rule(base, inv, fast_cfg):
    levers = O.candidate_levers(base, inv, fast_cfg)
    blocked = set(base.res.rules[~base.res.rules["relaxable"]]["rule_id"])
    for lever in levers:
        assert not (set(lever.overrides) & blocked), lever.label


def test_goal_seek_returns_distinct_options(base, inv, fast_cfg):
    out = O.goal_seek(base, inv, 0.24, fast_cfg)
    assert not out.empty
    assert out["option"].nunique() == len(out)
    assert len(out) <= 3


def test_goal_seek_ranks_by_risk_cost_when_it_reaches_the_target(base, inv, fast_cfg):
    out = O.goal_seek(base, inv, 0.23, fast_cfg)
    if not out.attrs["reached"]:
        pytest.skip("target not reachable with the reduced candidate set")
    assert out["reaches_target"].all()
    priced = out[out["risk_known"] & ~out["breaches_ceiling"]]["risk_cost_pp"].tolist()
    assert priced == sorted(priced)


def test_goal_seek_says_so_when_the_target_is_out_of_reach(base, inv, fast_cfg):
    out = O.goal_seek(base, inv, 0.95, fast_cfg)
    assert out.attrs["reached"] is False
    assert not out["reaches_target"].any()
    # It must still offer the closest it can get, best first.
    rates = out["approval_rate"].tolist()
    assert rates == sorted(rates, reverse=True)
    assert out["approval_rate"].iloc[0] > base.approval_rate


def test_an_option_breaching_the_bad_rate_ceiling_is_flagged(base, inv, fast_cfg):
    """Maximising approval alone is solved by approving everyone."""
    strict = {**fast_cfg, "optimise": {**fast_cfg["optimise"], "max_bad_rate": 0.001}}
    out = O.goal_seek(base, inv, 0.24, strict)
    assert out["breaches_ceiling"].all()
