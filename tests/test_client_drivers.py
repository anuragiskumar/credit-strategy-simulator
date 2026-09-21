"""Decline drivers as the diagnosis (TODO C0 and C1).

The engine puts every decline rule in one group and counts what loosening it would book. The
screen draws those groups and computes nothing, and the Simulator's preset reads the same
verdict rather than working the finding out a second time.
"""
import re
from pathlib import Path

import pytest

from src import client_analysis as A, client_simulate as S, client_view as V
from src.client_generate import generate, load_client_config
from src.rule_inventory import build_inventory

REPO = Path(__file__).resolve().parents[1]
UI = REPO / "ui"
HAS_RULES = bool(list(REPO.glob("business-rules-*.xlsx")))
needs_rules = pytest.mark.skipif(not HAS_RULES, reason="client rule files not present")


@pytest.fixture(scope="module")
def setup():
    cfg = load_client_config(overrides={"n_rows": 20_000})
    inv = build_inventory(REPO)
    base = S.build_baseline(generate(cfg), inv, cfg, window={})
    drivers = A.decline_drivers(base.df, base.res, base.outcome, base.cfg, model=base.model,
                                booked_bad_rate=base.booked_bad_rate)
    return base, inv, drivers


# --------------------------------------------------------------------------- engine
@needs_rules
def test_every_rule_gets_exactly_one_verdict(setup):
    _, _, drivers = setup
    assert set(drivers["verdict"]) <= set(A.VERDICTS)
    assert (drivers.loc[~drivers["relaxable"], "verdict"] == "not_relaxable").all()
    relax = drivers[drivers["relaxable"]]
    assert (relax.loc[relax["declines_alone"] == 0, "verdict"] == "overlap").all()
    review = drivers[drivers["verdict"] == "review"]
    assert (review["earns_its_place"] == False).all() and review["risk_known"].all()  # noqa: E712


@needs_rules
def test_approvals_gained_is_what_switching_the_rule_off_books(setup):
    """The one-pass count must equal a full replay of each rule switched off."""
    base, inv, drivers = setup
    gains = S.driver_gains(base, inv, drivers)
    checked = gains[gains["relaxable"] & (gains["declines_alone"] > 0)].head(12)
    assert len(checked) >= 5
    for r in checked.itertuples():
        out = S.simulate(base, inv, S.rule_lever(r.rule_id, enabled=False))
        assert out["swap_in"] == r.approvals_gained, r.rule_id
        assert r.approvals_gained <= r.declines_alone
    assert gains.loc[~gains["relaxable"], "approvals_gained"].isna().all()


@needs_rules
def test_the_summary_accounts_for_every_rule_and_every_lost_applicant(setup):
    base, inv, drivers = setup
    funnel = A.funnel(base.df, base.outcome)
    rows, summary = V.drivers_view(base, inv, drivers, funnel,
                                   V.clean(A.funnel_rules(base.res, base.outcome, base.cfg,
                                                          conditions=inv.conditions)))
    assert [g["id"] for g in summary["groups"]] == list(A.VERDICTS)
    assert sum(g["rules"] for g in summary["groups"]) == len(rows) == len(drivers)
    # Rows arrive in group order, so the screen never sorts.
    order = [list(A.VERDICTS).index(r["verdict"]) for r in rows]
    assert order == sorted(order)
    lost = sum(l["dropped"] for l in summary["losses"])
    assert lost == len(base.df) - int(base.outcome["booked"].sum())
    assert {l["stage"] for l in summary["losses"]} >= {"hard_reject", "credit_policy", "walked_away"}
    assert summary["threshold"] == pytest.approx(
        base.booked_bad_rate * base.cfg["drivers"]["earns_place_multiple"], abs=1e-6)
    fired = set(drivers["rule_id"])
    never = {r["rule_id"] for r in summary["never_fire"]}
    unevaluated = {r["rule_id"] for r in summary["not_evaluated"]}
    assert not fired & never and not (fired | never) & unevaluated
    # Every decline rule the Simulator lists sits in exactly one group here.
    listed = {rid for rid, c in base.res.compiled.items() if c.kind == "block"}
    assert fired | never | unevaluated == listed


# --------------------------------------------------------------------------- screens
def _code(name):
    text = (UI / name).read_text(encoding="utf-8")
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def test_the_drivers_screen_draws_the_engines_groups_and_judges_nothing():
    js = _code("client.js")
    page = js[js.index("function drTiles"):js.index("function wireDrivers")]
    assert "r.verdict" in page and "F.drivers_summary" in page
    for judged in ("earns_its_place", "risk_known", "declines_alone"):
        assert judged not in page, f"the screen re-derives {judged}"
    assert "data-dr-try" in page, "every judgeable rule links into the Simulator"
    assert "<details" in page, "groups collapse"


def test_the_simulator_preset_reads_the_drivers_verdict_instead_of_recomputing_it():
    js = _code("client.js")
    presets = js[js.index("function presets"):js.index("function presetCards")]
    assert "r.verdict === 'review'" in presets
    assert "rule_toggles" not in presets and "booked_bad_rate" not in presets


def test_rules_that_catch_nobody_are_listed_on_drivers_not_settings():
    assert "never_fire" in _code("client.js")
    settings = _code("settings.js")
    assert "R.never_fire.map" not in settings and "client.html#drivers" in settings
