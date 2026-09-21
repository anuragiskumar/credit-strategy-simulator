"""Governed settings (TODO C3): maker and checker, the approver's switches, and the recompute.

A value a committee owns changes only when one person proposes it and a different person approves
it; the engine refuses the proposer's own approval whatever a screen draws. An approved value
changes no figure until the next recompute, and the screen is told which values are waiting.
"""
import functools
import json
import threading
import urllib.request

import pytest

from src import client_api as API, client_context as C, client_policy as PO
from src.client_generate import generate, load_client_config
from src.rule_inventory import build_inventory

from tests.test_scenarios_export import REPO, needs_rules


@pytest.fixture
def cfg():
    return load_client_config()


@pytest.fixture
def store(tmp_path):
    return PO.PolicyStore(tmp_path / "policy.json")


# --------------------------------------------------------------------------- the store
def test_a_change_needs_a_second_person(store, cfg):
    p = store.propose("bad_rate_ceiling", 0.10, "Tighten after Q2", "Analyst", cfg)
    assert p["status"] == "pending" and p["from"] == cfg["optimise"]["max_bad_rate"] and p["to"] == 0.10
    assert store.effective(cfg)["optimise"]["max_bad_rate"] == cfg["optimise"]["max_bad_rate"], \
        "a proposal changes nothing"
    with pytest.raises(PO.PolicyError, match="second person") as e:
        store.decide(p["id"], True, "Analyst", cfg=cfg)
    assert e.value.status == 403
    done = store.decide(p["id"], True, "Risk approver", cfg=cfg)
    assert done["status"] == "approved" and done["decided_by"] == "Risk approver" and done["decided_at"]
    assert store.effective(cfg)["optimise"]["max_bad_rate"] == 0.10
    with pytest.raises(PO.PolicyError, match="already approved"):
        store.decide(p["id"], False, "Risk approver", cfg=cfg)


def test_the_proposer_may_withdraw_and_anyone_else_reject(store, cfg):
    a = store.propose("riskier_multiple", 1.3, "Stricter label", "Analyst", cfg)
    with pytest.raises(PO.PolicyError, match="already waiting") as e:
        store.propose("riskier_multiple", 1.4, "Again", "Someone else", cfg)
    assert e.value.status == 409
    assert store.decide(a["id"], False, "Analyst")["status"] == "withdrawn"
    b = store.propose("riskier_multiple", 1.4, "Again", "Analyst", cfg)
    assert store.decide(b["id"], False, "Risk approver", note="Not now")["status"] == "rejected"
    assert store.effective(cfg)["simulate"]["riskier_multiple"] == cfg["simulate"]["riskier_multiple"]


@pytest.mark.parametrize("key, to, reason, who, match", [
    ("bad_rate_ceiling", 0.9, "x", "A", "between 1% and 40%"),
    ("bad_rate_ceiling", "ten", "x", "A", "must be a number"),
    ("bad_rate_ceiling", 0.10, "  ", "A", "give a reason"),
    ("bad_rate_ceiling", 0.10, "x", None, "say who"),
    ("bad_rate_ceiling", 0.11, "x", "A", "already 11.0%"),
    ("missing_value_matches", True, "x", "A", "changed by the risk approver directly"),
    ("rule_012", 1, "x", "A", "not a setting"),
])
def test_a_proposal_the_store_refuses_says_why(store, cfg, key, to, reason, who, match):
    with pytest.raises(PO.PolicyError, match=match):
        store.propose(key, to, reason, who, cfg)


def test_a_proposal_overtaken_by_another_change_cannot_be_approved(store, cfg):
    first = store.propose("bad_rate_ceiling", 0.10, "One", "Analyst", cfg)
    store.decide(first["id"], True, "Risk approver", cfg=cfg)
    second = store.propose("bad_rate_ceiling", 0.09, "Two", "Analyst", cfg)
    assert second["from"] == 0.10
    # Someone edits the history (or a second engine approves) so the value moves under it.
    rows = json.loads(store.path.read_text())
    rows["changes"][0]["to"] = 0.12
    store.path.write_text(json.dumps(rows))
    with pytest.raises(PO.PolicyError, match="has changed since") as e:
        store.decide(second["id"], True, "Risk approver", cfg=cfg)
    assert e.value.status == 409


def test_a_replay_assumption_is_changed_directly_and_recorded(store, cfg):
    with pytest.raises(PO.PolicyError, match="proposal"):
        store.change("bad_rate_ceiling", 0.10, "Risk approver", cfg)
    with pytest.raises(PO.PolicyError, match="yes or no"):
        store.change("missing_value_matches", "yes", "Risk approver", cfg)
    r = store.change("missing_value_matches", True, "Risk approver", cfg)
    assert r["status"] == "approved" and r["proposed_by"] == r["decided_by"] == "Risk approver"
    assert store.effective(cfg)["replay"]["condition_on_missing_value_matches"] is True


def test_the_state_says_what_waits_for_a_recompute(store, cfg):
    p = store.propose("bad_rate_ceiling", 0.10, "Tighten", "Analyst", cfg)
    before = store.state(cfg, cfg)
    ceiling = next(s for s in before["settings"] if s["key"] == "bad_rate_ceiling")
    assert ceiling["pending"]["id"] == p["id"] and not ceiling["awaiting_recompute"] and ceiling["approved"] is None
    store.decide(p["id"], True, "Risk approver", cfg=cfg)
    after = store.state(cfg, cfg)                       # the figures were computed before the approval
    ceiling = next(s for s in after["settings"] if s["key"] == "bad_rate_ceiling")
    assert ceiling["value"] == 0.10 and ceiling["applied"] == cfg["optimise"]["max_bad_rate"]
    assert ceiling["awaiting_recompute"] and after["awaiting_recompute"]
    assert ceiling["approved"] == {"by": "Risk approver", "at": ceiling["approved"]["at"], "proposed_by": "Analyst"}
    assert not store.state(cfg, store.effective(cfg))["awaiting_recompute"], "recomputed: nothing waits"
    assert [h["status"] for h in after["history"]] == ["approved"] and after["history"][0]["label"] == "Bad-rate ceiling"


def test_a_damaged_history_is_refused_in_words(store, cfg):
    store.path.write_text("{nope")
    with pytest.raises(PO.PolicyError, match="damaged"):
        store.effective(cfg)


# --------------------------------------------------------------------------- the engine
@pytest.fixture(scope="module")
def engine(tmp_path_factory):
    def load():
        # A small book: with the missing-value switch on, too few loans are booked to fit the
        # model at the configured minimum, and a recompute is refused (tested below).
        cfg = load_client_config(overrides={"n_rows": 20_000})
        cfg["risk_model"] = {**cfg["risk_model"], "min_training_rows": 1000}
        return cfg
    cfg = load()
    inv = build_inventory(REPO)
    policy = PO.PolicyStore(tmp_path_factory.mktemp("policy") / "policy.json")
    cache = C.ContextCache(generate(cfg), inv, cfg)
    return API.Engine(base=cache.baseline(), inv=inv, cache=cache, policy=policy, file_cfg=cfg, load_cfg=load)


@needs_rules
def test_an_approved_ceiling_reaches_the_figures_only_on_recompute(engine):
    was = engine.health()["bad_rate_ceiling"]
    p = engine.propose_setting({"setting": "bad_rate_ceiling", "to": 0.095, "reason": "Committee, 21 Sep", "who": "Analyst"})
    with pytest.raises(API.ApiError, match="second person"):
        engine.decide_setting({"id": p["id"], "approve": True, "who": "Analyst"})
    engine.decide_setting({"id": p["id"], "approve": True, "who": "Risk approver"})
    s = engine.settings()
    assert s["awaiting_recompute"] and engine.health()["bad_rate_ceiling"] == was
    engine.recompute("Analyst", wait=True)
    assert engine.health()["bad_rate_ceiling"] == 0.095
    s = engine.settings()
    assert not s["awaiting_recompute"] and s["recompute"]["by"] == "Analyst" and not s["recompute"]["running"]


@needs_rules
def test_what_a_switch_decides_is_the_same_count_either_way(engine):
    """Flipping a switch and flipping it back moves the same applicants, so the count must match."""
    before = engine.impacts()["missing_value_matches"]
    assert before["changed"] > 0 and before["share"] == round(before["changed"] / engine.impacts()["applicants"], 4)
    engine.change_setting({"setting": "missing_value_matches", "to": True, "who": "Risk approver"})
    assert engine.impacts()["missing_value_matches"] == before, "nothing moves before the recompute"
    engine.recompute("Risk approver", wait=True)
    assert engine.recompute_state["error"] is None
    after = engine.impacts()["missing_value_matches"]
    assert after["changed"] == before["changed"]
    assert after["newly_passed"] == before["newly_declined"] and after["newly_declined"] == before["newly_passed"]


@needs_rules
def test_a_recompute_that_fails_keeps_the_figures_in_use_and_says_why(engine):
    base = engine.base
    real = engine.load_cfg
    engine.load_cfg = lambda: {**real(), "risk_model": {**real()["risk_model"], "min_training_rows": 10**7}}
    try:
        state = engine.recompute("Analyst", wait=True)
    finally:
        engine.load_cfg = real
    assert "WindowError" in state["error"] and not state["running"]
    assert engine.base is base, "the old figures keep answering"
    assert engine.settings()["recompute"]["error"] == state["error"]


def test_an_engine_without_a_history_refuses_settings_changes_in_words():
    eng = API.Engine(base=None, inv=None)
    with pytest.raises(API.ApiError, match="not configured") as e:
        eng.propose_setting({"setting": "bad_rate_ceiling", "to": 0.1})
    assert e.value.status == 501


@needs_rules
def test_the_settings_routes_answer_over_http(engine):
    from ui import serve
    serve.ENGINE.update(engine=engine, error=None, loading=False)
    srv = serve.Server(("127.0.0.1", 0), functools.partial(serve.Handler, directory=str(serve.HERE)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}"

    def call(path, body=None):
        req = urllib.request.Request(url + path, data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())
    try:
        status, s = call("/api/settings?product=" + engine.base.cfg["product"])
        assert status == 200 and {x["key"] for x in s["settings"]} == set(PO.SETTINGS)
        assert s["impacts"]["product"] == engine.base.cfg["product"]
        status, p = call("/api/settings/propose", {"setting": "safer_multiple", "to": 0.8, "reason": "r", "who": "Analyst"})
        assert status == 200
        assert call("/api/settings/decide", {"id": p["id"], "approve": True, "who": "Analyst"})[0] == 403
        assert call("/api/settings/decide", {"id": p["id"], "approve": True, "who": "Risk approver"})[0] == 200
        assert call("/api/settings/change", {"setting": "bad_rate_ceiling", "to": 0.1, "who": "Risk approver"})[0] == 400
        status, r = call("/api/recompute", {"who": "Analyst"})
        assert status == 200 and r["running"]
        assert call("/api/recompute", {"who": "Analyst"})[0] == 409
        while engine.recompute_state["running"]:
            threading.Event().wait(0.2)
        assert engine.recompute_state["error"] is None
    finally:
        srv.shutdown()
        serve.ENGINE.update(engine=None)
