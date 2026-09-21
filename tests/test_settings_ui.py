"""Settings (`ui/settings.html`), Administration (`ui/admin.html`), the permission seam
(`ui/session.js`), the demo menu (`ui/demo_bar.js`), and the fixture behind them.

The pages follow the rule the rest of the prototype does: the UI computes nothing, every figure
comes from an export. These tests hold the rest:

  * who sees what is decided in one place. Pages ask Session.can(); only demo_bar.js knows role
    names, and it is the one file the real server replaces, so the demo menu never ships;
  * the licence reaches a non-administrator only as a paused action, never as a date, and its
    term-and-renewal stages are never drawn: they differ by client and live in the spec notes;
  * what is real and what is simulated is never blurred, and the simulated parts are inert:
    nothing leaves the browser, a chosen file is never read, the demo password is never read;
  * the pages speak in product voice and name Azentio, never "the vendor".
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

import pandas as pd
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
TOP_LEVEL = {"meta", "rulepack", "dataset", "fields", "outcome", "policy", "run", "context", "governed", "simulated"}
PAGES = ("client.html", "settings.html", "admin.html")
PAGE_SCRIPTS = ("settings_kit.js", "page_shell.js", "settings.js", "admin.js")
ROLE_NAMES = ("Business user", "Analyst", "Risk approver", "Administrator",
              "'admin'", "'analyst'", "'approver'", "'business'")
NOTE_KEY = r"(?m)^    ([a-z_0-9]+): \{"


def _code(name: str) -> str:
    """Source with comments dropped, so a comment describing a rule cannot trip a check on the rule."""
    text = (UI / name).read_text(encoding="utf-8")
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return "\n".join(line for line in text.splitlines() if not line.strip().startswith("//"))


def _html(name: str) -> str:
    return (UI / name).read_text(encoding="utf-8")


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _keys(name: str) -> set[str]:
    return set(re.findall(NOTE_KEY, _html(name)))


# --------------------------------------------------------------------------- static files
def test_settings_and_administration_are_pages_of_their_own():
    for name in ("settings.html", "admin.html", "settings.js", "admin.js", "settings_kit.js", "page_shell.js",
                 "session.js", "demo_bar.js", "settings_notes.js", "admin_notes.js", "shell.css", "settings.css"):
        assert (UI / name).exists(), name
    for page in ("settings.html", "admin.html"):
        html = _html(page)
        assert 'name="viewport"' in html, page
        for css in ("tokens.css", "client.css", "shell.css", "settings.css"):
            assert f'href="{css}"' in html, (page, css)


@pytest.mark.parametrize("page, script", [("settings.html", "settings.js"), ("admin.html", "admin.js")])
def test_each_page_loads_its_scripts_in_the_order_they_depend_on(page, script):
    html = _html(page)
    order = ["settings_data.js", "session.js", "demo_bar.js", "settings_kit.js", "settings_notes.js",
             "page_shell.js", script]
    at = [html.index(f'src="{n}"') for n in order]
    assert at == sorted(at), f"{page} loads its scripts out of order"
    if page == "admin.html":
        assert html.index('src="settings_notes.js"') < html.index('src="admin_notes.js"') < html.index('src="admin.js"')


def test_client_html_no_longer_carries_the_settings_page():
    html, js = _html("client.html"), _code("client.js")
    for gone in ('src="settings.js"', 'src="settings_notes.js"', 'href="settings.css"', 'id="licchip"'):
        assert gone not in html, gone
    assert "SettingsScreen" not in js and "__SETTINGS_NOTES__" not in js
    assert "href: 'settings.html'" in js and "href: 'admin.html', need: 'admin.view'" in js


def test_every_page_carries_the_azentio_brand_and_declares_utf8():
    for page in PAGES:
        html = _html(page)
        assert "Azentio.ai | Credit Strategy Optimiser</title>" in html, page
        assert '<span class="az">Azentio<em>.ai</em></span>' in html, page
        assert '<meta charset="utf-8">' in html, f"{page} garbles its text on a server that sends no charset"


def test_the_pages_do_not_depend_on_the_analysis_fixture():
    """Settings reads its own fixture, so either export can be rebuilt without the other."""
    for name in PAGE_SCRIPTS:
        assert "__CLIENT__" not in _code(name), name


def test_the_phone_layout_guards_are_still_in_the_stylesheet():
    """Regression: a trim of settings.css once dropped these, and the page scrolled sideways on a phone."""
    css = _html("settings.css")
    for guard in (".su-sec .caveat .rid", ".su-sec .seg {", "prefers-reduced-motion"):
        assert guard in css, f"missing guard: {guard}"
    assert "max-width: 640px" in css and "max-width: 860px" in css


def test_the_settings_stylesheet_does_not_restyle_the_analysis_screens():
    """Loaded after client.css, so no bare selector may reach its elements."""
    css = re.sub(r"/\*.*?\*/", "", _html("settings.css"), flags=re.S)
    selectors = [sel.strip() for block in re.findall(r"(?m)^\s*([^{}@]+)\{", css) for sel in block.split(",")]
    allowed = (".su-", "#rail .navitem[data-jump]", "textarea.su-", "select.su-", "table.t.su-")
    for sel in selectors:
        assert sel.startswith(allowed) or sel in {"to", "from"} or re.fullmatch(r"\d+%|\d+%, \d+%", sel), \
            f"selector reaches beyond this page: {sel!r}"


def test_every_class_the_page_adds_is_prefixed_so_it_cannot_collide_with_client_css():
    css = _html("settings.css")
    assert set(re.findall(r"(?m)^\.(su-[a-z0-9-]+)", css)), "expected su- classes"
    assert not re.findall(r"(?m)^\.((?!su-)[a-z][a-z0-9-]*)", css), "an unprefixed class could collide"


# --------------------------------------------------------------------------- who sees what
def test_only_the_demo_menu_knows_role_names():
    """Pages ask Session what the person may do; a role name anywhere else is a check the server cannot replace."""
    for name in PAGE_SCRIPTS + ("session.js", "client.js"):
        found = [r for r in ROLE_NAMES if r in _code(name)]
        assert not found, f"{name} names a role: {found}"
    assert all(r in _code("demo_bar.js") for r in ("Business user", "Analyst", "Risk approver", "Administrator"))


def test_the_demo_menu_is_one_script_tag_on_every_page_and_nothing_else_refers_to_it():
    for page in PAGES:
        html = _html(page)
        assert html.count('src="demo_bar.js"') == 1, page
        assert html.index('src="session.js"') < html.index('src="demo_bar.js"'), page
    for name in PAGE_SCRIPTS + ("session.js", "client.js"):
        assert "demobar" not in _code(name) and "demo_bar" not in _code(name), name


def test_the_old_url_switches_are_gone():
    for name in PAGE_SCRIPTS + ("demo_bar.js",):
        body = _code(name)
        assert not re.search(r"[?&](?:dev|role)=", body), name


def test_with_no_provider_the_session_fails_closed():
    assert re.search(r"var state = \{ can: \[\], paused: \[\], licence: null", _code("session.js"))


def test_only_the_demo_menu_uses_browser_storage():
    for name in PAGE_SCRIPTS + ("session.js",):
        body = _code(name)
        for banned in ("localStorage", "sessionStorage", "indexedDB", "document.cookie"):
            assert banned not in body, f"{name} uses {banned}"


def test_every_action_a_page_asks_for_is_one_the_demo_menu_can_grant_or_a_licence_can_pause():
    asked = set()
    for name in PAGE_SCRIPTS + ("client.js",):
        body = _code(name)
        asked |= set(re.findall(r"\bcan\('([a-z.]+)'\)", body)) | set(re.findall(r"\bpaused\('([a-z.]+)'\)", body))
        asked |= set(re.findall(r"need: '([a-z.]+)'", body))
    granted = set(re.findall(r"'([a-z]+\.[a-z]+)'", _code("demo_bar.js")))
    pausable = set(X.PAUSED_SUSPENDED)
    assert asked, "no page asks Session anything"
    assert asked <= granted | pausable, f"asked for but never granted or paused: {sorted(asked - granted - pausable)}"
    assert granted <= asked, f"granted but never asked for: {sorted(granted - asked)}"


def test_administration_refuses_anyone_without_admin_view():
    body = _code("admin.js")
    assert "if (!can('admin.view'))" in body and "NO ACCESS" in body


# --------------------------------------------------------------------------- the licence
def test_no_page_draws_the_term_and_renewal_stages():
    """Each client has its own term, so the stages live in the licence file and the spec notes."""
    for name in PAGE_SCRIPTS + ("client.js",):
        body = _code(name)
        assert "ladder" not in body and "su-rung" not in body and "L.always" not in body, name
    assert "L.ladder" in _code("admin_notes.js"), "the stages must be explained in the spec notes"


def test_the_licence_reaches_a_non_administrator_only_as_a_paused_action():
    settings = _code("settings.js")
    assert "Session.licence" not in settings and "scenarios" not in settings and "valid_to" not in settings
    assert "paused_message" in settings
    admin = _code("admin.js")
    assert "need: 'licence.view'" in admin and "window.Session.licence()" in admin
    assert "r.can.indexOf('licence.view') >= 0 ? s : null" in _code("demo_bar.js"), \
        "the licence snapshot must reach only someone allowed to view it"


@needs_fixture
def test_every_licence_stage_says_what_it_pauses():
    scen = _fixture()["simulated"]["licence"]["scenarios"]
    assert all(isinstance(s["paused"], list) for s in scen.values())
    assert scen["current"]["paused"] == [] and scen["renewed"]["paused"] == []
    assert "recompute.run" in scen["read_only"]["paused"] and "analysis.view" in scen["suspended"]["paused"]


# --------------------------------------------------------------------------- what the screens may not do
def test_the_pages_use_only_the_provenance_kinds_and_only_for_counted_facts():
    used = set()
    for name in PAGE_SCRIPTS:
        used |= set(re.findall(r"pv\('([A-Z_]+)'", _code(name)))
    assert used <= PROVENANCE, f"unexpected provenance kinds: {used - PROVENANCE}"
    assert used == {"OBSERVED"}, "these pages show counted facts only; simulated is a tag, not a provenance"


def test_the_pages_never_derive_a_figure_from_two_fixture_fields():
    for name in PAGE_SCRIPTS:
        derived = re.findall(r"\b(?:F|r|o|t|g|v|d|s|x|R|D|T)\.\w+\s*/\s*(?:F|r|o|t|g|v|d|s|x|R|D|T)\.\w+", _code(name))
        assert not derived, f"{name} is deriving a figure: {derived}"


def test_nothing_leaves_the_browser_but_the_settings_api():
    """Settings talks to the engine about governed settings and nothing else; the rest talk to no one."""
    for name in PAGE_SCRIPTS + ("session.js", "demo_bar.js", "context_store.js"):
        body = _code(name)
        for banned in ("XMLHttpRequest", "sendBeacon", "WebSocket", "FileReader", ".text()", ".arrayBuffer("):
            assert banned not in body, f"{name} uses {banned}"
        if name not in ("settings.js", "admin.js"):
            assert "fetch(" not in body, f"{name} uses fetch("
    body = _code("settings.js")
    assert body.count("fetch(") == 1, "one api() helper, so every call is visible in one place"
    paths = set(re.findall(r"'(/api/[a-z/-]+)", body))
    assert paths == {"/api/settings", "/api/settings/propose", "/api/settings/decide", "/api/settings/change",
                     "/api/recompute"}, paths
    # Administration only reads: the settings history for its audit log, and nothing it sends.
    admin = _code("admin.js")
    assert admin.count("fetch(") == 1 and "fetch('/api/settings')" in admin and "method" not in admin


def test_the_demo_password_field_is_never_read():
    """A real credential typed into a simulated form must have nowhere to go."""
    body = _code("admin.js")
    assert 'id="su-pw"' in body and 'type="password"' in body
    for name in PAGE_SCRIPTS:
        lookups = re.findall(r"(?:getElementById|querySelector(?:All)?)\(\s*['\"][^'\"]*su-pw", _code(name))
        assert not lookups, f"su-pw is looked up in {name}"
    pw_line = next(line for line in body.splitlines() if 'id="su-pw"' in line)
    assert " name=" not in pw_line, "a named field would be submitted with a form"


def test_a_chosen_file_is_never_read_only_named():
    body = _code("admin.js")
    assert ".files[0].name" in body
    assert not re.findall(r"\.files\[0\](?!\.name)", body), "a chosen file is used for more than its name"


def _page_strings() -> str:
    """Every string literal the pages can put on screen, plus the fixture text they print."""
    literals = " ".join(" ".join(re.findall(r"'((?:[^'\\]|\\.)*)'", _code(n))) for n in PAGE_SCRIPTS)
    shown = json.dumps(_fixture()["simulated"]) + json.dumps(_fixture()["policy"]) if FIXTURE.exists() else ""
    return literals + " " + shown


# Phrases that belong in spec notes or a meeting, not on a screen a bank's CxO reads.
DEMO_VOICE = ["the bank gave us", "with the client", "the client has", "by the client", "this is a simulated",
              "nothing was actually", "demo only", "simulated.", "python -m", "in this demo", "client bank"]


def test_the_pages_speak_in_product_voice_and_leave_the_reasoning_to_spec_notes():
    text = _page_strings().lower()
    found = [p for p in DEMO_VOICE if p in text]
    assert not found, f"demo or vendor voice on the page: {found}"


def test_azentio_is_named_and_the_vendor_never_is():
    for name in PAGE_SCRIPTS + ("settings_notes.js", "admin_notes.js", "demo_bar.js") + PAGES:
        assert not re.search(r"\bvendor", _html(name), re.I), name
    if FIXTURE.exists():
        assert "vendor" not in json.dumps(_fixture()).lower()
        assert "Azentio" in json.dumps(_fixture()["simulated"]["licence"])


def test_administration_carries_one_preview_tag_for_the_page_not_one_per_section():
    body = _code("admin.js")
    assert len(re.findall(r"sim\(\)", body)) == 1
    assert not re.findall(r"section\('[a-z]+', '[^']+', sim\(\)", body)


def test_settings_is_four_tabs_analysis_first_and_has_no_licence():
    ids = re.findall(r"\{ id: '([a-z]+)', t: ", _code("settings.js"))
    assert ids == ["analysis", "appetite", "assumptions", "health"]
    body = _code("settings.js")
    assert "licence" not in " ".join(ids) and "Session.licence" not in body


def test_administration_is_six_tabs_overview_first_licence_last():
    body = _code("admin.js")
    ids = re.findall(r"\{ id: '([a-z]+)', t: ", body)
    assert ids == ["overview", "data", "access", "audit", "system", "licence"]
    assert "{ id: 'audit', t: 'Audit log', need: 'audit.view' }" in body
    assert "{ id: 'licence', t: 'Licence', need: 'licence.view' }" in body


def test_a_source_is_connected_by_one_flow_not_a_tab_per_database():
    body = _code("admin.js")
    assert "data-act=\"src\"" not in body and "SOURCES" not in body
    for db in ("Oracle", "PostgreSQL", "MySQL"):
        assert db not in _fn(body, "stepConnect"), "database types come from the fixture, as one field"
    assert "['Kind', 'Connect', 'Check', 'Map fields', 'Review']" in body


def test_the_licence_keeps_its_id_and_folds_the_signature_details_away():
    sec = _fn(_code("admin.js"), "secLicence")
    assert "L.licence_id" in sec and "signature ' + (L.signature.verified" in sec
    tech = sec[sec.index('su-tech'):]
    assert "L.signature.algorithm" in tech and "L.signature.fingerprint" in tech


def test_the_overview_opens_only_what_needs_attention():
    body = _code("admin.js")
    card = _fn(body, "card")
    assert "o.attn && o.detail" in card and "o.attn && o.tab" in card
    cards = _fn(body, "cards")
    assert "big: !ok" in cards and "attn: !ok" in cards, "the licence goes large only when not active"


def test_the_audit_log_reads_the_engines_settings_history():
    ev = _fn(_code("admin.js"), "events")
    assert "S.gov.history" in ev and "SIM.audit" in ev and "real: true" in ev


@needs_fixture
def test_the_roles_on_administration_are_the_roles_the_demo_menu_grants():
    ac = _fixture()["simulated"]["access"]
    roles = [r["role"] for r in ac["roles"]]
    assert roles == re.findall(r"label: '([^']+)', can:", _code("demo_bar.js"))
    assert [g["role"] for g in ac["sso"]["groups"]] == roles
    assert {u["role"] for u in ac["users"]} <= set(roles)
    assert any(u["status"] == "Requested" for u in ac["users"]), "the overview shows what a request looks like"


@needs_fixture
def test_the_example_audit_events_are_dated_and_leave_settings_to_the_engine():
    rows = _fixture()["simulated"]["audit"]
    assert rows and all(re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", r["at"]) for r in rows)
    assert "Settings" not in {r["kind"] for r in rows}, "settings changes are the engine's own records"


def test_the_workbook_inventory_and_audit_log_live_on_administration():
    settings, admin = _code("settings.js"), _code("admin.js")
    assert "RP.files" not in settings and "SIM.audit" not in settings
    assert "RP.files" in admin and "SIM.audit" in admin and "need: 'audit.view'" in admin
    assert "' rules replayed for ' + esc(RP.product) + ', from ' + n0(RP.totals.files)" in settings, "business users see one line"


def test_the_product_and_period_are_kept_in_one_place():
    """client.html and Settings share one per-viewer store; neither touches browser storage itself."""
    assert "localStorage" in _code("context_store.js")
    for name in ("client.js", "settings.js"):
        body = _code(name)
        assert "window.AnalysisContext." in body, name
        assert "cso.context" not in body, name
    for page in ("client.html", "settings.html"):
        html = _html(page)
        assert html.index('src="context_store.js"') < html.index('src="client.js"' if page == "client.html" else 'src="settings.js"')


def test_settings_offers_each_change_only_to_the_role_that_makes_it():
    body = _code("settings.js")
    assert "can('policy.propose')" in _fn(body, "proposeForm")
    assert "can('policy.approve')" in _fn(body, "pending")
    assert "mine" in _fn(body, "pending"), "the proposer is offered Withdraw, never Approve"
    assert "can('assumptions.change')" in _fn(body, "secAssumptions")
    assert "can('recompute.run')" in _fn(body, "secRecompute")


def test_an_approved_value_is_never_shown_as_if_the_figures_used_it():
    body = _code("settings.js")
    assert "awaiting_recompute" in _fn(body, "status") and "until the next recompute" in _fn(body, "status")
    assert "awaiting()" in body


def _fn(js, name):
    start = js.index("function " + name + "(")
    return js[start:js.index("\n  function ", start + 1)]


def test_every_spec_note_key_the_pages_use_has_an_entry_and_none_is_orphaned():
    settings_keys, admin_keys = _keys("settings_notes.js"), _keys("admin_notes.js")
    assert not settings_keys & admin_keys, f"a key in both would silently override: {sorted(settings_keys & admin_keys)}"

    def tagged(*names):
        return set().union(*(set(re.findall(r"N\('([a-z_0-9]+)'\)", _code(n))) for n in names))

    def html(page):
        return set(re.findall(r'data-note="([a-z_0-9]+)"', _html(page)))

    on_settings = tagged("settings.js", "settings_kit.js", "page_shell.js") | html("settings.html")
    on_admin = tagged("admin.js", "settings_kit.js", "page_shell.js") | html("admin.html")
    assert on_settings <= settings_keys, f"tagged on Settings with no note: {sorted(on_settings - settings_keys)}"
    assert on_admin <= settings_keys | admin_keys, \
        f"tagged on Administration with no note: {sorted(on_admin - settings_keys - admin_keys)}"
    assert settings_keys <= on_settings | on_admin, f"note with nothing tagged: {sorted(settings_keys - on_settings - on_admin)}"
    assert admin_keys <= on_admin, f"note with nothing tagged: {sorted(admin_keys - on_admin)}"


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
def test_the_demo_licence_ladder_runs_in_order_and_two_things_never_change():
    """The demo licence file's contents. Explained in the spec notes, never drawn."""
    lic = _fixture()["simulated"]["licence"]
    assert [r["id"] for r in lic["ladder"]] == ["active", "expiring", "grace", "read_only", "suspended"]
    joined = " ".join(lic["always"]).lower()
    assert "never deleted" in joined and "never blocked" in joined
    assert lic["signature"]["algorithm"] == "Ed25519"


@needs_fixture
def test_every_licence_scenario_carries_the_text_the_page_prints():
    """The page cannot work out days remaining, so every state must ship them."""
    need = {"status", "status_label", "does", "term", "valid_to", "headline", "remaining", "paused"}
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


def test_the_field_mapping_leads_with_the_data_in_use_and_the_example_is_a_step_of_connecting():
    body = _code("admin.js")
    sec = _fn(body, "secMapping")
    assert "Nothing can run" not in sec and "'IN USE'" in sec and "C.required_mapped" in sec
    assert "'EXAMPLE'" not in sec and "'EXAMPLE'" in _fn(body, "stepMap")


@needs_fixture
def test_the_outcome_block_is_the_engines_bad_definition():
    from src import client_analysis as A
    cfg = load_client_config()
    o = _fixture()["outcome"]
    bd = A.bad_definition(cfg)
    shown = {d["key"]: d["value"] for d in o["definition"]}
    assert shown["A loan is bad when it reaches"] == f"{bd['dpd']} days past due"
    assert shown["Within"] == f"{bd['within_months']} months of booking"
    assert {s["value"] for s in o["sources"]} == {"booking_date", "bad_date"}
    # The suite repoints data_path at the Streamlit dataset, so read the file the fixture was built from.
    path = REPO / "data" / "client_applications.parquet"
    if not path.exists():
        pytest.skip("client dataset not built")
    perf = A.observed_performance(pd.read_parquet(path), cfg)
    assert sum(p["judged"] for p in o["products"]) == int(perf["mature"].sum())
    # What the engine does not do yet stays under `simulated`, labelled as planned.
    assert "Exclude" not in json.dumps(o)
    assert "planned" in _fixture()["simulated"]["outcomes"]["note"].lower()


@needs_fixture
def test_the_policy_values_are_the_configs_values():
    cfg = load_client_config()
    gov = {p["key"]: p for p in _fixture()["governed"]["settings"]}
    assert gov["bad_rate_ceiling"]["configured"] == cfg["optimise"]["max_bad_rate"]
    assert gov["missing_value_matches"]["configured"] == cfg["replay"]["condition_on_missing_value_matches"]


# --------------------------------------------------------------------------- TODO C5
def test_every_column_has_a_business_name_and_settings_leads_with_it():
    from src import client_schema
    assert set(client_schema.LABELS) == set(client_schema.COLUMNS)
    F = _fixture()
    assert all(c["label"] for c in F["fields"]["columns"]) and all(n["label"] for n in F["dataset"]["nulls"])
    assert {r["rule_id"] for r in F["run"]["unevaluable_rules"]} == set(F["run"]["unevaluable"])
    js = _code("settings.js")
    assert "esc(n.label || n.column) + ' <span class=\"rid\">'" in js
    assert "esc(r.label || r.column) + ' <span class=\"rid\">'" in js


def test_the_dataset_size_is_shown_once_in_administration():
    """C5: the applicant count and dates live in Administration → Data. Data health and the
    overview card point at them rather than repeat them."""
    health = _code("settings.js")
    health = health[health.index("function secHealth("):health.index("function secMapping(")]
    assert "D.rows" not in health and "D.date_from" not in health
    admin = _code("admin.js")
    cards = admin[admin.index("function cards("):admin.index("function secOverview(")]
    assert "D.rows" not in cards and "D.date_from" not in cards
    assert "{ key: 'Applicants', value: n0(D.rows) }" in admin


def test_administration_asks_the_engine_once_the_viewer_becomes_an_admin():
    """The demo bar switches role on an open page; the overview must not keep the file's figures."""
    js = _code("admin.js")
    assert "window.Session.onChange(function () { if (can('admin.view') && !S.asked) load(); });" in js
    assert "S.asked = true;" in js[js.index("function load("):js.index("function load(") + 200]
