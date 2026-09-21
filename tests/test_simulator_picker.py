"""Simulator → All rules as a picker (TODO C2).

The list names each rule and its state and carries no controls; the detail, opened by clicking
a row, says what the rule declines in words and holds the switch and the threshold editor. The
words come from the engine, built from the same parsed conditions the replay evaluates.
"""
import re
from pathlib import Path

import pandas as pd
import pytest

from src import client_analysis as A, client_api as API, client_simulate as S
from src.client_generate import generate, load_client_config
from src.rule_inventory import build_inventory

REPO = Path(__file__).resolve().parents[1]
UI = REPO / "ui"
HAS_RULES = bool(list(REPO.glob("business-rules-*.xlsx")))
needs_rules = pytest.mark.skipif(not HAS_RULES, reason="client rule files not present")


def _cond(**kw):
    base = {"rule_id": "t#1", "table": "t", "field": "x", "operator": "lt", "value_low": None,
            "value_high": None, "value_set": None, "tunability": "tunable", "raw": "", "note": ""}
    return {**base, **kw}


def test_a_rule_reads_as_a_sentence_with_its_scope_apart():
    c = pd.DataFrame([
        _cond(field="simahcreditscore", operator="lte", value_low=650.0),
        _cond(field="crifscore", operator="lt", value_low=570.0),
        _cond(field="customersegment", operator="in", value_set="ST|SMG|PVTL", tunability="scope"),
        _cond(field="age", operator="outside", value_low=20.0, value_high=70.0, tunability="fixed"),
    ])
    s = A.rule_sentence(c, "t#1", {"simahcreditscore": "SIMAH score", "customersegment": "customer segment"})
    assert s["when"] == "SIMAH score is 650 or below and crifscore is below 570 and age is outside 20–70"
    assert s["applies_to"] == "customer segment is ST, SMG or PVTL"
    assert A.rule_sentence(c, "other#1") == {"when": None, "applies_to": None}


def test_a_calculated_field_is_not_passed_off_as_a_name():
    c = pd.DataFrame([_cond(field="count(simahtransform[item.a-item.b != 0]) > 0", operator="eq",
                            value_set="true")])
    assert A.rule_sentence(c, "t#1")["when"].startswith("a calculated condition holds")


@needs_rules
def test_the_catalogue_carries_the_stage_and_the_sentence():
    cfg = load_client_config(overrides={"n_rows": 20_000})
    inv = build_inventory(REPO)
    base = S.build_baseline(generate(cfg), inv, cfg, window={})
    rows = API.rule_catalogue(base, inv)
    stages = A.funnel_layout(base.cfg)["stages"]
    for r in rows:
        assert r["stage_label"] == stages[r["stage"]]["label"], r["rule_id"]
        assert set(r["sentence"]) == {"when", "applies_to"}
        assert r["editable"] or r["reason"], f"{r['rule_id']} is locked without a reason"
    # Every rule the replay can evaluate says what it declines.
    assert all(r["sentence"]["when"] for r in rows if r["tests"])


# --------------------------------------------------------------------------- screen
def _code(name):
    text = (UI / name).read_text(encoding="utf-8")
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def _fn(js, name):
    start = js.index("function " + name + "(")
    return js[start:js.index("\n  function ", start + 1)]


def test_the_rows_carry_no_controls():
    row = _fn(_code("client.js"), "ruleRow")
    assert "data-sim-pick" in row
    row_only = row[:row.index("ruleDetailBody")]
    for control in ("<input", "data-sim-rule", "data-sim-apply", "data-sim-edit", "btn"):
        assert control not in row_only, f"a row carries {control}"


def test_the_list_opens_on_rules_that_stop_someone_grouped_by_stage():
    js = _code("client.js")
    assert re.search(r"filter: 'alone'", js), "the default filter is 'Stops someone on its own'"
    panel = _fn(js, "rulesPanel")
    assert "stageGroups(" in panel and "<details" in panel
    assert "stage_label" in _fn(js, "stageGroups")


def test_a_locked_rule_shows_the_lock_and_the_reason_and_nothing_else():
    body = _fn(_code("client.js"), "ruleDetailBody")
    locked = body[body.index("if (st.id === 'locked')"):body.index("var d = driverFor")]
    assert "r.reason" in locked and "return" in locked
    for control in ("data-sim-rule", "data-sim-apply", "<input"):
        assert control not in locked
    # The switch and the editor come after the locked branch has returned.
    assert body.index("data-sim-rule") > body.index("if (st.id === 'locked')")
    assert "Add to scenario" in _fn(_code("client.js"), "thresholdEditor")
