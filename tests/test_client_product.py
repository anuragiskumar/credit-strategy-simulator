"""Product as part of the analysis context (TODO B1).

The brief covers TWQR and IJMB. Each product's applicants are replayed under that product's own
rules, and a request names the product the same way it names the window.
"""
from pathlib import Path

import pandas as pd
import pytest

from src import client_api as API, client_context as C, client_replay, client_simulate as S
from src.client_generate import generate, generate_file, load_client_config
from src.rule_inventory import build_inventory

REPO = Path(__file__).resolve().parents[1]
HAS_RULES = bool(list(REPO.glob("business-rules-*.xlsx")))
pytestmark = pytest.mark.skipif(not HAS_RULES, reason="client rule files not present")

OFF = [{"type": "off", "rule_id": "racAndPolicies#012"}]


@pytest.fixture(scope="module")
def cfg():
    c = load_client_config(overrides={"n_rows": 20_000})
    c["generate_products"] = {"IJMB": {"n_rows": 12_000, "seed": 20260921}}
    return {**c, "optimise": {**c["optimise"], "beam_width": 2, "max_depth": 2,
                              "max_rule_candidates": 4, "field_moves": []}}


@pytest.fixture(scope="module")
def df(cfg):
    return generate_file(cfg)


@pytest.fixture(scope="module")
def engine(df, cfg):
    cache = C.ContextCache(df, build_inventory(REPO), cfg)
    return API.Engine(base=cache.baseline(), inv=cache.inv, cache=cache)


# --------------------------------------------------------------------------- the data
def test_the_file_carries_one_block_per_product(df):
    assert df["product"].value_counts().to_dict() == {"TWQR": 20_000, "IJMB": 12_000}
    assert df["application_id"].is_unique


def test_adding_a_product_leaves_the_default_products_applicants_untouched(df, cfg):
    alone = generate(cfg)
    twqr = df[df["product"] == "TWQR"].reset_index(drop=True)
    pd.testing.assert_frame_equal(twqr, alone)


def test_each_block_is_booked_by_its_own_products_rules(df, cfg, engine):
    ijmb = engine.cache.full("IJMB")
    assert (ijmb.df["product"] == "IJMB").all()
    base = engine.baseline(window={}, product="IJMB")
    booked = base.outcome["booked"]
    # Every IJMB applicant with a booking date was booked by the IJMB replay (the last
    # fortnight's approvals are booked after the extract, so the converse need not hold).
    dated = ijmb.df["booking_date"].notna()
    assert booked[dated[dated].index].all()


# --------------------------------------------------------------------------- the engine
def test_the_replay_only_sees_the_products_applicants_and_rules(engine, cfg):
    twqr, ijmb = engine.cache.full("TWQR"), engine.cache.full("IJMB")
    assert len(twqr.df) == 20_000 and len(ijmb.df) == 12_000
    compiled = client_replay.compile_rules(engine.inv, product="IJMB")
    assert set(ijmb.res.compiled) == {c.rule_id for c in compiled}
    assert set(ijmb.res.compiled) != set(twqr.res.compiled)


def test_the_products_on_offer_are_those_configured_and_present(engine):
    assert engine.cache.products() == ["TWQR", "IJMB"]
    h = engine.health()
    assert h["products"] == ["TWQR", "IJMB"] and h["default_product"] == "TWQR"


def test_a_request_for_a_product_runs_on_that_product(engine):
    twqr, ijmb = engine.health(), engine.health(product="IJMB")
    assert ijmb["product"] == "IJMB"
    assert ijmb["applicants"] < twqr["applicants"]
    assert ijmb["approval_rate"] != twqr["approval_rate"]
    out = engine.simulate([{"type": "off", "rule_id": "yknBasicCheckValidation#016"}],
                          product="IJMB")
    assert out["product"] == "IJMB" and out["window"]["applicants"] == ijmb["applicants"]


def test_the_rule_list_is_the_products_own(engine):
    ijmb = {r["rule_id"] for r in engine.rules(product="IJMB")}
    twqr = {r["rule_id"] for r in engine.rules()}
    assert ijmb and ijmb != twqr


def test_product_and_window_together_pick_the_baseline(engine):
    six = next(p for p in engine.health(product="IJMB")["window_presets"] if p["id"] == "last_6m")
    a = engine.baseline(six, "IJMB")
    b = engine.baseline(six, "TWQR")
    assert a is not b
    assert a.cfg["product"] == "IJMB" and b.cfg["product"] == "TWQR"
    assert engine.baseline(six, "IJMB") is a


@pytest.mark.parametrize("product, match", [
    ("MURABAHA", "no MURABAHA applications"),
    (42, "product code"),
])
def test_a_product_the_data_does_not_carry_is_refused_in_words(engine, product, match):
    with pytest.raises(API.ApiError, match=match):
        engine.simulate(OFF, product=product)
