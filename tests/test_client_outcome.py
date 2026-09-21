"""The real-data outcome contract (TODO A1).

A bank supplies when it booked each loan and when a loan first went bad, plus the date of the
extract. It never supplies `latent_bad`. These tests hold the engine to that: it must run on a
file without the truth column, give identical answers whether or not the column is there, and
never let a loan that has not had time to go bad count as a good one.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src import client_analysis as A, client_loader, client_schema, client_simulate as S
from src.client_generate import generate, load_client_config
from src.rule_inventory import build_inventory

REPO = Path(__file__).resolve().parents[1]
HAS_RULES = bool(list(REPO.glob("business-rules-*.xlsx")))
N = 20_000


def _cfg(**outcome):
    cfg = load_client_config(overrides={"n_rows": N})
    cfg["outcome"] = {**cfg["outcome"], **outcome}
    return cfg


def _loans(rows):
    """Booked loans as (booking_date, bad_date) pairs, bad_date None for never bad."""
    return pd.DataFrame({"booking_date": pd.to_datetime([b for b, _ in rows]),
                         "bad_date": pd.to_datetime([d for _, d in rows])})


# --------------------------------------------------------------------------- the definition
def test_a_loan_is_judged_only_once_it_has_run_the_whole_definition_window():
    cfg = _cfg(as_of="2026-08-31")      # 12 months of performance, from config
    perf = A.observed_performance(_loans([
        ("2025-08-31", None),           # exactly 12 months: mature, never bad -> good
        ("2025-09-01", None),           # one day short: immature, NOT good
        ("2024-01-10", "2024-06-01"),   # mature and went bad -> bad
        ("2026-03-01", "2026-06-01"),   # already bad but immature -> not yet counted
        (None, None),                   # never booked
    ]), cfg)
    assert perf["mature"].tolist() == [True, False, True, False, False]
    obs = perf["observed_bad"].tolist()
    assert obs[0] == 0.0 and obs[2] == 1.0
    assert np.isnan(obs[1]) and np.isnan(obs[3]) and np.isnan(obs[4])


def test_going_bad_after_the_definition_window_is_not_bad():
    perf = A.observed_performance(_loans([("2024-01-01", "2025-03-01")]), _cfg())
    assert perf["observed_bad"].tolist() == [0.0]


def test_the_definition_window_is_read_from_config():
    loans = _loans([("2024-01-01", "2025-03-01")])      # bad after 14 months
    bd = {"dpd": 90, "within_months": 18}
    assert A.observed_performance(loans, _cfg(bad_definition=bd))["observed_bad"].tolist() == [1.0]


def test_nothing_after_the_extract_date_is_observed():
    """A bad date later than the extract is a data error, not a bad loan the bank has seen."""
    perf = A.observed_performance(_loans([("2024-01-01", "2024-09-01")]), _cfg(as_of="2024-06-30"))
    assert perf["mature"].tolist() == [False]


def test_an_unset_extract_date_is_refused_in_words():
    with pytest.raises(A.OutcomeError, match="as_of"):
        A.observed_performance(_loans([("2024-01-01", None)]), _cfg(as_of=None))


# --------------------------------------------------------------------------- the schema
@pytest.fixture(scope="module")
def df():
    return generate(load_client_config(overrides={"n_rows": N}))


def test_performance_dates_are_engine_visible_and_the_truth_is_not():
    assert {"booking_date", "bad_date"} <= set(client_schema.ENGINE_VISIBLE)
    assert "latent_bad" not in client_schema.ENGINE_VISIBLE


@pytest.mark.parametrize("breakage, message", [
    (lambda d, b: d.assign(bad_date=d["bad_date"].mask(~b, d["app_date"])),
     "never booked"),
    (lambda d, b: d.assign(booking_date=d["booking_date"].mask(b, d["app_date"] - pd.Timedelta(days=1))),
     "booking_date before app_date"),
    (lambda d, b: d.assign(bad_date=d["bad_date"].mask(b, d["booking_date"] - pd.Timedelta(days=1))),
     "bad_date before booking_date"),
])
def test_validation_rejects_impossible_performance_dates(df, breakage, message):
    booked = df["booking_date"].notna()
    assert message in "; ".join(client_schema.validate(breakage(df, booked)))


# --------------------------------------------------------------------------- the generator
def test_the_generator_dates_performance_only_for_loans_it_booked(df):
    as_of = pd.Timestamp(load_client_config()["outcome"]["as_of"])
    booked = df["booking_date"].notna()
    assert 0 < booked.mean() < 0.5
    assert df.loc[~booked, "bad_date"].isna().all()
    assert (df["booking_date"].dropna() <= as_of).all()
    assert (df["bad_date"].dropna() <= as_of).all()
    # Recent loans are genuinely immature: the whole last year of bookings has no verdict yet.
    assert df.loc[df["booking_date"] > as_of - pd.DateOffset(months=12), "booking_date"].size > 0


def test_on_mature_loans_the_observed_outcome_is_the_truth(df):
    """Synthetic data only: the dates the generator records must agree with what it planted."""
    perf = A.observed_performance(df, load_client_config())
    mature = perf["mature"]
    assert mature.sum() > 2000
    assert (perf.loc[mature, "observed_bad"].astype(bool) == df.loc[mature, "latent_bad"]).all()


# --------------------------------------------------------------------------- a bank's file
@pytest.mark.skipif(not HAS_RULES, reason="client rule files not present")
def test_a_bank_file_without_latent_bad_loads_and_runs(df, tmp_path):
    """TODO A1's done-when: booked outcomes in, no truth column, the whole engine runs."""
    cfg = load_client_config(overrides={"n_rows": N})
    path = tmp_path / "bank.parquet"
    df.drop(columns="latent_bad").to_parquet(path, index=False)

    loaded = client_loader.load_applications(path)
    assert "latent_bad" not in loaded.columns
    inv = build_inventory(REPO)
    base = S.build_baseline(loaded, inv, cfg)
    assert 0 < base.booked_bad_rate < 1
    assert base.observed_loans < int(base.outcome["booked"].sum())

    drivers = A.decline_drivers(loaded, base.res, base.outcome, cfg, model=base.model)
    assert not drivers.empty
    top = drivers.iloc[0]["rule_id"]
    result = S.simulate(base, inv, S.rule_lever(top, enabled=False))
    assert result["swap_in"] > 0


@pytest.mark.skipif(not HAS_RULES, reason="client rule files not present")
def test_the_truth_column_changes_nothing_the_engine_reports(df):
    cfg = load_client_config(overrides={"n_rows": N})
    inv = build_inventory(REPO)
    with_truth = S.build_baseline(df, inv, cfg)
    without = S.build_baseline(df.drop(columns="latent_bad"), inv, cfg)
    pd.testing.assert_frame_equal(with_truth.outcome, without.outcome)
    assert with_truth.model.gini == without.model.gini
