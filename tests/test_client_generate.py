"""The generated population is the demo's evidence base, so its properties are tested, not assumed.

The planted answers matter most. The engine is meant to replace a human's judgement, so the
only way to know it works is to hide a known truth in the data and check the truth is
recoverable. These tests assert the truths are actually there; step 3 asserts the engine
finds them.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src import client_loader, client_schema
from src.client_generate import calibration_report, generate, load_client_config, threshold_coverage

REPO = Path(__file__).resolve().parents[1]
HAS_RULES = bool(list(REPO.glob("business-rules-*.xlsx")))
needs_rules = pytest.mark.skipif(not HAS_RULES, reason="client rule files not present")

N = 20_000


@pytest.fixture(scope="module")
def cfg():
    return load_client_config(overrides={"n_rows": N})


@pytest.fixture(scope="module")
def df(cfg):
    return generate(cfg)


# --------------------------------------------------------------------------- schema
def test_generated_population_matches_the_canonical_schema(df):
    assert client_schema.validate(df, require_latent=True) == []
    assert list(df.columns) == list(client_schema.COLUMNS)
    assert len(df) == N


def test_latent_bad_is_not_engine_visible():
    assert "latent_bad" not in client_schema.ENGINE_VISIBLE
    assert "latent_bad" in client_schema.COLUMNS


def test_generation_is_deterministic(cfg):
    a = generate(cfg)
    b = generate(cfg)
    pd.testing.assert_frame_equal(a, b)


def test_a_different_seed_gives_a_different_population(cfg):
    other = generate(load_client_config(overrides={"n_rows": N, "seed": cfg["seed"] + 1}))
    assert not other["simah_score"].equals(generate(cfg)["simah_score"])


def test_validation_rejects_a_military_applicant_without_a_rank(df):
    broken = df.copy()
    mil = broken["employment_type"].eq("MILITARY")
    broken.loc[mil, "military_rank"] = pd.NA
    assert any("military_rank" in p for p in client_schema.validate(broken))


def test_validation_rejects_nationality_disagreeing_with_is_saudi(df):
    broken = df.copy()
    broken.loc[broken.index[0], "is_saudi"] = not broken["is_saudi"].iloc[0]
    assert any("is_saudi" in p for p in client_schema.validate(broken))


# --------------------------------------------------------------------------- dialects
def test_each_rule_table_gets_its_own_segment_vocabulary(df):
    rac = client_schema.to_dialect(df, "racAndPolicies")
    sim = client_schema.to_dialect(df, "simati_chk_IAF")
    ykn = client_schema.to_dialect(df, "yknBasicCheckValidation")
    assert set(rac.dropna()) <= {"ST", "SMG", "PVTL", "PVTSML", "SE", "PRIO", "PRIV-BSF"}
    assert "Establishment" in set(sim.dropna())
    assert set(ykn.dropna()) <= {"G", "SG", "PL", "PS", "SE", "BSFPB", "BSFE", "M", "P"}


def test_ykn_folds_military_and_pensioner_into_the_segment_column(df):
    ykn = client_schema.to_dialect(df, "yknBasicCheckValidation")
    mil = df["employment_type"].eq("MILITARY")
    assert (ykn[mil] == "M").all()
    pen = df["is_pensioner"] & ~mil
    assert (ykn[pen] == "P").all()
    # ...and the other dialects must not, or the same applicant would be scoped differently.
    assert "M" not in set(client_schema.to_dialect(df, "racAndPolicies").dropna())


def test_unknown_table_has_no_dialect(df):
    with pytest.raises(KeyError):
        client_schema.to_dialect(df, "nope")


# --------------------------------------------------------------------------- loader
@needs_rules
def test_rule_frame_exposes_the_fields_the_rules_name(df):
    frame = client_loader.rule_frame(df, "racAndPolicies")
    for field in ("customersegment", "nationality", "age", "income", "simahcreditscore",
                  "crifscore", "typeofemployment", "pensioner", "employer_keyword_check",
                  "loanamount", "employername", "sourcetype"):
        assert field in frame.columns, field
    assert set(frame["pensioner"].dropna()) <= {"true", "false"}
    assert set(frame["typeofemployment"].dropna()) <= {"CV", "ML"}


def test_employer_keyword_is_derived_not_assigned(df):
    """Moving the keyword list must move the population, or the simulator is a no-op."""
    hits = client_loader.employer_keyword_hit(df["employer_name"], ["مؤسسة"])
    none = client_loader.employer_keyword_hit(df["employer_name"], ["nothing-matches-this"])
    assert (hits == "Y").sum() > 0
    assert (none == "Y").sum() == 0


@needs_rules
def test_keyword_check_only_fires_on_the_arabic_trader_names(df):
    frame = client_loader.rule_frame(df, "racAndPolicies")
    hit = frame["employer_keyword_check"].eq("Y")
    assert hit.sum() > 0
    assert not df.loc[hit, "employer_name"].isin(["Saudi Aramco", "SABIC", "GOSI"]).any()
    # Small traders and the self-employed are the ones the list is aimed at.
    small = df["employer_segment"].isin(["PRIVATE_SMALL", "SELF_EMPLOYED"])
    assert hit[small].mean() > hit[~small].mean() * 5


def test_map_source_renames_a_third_party_file(df):
    source = df[client_schema.ENGINE_VISIBLE].rename(columns={"monthly_income": "SALARY",
                                                          "simah_score": "BUREAU_SCORE"})
    mapped = client_loader.map_source(source, {"SALARY": "monthly_income",
                                           "BUREAU_SCORE": "simah_score"})
    assert client_schema.validate(mapped) == []


def test_map_source_refuses_a_file_missing_a_canonical_column(df):
    source = df[client_schema.ENGINE_VISIBLE].drop(columns=["crif_score"])
    with pytest.raises(client_loader.MappingError, match="crif_score"):
        client_loader.map_source(source, {})


def test_map_source_fills_a_missing_column_from_constants(df):
    source = df[client_schema.ENGINE_VISIBLE].drop(columns=["product"])
    mapped = client_loader.map_source(source, {}, constants={"product": "TWQR"})
    assert (mapped["product"] == "TWQR").all()


# --------------------------------------------------------------------------- planted answers
def test_planted_digital_channel_carries_the_weakest_applicant_mix(df):
    by = df.groupby("channel", observed=True).agg(
        income=("monthly_income", "median"), bad=("latent_bad", "mean"),
        no_score=("simah_score", lambda s: s.isna().mean()))
    assert by.loc["digital", "income"] == by["income"].min()
    assert by.loc["digital", "bad"] == by["bad"].max()
    assert by.loc["digital", "no_score"] == by["no_score"].max()


def test_planted_length_of_service_does_not_predict_risk(df):
    corr = np.corrcoef(df["length_of_service_months"].astype(float),
                       df["latent_bad"].astype(float))[0, 1]
    assert abs(corr) < 0.02, f"length of service correlates {corr:.4f} with the outcome"


def test_planted_missing_bureau_score_is_the_riskiest_group(df, cfg):
    missing = df["simah_score"].isna()
    ratio = df.loc[missing, "latent_bad"].mean() / df.loc[~missing, "latent_bad"].mean()
    assert ratio >= cfg["risk"]["no_score_min_ratio"]
    assert missing.sum() > 500


def test_planted_portfolio_concentration_matches_gurus_example(df):
    share = df["sector"].value_counts(normalize=True)
    assert share.idxmax() == "it"
    assert share["finance"] < 0.05
    assert (df["sector"] == "government").sum() == 0


def test_bureau_score_actually_separates_good_from_bad(df):
    """A score that does not rank risk would make every cutoff result meaningless."""
    scored = df[df["simah_score"].notna()]
    low = scored[scored["simah_score"] < 550]["latent_bad"].mean()
    high = scored[scored["simah_score"] >= 700]["latent_bad"].mean()
    assert low > high * 5


# --------------------------------------------------------------------------- calibration
def test_population_bad_rate_hits_the_target(df, cfg):
    assert abs(df["latent_bad"].mean() - cfg["risk"]["target_bad_rate"]) \
        <= cfg["calibration"]["bad_rate_tolerance"]


def test_every_segment_is_populated(df, cfg):
    share = df["employer_segment"].value_counts(normalize=True)
    assert set(share.index) == set(client_schema.EMPLOYER_SEGMENTS)
    assert share.min() >= cfg["calibration"]["min_segment_share"]


@needs_rules
def test_no_rule_threshold_is_left_unreachable(df, cfg):
    """A threshold with nobody on one side silently removes that rule from the ranking."""
    report = calibration_report(df, cfg, REPO)
    assert report["rules_that_cannot_fire"] == [], report["rules_that_cannot_fire"]
    assert report["fields_without_a_column"] == []


@needs_rules
def test_threshold_coverage_reports_every_tunable_twqr_threshold(df):
    cov = threshold_coverage(df, REPO)
    assert len(cov) > 40
    assert set(cov["kind"].dropna()) <= {"cutoff", "band edge"}
    for field in ("age", "income", "simahcreditscore", "crifscore", "loanamount"):
        assert field in set(cov["field"])
