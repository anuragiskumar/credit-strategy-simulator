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
    for name in ("client.js", "client_funnel_model.js"):
        js = (UI / name).read_text(encoding="utf-8")
        body = "\n".join(line for line in js.splitlines()
                          if not line.strip().startswith(("*", "//", "/*")))
        derived = re.findall(r"\b(?:F|r|o|t|g|v|d|s|x)\.\w+\s*/\s*(?:F|r|o|t|g|v|d|s|x)\.\w+", body)
        assert not derived, f"{name} is deriving a figure: {derived}"


def test_no_two_functions_in_the_page_script_share_a_name():
    """Regression: one IIFE holds every screen, so a second `function pts` silently replaced the
    funnel's polygon helper and the Portfolio funnel drew nothing."""
    js = (UI / "client.js").read_text(encoding="utf-8")
    names = re.findall(r"^\s*function (\w+)\(", js, re.M)
    dups = sorted({n for n in names if names.count(n) > 1})
    assert not dups, f"functions declared twice in client.js: {dups}"


def test_the_funnel_model_loads_before_the_page_script():
    html = (UI / "client.html").read_text(encoding="utf-8")
    assert html.index('src="client_funnel_model.js"') < html.index('src="client.js"')


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


@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture not built")
def test_the_simulator_lists_every_decline_rule_not_the_precomputed_eight():
    """Regression: the Switch one rule off panel offered the top 8 rules and nothing else."""
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    catalogue = data["rule_catalogue"]
    assert len(catalogue) > len(data["rule_toggles"])
    ids = {r["rule_id"] for r in catalogue}
    assert {t["rule_id"] for t in data["rule_toggles"]} <= ids
    for r in catalogue:
        assert {"rule_id", "label", "declines_alone", "editable", "reason", "thresholds"} <= set(r)
        assert r["editable"] or r["reason"], r["rule_id"]


def test_the_simulator_falls_back_to_the_fixture_when_the_engine_is_not_running():
    js = (UI / "client.js").read_text(encoding="utf-8")
    assert "/api/health" in js and "engineUnavailable" in js
    assert "F.rule_catalogue" in js


def test_goal_seek_target_is_typed_not_hard_coded_on_the_page():
    js = (UI / "client.js").read_text(encoding="utf-8")
    assert 'id="goaltarget"' in js and 'id="goalceiling"' in js
    assert "/api/goal-seek" in js


# --------------------------------------------------------------------------- fixture shape
@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture not built")
def test_the_exported_fixture_has_every_key_the_screens_read():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for key in ("meta", "headline", "funnel", "by_channel", "portfolio", "drivers",
                "model", "sweeps", "rule_toggles", "goal_seek", "rule_catalogue"):
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


IDENTIFIERS = {"policy_code", "reason_code", "rule_id"}
"""Codes that happen to be digits (IJMB's bureau rules carry codes like "4476"). An identifier is
text: shipping it as a number would drop a leading zero and invite arithmetic on it."""


@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture not built")
def test_no_figure_is_shipped_as_a_string():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    numeric_as_text = []

    def walk(node, path=""):
        if isinstance(node, dict):
            for k, v in node.items():
                if k not in IDENTIFIERS:
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


def test_funnel_losses_are_grey_never_a_hue_or_a_hatch():
    """Colour means provenance and hatching means NOT MODELLED, so a loss can be neither."""
    css = (UI / "client.css").read_text(encoding="utf-8")
    start = css.index("/* ------------------------------------------------------------------ funnel")
    end = css.index("/* ------------------------------------------------------------------ bars in tables */")
    block = css[start:end]
    assert "var(--loss-lender)" in block and "var(--loss-customer)" in block
    # Focus rings use the app-wide focus colour (tokens.css :focus-visible), so focus rules are exempt.
    drawn = "\n".join(line for line in block.splitlines() if "focus" not in line)
    assert not re.search(r"var\(--(breach|inf|pred|warn|nm)\b", drawn), \
        "the funnel may use --obs for still-in and the loss greys, nothing else chromatic"
    assert "repeating-linear-gradient" not in block and "pattern" not in block
    tokens = (UI / "tokens.css").read_text(encoding="utf-8")
    assert tokens.count("--loss-lender:") == 3, "light, dark (media) and dark (data-theme)"


def test_the_funnel_panel_uses_a_true_minus_sign():
    js = (UI / "client.js").read_text(encoding="utf-8")
    model = (UI / "client_funnel_model.js").read_text(encoding="utf-8")
    assert re.search(r"−'\s*\+\s*n0\(s\.lost\)", js)
    assert "'−' + s.lost.toLocaleString" in model
    assert "'-' + n0(" not in js


def test_every_engine_call_from_the_page_carries_the_product_and_period():
    """A call without the context would answer for the default period while the screen shows another."""
    js = (UI / "client.js").read_text(encoding="utf-8")
    calls = re.findall(r"(?:api|apiStream)\('(/api/[a-z-/]+)'([^)]*)", js)
    assert calls, "no engine calls found"
    # A saved scenario carries its own product and period, so listing, comparing and deleting
    # saved scenarios are the calls that must not take the screen's context. Saving one does.
    own_context = {"/api/scenarios/compare", "/api/scenarios/delete"}
    for path, rest in calls:
        if path in own_context or (path == "/api/scenarios" and not rest.strip()):
            continue
        assert "ctxQuery(" in rest or "ctxBody(" in rest, f"{path} is sent without the context"


def test_the_period_and_product_controls_are_in_the_top_bar():
    html = (UI / "client.html").read_text(encoding="utf-8")
    for el in ('id="productchip"', 'id="periodchip"', 'id="ctxmenu"'):
        assert el in html, el


def test_every_analysis_screen_says_how_current_its_data_is():
    """TODO B5: the extract date and when the figures were built, on the period line and in the export."""
    js = (UI / "client.js").read_text(encoding="utf-8")
    period = js[js.index("function periodLine("):js.index("function renderChrome(")]
    assert "asOfText()" in period and "N('as_of')" in period
    pack = js[js.index("function packContext("):js.index("function packOutcome(")]
    assert "asOfText()" in pack and "engine data built" not in pack
    body = js[js.index("function asOfText("):js.index("function defaultMonths(")]
    assert "m.data_as_of" in body and "m.generated" in body


# --------------------------------------------------------------------------- TODO C5
def test_every_slice_value_on_screen_has_a_business_name():
    """C5: "Direct sales agents", not "dsa". Every value the Portfolio table or a channel split
    shows has a name from config, and a score band reads as a range."""
    view = json.loads(FIXTURE.read_text(encoding="utf-8"))
    labels = view["meta"]["value_labels"]
    for slice_name, book in view["portfolio"].items():
        for r in book["rows"]:
            code = r[slice_name]
            assert code in labels[slice_name], f"{slice_name} {code!r} has no business name"
            assert labels[slice_name][code] != code or slice_name == "score_band"
    for r in view["by_channel"]:
        assert r["channel"] in labels["channel"]
    assert "(" not in "".join(labels["score_band"].values()), "score bands read as ranges, not intervals"


def test_band_labels_read_as_ranges():
    from src.client_view import band_label
    assert band_label("(0.0, 500.0]") == "500 or below"
    assert band_label("(650.0, 700.0]") == "651–700"
    assert band_label("no score") == "No score"


def test_slice_values_lead_with_the_name_and_keep_the_code():
    js = (UI / "client.js").read_text(encoding="utf-8")
    port = js[js.index("function pagePortfolio("):js.index("function shortMonth(")]
    assert "valueCell(key, r[key])" in port and "esc(r[key])" not in port
    assert "valueCell('channel', r.channel)" in js
    csv = js[js.index("function csvSpec("):js.index("function csvSpec(") + 3000]
    assert "name: valueName('channel', r.channel)" in csv, "the CSV carries the code and the name"


@pytest.mark.parametrize("name", ["client.js", "settings.js", "admin.js"])
def test_provenance_pills_sit_on_figures_not_on_section_headers(name):
    """C5: a pill says how a figure is known, so it goes where the figure is: a tile, a column,
    a chart key. A panel or section header carries none."""
    js = (UI / name).read_text(encoding="utf-8")
    heads = re.findall(r"(?:panel|section|accordion)\((?:'[^']*'|[^,]+), (?:'[^']*', )?([^\n]*)", js)
    offenders = [h[:80] for h in heads if h.lstrip().startswith("pv(") or "+ pv(" in h.split(",")[0]]
    assert not offenders, offenders
    assert "right: pv(" not in js, "overview cards carry no pill in their header"


def test_the_demo_strip_says_what_it_is_for_and_repeats_no_figure():
    """C5: the applicant count and period live on the period line and in Administration → Data,
    not in the strip on every page."""
    for page in ("client.html", "settings.html", "admin.html"):
        html = (UI / page).read_text(encoding="utf-8")
        strip = re.search(r'id="demostriptext">([^<]*)<', html)
        assert strip and strip[1].startswith("The rules and the method are real"), page
        assert not re.search(r"\d", strip[1]), page
    for js in ("client.js", "page_shell.js"):
        assert "demostriptext" not in (UI / js).read_text(encoding="utf-8"), js


def test_no_explanatory_paragraph_in_the_default_portfolio_view():
    """C5: answer, evidence, detail on demand. The method moves to the spec notes."""
    js = (UI / "client.js").read_text(encoding="utf-8")
    port = js[js.index("function overTimePanel("):js.index("function funnelPanelHtml(") + 4000]
    assert "caveat('', 'ROLL'" not in js and "caveat('warn', 'CONC'" not in js
    assert "caveat('sans', 'NOTE'" not in js
    assert "Why no roll rates" in port


def test_with_the_engine_running_figures_built_is_the_engines_time_without_a_redraw():
    """C5, one fact in one place: Settings and Administration show the engine's compute time, so
    the analysis screens must too. When the engine's figures match the file's, only the words
    change, in place, so a presenter part-way through the funnel keeps it."""
    js = (UI / "client.js").read_text(encoding="utf-8")
    body = js[js.index("function confirmFigures("):js.index("function engineUnavailable(")]
    assert "api('/api/view' + ctxQuery())" in body and "seq !== CTX.seq" in body
    assert "F.meta.generated = v.meta.generated" in body and "firstChild.nodeValue = asOfText()" in body
    assert "go(" not in body, "a matching view must not redraw the page"
    assert "if (custom) setContext(custom); else confirmFigures();" in js
