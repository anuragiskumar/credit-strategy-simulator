"""The Settings page of `ui/client.html` and the fixture behind it.

The screen follows the rule the rest of the prototype does: the UI computes nothing, every
figure comes from an export. It adds two more, and these tests hold both:

  * what is real and what is simulated is never blurred. Everything simulated lives under one
    key of the fixture, and the screen tags anything drawn from it;
  * the simulated parts are inert. Nothing leaves the browser, a chosen file is never read, and
    the demo password field is never read, so a real credential typed into it cannot leak.

The page was built apart from the three analysis screens and then merged into `client.html`. The
merge tests below hold the seams: script order, the one page registration, and note keys that
never collide with `client_notes.js`. This suite stays apart from `test_client_ui.py` so each
file tests one thing.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

import pytest

from src.client_generate import load_client_config
from src.client_replay import compile_rules, locked_rules
from src.rule_inventory import build_inventory
from ui import settings_export as X

REPO = Path(__file__).resolve().parents[1]
UI = REPO / "ui"
FIXTURE = UI / "settings.json"
HAS_RULES = bool(list(REPO.glob("business-rules-*.xlsx")))
needs_fixture = pytest.mark.skipif(not FIXTURE.exists(), reason="fixture not built")

PROVENANCE = {"OBSERVED", "PREDICTED", "INFERRED", "NOT_MODELLED", "BLENDED"}
TOP_LEVEL = {"meta", "rulepack", "dataset", "fields", "policy", "run", "simulated"}


def _code(name: str) -> str:
    """Source with comments dropped, so a comment describing a rule cannot trip a check on the rule."""
    text = (UI / name).read_text(encoding="utf-8")
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return "\n".join(line for line in text.splitlines() if not line.strip().startswith("//"))


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- static files
def test_the_page_ships_and_client_html_loads_it():
    for name in ("settings.css", "settings.js", "settings_notes.js", "settings_export.py"):
        assert (UI / name).exists(), name
    assert not (UI / "settings.html").exists(), "the standalone page was merged into client.html"
    html = (UI / "client.html").read_text(encoding="utf-8")
    assert 'href="tokens.css"' in html and 'href="settings.css"' in html


def test_the_settings_scripts_load_before_the_page_script_because_it_boots_at_load():
    html = (UI / "client.html").read_text(encoding="utf-8")
    at = {n: html.index(f'src="{n}"') for n in
          ("settings_data.js", "settings_notes.js", "settings.js", "client.js")}
    assert at["settings_data.js"] < at["settings.js"] < at["client.js"]
    assert at["settings_notes.js"] < at["client.js"]


def test_the_licence_chip_is_in_the_topbar_and_annotated():
    html = (UI / "client.html").read_text(encoding="utf-8")
    assert 'id="licchip"' in html and 'data-note="lic_chip"' in html


def test_client_js_registers_the_page_and_calls_the_module_at_each_seam():
    js = _code("client.js")
    assert "id: 'settings'" in js
    for seam in ("SettingsScreen.page()", "SettingsScreen.rail()", "SettingsScreen.after()", "SettingsScreen.init("):
        assert seam in js, seam
    assert "__SETTINGS_NOTES__" in js, "notes from settings_notes.js are not merged"
    # The settings notes read the settings fixture; handing them the analysis fixture throws at runtime.
    assert "__SETTINGS_NOTES__(window.__SETTINGS__)" in js


def test_the_settings_module_does_not_depend_on_the_analysis_fixture():
    """It reads its own fixture, so either export can be rebuilt without the other."""
    assert "__CLIENT__" not in _code("settings.js")


def test_the_settings_notes_never_reuse_a_key_from_the_analysis_notes():
    key = r"(?m)^    ([a-z_0-9]+): \{"
    client = set(re.findall(key, (UI / "client_notes.js").read_text(encoding="utf-8")))
    settings = set(re.findall(key, (UI / "settings_notes.js").read_text(encoding="utf-8")))
    assert client and settings
    assert client & settings == set(), f"a key in both would silently override: {sorted(client & settings)}"


def test_the_phone_layout_guards_are_still_in_the_stylesheet():
    """Regression: a trim of settings.css once dropped these, and the page scrolled sideways on a phone."""
    css = (UI / "settings.css").read_text(encoding="utf-8")
    for guard in ("#licchip {", ".su-sec .caveat .rid", ".su-sec .seg {", "prefers-reduced-motion"):
        assert guard in css, f"missing guard: {guard}"
    assert "max-width: 640px" in css and "max-width: 860px" in css


def test_the_settings_stylesheet_does_not_restyle_the_analysis_screens():
    """Loaded on the same page as client.css, so no bare selector may reach its elements."""
    css = re.sub(r"/\*.*?\*/", "", (UI / "settings.css").read_text(encoding="utf-8"), flags=re.S)
    selectors = [sel.strip() for block in re.findall(r"(?m)^\s*([^{}@]+)\{", css) for sel in block.split(",")]
    allowed = (".su-", "#licchip", "#rail .navitem[data-jump]", "textarea.su-", "select.su-", "table.t.su-")
    for sel in selectors:
        assert sel.startswith(allowed) or sel in {"to", "from"} or re.fullmatch(r"\d+%|\d+%, \d+%", sel), \
            f"selector reaches beyond this page: {sel!r}"


def test_every_class_the_page_adds_is_prefixed_so_it_cannot_collide_with_client_css():
    css = (UI / "settings.css").read_text(encoding="utf-8")
    assert set(re.findall(r"(?m)^\.(su-[a-z0-9-]+)", css)), "expected su- classes"
    assert not re.findall(r"(?m)^\.((?!su-)[a-z][a-z0-9-]*)", css), "an unprefixed class could collide"


# --------------------------------------------------------------------------- what the screen may not do
def test_the_page_uses_only_the_provenance_kinds_and_only_for_counted_facts():
    used = set(re.findall(r"pv\('([A-Z_]+)'", _code("settings.js")))
    assert used <= PROVENANCE, f"unexpected provenance kinds: {used - PROVENANCE}"
    assert used == {"OBSERVED"}, "settings shows counted facts only; simulated is a tag, not a provenance"


def test_the_page_never_derives_a_figure_from_two_fixture_fields():
    body = _code("settings.js")
    derived = re.findall(r"\b(?:F|r|o|t|g|v|d|s|x|R|D|T)\.\w+\s*/\s*(?:F|r|o|t|g|v|d|s|x|R|D|T)\.\w+", body)
    assert not derived, f"settings.js is deriving a figure: {derived}"


def test_nothing_leaves_the_browser_and_nothing_is_stored():
    body = _code("settings.js")
    for banned in ("fetch(", "XMLHttpRequest", "sendBeacon", "WebSocket", "localStorage",
                   "sessionStorage", "indexedDB", "document.cookie", "FileReader", ".text()",
                   ".arrayBuffer("):
        assert banned not in body, f"settings.js uses {banned}"


def test_the_demo_password_field_is_never_read():
    """A real credential typed into a simulated form must have nowhere to go."""
    body = _code("settings.js")
    assert 'id="su-pw"' in body
    lookups = re.findall(r"(?:getElementById|querySelector(?:All)?)\(\s*['\"][^'\"]*su-pw", body)
    assert not lookups, "su-pw is looked up in script"
    assert 'type="password"' in body
    pw_line = next(line for line in body.splitlines() if 'id="su-pw"' in line)
    assert " name=" not in pw_line, "a named field would be submitted with a form"


def test_a_chosen_file_is_never_read_only_named():
    body = _code("settings.js")
    assert ".files[0].name" in body
    assert not re.findall(r"\.files\[0\](?!\.name)", body), "a chosen file is used for more than its name"


def _page_strings() -> str:
    """Every string literal settings.js can put on screen, plus the fixture text it prints."""
    body = _code("settings.js")
    literals = " ".join(re.findall(r"'((?:[^'\\]|\\.)*)'", body))
    shown = json.dumps(_fixture()["simulated"]) + json.dumps(_fixture()["policy"]) if FIXTURE.exists() else ""
    return literals + " " + shown


# Phrases that belong in spec notes or a meeting, not on a screen a bank's CxO reads.
DEMO_VOICE = ["the bank gave us", "with the client", "the client has", "by the client", "this is a simulated",
              "nothing was actually", "demo only", "simulated.", "python -m", "in this demo", "client bank"]


def test_the_page_speaks_in_product_voice_and_leaves_the_reasoning_to_spec_notes():
    text = _page_strings().lower()
    found = [p for p in DEMO_VOICE if p in text]
    assert not found, f"demo or vendor voice on the page: {found}"


def test_the_part_simulated_banner_shows_only_in_presenter_mode():
    body = _code("settings.js")
    assert "PART SIMULATED" not in body
    assert "(DEV ? caveat(" in body, "the presenter explanation must sit behind the dev flag"


def test_the_administration_group_carries_one_preview_tag_not_one_per_accordion():
    body = _code("settings.js")
    accordions = re.findall(r"accordion\('[a-z]+', '[^']+', ([^,]+),", body)
    assert accordions and all("sim()" not in a for a in accordions), accordions
    assert re.search(r"function adminHead\(\)[^}]*sim\(\)", body, re.S)


def test_the_analysis_inputs_come_before_the_licence():
    ids = re.findall(r"\{ id: '([a-z]+)', t: ", _code("settings.js"))
    assert ids.index("rules") < ids.index("licence") and ids[0] == "rules"


def test_the_presenter_controls_appear_only_behind_an_explicit_flag():
    """`localhost` would put them on screen during a demo run from a laptop."""
    body = _code("settings.js")
    dev = re.search(r"var DEV = (.+);", body).group(1)
    assert "dev=1" in dev and "localhost" not in dev and "hostname" not in dev


def test_every_spec_note_key_the_page_uses_has_an_entry_and_none_is_orphaned():
    key = r"(?m)^    ([a-z_0-9]+): \{"
    notes = set(re.findall(key, (UI / "settings_notes.js").read_text(encoding="utf-8")))
    used = set(re.findall(r"N\('([a-z_0-9]+)'\)", _code("settings.js")))
    # `lic_chip` is tagged in client.html's topbar, not drawn by the script.
    used |= set(re.findall(r'data-note="([a-z_0-9]+)"', (UI / "client.html").read_text(encoding="utf-8"))) & notes
    client_notes = set(re.findall(key, (UI / "client_notes.js").read_text(encoding="utf-8")))
    assert used - notes - client_notes == set(), f"tagged with no note: {sorted(used - notes - client_notes)}"
    assert notes - used == set(), f"note with nothing tagged: {sorted(notes - used)}"


# --------------------------------------------------------------------------- fixture shape
@needs_fixture
def test_data_js_matches_the_json_fixture():
    js = (UI / "settings_data.js").read_text(encoding="utf-8")
    assert js.startswith("window.__SETTINGS__ = ")
    assert json.loads(js[len("window.__SETTINGS__ = "):].rstrip().rstrip(";")) == _fixture()


@needs_fixture
def test_everything_simulated_sits_under_one_key_and_says_so():
    data = _fixture()
    assert set(data) == TOP_LEVEL
    assert data["simulated"]["simulated"] is True
    for key in TOP_LEVEL - {"simulated", "meta"}:     # meta.note is where the split is stated
        assert "simulated" not in json.dumps(data[key]).lower().replace("synthetic", ""), \
            f"'{key}' mentions simulated content outside the simulated block"


@needs_fixture
def test_the_fixture_says_out_loud_that_the_applicants_are_synthetic():
    assert _fixture()["meta"]["synthetic"] is True


@needs_fixture
def test_the_three_databases_are_offered_with_their_usual_ports():
    types = {t["id"]: t for t in _fixture()["simulated"]["connectors"]["types"]}
    assert {k: v["default_port"] for k, v in types.items()} == {"oracle": 1521, "postgres": 5432, "mysql": 3306}
    for t in types.values():
        assert any(f["key"] == "host" and f["required"] for f in t["fields"]), t["id"]


@needs_fixture
def test_the_licence_ladder_runs_in_order_and_two_things_never_change():
    lic = _fixture()["simulated"]["licence"]
    assert [r["id"] for r in lic["ladder"]] == ["active", "expiring", "grace", "read_only", "suspended"]
    joined = " ".join(lic["always"]).lower()
    assert "never deleted" in joined and "never blocked" in joined
    assert lic["signature"]["algorithm"] == "Ed25519"


@needs_fixture
def test_every_licence_scenario_carries_the_text_the_page_prints():
    """The page cannot work out days remaining, so every state must ship them."""
    need = {"status", "status_label", "does", "term", "valid_to", "headline", "remaining", "chip"}
    for name, snap in _fixture()["simulated"]["licence"]["scenarios"].items():
        assert need <= set(snap), name
    assert {"current", "active", "expiring", "grace", "read_only", "suspended", "renewed"} == \
        set(_fixture()["simulated"]["licence"]["scenarios"])


# --------------------------------------------------------------------------- licence logic
END = dt.date(2026, 12, 31)


@pytest.mark.parametrize("as_of, expected", [
    (dt.date(2026, 9, 21), "active"),
    (END - dt.timedelta(days=31), "active"),
    (END - dt.timedelta(days=30), "expiring"),
    (END, "expiring"),
    (END + dt.timedelta(days=1), "grace"),
    (END + dt.timedelta(days=15), "grace"),
    (END + dt.timedelta(days=16), "read_only"),
    (END + dt.timedelta(days=45), "read_only"),
    (END + dt.timedelta(days=46), "suspended"),
])
def test_the_licence_state_follows_the_dates(as_of, expected):
    assert X._status(as_of, END) == expected


def test_the_days_remaining_are_worked_out_by_the_export_not_the_page():
    lic = X.build_licence(dt.date(2026, 9, 21))
    assert lic["scenarios"]["current"]["remaining"] == "101 days remaining"
    assert lic["scenarios"]["current"]["headline"] == "Valid until 31 Dec 2026"
    assert lic["scenarios"]["grace"]["headline"].startswith("Expired on")
    assert lic["scenarios"]["renewed"]["status"] == "active"
    assert lic["scenarios"]["renewed"]["valid_to"] == "31 Mar 2027"


def test_the_ladder_dates_are_in_order():
    dates = [dt.datetime.strptime(r["from"], "%d %b %Y").date() for r in X._ladder(END)[1:]]
    assert dates == sorted(dates)


# --------------------------------------------------------------------------- real facts agree with the engine
@needs_fixture
@pytest.mark.skipif(not HAS_RULES, reason="rule workbooks not present")
def test_the_rule_counts_on_screen_are_the_engines_counts():
    cfg = load_client_config()
    rep = cfg["replay"]
    inv = build_inventory(rep["rules_folder"])
    compiled = compile_rules(inv, product=cfg["product"], include_inactive=rep["include_inactive_rules"],
                             stage_map=rep["stage_by_table"], locked=locked_rules(cfg))
    data = _fixture()
    assert data["rulepack"]["totals"]["in_scope"] == len(compiled)
    assert data["rulepack"]["totals"]["rules"] == len(inv.rules)
    # Every in-scope rule is either replayed or named as unevaluable: none goes missing.
    assert data["run"]["rules_replayed"] + len(data["run"]["unevaluable"]) == len(compiled)


@needs_fixture
def test_the_required_fields_are_all_supplied_by_the_demo_dataset():
    f = _fixture()["fields"]
    assert f["required_mapped"] == f["required"] > 0


@needs_fixture
def test_the_example_layout_states_how_many_required_fields_are_unmapped():
    ex = _fixture()["simulated"]["example_layout"]
    s = ex["summary"]
    assert s["required_mapped"] + len(s["unmapped_required"]) == s["required"]
    # It must still disclaim being the bank's own schema, in the bank's voice.
    assert "illustrative" in ex["note"].lower() and "not your own schema" in ex["note"].lower()


@needs_fixture
def test_the_policy_values_are_the_configs_values():
    cfg = load_client_config()
    ap = {p["key"]: p["value"] for p in _fixture()["policy"]["appetite"]}
    assert ap["Bad-rate ceiling"] == cfg["optimise"]["max_bad_rate"]
