"""Rule replay, funnel and decline drivers (step 3).

The tests that matter most are the ones asserting the engine RECOVERS the answers planted in
step 2. A ranking that looks plausible but is wrong is the failure mode the brief warns about
throughout, and the only defence is a dataset whose right answer is known.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src import client_analysis as A, client_replay, client_risk
from src.client_generate import generate, load_client_config
from src.rule_inventory import build_inventory

REPO = Path(__file__).resolve().parents[1]
HAS_RULES = bool(list(REPO.glob("business-rules-*.xlsx")))
pytestmark = pytest.mark.skipif(not HAS_RULES, reason="client rule files not present")

N = 20_000


@pytest.fixture(scope="module")
def cfg():
    return load_client_config(overrides={"n_rows": N})


@pytest.fixture(scope="module")
def inv():
    return build_inventory(REPO)


@pytest.fixture(scope="module")
def df(cfg):
    return generate(cfg)


@pytest.fixture(scope="module")
def res(df, inv, cfg):
    return client_replay.replay(df, inv, cfg)


@pytest.fixture(scope="module")
def outcome(df, res, cfg):
    return A.stage_outcome(df, res, cfg)


@pytest.fixture(scope="module")
def model(df, outcome, cfg):
    return client_risk.fit(df, outcome, cfg)


@pytest.fixture(scope="module")
def full(inv):
    """The production-size population.

    Some findings are real but small. At 20k rows a length-of-service rule declines fewer
    than 50 applicants on its own, and the engine rightly refuses to judge it — so the claim
    has to be tested at the size the demo actually runs.
    """
    cfg = load_client_config()
    df = generate(cfg)
    res = client_replay.replay(df, inv, cfg)
    outcome = A.stage_outcome(df, res, cfg)
    return df, res, outcome, cfg, client_risk.fit(df, outcome, cfg)


# --------------------------------------------------------------------------- replay
def test_replay_evaluates_every_applicable_rule(res):
    assert len(res.rules) > 200
    assert res.hits.shape[1] == len(res.rules)
    # Only the SIMAH installment-change rule needs data we do not model.
    assert len(res.unevaluable) <= 1


def test_replay_is_deterministic(df, inv, cfg):
    a = client_replay.replay(df, inv, cfg)
    b = client_replay.replay(df, inv, cfg)
    pd.testing.assert_frame_equal(a.hits, b.hits)


def test_inactive_rules_are_excluded_by_default(res, inv, cfg, df):
    assert res.rules["is_active"].all()
    with_inactive = client_replay.replay(
        df, inv, {**cfg, "replay": {**cfg["replay"], "include_inactive_rules": True}})
    assert len(with_inactive.rules) >= len(res.rules)


def test_disabling_a_rule_removes_it_from_the_replay(df, inv, cfg, res):
    target = res.rules.nlargest(1, "matched")["rule_id"].iloc[0]
    off = client_replay.replay(df, inv, cfg, overrides={target: {"enabled": False}})
    assert target not in off.hits.columns


# --------------------------------------------------------------------------- funnel
def test_every_applicant_lands_in_exactly_one_stage(df, outcome):
    assert outcome["stage"].notna().all()
    assert len(outcome) == len(df)
    assert set(outcome["stage"].unique()) <= set(A.STAGES)


def test_funnel_stages_account_for_the_whole_population(df, outcome):
    table = A.funnel(df, outcome)
    assert table.iloc[0]["left"] == len(df)
    assert table.iloc[-1]["left"] == int(outcome["booked"].sum())
    # Each stage's survivors equal the previous stage's minus its drop-outs.
    for i in range(1, len(table) - 1):
        assert table.iloc[i]["left"] == table.iloc[i - 1]["left"] - table.iloc[i]["dropped"]
        # A stage's loss rate is measured against those who reached it, not all applicants.
        assert table.iloc[i]["entered"] == table.iloc[i - 1]["left"]
        assert table.iloc[i]["dropped_pct_of_entered"] == pytest.approx(
            100 * table.iloc[i]["dropped"] / table.iloc[i]["entered"], abs=0.05)


def test_eligibility_records_which_of_its_two_conditions_failed(df, res, outcome, cfg):
    elig = outcome[outcome["stage"] == "eligibility"]
    reasons = set(elig["reason_rule"].unique())
    assert reasons <= {A.ELIG_PRODUCT_MIN, A.ELIG_MIN_SHARE}
    assert (elig["reason_rule"] == A.ELIG_PRODUCT_MIN).sum() + \
           (elig["reason_rule"] == A.ELIG_MIN_SHARE).sum() == len(elig)
    fn = cfg["funnel"]
    offer, req = elig["offered_amount"], df.loc[elig.index, "requested_amount"]
    below_min = elig["reason_rule"] == A.ELIG_PRODUCT_MIN
    assert (offer[below_min] < fn["product_min_amount"]).all()
    # An offer failing both conditions is credited to the product minimum, never to the share.
    share_only = ~below_min
    assert (offer[share_only] >= fn["product_min_amount"]).all()
    assert (offer[share_only] < req[share_only] * fn["min_acceptable_offer_ratio"]).all()


def test_funnel_rules_sum_to_each_stage_and_are_not_capped(res, outcome, cfg):
    table = A.funnel(pd.DataFrame(index=outcome.index), outcome).set_index("stage")
    for block in A.funnel_rules(res, outcome, cfg):
        stage = block["stage"]
        assert block["total"] == block["counted"] == table.loc[stage, "dropped"]
        assert sum(r["count"] for r in block["rules"]) == block["total"], stage
        # No top-N cut: every distinct reason on the stage is listed.
        distinct = outcome.loc[outcome["stage"] == stage, "reason_rule"].nunique(dropna=False)
        assert block["n_rules"] == len(block["rules"]) == distinct, stage
        counts = [r["count"] for r in block["rules"]]
        assert counts == sorted(counts, reverse=True)


def test_funnel_layout_comes_from_config_not_row_position(cfg):
    import copy
    layout = A.funnel_layout(cfg)
    assert layout["order"] == A.STAGES
    for s in A.STAGES[1:-1]:
        assert layout["stages"][s]["group"] in layout["groups"]
    moved = copy.deepcopy(cfg)
    moved["funnel"]["stages"]["eligibility"]["group"] = "customer_choice"
    assert A.funnel_layout(moved)["stages"]["eligibility"]["group"] == "customer_choice"
    broken = copy.deepcopy(cfg)
    del broken["funnel"]["stages"]["walked_away"]
    with pytest.raises(ValueError):
        A.funnel_layout(broken)
    grouped_endpoint = copy.deepcopy(cfg)
    grouped_endpoint["funnel"]["stages"]["booked"]["group"] = "risk_declines"
    with pytest.raises(ValueError):
        A.funnel_layout(grouped_endpoint)


def test_decline_reason_is_always_a_rule_that_actually_matched(res, outcome):
    declined = outcome[outcome["stage"].isin(["hard_reject", "credit_policy"])]
    assert declined["reason_rule"].notna().all()
    for rule_id, group in declined.groupby("reason_rule"):
        assert res.hits.loc[group.index, rule_id].all(), rule_id


def test_the_offer_never_exceeds_the_request(df, outcome):
    assert (outcome["offered_amount"] <= df["requested_amount"] + 1e-6).all()


def test_performance_is_observed_only_on_booked_applicants(outcome):
    assert outcome.loc[~outcome["booked"], "observed_bad"].isna().all()
    assert outcome.loc[outcome["booked"], "observed_bad"].notna().all()


# --------------------------------------------------------------------------- drivers
def test_a_rule_never_declines_alone_more_often_than_it_declines(df, res, outcome, cfg):
    d = A.decline_drivers(df, res, outcome, cfg)
    assert (d["declines_alone"] <= d["declines"]).all()


def test_regulatory_rules_are_never_reported_as_failing_to_earn_their_place(
        df, res, outcome, cfg, model):
    """The engine must not recommend relaxing a PEP or diplomatic-service rule."""
    d = A.decline_drivers(df, res, outcome, cfg, model=model)
    not_relaxable = d[~d["relaxable"]]
    assert not not_relaxable.empty
    assert (not_relaxable["earns_its_place"] != False).all()  # noqa: E712 — None is allowed
    fields = " ".join(not_relaxable["fields"])
    assert "politicallyexposedperson" in fields and "diplomaticservice" in fields


def test_relaxability_covers_the_tunable_rules(res):
    """Scoping a rule by nationality must not make its threshold untunable."""
    assert res.rules["relaxable"].sum() > 150
    assert (~res.rules["relaxable"]).sum() < 15


# --------------------------------------------------------------------------- planted answers
def test_engine_finds_planted_digital_channel_dominance(df, outcome):
    by = A.by_source(df, outcome, "channel")
    assert by.index[0] == "digital"
    assert by.loc["digital", "share_of_all_declines"] > 45
    assert by.loc["digital", "approval_rate"] == by["approval_rate"].min()


def test_engine_finds_planted_length_of_service_rules_buy_no_safety(full):
    """Plant 2: length of service does not predict risk, yet rules decline on it."""
    df, res, outcome, cfg, model = full
    d = A.decline_drivers(df, res, outcome, cfg, model=model)
    los = d[d["fields"].str.contains("lengthofservice|monthcnt", na=False)]
    judged = los[los["earns_its_place"].notna()]
    assert not judged.empty, "no length-of-service rule could be judged"
    assert not judged["earns_its_place"].any(), \
        "a length-of-service rule was reported as earning its place"


def test_engine_finds_the_contradictory_age_rule_costing_approvals(
        df, res, outcome, cfg, model):
    """The 20-60 vs 30-70 conflict from step 1, now measured in applicants."""
    d = A.decline_drivers(df, res, outcome, cfg, model=model)
    ykn = d[d["rule_id"].str.startswith("yknBasicCheckValidation")]
    top = ykn.nlargest(1, "declines_alone").iloc[0]
    assert top["declines_alone"] > 1000
    assert top["earns_its_place"] is False or top["earns_its_place"] == False  # noqa: E712


def test_portfolio_finds_planted_concentration(df, outcome, cfg):
    book = A.portfolio(df, outcome, "sector")
    assert book.index[0] == "it"
    flags = A.concentration_flags(book, cfg)
    assert "over-exposed" in set(flags["flag"])
    assert "government" not in set(book.index)


# --------------------------------------------------------------------------- risk honesty
def test_pd_model_trains_only_on_booked_applicants(model, outcome):
    assert model.n_train == int(outcome["booked"].sum())
    assert model.gini > 0.2


def test_risk_estimate_is_refused_outside_the_booked_population(df, outcome, cfg, model):
    """The brief's warning: below the historical cutoff, a confident number is dangerous."""
    starved = client_risk.PDModel(
        pipeline=model.pipeline, gini=model.gini, n_train=model.n_train,
        train_bad_rate=model.train_bad_rate, impute_score=model.impute_score,
        score_floor=800.0, score_ceiling=900.0, booked_missing_score=False)
    low = (df["simah_score"] < 600).to_numpy()
    out = client_risk.predict_group(starved, df, low, cfg)
    assert out["known"] is False
    assert "never" in out["reason"] or "outside" in out["reason"]


def test_risk_estimate_tracks_the_truth_where_it_is_allowed_to_answer(
        df, res, outcome, cfg, model):
    d = A.decline_drivers(df, res, outcome, cfg, model=model, include_oracle=True)
    known = d[d["risk_known"] & (d["declines_alone"] >= 100)]
    err = (known["est_bad_rate_if_relaxed"] - known["oracle_bad_rate"]).abs()
    assert err.mean() < 0.05, f"honest estimate drifts {err.mean():.3f} from the truth"


def test_oracle_is_never_used_when_include_oracle_is_off(df, res, outcome, cfg, model):
    d = A.decline_drivers(df, res, outcome, cfg, model=model)
    assert "oracle_bad_rate" not in d.columns


def test_no_rule_is_judged_on_a_handful_of_applicants(df, res, outcome, cfg, model):
    """A verdict on ten applicants is noise, and worse than silence to a risk committee."""
    d = A.decline_drivers(df, res, outcome, cfg, model=model)
    judged = d[d["earns_its_place"].notna() & d["relaxable"]]
    assert (judged["declines_alone"] >= cfg["risk_model"]["min_group_size"]).all()
