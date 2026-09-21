"""One context, one answer, whichever way it is asked (TODO A5).

The same product and window must give the same figures through the fixture export (the offline
screens), the live engine (/api/view and /api/health) and the CLI. They share one baseline
builder, and this holds them to it for every precomputed context.
"""
from pathlib import Path

import pytest

from src import client_api as API, client_ask, client_context as C, client_llm
from src.client_generate import generate_file, load_client_config
from src.rule_inventory import build_inventory
from ui import client_export

REPO = Path(__file__).resolve().parents[1]
HAS_RULES = bool(list(REPO.glob("business-rules-*.xlsx")))
pytestmark = pytest.mark.skipif(not HAS_RULES, reason="client rule files not present")


@pytest.fixture(scope="module")
def setup(tmp_path_factory):
    cfg = load_client_config(overrides={"n_rows": 20_000})
    cfg["generate_products"] = {"IJMB": {"n_rows": 12_000, "seed": 20260921}}
    df = generate_file(cfg)
    path = tmp_path_factory.mktemp("consistency") / "applications.parquet"
    df.to_parquet(path, index=False)
    cfg["data_path"] = str(path)
    inv = build_inventory(REPO)
    payload = client_export.build(cfg, inv, quick=True)
    cache = C.ContextCache(df, inv, cfg)
    engine = API.Engine(base=cache.baseline(), inv=inv, cache=cache)
    return cfg, df, inv, payload, engine


def _contexts(payload):
    menu = payload["context_menu"]
    for product, spec in menu["products"].items():
        for preset in spec["presets"]:
            view = payload if preset["context"] == payload["meta"]["context"] \
                else payload["contexts"][preset["context"]]
            yield product, preset, view


def test_the_fixture_carries_every_product_and_preset(setup):
    _, _, _, payload, _ = setup
    ids = [p["context"] for _, p, _ in _contexts(payload)]
    assert ids == ["TWQR:last_6m", "TWQR:last_12m", "TWQR:all",
                   "IJMB:last_6m", "IJMB:last_12m", "IJMB:all"]
    assert payload["meta"]["context"] == payload["context_menu"]["default_context"] == "TWQR:last_12m"


def test_the_engine_serves_what_the_fixture_carries(setup):
    _, _, _, payload, engine = setup
    for product, preset, view in _contexts(payload):
        live = engine.view(preset, product)
        for key in ("headline", "funnel", "funnel_rules", "portfolio", "by_channel"):
            assert live[key] == view[key], (preset["context"], key)
        assert live["meta"]["window"] == view["meta"]["window"], preset["context"]
        h = engine.health(preset, product)
        assert h["approval_rate"] == pytest.approx(view["headline"]["approval_rate"], abs=1e-6)
        assert h["booked_bad_rate"] == pytest.approx(view["headline"]["booked_bad_rate"], abs=1e-6)


def test_the_cli_answers_what_the_screens_show(setup):
    cfg, df, inv, payload, _ = setup
    call = client_llm.EngineCall(intent="approval_rate")
    for product, preset, view in _contexts(payload):
        base = client_ask.load_baseline(df, inv, cfg, product=product,
                                        app_from=preset["app_from"], app_to=preset["app_to"])
        out = client_ask.execute(call, base, inv, base.cfg)
        assert out["approval_rate"] == pytest.approx(view["headline"]["approval_rate"], abs=1e-6)
        assert out["booked"] == view["headline"]["booked"]
        assert out["applicants"] == view["meta"]["applicants"]


def test_goal_targets_sit_above_each_contexts_own_approval_rate(setup):
    _, _, _, payload, _ = setup
    for _, preset, view in _contexts(payload):
        assert min(view["goal_targets"]) > view["headline"]["approval_rate"], preset["context"]


def test_a_products_simulator_only_offers_cutoffs_its_rules_test(setup):
    _, _, _, payload, engine = setup
    assert {c["field"] for c in engine.health(product="TWQR")["cutoffs"]} == \
        {"simahcreditscore", "crifscore"}
    assert {c["field"] for c in engine.health(product="IJMB")["cutoffs"]} == {"simahcreditscore"}
