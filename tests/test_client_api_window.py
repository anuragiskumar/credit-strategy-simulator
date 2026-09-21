"""The analysis window through the API (TODO A3).

The screen sends a `window` with a simulate or goal-seek request, or as query parameters on
health and rules. It gets back the window each figure ran on, and a window the engine will not
analyse comes back as a 400 with the reason in words — the same way a locked rule does.
"""
import functools
import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

from src import client_api as API, client_context as C
from src.client_generate import generate, load_client_config
from src.rule_inventory import build_inventory

REPO = Path(__file__).resolve().parents[1]
HAS_RULES = bool(list(REPO.glob("business-rules-*.xlsx")))
pytestmark = pytest.mark.skipif(not HAS_RULES, reason="client rule files not present")

OFF = [{"type": "off", "rule_id": "racAndPolicies#012"}]


@pytest.fixture(scope="module")
def engine():
    c = load_client_config(overrides={"n_rows": 20_000})
    cfg = {**c, "optimise": {**c["optimise"], "beam_width": 2, "max_depth": 2,
                             "max_rule_candidates": 4, "field_moves": []}}
    cache = C.ContextCache(generate(cfg), build_inventory(REPO), cfg)
    return API.Engine(base=cache.baseline(), inv=cache.inv, cache=cache)


@pytest.fixture(scope="module")
def six(engine):
    return next(p for p in engine.health()["window_presets"] if p["id"] == "last_6m")


# --------------------------------------------------------------------------- health
def test_health_gives_the_data_range_the_default_window_and_the_presets(engine):
    h = engine.health()
    lo, hi = C.data_range(engine.cache.df)
    assert h["data_range"] == {"app_from": f"{lo:%Y-%m-%d}", "app_to": f"{hi:%Y-%m-%d}"}
    assert h["default_window"]["app_to"] == h["data_range"]["app_to"]
    assert h["window"] == h["default_window"]
    assert h["outcome"] == {"as_of": "2026-08-31", "dpd": 90, "within_months": 12}
    assert [p["id"] for p in h["window_presets"]] == ["last_6m", "last_12m", "all"]
    assert h["window_presets"][-1]["app_from"] == h["data_range"]["app_from"]


def test_the_default_window_is_the_last_twelve_months(engine):
    h = engine.health()
    twelve = next(p for p in h["window_presets"] if p["id"] == "last_12m")
    assert h["default_window"]["app_from"] == twelve["app_from"]


def test_health_for_a_window_gives_that_windows_headline(engine, six):
    h = engine.health(six)
    assert h["window"]["app_from"] == six["app_from"]
    assert h["applicants"] < engine.health()["applicants"]
    assert h["booked_bad_rate"] == engine.health()["booked_bad_rate"]   # mature loans, not window


# --------------------------------------------------------------------------- requests
def test_a_scenario_runs_on_the_window_it_is_sent_with(engine, six):
    default = engine.simulate(OFF)
    windowed = engine.simulate(OFF, window=six)
    assert windowed["window"]["app_from"] == six["app_from"]
    assert default["window"] == engine.health()["default_window"]
    assert windowed["result"]["swap_in"] < default["result"]["swap_in"]


def test_an_empty_window_means_the_whole_file(engine):
    out = engine.simulate(OFF, window={})
    assert out["window"]["applicants"] == len(engine.cache.df)


def test_goal_seek_reports_the_window_it_searched(engine, six):
    base = engine.baseline(six)
    out = engine.goal_seek(target=base.approval_rate + 0.02, window=six)
    assert out["window"]["app_from"] == six["app_from"]


def test_the_rule_list_follows_the_window(engine, six):
    whole = {r["rule_id"]: r for r in engine.rules(window={})}
    recent = {r["rule_id"]: r for r in engine.rules(window=six)}
    rid = "racAndPolicies#012"
    assert recent[rid]["declines_alone"] < whole[rid]["declines_alone"]


@pytest.mark.parametrize("window, match", [
    ({"app_from": "2026-06-01", "app_to": "2026-01-01"}, "after it ends"),
    ({"app_from": "2031-01-01"}, "the data covers"),
    ({"app_from": "not a date"}, "not a date"),
    ({"app_from": "2026-08-25", "app_to": "2026-08-31"}, "Widen the window"),
    ({"performance_months": 20}, "Shorten the performance window"),
    ({"months": 6}, "does not know"),
])
def test_a_window_the_engine_will_not_analyse_is_refused_in_words(engine, window, match):
    with pytest.raises(API.ApiError, match=match):
        engine.simulate(OFF, window=window)


# --------------------------------------------------------------------------- HTTP
@pytest.fixture(scope="module")
def server(engine):
    from ui import serve
    serve.ENGINE.update(engine=engine, error=None, loading=False)
    srv = serve.Server(("127.0.0.1", 0), functools.partial(serve.Handler,
                                                           directory=str(serve.HERE)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    serve.ENGINE.update(engine=None)


def _call(url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_http_carries_the_window_both_ways(server, six):
    q = urllib.parse.urlencode({"app_from": six["app_from"], "app_to": six["app_to"]})
    status, h = _call(f"{server}/api/health?{q}")
    assert status == 200 and h["window"]["app_from"] == six["app_from"]
    status, rules = _call(f"{server}/api/rules?{q}")
    assert status == 200 and rules["rules"]
    status, out = _call(server + "/api/simulate", {"changes": OFF, "window": six})
    assert status == 200 and out["window"]["app_from"] == six["app_from"]


def test_http_refuses_a_bad_window_with_a_400_in_words(server):
    status, err = _call(server + "/api/simulate",
                        {"changes": OFF, "window": {"app_from": "2031-01-01"}})
    assert status == 400 and "the data covers" in err["error"]
    status, err = _call(f"{server}/api/health?app_from=2026-06-01&app_to=2026-01-01")
    assert status == 400 and "after it ends" in err["error"]
