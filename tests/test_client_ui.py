"""The three CxO screens and the fixture behind them (step 5).

The rule these enforce is the one the prototype's README states: the UI computes nothing.
Every figure comes from `ui/client_export.py`, which calls the same engine functions the tests
call, so a screen cannot quietly disagree with the engine.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from src import client_analysis as A, client_simulate as S
from src.client_generate import generate, load_client_config
from src.rule_inventory import build_inventory
from ui import client_export

REPO = Path(__file__).resolve().parents[1]
UI = REPO / "ui"
HAS_RULES = bool(list(REPO.glob("business-rules-*.xlsx")))
FIXTURE = UI / "client_fixture.json"

PROVENANCE = {"OBSERVED", "PREDICTED", "INFERRED", "NOT_MODELLED", "BLENDED"}


# --------------------------------------------------------------------------- static files
def test_the_three_screens_ship_with_the_shared_design_system():
    for name in ("client.html", "client.css", "client.js"):
        assert (UI / name).exists(), name
    html = (UI / "client.html").read_text(encoding="utf-8")
    assert 'href="tokens.css"' in html, "must reuse the one design system, not a copy"
    assert 'src="client_data.js"' in html and 'src="client.js"' in html


def test_both_pages_declare_a_viewport_so_the_responsive_css_applies():
    """tokens.css carries mobile rules that never fire without this."""
    for name in ("index.html", "client.html"):
        assert 'name="viewport"' in (UI / name).read_text(encoding="utf-8"), name


def test_the_rail_toggle_uses_the_class_the_stylesheet_reveals():
    """Regression: the button toggled `open` while tokens.css reveals on `is-open`."""
    css = (UI / "tokens.css").read_text(encoding="utf-8")
    js = (UI / "client.js").read_text(encoding="utf-8")
    assert ".rail.is-open" in css
    assert "classList.toggle('open')" not in js
    assert "is-open" in js


def test_the_page_uses_only_the_four_provenance_kinds():
    js = (UI / "client.js").read_text(encoding="utf-8")
    used = set(re.findall(r"pv\('([A-Z_]+)'", js))
    assert used <= PROVENANCE, f"unexpected provenance kinds: {used - PROVENANCE}"
    assert {"OBSERVED", "INFERRED", "NOT_MODELLED"} <= used


def test_the_page_never_derives_a_rate_from_two_fixture_fields():
    """The UI computes nothing: every rate is exported, never divided out on the page.

    Checked narrowly — one fixture field divided by another — because that is the mistake
    that makes a screen disagree with the CLI. Formatting arithmetic (a percentage, a bar
    width, a thousands separator) is fine and is what the helpers at the top do.
    """
    js = (UI / "client.js").read_text(encoding="utf-8")
    body = "\n".join(line for line in js.splitlines()
                      if not line.strip().startswith(("*", "//", "/*")))
    derived = re.findall(r"\b(?:F|r|o|t|g|v)\.\w+\s*/\s*(?:F|r|o|t|g|v)\.\w+", body)
    assert not derived, f"the page is deriving a figure: {derived}"


@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture not built")
def test_the_fixture_supplies_every_rate_the_screens_show():
    """If a rate were missing the page would have to work it out, which is the rule broken."""
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert {"approval_rate", "booked_bad_rate"} <= set(data["headline"])
    assert {"left_pct", "dropped", "left"} <= set(data["funnel"][0])
    assert {"approval_rate", "share_of_all_declines"} <= set(data["by_channel"][0])
    assert {"share_of_exposure", "bad_rate"} <= set(
        data["portfolio"]["employer_segment"]["rows"][0])
    assert {"declines", "declines_alone", "sole_reason_pct"} <= set(data["drivers"][0])
    if data["rule_toggles"]:
        assert {"approval_change_pp", "expected_bad_rate"} <= set(data["rule_toggles"][0])
    if data["goal_seek"]:
        assert {"risk_cost_pp", "approval_change_pp"} <= set(data["goal_seek"][0]["options"][0])


# --------------------------------------------------------------------------- fixture shape
@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture not built")
def test_the_exported_fixture_has_every_key_the_screens_read():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for key in ("meta", "headline", "funnel", "by_channel", "portfolio", "drivers",
                "model", "sweeps", "rule_toggles", "goal_seek"):
        assert key in data, key
    for slice_name in ("employer_segment", "sector", "channel", "score_band", "nationality"):
        assert slice_name in data["portfolio"], slice_name
        assert data["portfolio"][slice_name]["rows"]


@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture not built")
def test_the_fixture_says_out_loud_that_the_applicants_are_synthetic():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert data["meta"]["synthetic"] is True
    html = (UI / "client.html").read_text(encoding="utf-8")
    assert "SYNTHETIC" in html


@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture not built")
def test_the_fixture_records_the_replay_decisions_it_depends_on():
    """Evaluation order and the missing-value rule are decisions, not facts about the client."""
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    decisions = data["meta"]["replay_decisions"]
    assert "condition_on_missing_value_matches" in decisions
    assert "no_rule_matched" in decisions
    assert "stage_by_table" in decisions


@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture not built")
def test_no_nan_or_infinity_reaches_the_page():
    """JSON NaN would crash the page; a silent 0 would be worse."""
    raw = FIXTURE.read_text(encoding="utf-8")
    assert "NaN" not in raw and "Infinity" not in raw


@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture not built")
def test_every_unpriced_scenario_carries_no_number():
    """`risk_known: false` must never ship an estimate alongside it."""
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for t in data["rule_toggles"]:
        if not t["risk_known"]:
            assert t["expected_bad_rate"] is None, t["rule_id"]
    for sweep in data["sweeps"]:
        for row in sweep["rows"]:
            if not row["risk_known"]:
                assert row["expected_bad_rate"] is None


@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture not built")
def test_goal_seek_options_are_present_and_flagged():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert data["goal_seek"]
    for run in data["goal_seek"]:
        assert "reached" in run and "ceiling" in run
        for option in run["options"]:
            assert {"approval_rate", "breaches_ceiling", "reaches_target"} <= set(option)


@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture not built")
def test_data_js_matches_the_json_fixture():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    js = (UI / "client_data.js").read_text(encoding="utf-8")
    assert js.startswith("window.__CLIENT__ = ")
    assert json.loads(js[len("window.__CLIENT__ = "):].rstrip().rstrip(";")) == data


# --------------------------------------------------------------------------- agreement
@pytest.mark.skipif(not HAS_RULES, reason="client rule files not present")
def test_the_export_agrees_with_the_engine():
    """The screens must show what `decline_drivers` returns, not a second opinion."""
    cfg = load_client_config(overrides={"n_rows": 20_000})
    inv = build_inventory(REPO)
    df = generate(cfg)
    base = S.build_baseline(df, inv, cfg)
    drivers = A.decline_drivers(df, base.res, base.outcome, cfg, model=base.model)
    funnel = A.funnel(df, base.outcome)

    top = drivers.iloc[0]
    assert top["declines_alone"] <= top["declines"]
    assert funnel.iloc[0]["left"] == len(df)
    assert round(base.approval_rate, 4) == round(float(base.outcome["booked"].mean()), 4)


def test_clean_turns_unrepresentable_numbers_into_null():
    """A NaN would break the JSON; a 0 in its place would be a lie on a CxO screen."""
    assert client_export.clean(float("nan")) is None
    assert client_export.clean({"a": float("inf")}) == {"a": None}


def test_clean_keeps_numbers_as_numbers():
    """Regression: counts shipped as strings, and only rendered because JS coerces them."""
    assert client_export.clean([1, 2.5, "x", None]) == [1, 2.5, "x", None]
    assert client_export.clean(True) is True and client_export.clean(False) is False
    assert isinstance(client_export.clean(7), int)


@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture not built")
def test_no_figure_is_shipped_as_a_string():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    numeric_as_text = []

    def walk(node, path=""):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{path}/{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")
        elif isinstance(node, str):
            try:
                float(node)
            except ValueError:
                return
            numeric_as_text.append((path, node))

    walk(data)
    assert not numeric_as_text, f"{len(numeric_as_text)} numbers shipped as strings, " \
                                f"e.g. {numeric_as_text[:3]}"


# --------------------------------------------------------------------------- spec notes
def _note_keys_used() -> set[str]:
    """Every key a screen tags with N('key') or a literal data-note="key"."""
    used: set[str] = set()
    for name in ("client.js", "client.html"):
        text = (UI / name).read_text(encoding="utf-8")
        used |= set(re.findall(r"\bN\('([a-z0-9_]+)'\)", text))
        used |= set(re.findall(r'data-note="([a-z0-9_]+)"', text))
    return used


def _note_keys_defined() -> set[str]:
    """Top-level entries of the object client_notes.js returns (four-space indent)."""
    text = (UI / "client_notes.js").read_text(encoding="utf-8")
    return set(re.findall(r"^    ([a-z0-9_]+): \{", text, re.M))


def test_spec_notes_are_off_by_default_and_toggled_by_an_icon_beside_the_theme_button():
    html = (UI / "client.html").read_text(encoding="utf-8")
    assert 'id="specbtn"' in html and 'aria-pressed="false"' in html
    assert html.index('id="specbtn"') < html.index('id="themebtn"'), "icon sits next to the theme switch"
    assert 'src="client_notes.js"' in html
    # Nothing numbered or footnoted is in the static page; it only exists once the icon is pressed.
    assert "specnum" not in html and "specnotes" not in html
    js = (UI / "client.js").read_text(encoding="utf-8")
    assert "spec: false" in js, "the default must be hidden"


def test_every_tagged_element_has_a_note_and_no_note_is_orphaned():
    used, defined = _note_keys_used(), _note_keys_defined()
    assert used, "no element is tagged with a spec note"
    assert not used - defined, f"tagged but no note text: {sorted(used - defined)}"
    # stage_* keys are built at runtime from the funnel stage names, so they are checked below.
    orphans = {k for k in defined - used if not k.startswith("stage_")}
    assert not orphans, f"note text that nothing on screen points to: {sorted(orphans)}"


@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture not built")
def test_every_funnel_stage_has_a_note():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    missing = {f"stage_{r['stage']}" for r in data["funnel"]} - _note_keys_defined()
    assert not missing, f"funnel stages with no spec note: {sorted(missing)}"


def test_spec_note_badges_use_ink_not_a_provenance_colour():
    """Colour encodes provenance and nothing else, so the numbering must stay neutral."""
    css = (UI / "client.css").read_text(encoding="utf-8")
    badge = re.search(r"^\.specnum \{(.*?)\}", css, re.S | re.M)
    assert badge, ".specnum rule missing"
    assert "var(--ink)" in badge.group(1)
    assert not re.search(r"var\(--(obs|pred|inf|nm|warn|breach)\b", badge.group(1))


def test_the_notes_file_is_text_only():
    """It explains the screens; it must not compute figures or reach for the network."""
    text = (UI / "client_notes.js").read_text(encoding="utf-8")
    assert "fetch(" not in text and "XMLHttpRequest" not in text
    body = "\n".join(l for l in text.splitlines() if not l.strip().startswith(("*", "//", "/*")))
    assert not re.findall(r"\bF\.\w+\s*/\s*F\.\w+", body)
