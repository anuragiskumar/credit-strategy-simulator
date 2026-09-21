"""The analysis window (TODO A2, with the A5 tests).

Two windows, two questions: the application window decides who is replayed; the performance
window decides which booked loans are old enough to judge. The test that matters most is the
done-when — choosing a recent window must not make the bad rate look better just because its
loans have not had time to go bad.
"""
from pathlib import Path

import pandas as pd
import pytest

from src import client_api, client_context as C, client_replay, client_simulate as S
from src.client_generate import generate, load_client_config
from src.rule_inventory import build_inventory

REPO = Path(__file__).resolve().parents[1]
HAS_RULES = bool(list(REPO.glob("business-rules-*.xlsx")))
pytestmark = pytest.mark.skipif(not HAS_RULES, reason="client rule files not present")

N = 20_000
W = C.AnalysisWindow


@pytest.fixture(scope="module")
def cfg():
    return load_client_config(overrides={"n_rows": N})


@pytest.fixture(scope="module")
def df(cfg):
    return generate(cfg)


@pytest.fixture(scope="module")
def cache(df, cfg):
    return C.ContextCache(df, build_inventory(REPO), cfg)


@pytest.fixture(scope="module")
def whole(cache):
    return cache.baseline(W())            # no dates: the edges of the data


@pytest.fixture(scope="module")
def recent(cache, df, cfg):
    return cache.baseline(C.last_months(df, cfg, 3))


# --------------------------------------------------------------------------- parsing
def test_a_window_is_read_from_a_request_body():
    w = W.from_dict({"app_from": "2025-09-01", "app_to": "2026-08-31", "performance_months": "6"})
    assert w == W(pd.Timestamp("2025-09-01"), pd.Timestamp("2026-08-31"), 6)
    assert W.from_dict(None) == W()


@pytest.mark.parametrize("body, match", [
    ("last year", "must be an object"),
    ({"from": "2025-01-01"}, "does not know"),
    ({"app_from": "yesterday-ish"}, "not a date"),
    ({"performance_months": "twelve"}, "whole number"),
    ({"performance_months": 0}, "at least one month"),
])
def test_an_unreadable_window_is_refused_in_words(body, match):
    with pytest.raises(C.WindowError, match=match):
        W.from_dict(body)


def test_resolving_fills_in_the_data_edges_and_the_configured_performance_window(df, cfg):
    w = C.resolve(W(), df, cfg)
    lo, hi = C.data_range(df)
    assert (w.app_from, w.app_to) == (lo, hi)
    assert w.performance_months == cfg["outcome"]["bad_definition"]["within_months"]


def test_the_default_is_the_last_twelve_months_of_applications(df, cfg):
    w = C.default_window(df, cfg)
    _, hi = C.data_range(df)
    assert w.app_to == hi
    assert w.app_from == hi - pd.DateOffset(months=12) + pd.Timedelta(days=1)
    assert w.to_dict()["label"] == f"{w.app_from:%-d %b %Y} – {hi:%-d %b %Y}"


# --------------------------------------------------------------------------- boundaries (A5)
def test_both_ends_of_the_window_are_inclusive_by_calendar_day():
    dates = pd.to_datetime(["2025-02-28", "2025-03-01", "2025-03-01 17:45",
                            "2025-03-31", "2025-04-01"], format="ISO8601")
    frame = pd.DataFrame({"app_date": dates})
    w = W(pd.Timestamp("2025-03-01"), pd.Timestamp("2025-03-31"), 12)
    assert C.app_mask(frame, w).tolist() == [False, True, True, True, False]


@pytest.mark.parametrize("window, match", [
    (W(pd.Timestamp("2026-03-01"), pd.Timestamp("2026-02-01")), "after it ends"),
    (W(pd.Timestamp("2030-01-01"), pd.Timestamp("2030-06-30")), "the data covers"),
])
def test_an_impossible_window_is_refused_in_words(df, cfg, window, match):
    with pytest.raises(C.WindowError, match=match):
        C.resolve(window, df, cfg)


def test_an_empty_window_is_refused(cfg):
    with pytest.raises(C.WindowError, match="no applications"):
        C.check(W(pd.Timestamp("2025-03-01"), pd.Timestamp("2025-03-01"), 12), 0, 5000, cfg)


def test_a_window_too_thin_to_act_on_is_refused(cache, df):
    _, hi = C.data_range(df)
    with pytest.raises(C.WindowError, match="Widen the window"):
        cache.baseline(W(hi - pd.Timedelta(days=6), hi))


def test_a_performance_window_no_loan_has_run_is_refused(cache):
    with pytest.raises(C.WindowError, match="Shorten the performance window"):
        cache.baseline(W(performance_months=20))


# --------------------------------------------------------------------------- the done-when
def test_a_recent_window_cannot_make_the_bad_rate_look_better(whole, recent):
    """Last 3 months: none of its own loans is old enough to judge, so none of them is judged."""
    booked = recent.outcome["booked"]
    assert booked.sum() > 0
    assert recent.outcome.loc[booked, "observed_bad"].isna().all()
    assert recent.booked_bad_rate == whole.booked_bad_rate
    assert 0 < recent.booked_bad_rate < 1


def test_a_recent_window_changes_who_is_replayed(whole, recent):
    assert len(recent.df) < len(whole.df) / 4
    assert recent.df["app_date"].min() >= recent.window.app_from
    assert recent.window_dict()["applicants"] == len(recent.df)


def test_immature_loans_are_kept_out_of_pd_training(whole, cfg):
    as_of = pd.Timestamp(cfg["outcome"]["as_of"])
    months = whole.window.performance_months
    assert whole.model.n_train == whole.observed_loans
    assert whole.observed_loans < int(whole.outcome["booked"].sum())
    assert whole.perf.booked_to <= as_of - pd.DateOffset(months=months)


def test_a_shorter_performance_window_matures_more_loans(cache, whole, cfg):
    short = cache.baseline(W(performance_months=6))
    assert short.observed_loans > whole.observed_loans
    assert short.cfg["outcome"]["bad_definition"]["within_months"] == 6
    as_of = pd.Timestamp(cfg["outcome"]["as_of"])
    assert short.perf.booked_to <= as_of - pd.DateOffset(months=6)


# --------------------------------------------------------------------------- consistency (A5)
def test_a_window_sliced_from_the_whole_replay_equals_replaying_the_window(recent, cache, cfg):
    direct = client_replay.replay(recent.df, cache.inv, cfg)
    pd.testing.assert_frame_equal(recent.res.hits, direct.hits[recent.res.hits.columns])
    pd.testing.assert_frame_equal(
        recent.res.rules.set_index("rule_id")[["matched"]],
        direct.rules.set_index("rule_id")[["matched"]])


def test_every_scenario_reports_the_window_it_ran_on(recent, cache):
    top = recent.res.rules.sort_values("matched").iloc[-1]["rule_id"]
    r = S.simulate(recent, cache.inv, S.rule_lever(top, enabled=False))
    assert r["window"]["app_from"] == recent.window.to_dict()["app_from"]
    assert r["window"]["mature_loans"] == recent.observed_loans
    assert r["booked_bad_rate_before"] == round(recent.booked_bad_rate, 4)


def test_a_tightening_in_a_recent_window_is_judged_on_mature_loans(recent, cache):
    """Swap-outs in the window are too recent to have repaid; mature loans like them have."""
    lever = client_api.cutoff_lever(recent, cache.inv, {"type": "cutoff", "field": "simahcreditscore",
                                                        "from": 600, "to": 640})
    r = S.simulate(recent, cache.inv, lever)
    assert r["swap_out"] > 0
    assert r["swap_out_observed_bad_rate"] is not None
    assert r["swap_out_observed_loans"] > 0
    assert r["expected_bad_rate_known"]


# --------------------------------------------------------------------------- the cache
def test_the_file_is_replayed_once_and_a_window_is_built_once(cache, df, cfg):
    first = cache.full()
    a = cache.baseline(C.last_months(df, cfg, 6))
    assert cache.full() is first
    assert cache.baseline(C.last_months(df, cfg, 6)) is a


def test_only_recent_windows_are_kept(df, cfg):
    small = C.ContextCache(df, build_inventory(REPO), cfg, size=2)
    a = small.baseline(C.last_months(df, cfg, 6))
    small.baseline(C.last_months(df, cfg, 7))
    small.baseline(C.last_months(df, cfg, 8))
    assert small.baseline(C.last_months(df, cfg, 6)) is not a
