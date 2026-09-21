"""Trend over time and vintage (TODO B2).

Both read the product's whole file. A month is given a bad rate only once its loans have run the
performance window, and a vintage curve only reaches a month every loan in it has run, so the
recent book can never look safer than the loans behind it. Neither reads `latent_bad`.
"""
import inspect
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src import client_analysis as A, client_context as C, client_simulate as S
from src.client_generate import generate, load_client_config
from src.rule_inventory import build_inventory

REPO = Path(__file__).resolve().parents[1]
UI = REPO / "ui"
HAS_RULES = bool(list(REPO.glob("business-rules-*.xlsx")))
needs_rules = pytest.mark.skipif(not HAS_RULES, reason="client rule files not present")


def test_months_to_bad_matches_the_bad_definitions_calendar():
    rng = np.random.default_rng(7)
    booking = pd.Series(pd.Timestamp("2024-01-01") + pd.to_timedelta(rng.integers(0, 700, 400), unit="D"))
    bad = booking + pd.to_timedelta(rng.integers(0, 500, 400), unit="D")
    bad = bad.where(rng.random(400) < 0.7)
    k = A._months_to_bad(booking, bad)
    for b, d, got in zip(booking, bad, k):
        if pd.isna(d):
            assert np.isnan(got)
            continue
        want = next(m for m in range(1, 40) if d <= b + pd.DateOffset(months=m))
        assert got == want, (b, d)


@pytest.fixture(scope="module")
def base():
    cfg = load_client_config(overrides={"n_rows": 20_000})
    inv = build_inventory(REPO)
    df = generate(cfg)
    full = S.full_replay(df, inv, cfg)
    window = C.last_months(full.df, cfg, 12)
    return S.build_baseline(df, inv, cfg, window=window, full=full)


@needs_rules
def test_a_month_is_given_a_bad_rate_only_once_its_loans_have_run_the_window(base):
    df, outcome = base.whole
    rows = A.trend_by_month(df, outcome, base.cfg, base.window)
    tr = base.cfg["trend"]
    assert sum(r["applications"] for r in rows) == len(df)
    for r in rows:
        if r["bad_rate"] is None:
            assert r["bad_rate_reason"]
            assert r["booked"] < tr["min_loans"] or r["mature_share"] < tr["min_mature_share"]
        else:
            assert r["mature_share"] >= tr["min_mature_share"] and r["mature"] >= 1
    # The latest months cannot be judged yet, and every month of the default window is among them.
    assert rows[-1]["bad_rate"] is None and "judged from" in rows[-1]["bad_rate_reason"]
    assert all(r["bad_rate"] is None for r in rows if r["in_window"])
    assert sum(r["in_window"] for r in rows) == 12
    # The approval rate is the replay's, as in the headline.
    win = [r for r in rows if r["in_window"]]
    assert sum(r["booked"] for r in win) == int(base.outcome["booked"].sum())


@needs_rules
def test_a_vintage_curve_stops_where_its_loans_stop_and_meets_the_bad_rate(base):
    df, _ = base.whole
    cfg = base.cfg
    as_of = pd.Timestamp(cfg["outcome"]["as_of"])
    months = cfg["outcome"]["bad_definition"]["within_months"]
    perf = A.observed_performance(df, cfg)
    booking = pd.to_datetime(df["booking_date"])
    for gran in ("month", "quarter"):
        v = A.vintage(df, cfg, gran)
        assert sum(c["loans"] for c in v["cohorts"]) == int(booking.notna().sum())
        for c in v["cohorts"]:
            last = pd.Timestamp(c["booked_to"])
            assert last + pd.DateOffset(months=c["max_mob"]) <= as_of
            assert last + pd.DateOffset(months=c["max_mob"] + 1) > as_of
            ys = [p[1] for p in c["points"]]
            assert ys == sorted(ys), "a cumulative curve never falls"
            at = dict(c["points"]).get(months)
            if at is not None:
                # At the definition's month, the curve is the cohort's bad rate as the engine reads it.
                period = booking.dt.to_period("Q" if gran == "quarter" else "M").astype(str)
                mask = booking.notna() & (period == c["cohort"])
                assert perf.loc[mask, "mature"].all()
                assert at == pytest.approx(perf.loc[mask, "observed_bad"].mean(), abs=1e-6)


@needs_rules
def test_the_view_carries_over_time_for_the_whole_file(base):
    from src.client_view import build_view
    view = build_view(base, build_inventory(REPO), quick=True)
    ot = view["over_time"]
    assert len(ot["months"]) == len(base.whole[0]["app_date"].dt.to_period("M").unique())
    assert set(ot["vintage"]) == set(base.cfg["trend"]["vintage_granularity"])
    assert ot["roll_rate"]["available"] is False and ot["roll_rate"]["reason"]


def test_over_time_never_reads_the_truth():
    for fn in (A.trend_by_month, A.vintage, A.over_time, A._months_to_bad):
        assert "latent_bad" not in inspect.getsource(fn), fn.__name__


# --------------------------------------------------------------------------- the page
def _code(name):
    return re.sub(r"/\*.*?\*/", "", (UI / name).read_text(encoding="utf-8"), flags=re.S)


def _fn(js, name):
    start = js.index("function " + name + "(")
    return js[start:js.index("\n  function ", start + 1)]


def test_the_portfolio_shows_over_time_and_draws_no_rate_it_was_not_given():
    js = _code("client.js")
    assert "overTimePanel()" in _fn(js, "pagePortfolio")
    chart = _fn(js, "trendChart")
    # A gap is a gap: the bad-rate line breaks where the engine gave no rate, and says why.
    assert "bad_rate_reason" in chart and "never bridge" in (UI / "client.js").read_text(encoding="utf-8")
    for fn in ("trendChart", "vintageChart", "trendTable", "vintageTable"):
        body = _fn(js, fn)
        assert "latent" not in body and "Math.random" not in body, fn
    assert "roll_rate.reason" in _fn(js, "overTimePanel")


def test_the_fixture_carries_over_time():
    import json
    f = json.loads((UI / "client_fixture.json").read_text(encoding="utf-8"))
    for ctx in [f] + list(f["contexts"].values()):
        assert ctx["over_time"]["months"] and ctx["over_time"]["vintage"], ctx["meta"].get("context")
