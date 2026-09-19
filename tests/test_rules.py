import time

import numpy as np
import pandas as pd
import pytest

from src.contracts import SegmentOverride, Strategy
from src.rules import (ReproductionError, assert_reproduction, evaluate_strategy, reproduction_report,
                       with_overrides, with_rule_enabled, with_rule_params)
from tests.conftest import make_applicants

RELAXABLE = ("R3_THIN_FILE", "R4_BUREAU_HIST", "R5_SCORE", "R6_FOIR")


# ------------------------------------------------------------------ rule boundaries (hand-built)
@pytest.mark.parametrize("change, rule", [
    ({"age": 20}, "R1_AGE"), ({"age": 61}, "R1_AGE"),
    ({"fraud_flag": True}, "R2_FRAUD"),
    ({"bureau_score": np.nan}, "R3_THIN_FILE"), ({"bureau_vintage_months": 5}, "R3_THIN_FILE"),
    ({"max_dpd_12m": 60}, "R4_BUREAU_HIST"), ({"enquiries_6m": 7}, "R4_BUREAU_HIST"),
    ({"bureau_score": 699.0}, "R5_SCORE"),
    ({"foir": 0.51}, "R6_FOIR"),
])
def test_each_rule_fails_on_its_own(strategy, change, rule):
    ev = evaluate_strategy(make_applicants([change]), strategy)
    assert ev["decision"].iloc[0] == "decline"
    assert ev["first_failed_rule"].iloc[0] == rule
    for r in strategy.rules:
        assert bool(ev[f"failed_{r.id}"].iloc[0]) == (r.id == rule or (rule == "R3_THIN_FILE" and r.id == "R5_SCORE"
                                                                       and np.isnan(change.get("bureau_score", 1))))


@pytest.mark.parametrize("change", [
    {"age": 21}, {"age": 60}, {"bureau_vintage_months": 6}, {"max_dpd_12m": 30},
    {"enquiries_6m": 6}, {"bureau_score": 700.0}, {"foir": 0.50}, {},
])
def test_boundaries_that_pass(strategy, change):
    ev = evaluate_strategy(make_applicants([change]), strategy)
    assert ev["decision"].iloc[0] == "approve"
    assert ev["first_failed_rule"].iloc[0] is None


def test_first_failed_rule_and_all_failed_rules(strategy):
    df = make_applicants([{"age": 19, "bureau_score": 650.0, "foir": 0.7, "max_dpd_12m": 90}])
    ev = evaluate_strategy(df, strategy)
    assert ev["first_failed_rule"].iloc[0] == "R1_AGE"
    failed = {r.id for r in strategy.rules if ev[f"failed_{r.id}"].iloc[0]}
    assert failed == {"R1_AGE", "R4_BUREAU_HIST", "R5_SCORE", "R6_FOIR"}


def test_no_hit_fails_thin_file_first(strategy):
    ev = evaluate_strategy(make_applicants([{"bureau_score": np.nan, "bureau_vintage_months": 0}]), strategy)
    assert ev["first_failed_rule"].iloc[0] == "R3_THIN_FILE"


def test_disabled_rule_never_fails(strategy):
    relaxed = with_rule_enabled(strategy, {"R6_FOIR": False})
    ev = evaluate_strategy(make_applicants([{"foir": 0.95}]), relaxed)
    assert ev["decision"].iloc[0] == "approve"


# ------------------------------------------------------------------ reproduction (7.3)
def test_reproduces_history_for_every_non_override_row(sample, strategy):
    rep = reproduction_report(sample, strategy)
    assert rep["match_rate_excl_overrides"] == 1.0
    assert rep["decline_reason_match_rate"] == 1.0
    assert_reproduction(rep)


def test_mismatches_are_exactly_the_manual_overrides(sample, strategy):
    ev = evaluate_strategy(sample, strategy)
    mismatch = (ev["decision"].astype(str) != sample["hist_decision"].astype(str)).to_numpy()
    assert set(sample.index[mismatch]) == set(sample.index[sample["manual_override"]])
    assert sample["manual_override"].sum() > 0          # not vacuous
    rep = reproduction_report(sample, strategy, ev)
    assert rep["n_mismatches"] == rep["n_manual_overrides"] == int(sample["manual_override"].sum())
    assert rep["mismatches"]["manual_override"].all()
    assert set(rep["mismatches"]["direction"]) == {"decline→approve", "approve→decline"}


def test_reproduction_fails_loudly_on_a_non_override_mismatch(sample, strategy):
    tampered = sample.copy()
    i = tampered.index[~tampered["manual_override"] & (tampered["hist_decision"] == "approve")][0]
    tampered.loc[i, "hist_decision"] = "decline"
    rep = reproduction_report(tampered, strategy)
    assert rep["match_rate_excl_overrides"] < 1.0
    with pytest.raises(ReproductionError):
        assert_reproduction(rep)


def test_engine_speed_on_a_million_rows(sample, strategy):
    big = pd.concat([sample] * 2000, ignore_index=True)
    assert len(big) == 1_000_000
    t = time.perf_counter()
    evaluate_strategy(big, strategy)
    assert time.perf_counter() - t < 2.0


# ------------------------------------------------------------------ mandatory rules
def test_mandatory_rules_cannot_be_edited_or_switched_off(strategy):
    with pytest.raises(ValueError):
        with_rule_params(strategy, {"R1_AGE": {"min_age": 18}})
    with pytest.raises(ValueError):
        with_rule_enabled(strategy, {"R2_FRAUD": False})


def test_override_cannot_relax_a_mandatory_rule(strategy):
    ov = SegmentOverride({"bureau_score": (600, 700)}, relaxes=("R5_SCORE", "R1_AGE"))
    with pytest.raises(ValueError):
        evaluate_strategy(make_applicants([{}]), with_overrides(strategy, (ov,)))


def test_override_never_approves_age_or_fraud_failures(strategy):
    df = make_applicants([
        {"age": 19, "bureau_score": 690.0}, {"age": 62, "bureau_score": 690.0},
        {"fraud_flag": True, "bureau_score": 690.0}, {"bureau_score": 690.0},
    ])
    ov = SegmentOverride({"bureau_score": (600, 700)}, relaxes=RELAXABLE)   # as permissive as possible
    ev = evaluate_strategy(df, with_overrides(strategy, (ov,)))
    assert ev["decision"].tolist() == ["decline", "decline", "decline", "approve"]
    assert ev["approved_by_override"].tolist() == [False, False, False, True]


# ------------------------------------------------------------------ override semantics (7.2)
def test_override_only_flips_decline_to_approve(strategy):
    df = make_applicants([{"bureau_score": 800.0}, {"bureau_score": 690.0}, {"bureau_score": 690.0, "foir": 0.6}])
    ov = SegmentOverride({"bureau_score": (680, 700), "employment_type": ["self_employed"]}, ("R5_SCORE",))
    ev = evaluate_strategy(df, with_overrides(strategy, (ov,)))
    # row 0 is a base approval outside the override: untouched. Rows 1-2 are salaried: no match.
    assert ev["decision"].tolist() == ["approve", "decline", "decline"]
    assert not ev["approved_by_override"].any()


def test_override_requires_every_non_relaxed_rule_to_pass(strategy):
    df = make_applicants([
        {"bureau_score": 690.0},                       # fails R5 only          -> approved
        {"bureau_score": 690.0, "foir": 0.55},         # fails R5 and R6        -> stays declined
        {"bureau_score": 690.0, "max_dpd_12m": 60},    # fails R5 and R4        -> stays declined
        {"bureau_score": 690.0, "bureau_vintage_months": 3},   # R3 and R5      -> stays declined
    ])
    ov = SegmentOverride({"bureau_score": (680, 700)}, relaxes=("R5_SCORE",))
    ev = evaluate_strategy(df, with_overrides(strategy, (ov,)))
    assert ev["decision"].tolist() == ["approve", "decline", "decline", "decline"]


def test_override_conditions_band_max_and_categorical(strategy):
    df = make_applicants([
        {"bureau_score": 680.0, "foir": 0.35},                             # in
        {"bureau_score": 700.0 - 1e-9, "foir": 0.35},                      # in (upper bound exclusive)
        {"bureau_score": 679.0, "foir": 0.35},                             # below band
        {"bureau_score": 690.0, "foir": 0.36},                             # foir above foir_max
        {"bureau_score": 690.0, "foir": 0.30, "employment_type": "other"},  # wrong employment
    ])
    ov = SegmentOverride({"bureau_score": (680, 700), "foir_max": 0.35, "employment_type": ["salaried"]},
                         ("R5_SCORE",))
    ev = evaluate_strategy(df, with_overrides(strategy, (ov,)))
    assert ev["approved_by_override"].tolist() == [True, True, False, False, False]


def test_override_order_is_irrelevant(strategy):
    df = make_applicants([{"bureau_score": 690.0}, {"bureau_score": 670.0, "foir": 0.55}])
    a = SegmentOverride({"bureau_score": (680, 700)}, ("R5_SCORE",))
    b = SegmentOverride({"bureau_score": (660, 680)}, ("R5_SCORE", "R6_FOIR"))
    e1 = evaluate_strategy(df, with_overrides(strategy, (a, b)))
    e2 = evaluate_strategy(df, with_overrides(strategy, (b, a)))
    pd.testing.assert_frame_equal(e1, e2)
    assert e1["decision"].tolist() == ["approve", "approve"]


def test_unknown_override_column_raises(strategy):
    ov = SegmentOverride({"nonexistent": (0, 1)}, ("R5_SCORE",))
    with pytest.raises(KeyError):
        evaluate_strategy(make_applicants([{}]), with_overrides(strategy, (ov,)))
