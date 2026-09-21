"""The simulator's engine API: what the screen sends, what it gets back, and what it is refused.

These call `src/client_api.py`, the functions `ui/serve.py` routes to, so a passing test here is
the screen's contract. One test goes through real HTTP to prove the routing and error codes.
"""
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from src import client_api as API, client_simulate as S
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
    c = load_client_config(overrides={"n_rows": 20_000})
    # A small search: these tests prove the contract, not the optimiser.
    return {**c, "optimise": {**c["optimise"], "beam_width": 2, "max_depth": 2,
                              "max_rule_candidates": 4, "field_moves": []}}


@pytest.fixture(scope="module")
def engine(cfg, inv):
    return API.Engine(base=S.build_baseline(generate(cfg), inv, cfg), inv=inv)


# --------------------------------------------------------------------------- rule list
def test_the_rule_list_is_every_decline_rule_not_a_top_eight(engine):
    rules = engine.rules()
    blocking = [c for c in engine.base.res.compiled.values() if c.kind == "block"]
    assert len(rules) == len(blocking) > 8


def test_the_rule_list_is_ordered_by_declines_alone(engine):
    alone = [r["declines_alone"] for r in engine.rules()]
    assert alone == sorted(alone, reverse=True)


def test_a_rule_that_cannot_be_changed_says_why_and_offers_no_thresholds(engine):
    fixed = [r for r in engine.rules() if not r["editable"]]
    assert fixed
    for r in fixed:
        assert r["reason"] and r["thresholds"] == []


def test_minimum_income_non_saudi_offers_its_income_threshold(engine):
    r = next(r for r in engine.rules() if r["rule_id"] == "racAndPolicies#028")
    assert r["editable"]
    assert {"field": "income", "operator": "lt", "value_low": 5000.0,
            "value_high": None} in r["thresholds"]


def test_the_rule_list_is_json_serialisable(engine):
    json.dumps(engine.rules(), allow_nan=False)


# --------------------------------------------------------------------------- simulate
def test_a_ladder_reports_every_step_cumulatively(engine):
    out = engine.simulate([
        {"type": "off", "rule_id": "racAndPolicies#012"},
        {"type": "threshold", "rule_id": "racAndPolicies#028", "field": "income",
         "value_low": 4000},
    ])
    first, second = out["steps"]
    assert out["result"] == second
    assert second["swap_in"] >= first["swap_in"]
    assert first["change_direction"] == "loosen"
    # Each step carries what it added, so the page never subtracts one figure from another.
    assert first["added_swap_in"] == first["swap_in"]
    assert second["added_swap_in"] == second["swap_in"] - first["swap_in"]
    assert second["added_pp"] == pytest.approx(
        second["approval_change_pp"] - first["approval_change_pp"], abs=0.011)
    json.dumps(out, allow_nan=False)


def test_reverting_a_step_is_asking_again_without_it(engine):
    a = {"type": "off", "rule_id": "racAndPolicies#012"}
    b = {"type": "off", "rule_id": "yknBasicCheckValidation#016"}
    ladder = engine.simulate([a, b])
    reverted = engine.simulate([a])
    assert reverted["result"] == {**ladder["steps"][0]}


def test_a_tightening_is_where_newly_declined_comes_from(engine):
    out = engine.simulate([{"type": "threshold", "rule_id": "racAndPolicies#028",
                            "field": "income", "value_low": 12000}])["result"]
    assert out["direction"] == "tighten"
    assert out["swap_out"] > 0 and out["swap_in"] == 0
    assert out["risk_known"] and out["swap_out_observed_bad_rate"] is not None
    assert sum(v["swap_out"] for v in out["swap_in_by_channel"].values()) == out["swap_out"]


# --------------------------------------------------------------------------- score cutoffs
SIMAH = {"type": "cutoff", "field": "simahcreditscore", "from": 600}


def test_lowering_a_cutoff_loosens_and_matches_the_sweep(engine, inv):
    ladder = engine.simulate([{**SIMAH, "to": 580}])
    out = ladder["result"]
    assert ladder["steps"][0]["change_direction"] == "loosen"
    assert out["swap_in"] > 0 and out["swap_out"] == 0
    curve = S.sweep(engine.base, inv, "simahcreditscore", 600, [580],
                    product=engine.base.cfg["product"])
    assert out["swap_in"] == int(curve.iloc[0]["swap_in"])


def test_raising_a_cutoff_tightens_and_declines_people_approved_today(engine):
    out = engine.simulate([{**SIMAH, "to": 640}])
    assert out["steps"][0]["change_direction"] == "tighten"
    # Mostly swap-outs; a rule written the other way round can still release the odd applicant.
    assert out["result"]["swap_out"] > out["result"]["swap_in"]


def test_a_cutoff_stacks_with_rule_changes(engine):
    top = engine.rules()[0]["rule_id"]
    out = engine.simulate([{"type": "off", "rule_id": top}, {**SIMAH, "to": 560}])
    assert len(out["steps"]) == 2
    assert out["result"]["swap_in"] >= out["steps"][0]["swap_in"]


def test_health_lists_the_cutoff_sliders(engine):
    h = engine.health()
    assert {c["field"] for c in h["cutoffs"]} == {"simahcreditscore", "crifscore"}
    for c in h["cutoffs"]:
        assert c["from"] in c["values"]


def test_goal_seek_options_come_back_as_changes_the_simulator_accepts(engine):
    out = engine.goal_seek(target=engine.base.approval_rate + 0.01)
    best = out["options"][0]
    assert best["changes"]
    again = engine.simulate(best["changes"])["result"]
    assert again["approval_rate"] == pytest.approx(best["approval_rate"], abs=1e-4)


@pytest.mark.parametrize("changes, match", [
    ([{**SIMAH, "to": 600}], "already at"),
    ([{"type": "cutoff", "field": "simahcreditscore"}], "needs a field"),
    ([{**SIMAH, "to": 580}, {**SIMAH, "to": 570}], "appears twice"),
    ([{"type": "cutoff", "field": "simahcreditscore", "from": 1, "to": 2}], "no .* rule tests"),
    ([], "at least one"),
    ("off", "must be a list"),
    ([{"type": "delete", "rule_id": "x"}], "unknown change type"),
    ([{"type": "off", "rule_id": "nope#1"}], "not a rule"),
    ([{"type": "threshold", "rule_id": "racAndPolicies#028", "field": "income",
       "value_low": "lots"}], "not a number"),
    ([{"type": "off", "rule_id": "racAndPolicies#012"}] * 2, "appears twice"),
    ([{"type": "threshold", "rule_id": "racAndPolicies#028", "field": "income", "value_low": 4000},
      {"type": "off", "rule_id": "racAndPolicies#028"}], "appears twice"),
    ([{"type": "off", "rule_id": "racAndPolicies#012"}] * (API.MAX_CHANGES + 1), "at most"),
])
def test_bad_requests_are_refused_in_words(engine, changes, match):
    with pytest.raises(API.ApiError, match=match):
        engine.simulate(changes)


def test_a_fixed_rule_is_refused_by_the_api_too(engine):
    fixed = next(r for r in engine.rules() if r["fixed_field"])
    with pytest.raises(API.ApiError, match="fixed field"):
        engine.simulate([{"type": "off", "rule_id": fixed["rule_id"]}])


# --------------------------------------------------------------------------- goal-seek
def test_goal_seek_takes_the_persons_target_and_ceiling(engine):
    today = engine.base.approval_rate
    out = engine.goal_seek(target=round(100 * today + 1, 1), ceiling=12)
    assert out["target"] == pytest.approx(today + 0.01, abs=1e-3)
    assert out["ceiling"] == pytest.approx(0.12)
    assert out["options"]
    json.dumps(out, allow_nan=False)


@pytest.mark.parametrize("target, ceiling, match", [
    (None, None, "give a target"),
    (0.01, None, "above today"),
    (1.5, None, "above today"),            # 150% once read as a percentage
    (0.5, 0, "between 0% and 100%"),
])
def test_goal_seek_refuses_targets_that_make_no_sense(engine, target, ceiling, match):
    with pytest.raises(API.ApiError, match=match):
        engine.goal_seek(target=target, ceiling=ceiling)


def test_goal_seek_never_touches_a_frozen_rule(engine):
    top = engine.rules()[0]["rule_id"]
    out = engine.goal_seek(target=engine.base.approval_rate + 0.02, frozen=[top])
    assert out["frozen"] == [top]
    for o in out["options"]:
        assert top not in o["option"]


# --------------------------------------------------------------------------- HTTP
@pytest.fixture(scope="module")
def server(engine):
    import functools
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


def test_http_routes_reach_the_engine_and_errors_come_back_as_400(server):
    status, health = _call(server + "/api/health")
    assert status == 200 and health["ready"] is True
    assert health["goal_search"]["max_rule_candidates"] >= 1
    status, rules = _call(server + "/api/rules")
    assert status == 200 and len(rules["rules"]) > 8
    status, out = _call(server + "/api/simulate",
                        {"changes": [{"type": "off", "rule_id": "racAndPolicies#012"}]})
    assert status == 200 and out["result"]["swap_in"] > 0
    status, err = _call(server + "/api/simulate", {"changes": []})
    assert status == 400 and "at least one" in err["error"]
    status, err = _call(server + "/api/nothing")
    assert status == 404


def test_the_static_pages_are_still_served(server):
    with urllib.request.urlopen(server + "/client.html", timeout=10) as r:
        assert r.status == 200
