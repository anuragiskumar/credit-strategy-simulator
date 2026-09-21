"""Saved scenarios (TODO B4) and export (TODO B3).

A saved scenario keeps the engine's own answer, re-run at save time, and who saved it and when.
Comparing re-runs each one and says when the answer has moved since. Deleting keeps the record.
Export writes what the engine produced: CSV from the payload, never scraped from the screen, and
a print pack that carries the context and the provenance of every figure.
"""
import json
import re
import threading
from pathlib import Path

import pytest

from src import client_api as API, client_scenarios as SC, client_simulate as S
from src.client_generate import generate, load_client_config
from src.rule_inventory import build_inventory

REPO = Path(__file__).resolve().parents[1]
UI = REPO / "ui"
HAS_RULES = bool(list(REPO.glob("business-rules-*.xlsx")))
needs_rules = pytest.mark.skipif(not HAS_RULES, reason="client rule files not present")

OFF = [{"type": "off", "rule_id": "racAndPolicies#012"}]


# --------------------------------------------------------------------------- the store
def _record(name, product="TWQR"):
    return {"name": name, "product": product, "window": {}, "changes": OFF, "steps": [],
            "outcome": {}, "saved_by": "Analyst"}


def test_the_store_names_dates_and_keeps_a_deleted_scenario(tmp_path):
    store = SC.ScenarioStore(tmp_path / "s.json")
    a = store.add(_record("Loosen age"))
    assert a["id"] and a["saved_at"].endswith("Z") and a["saved_by"] == "Analyst"
    with pytest.raises(SC.ScenarioError, match="already called “Loosen age”"):
        store.add(_record("  LOOSEN AGE "))
    store.add(_record("Loosen age", product="IJMB"))          # names are unique per product
    with pytest.raises(SC.ScenarioError, match="name"):
        store.add(_record("   "))
    store.delete(a["id"], "Approver")
    assert [r["product"] for r in store.list()] == ["IJMB"]
    kept = json.loads((tmp_path / "s.json").read_text())["scenarios"]
    gone = next(r for r in kept if r["id"] == a["id"])
    assert gone["deleted_by"] == "Approver" and gone["deleted_at"]
    store.add(_record("Loosen age"))                         # the name is free again
    with pytest.raises(SC.ScenarioError) as e:
        store.get(a["id"])
    assert e.value.status == 404


def test_a_damaged_store_is_refused_in_words(tmp_path):
    (tmp_path / "s.json").write_text("{not json")
    with pytest.raises(SC.ScenarioError, match="damaged"):
        SC.ScenarioStore(tmp_path / "s.json").list()


def test_drift_names_what_moved():
    saved = {"approval_rate": 0.25, "expected_bad_rate": 0.08, "risk_known": True, "swap_in": 10, "swap_out": 0}
    assert SC.drift(saved, dict(saved)) == []
    assert SC.drift(saved, {**saved, "approval_rate": 0.26, "swap_in": 11}) == ["approval rate", "who moves"]
    assert SC.drift(saved, {**saved, "risk_known": False}) == ["bad rate"]


# --------------------------------------------------------------------------- the engine
@pytest.fixture(scope="module")
def engine(tmp_path_factory):
    cfg = load_client_config(overrides={"n_rows": 20_000})
    inv = build_inventory(REPO)
    store = SC.ScenarioStore(tmp_path_factory.mktemp("scenarios") / "scenarios.json")
    return API.Engine(base=S.build_baseline(generate(cfg), inv, cfg), inv=inv, store=store)


@needs_rules
def test_saving_keeps_the_engines_answer_not_the_pages(engine):
    sc = engine.save_scenario({"name": "Switch off 012", "changes": OFF, "who": "Analyst",
                               # whatever the page claims is ignored: the engine re-runs it
                               "outcome": {"approval_rate": 0.99}})
    run = engine.simulate(OFF)["result"]
    assert sc["outcome"] == SC.outcome(run)
    assert sc["steps"][0]["text"].startswith("Switch off “") and "#012" not in sc["steps"][0]["text"]
    assert sc["steps"][0]["added_swap_in"] == run["swap_in"]
    assert sc["saved_by"] == "Analyst" and sc["product"] == engine.base.cfg["product"]
    with pytest.raises(API.ApiError, match="add at least one change"):
        engine.save_scenario({"name": "Empty", "changes": []})


@needs_rules
def test_compare_re_runs_each_scenario_and_flags_what_moved(engine):
    a = engine.save_scenario({"name": "A", "changes": OFF})
    b = engine.save_scenario({"name": "B", "changes": [{"type": "cutoff", "field": "simahcreditscore",
                                                        "from": 600, "to": 580}]})
    out = engine.compare_scenarios([a["id"], b["id"]])
    assert out["same_context"] is True
    assert [r["drift"] for r in out["scenarios"]] == [[], []]
    assert out["scenarios"][0]["now"] == a["outcome"]
    # A scenario whose saved answer no longer matches (new data, a new rule pack) says so.
    path = engine.store.path
    rows = json.loads(path.read_text())
    for r in rows["scenarios"]:
        if r["id"] == a["id"]:
            r["outcome"]["approval_rate"] = 0.01
    path.write_text(json.dumps(rows))
    moved = engine.compare_scenarios([a["id"], b["id"]])["scenarios"][0]
    assert moved["drift"] == ["approval rate"]
    with pytest.raises(API.ApiError, match="between 2 and"):
        engine.compare_scenarios([a["id"]])


@needs_rules
def test_the_scenario_routes_answer_over_http(engine):
    import functools
    import urllib.request
    from ui import serve
    serve.ENGINE.update(engine=engine, error=None, loading=False)
    srv = serve.Server(("127.0.0.1", 0), functools.partial(serve.Handler, directory=str(serve.HERE)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}"

    def call(path, body=None):
        req = urllib.request.Request(url + path, data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())
    try:
        status, sc = call("/api/scenarios", {"name": "Over HTTP", "changes": OFF, "who": "Analyst"})
        assert status == 200
        status, listing = call("/api/scenarios")
        assert status == 200 and listing["compare_max"] >= 2
        assert sc["id"] in [s["id"] for s in listing["scenarios"]]
        assert call("/api/scenarios", {"name": "over http", "changes": OFF})[0] == 409
        assert call("/api/scenarios/delete", {"id": sc["id"], "who": "Analyst"})[0] == 200
        assert call("/api/scenarios/delete", {"id": sc["id"]})[0] == 404
    finally:
        srv.shutdown()
        serve.ENGINE.update(engine=None)


# --------------------------------------------------------------------------- the page
def _code(name):
    return re.sub(r"/\*.*?\*/", "", (UI / name).read_text(encoding="utf-8"), flags=re.S)


def _fn(js, name):
    start = js.index("function " + name + "(")
    return js[start:js.index("\n  function ", start + 1)]


def test_every_table_on_the_screens_offers_a_csv():
    js = _code("client.js")
    spec = _fn(js, "csvSpec")
    ids = re.findall(r"case '([\w-]+)':", spec)
    for id_ in ids:
        assert re.search(r"csvBtn\('" + re.escape(id_) + r"['(:]", js), f"no button for the {id_} CSV"
    # Every table the screens draw with the shared helper sits in a panel with a CSV button.
    for fn in ("pagePortfolio", "sourcePanel", "drLosses", "drGroups", "rulesPanel", "sweepPanels", "outcomeDetails"):
        assert "csvBtn(" in _fn(js, fn), fn


def test_the_csv_comes_from_the_payload_and_marks_estimates():
    js = _code("client.js")
    spec = _fn(js, "csvSpec")
    assert "querySelector" not in spec and "innerText" not in spec, "a CSV scraped from the screen"
    assert "est_bad_rate_if_relaxed: INF" in spec and "expected_bad_rate: INF" in spec
    to_csv = _fn(js, "toCsv")
    assert "' [' + prov[k] + ']'" in to_csv and "\\ufeff" in to_csv


def test_the_print_pack_carries_context_and_provenance():
    js = _code("client.js")
    pack = _fn(js, "printPack")
    assert "packKey()" in pack
    for fn in ("printScenario", "printGoalOption", "printComparison"):
        assert "packContext(" in _fn(js, fn), fn
    ctx = _fn(js, "packContext")
    for fact in ("Applications replayed", "Bad rate observed on", "Bad-rate limit", "Prepared", "synthetic"):
        assert fact in ctx, fact
    css = (UI / "client.css").read_text(encoding="utf-8")
    assert "@media print" in css and "#printpack" in css


def test_saved_scenarios_live_in_the_engine_not_the_browser():
    js = _code("client.js")
    for fn in ("loadSaved", "saveScenario", "runCompare", "deleteSaved"):
        body = _fn(js, fn)
        assert "api('/api/scenarios" in body, fn
        assert "localStorage" not in body, fn
    assert "Session.who()" in _fn(js, "saveScenario")
