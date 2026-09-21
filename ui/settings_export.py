"""Export the fixture for the Settings screen (`ui/settings.html`).

    python -m ui.settings_export

The screen computes nothing, exactly like the three client screens: every figure and every
piece of text it shows is read from `window.__SETTINGS__`, produced here. This module is kept
apart from `ui/client_export.py` on purpose. The two screens are built in parallel and are
merged later, so neither may rewrite the other's fixture.

The fixture has two kinds of content, and the split is the point:

  * REAL     read from the engine and the files on disk: the rule workbooks, the applicant
             table, the field requirements, the policy and risk-appetite values, the replay
             assumptions, and how long the last replay took.
  * SIMULATED everything the deployed product needs but this demo does not: database
             connectors, file upload, the licence, outcome definitions, access control,
             versions and updates. All of it sits under the single top-level key `simulated`.
             The screen tags anything drawn from that key, and a test asserts nothing
             simulated leaks outside it.

The applicant table and the rules are the same ones the three client screens use, so the
two fixtures agree on facts (rule counts, applicant count) without sharing a file.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import time
from pathlib import Path

import pandas as pd

from src import client_loader, client_schema
from src.client_generate import load_client_config
from src.client_replay import compile_rules, locked_rules, replay
from src.config import resolve_path
from src.rule_inventory import build_inventory

HERE = Path(__file__).resolve().parent

# Rule fields that are not a plain column rename in `client_loader.FIELD_SOURCES`: the loader
# derives them (dialect maps, flags, the employer keyword lookup), so the requirement is real
# but the canonical column is found here rather than there.
DERIVED_FIELD_SOURCES = {
    "typeofemployment": "employment_type",
    "natureofemployment": "is_pensioner",
    "pensioner": "is_pensioner",
    "customersegment": "employer_segment",
    "employeesegment": "employer_segment",
    "employer_keyword_check": "employer_name",
}

# Plain names for the checks the optimiser never relaxes; the engine field is kept as a tooltip.
HARD_REJECT_LABELS = {
    "employername": "Restricted employer",
    "politicallyexposedperson": "Politically exposed person",
    "relatedtopep": "Related to a politically exposed person",
    "diplomaticservice": "Diplomatic service",
}

PREVIEW_COLUMNS = ["application_id", "app_date", "channel", "employer_segment",
                   "monthly_income", "simah_score", "requested_amount", "tenure_months"]
PREVIEW_ROWS = 6


def _date(d: dt.date) -> str:
    return f"{d.day} {d.strftime('%b %Y')}"


def _sha12(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def _canonical_for(rule_field: str) -> str | None:
    if rule_field in client_loader.FIELD_SOURCES:
        return client_loader.FIELD_SOURCES[rule_field]
    if rule_field in client_loader.BOOLEAN_AS_ONE:
        return client_loader.BOOLEAN_AS_ONE[rule_field]
    return DERIVED_FIELD_SOURCES.get(rule_field)


# --------------------------------------------------------------------------- REAL sections
def build_rulepack(cfg: dict, inv, compiled) -> dict:
    rep = cfg["replay"]
    folder = resolve_path(rep["rules_folder"])
    in_scope = {}
    for c in compiled:
        in_scope[c.table] = in_scope.get(c.table, 0) + 1

    files = []
    for path in sorted(folder.glob("business-rules-*.xlsx")):
        rules = inv.rules[inv.rules.source_file == path.name]
        tables = []
        for table, g in rules.groupby("table", sort=False):
            n_scope = in_scope.get(table, 0)
            if table == "employer_keyword_check":
                role = "lookup"
            elif n_scope == 0:
                role = "not replayed"
            else:
                role = "decision table"
            tables.append({
                "table": table,
                "role": role,
                "stage": rep["stage_by_table"].get(table),
                "rules": int(len(g)),
                "in_scope": int(n_scope),
                "inactive": int((~g.is_active).sum()),
            })
        files.append({
            "file": path.name,
            "sha12": _sha12(path),
            "modified": _date(dt.date.fromtimestamp(path.stat().st_mtime)),
            "tables": tables,
        })
    all_tables = [t for f in files for t in f["tables"]]
    return {
        "files": files,
        "totals": {"files": len(files), "tables": len(all_tables),
                   "rules": sum(t["rules"] for t in all_tables),
                   "in_scope": sum(t["in_scope"] for t in all_tables),
                   "inactive": sum(t["inactive"] for t in all_tables)},
        "product": cfg["product"],
        "options": {"include_inactive_rules": bool(rep["include_inactive_rules"])},
        "stage_by_table": dict(rep["stage_by_table"]),
    }


def build_dataset(cfg: dict, df: pd.DataFrame | None) -> dict:
    if df is None:
        return {"available": False}
    problems = client_schema.validate(df)
    nulls = df.isna().mean()
    preview = df[PREVIEW_COLUMNS].head(PREVIEW_ROWS).copy()
    preview["app_date"] = preview["app_date"].dt.strftime("%Y-%m-%d")
    return {
        "available": True,
        "label": "Demo dataset (synthetic)",
        "rows": int(len(df)),
        "columns": int(df.shape[1]),
        "date_from": _date(df["app_date"].min().date()),
        "date_to": _date(df["app_date"].max().date()),
        "window_days": int(cfg["app_date_days"]),
        "schema_problems": problems,
        "nulls": [{"column": c, "share": round(float(s), 4)} for c, s in nulls.items()
                  if s > 0 and c not in client_schema.PERFORMANCE],
        "preview": {"columns": PREVIEW_COLUMNS, "rows": clean_rows(preview)},
    }


def clean_rows(df: pd.DataFrame) -> list[list]:
    def one(v):
        if pd.isna(v):
            return None
        v = v.item() if hasattr(v, "item") else v      # numpy scalar -> plain Python
        return round(v, 1) if isinstance(v, float) else v

    return [[one(v) for v in row] for row in df.itertuples(index=False)]


def build_fields(compiled, df: pd.DataFrame | None) -> dict:
    """What the rules need from the applicant table, and what nothing supplies."""
    readers: dict[str, set[str]] = {}
    unsupplied: dict[str, set[str]] = {}
    for c in compiled:
        for f in c.fields:
            col = _canonical_for(f)
            if col is None:
                unsupplied.setdefault(f, set()).add(c.rule_id)
            else:
                readers.setdefault(col, set()).add(c.rule_id)

    nulls = df.isna().mean() if df is not None else {}
    rows = []
    for col, dtype in client_schema.COLUMNS.items():
        n = len(readers.get(col, ()))
        if col == "latent_bad":
            role, need = "synthetic only", "Not requested"
        elif col == "walked_away":
            role, need = "outcome", "Needed for the funnel"
        elif n:
            role, need = "rule input", "Required"
        else:
            role, need = "analysis", "Recommended"
        rows.append({
            "column": col, "dtype": dtype,
            "nullable": col in client_schema.NULLABLE,
            "role": role, "need": need, "rules": n,
            "null_share": round(float(nulls[col]), 4) if col in nulls else None,
        })
    rows.sort(key=lambda r: (["Required", "Needed for the funnel", "Recommended", "Not requested"]
                             .index(r["need"]), -r["rules"], r["column"]))
    have = set(df.columns) if df is not None else set()
    return {
        "columns": rows,
        "required": sum(1 for r in rows if r["need"] == "Required"),
        "required_mapped": sum(1 for r in rows if r["need"] == "Required" and r["column"] in have),
        "unsupplied": [{"field": f, "rules": len(ids)} for f, ids in
                       sorted(unsupplied.items(), key=lambda kv: -len(kv[1]))],
    }


def build_policy(cfg: dict) -> dict:
    """The values a risk committee owns. Read from config, shown, not editable in a static page."""
    rep, opt = cfg["replay"], cfg["optimise"]
    return {
        "appetite": [
            {"key": "Bad-rate ceiling", "value": opt["max_bad_rate"], "fmt": "pct0",
             "help": "No recommended strategy may exceed this expected bad rate."},
            {"key": "Rule earns its place above", "value": cfg["drivers"]["earns_place_multiple"],
             "fmt": "x2", "help": "A rule is keeping its place if the applicants it alone declines "
                                    "are at least this many times riskier than the booked book."},
            {"key": "Riskier swap-ins above", "value": cfg["simulate"]["riskier_multiple"], "fmt": "x2",
             "help": "Newly approved applicants above this multiple of the booked bad rate are called riskier."},
            {"key": "Safer swap-ins below", "value": cfg["simulate"]["safer_multiple"], "fmt": "x2",
             "help": "Newly approved applicants below this multiple are called safer."},
        ],
        "model": [
            {"key": "Minimum group size", "value": cfg["risk_model"]["min_group_size"], "fmt": "n0",
             "help": "A group smaller than this gets no risk estimate, however tempting."},
            {"key": "Minimum support coverage", "value": cfg["risk_model"]["min_support_coverage"],
             "fmt": "pct0", "help": "Share of a group that must sit inside the booked score range."},
            {"key": "Minimum missing-score booked", "value": cfg["risk_model"]["min_missing_score_booked"],
             "fmt": "n0", "help": "Applicants with no score are only estimated if the bank booked this many."},
        ],
        "portfolio": [
            {"key": "Over-exposed at", "value": cfg["portfolio"]["over_exposed_multiple"], "fmt": "x1",
             "help": "A slice holding this multiple of an even split is flagged as concentrated."},
            {"key": "Under-exposed at", "value": cfg["portfolio"]["under_exposed_multiple"], "fmt": "x1",
             "help": "A slice below this multiple of an even split is flagged as thin."},
            {"key": "Score bands", "value": cfg["portfolio"]["score_bands"], "fmt": "list",
             "help": "Bureau score cut points used to slice the book."},
        ],
        "product": [
            {"key": "Product minimum amount (SAR)", "value": cfg["funnel"]["product_min_amount"],
             "fmt": "n0", "help": "Requests below this are declined by the product rules."},
            {"key": "Minimum acceptable offer", "value": cfg["funnel"]["min_acceptable_offer_ratio"],
             "fmt": "pct0", "help": "Share of the request an applicant will still accept."},
        ],
        # The three decisions the rule files do not make. Each is an open question with the client.
        "assumptions": [
            {"key": "A missing value satisfies a condition",
             "value": "Yes" if rep["condition_on_missing_value_matches"] else "No",
             "help": "16% of applicants have no bureau score and about 100 rules test it, so this one "
                     "switch moves a lot of people."},
            {"key": "An applicant no rule catches",
             "value": rep["no_rule_matched"].capitalize(),
             "help": "Whether an applicant no rule declines is approved or declined."},
            {"key": "Include inactive rules",
             "value": "Yes" if rep["include_inactive_rules"] else "No",
             "help": "The 10 inactive rules stay off, as in production."},
        ],
        "hard_reject_fields": list(rep["hard_reject_fields"]),
        "hard_reject": [{"field": f, "label": HARD_REJECT_LABELS.get(f, f)} for f in rep["hard_reject_fields"]],
        "levers": [{"field": m["field"], "from": m["from"], "to": m["to"], "label": m["label"]}
                   for m in opt["field_moves"]],
    }


def build_run(cfg: dict, df: pd.DataFrame | None, inv, compiled) -> dict:
    """Replay once and report what the run looked like. Timing is measured, not quoted."""
    if df is None:
        return {"available": False}
    t0 = time.perf_counter()
    res = replay(df, inv, cfg)
    seconds = time.perf_counter() - t0
    never = res.rules[res.rules.matched == 0]
    return {
        "available": True,
        "applicants": int(len(df)),
        "rules_in_scope": len(compiled),
        "rules_replayed": int(len(res.rules)),
        "unevaluable": list(res.unevaluable),
        "never_fire": [{"rule_id": r.rule_id,
                        "description": (r.description or "")[:90]}
                       for r in never.head(8).itertuples()],
        "never_fire_count": int(len(never)),
        "replay_seconds": round(seconds, 1),
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }


# --------------------------------------------------------------------------- SIMULATED
# What each licence stage pauses, as the actions the permission layer checks (ui/session.js).
# In the deployed product this list is read from the client's signed licence file, because stages
# and durations differ by client; here it is one illustrative licence.
PAUSED_READ_ONLY = ["data.load", "rules.load", "recompute.run", "config.change"]
PAUSED_SUSPENDED = PAUSED_READ_ONLY + ["analysis.view"]


def _ladder(end: dt.date) -> list[dict]:
    """Illustrative enforcement ladder. The durations are contract terms, not engine facts.

    Not drawn on any screen: every client has its own term, so the ladder lives in the contract
    and the spec notes. The screens only act on `paused` for the current stage."""
    expiring = end - dt.timedelta(days=30)
    grace_end = end + dt.timedelta(days=15)
    ro_end = grace_end + dt.timedelta(days=30)
    return [
        {"id": "active", "label": "Active", "from": "Start of term",
         "does": "Everything works.", "paused": []},
        {"id": "expiring", "label": "Expiring", "from": _date(expiring),
         "does": "A banner and reminders to the named contacts. Everything still works.", "paused": []},
        {"id": "grace", "label": "Grace", "from": _date(end + dt.timedelta(days=1)),
         "does": "Everything still works. Daily reminders to administrators.", "paused": []},
        {"id": "read_only", "label": "Read-only", "from": _date(grace_end + dt.timedelta(days=1)),
         "does": "Screens, analysis and export keep working. New data loads, configuration "
                 "changes and recomputes are paused.", "paused": PAUSED_READ_ONLY},
        {"id": "suspended", "label": "Suspended", "from": _date(ro_end + dt.timedelta(days=1)),
         "does": "Analysis screens lock; this page and export stay open.", "paused": PAUSED_SUSPENDED},
    ]


def _status(as_of: dt.date, end: dt.date) -> str:
    if as_of < end - dt.timedelta(days=30):      # the ladder prints this day as the first expiring one
        return "active"
    if as_of <= end:
        return "expiring"
    if as_of <= end + dt.timedelta(days=15):
        return "grace"
    if as_of <= end + dt.timedelta(days=45):
        return "read_only"
    return "suspended"


def _snapshot(as_of: dt.date, end: dt.date, start: dt.date, ladder: list[dict], *,
              renewed: bool = False) -> dict:
    status = _status(as_of, end)
    days = (end - as_of).days
    if days >= 0:
        headline = f"Valid until {_date(end)}"
        remaining = f"{days} days remaining"
    else:
        headline = f"Expired on {_date(end)}"
        remaining = f"{-days} days ago"
    label = next(s["label"] for s in ladder if s["id"] == status)
    does = next(s["does"] for s in ladder if s["id"] == status)
    paused = next(s["paused"] for s in ladder if s["id"] == status)
    return {"status": status, "status_label": label, "does": does,
            "term": f"{_date(start)} to {_date(end)}",
            "valid_to": _date(end), "headline": headline, "remaining": remaining,
            "chip": f"Licence · valid to {_date(end)}" if days >= 0 else f"Licence · {label.lower()}",
            "paused": paused, "renewed": renewed}


def build_licence(as_of: dt.date) -> dict:
    start, end = dt.date(2026, 9, 1), dt.date(2026, 12, 31)
    ladder = _ladder(end)
    renewed_end = dt.date(2027, 3, 31)
    scenarios = {
        "current": _snapshot(as_of, end, start, ladder),
        "active": _snapshot(end - dt.timedelta(days=100), end, start, ladder),
        "expiring": _snapshot(end - dt.timedelta(days=12), end, start, ladder),
        "grace": _snapshot(end + dt.timedelta(days=6), end, start, ladder),
        "read_only": _snapshot(end + dt.timedelta(days=25), end, start, ladder),
        "suspended": _snapshot(end + dt.timedelta(days=60), end, start, ladder),
        "renewed": _snapshot(as_of, renewed_end, start, ladder, renewed=True),
    }
    return {
        "licensee": "Licensed bank",
        "licence_id": "TWQR-2026-0001",
        "issued_by": "Azentio licence service (offline signing)",
        "entitlements": [
            {"key": "Product", "value": "TWQR"},
            {"key": "Modules", "value": "Portfolio · Decline drivers · Simulator"},
            {"key": "Environments", "value": "Production · UAT"},
            {"key": "Named users", "value": "25"},
        ],
        "signature": {"algorithm": "Ed25519", "verified": True, "fingerprint": "9f2c 41ab 07de 5c18",
                      "note": "Verified offline against the Azentio public key shipped with the product."},
        "ladder": ladder,
        "always": ["Client data is never deleted.", "Export is never blocked."],
        "scenarios": scenarios,
        "refresh": {
            "none": "No new licence found. The licence on file is unchanged.",
            "found": "A renewed licence file was found, verified and applied.",
            "apply": "The licence file was verified and applied.",
            "paused_message": "Paused under the current licence. Contact your administrator.",
            "how": "The deployed product has no outbound internet, so refresh does not ask a server "
                   "whether payment arrived. It re-reads the licence store and re-verifies the signature. "
                   "After payment Azentio issues a new signed licence file, delivered through the "
                   "patch channel or applied here by an administrator.",
        },
        "reminders": {"contacts": ["risk-admin@client-bank.example", "it-ops@client-bank.example"],
                      "notice_days": [90, 60, 30, 7]},
    }


def build_connectors() -> dict:
    tls = lambda choices: {"key": "tls", "label": "Transport security", "type": "select", "choices": choices}
    return {
        "types": [
            {"id": "oracle", "label": "Oracle Database", "driver": "python-oracledb (thin mode)",
             "default_port": 1521,
             "fields": [
                 {"key": "host", "label": "Host", "type": "text", "required": True,
                  "placeholder": "los-db.bank.internal"},
                 {"key": "port", "label": "Port", "type": "number", "default": "1521"},
                 {"key": "service", "label": "Service name", "type": "text", "required": True,
                  "placeholder": "LOSPRD"},
                 {"key": "schema", "label": "Schema", "type": "text", "placeholder": "LOS"},
                 tls(["TLS", "Wallet (mutual TLS)", "Off"]),
             ]},
            {"id": "postgres", "label": "PostgreSQL", "driver": "psycopg 3",
             "default_port": 5432,
             "fields": [
                 {"key": "host", "label": "Host", "type": "text", "required": True,
                  "placeholder": "los-db.bank.internal"},
                 {"key": "port", "label": "Port", "type": "number", "default": "5432"},
                 {"key": "database", "label": "Database", "type": "text", "required": True,
                  "placeholder": "los"},
                 {"key": "schema", "label": "Schema", "type": "text", "default": "public"},
                 tls(["verify-full", "verify-ca", "require", "disable"]),
             ]},
            {"id": "mysql", "label": "MySQL", "driver": "PyMySQL",
             "default_port": 3306,
             "fields": [
                 {"key": "host", "label": "Host", "type": "text", "required": True,
                  "placeholder": "los-db.bank.internal"},
                 {"key": "port", "label": "Port", "type": "number", "default": "3306"},
                 {"key": "database", "label": "Database", "type": "text", "required": True,
                  "placeholder": "los"},
                 tls(["VERIFY_IDENTITY", "VERIFY_CA", "REQUIRED", "DISABLED"]),
             ]},
        ],
        "auth": [
            {"id": "vault", "label": "Vault reference", "help": "Recommended. The credential lives in the "
             "bank's secrets store and is never typed into a browser."},
            {"id": "password", "label": "Username and password",
             "help": "For estates without a vault. Entered once and held server-side."},
        ],
        "extraction": {
            "objects": ["Table or view", "SQL query"],
            "refresh": ["Manual", "Nightly", "Hourly"],
            "read_only_note": "Use a read-only account. The product never writes to the source system.",
        },
    }


def build_simulated(as_of: dt.date, real_fields: dict) -> dict:
    fields = [r["column"] for r in real_fields["columns"] if r["need"] != "Not requested"]
    # An example client layout. Illustrative: the real schema is not in yet, so no source name
    # here is a claim about the client's system.
    example_names = {
        "application_id": "APP_REF", "app_date": "APP_DT", "product": "PROD_CD",
        "requested_amount": "REQ_AMT", "tenure_months": "TENOR_M", "monthly_income": "TOT_INCOME",
        "age": "APPLICANT_AGE", "gender": "GENDER", "nationality": "NATIONALITY",
        "employer_segment": "EMP_SEGMENT", "employer_name": "EMPLOYER_NM", "simah_score": "SIMAH_SCR",
        "crif_score": "CRIF_SCR", "channel": "SRC_CHANNEL",
    }
    layout = [{"column": c, "source": example_names.get(c)} for c in fields]
    required = {r["column"] for r in real_fields["columns"] if r["need"] == "Required"}
    unmapped_required = [x["column"] for x in layout if x["column"] in required and not x["source"]]
    return {
        "simulated": True,
        "licence": build_licence(as_of),
        "connectors": build_connectors(),
        "connection_test": {
            "steps": [
                {"label": "Reach host", "detail": "Resolved and connected", "ms": 42},
                {"label": "Secure the channel", "detail": "Certificate chain accepted", "ms": 118},
                {"label": "Authenticate", "detail": "Service account accepted", "ms": 76},
                {"label": "Confirm read-only", "detail": "No write privileges found", "ms": 31},
                {"label": "Find the object", "detail": "Table located, 34 columns", "ms": 64},
                {"label": "Count rows", "detail": "Estimate returned", "ms": 210},
            ],
            "failures": {
                "host_missing": {"label": "Reach host", "detail": "No host was entered."},
                "port_invalid": {"label": "Reach host", "detail": "The port must be a number."},
                "required_missing": {"label": "Connection details", "detail": "A required field is empty."},
            },
            "done": "All checks passed. Live connections are not available in this environment.",
        },
        "upload": {
            "data": "Loading a file is not available in this environment.",
            "rules": "Loading a rule pack is not available in this environment.",
            "accept_data": ".csv,.xlsx,.parquet",
            "accept_rules": ".xlsx",
        },
        "example_layout": {
            "source_object": "LOS.APPLICATIONS_V",
            "note": "An illustrative layout with bank-style column names, not your own schema.",
            "mapping": layout,
            "summary": {"required": len(required),
                        "required_mapped": len(required) - len(unmapped_required),
                        "unmapped_required": unmapped_required},
        },
        "outcomes": {
            "note": "How a loan is classed as bad, and where its repayment history is read from.",
            "definition": [
                {"key": "A loan is bad when it reaches", "value": "90 days past due"},
                {"key": "Within", "value": "12 months on book"},
                {"key": "Only loans booked at least", "value": "12 months ago"},
                {"key": "Exclude", "value": "Early settlements and fraud cases"},
            ],
            "sources": [
                {"key": "Booked flag", "value": "LOAN_STATUS = 'DISBURSED'"},
                {"key": "Performance", "value": "COLLECTIONS.DPD_MAX_12M"},
                {"key": "Offer accepted", "value": "OFFER.ACCEPTED_FLAG"},
                {"key": "Bank's actual decision", "value": "DECISION.OUTCOME and DECISION.REASON_CD"},
            ],
            "reconciliation": "The bank's actual decision is compared with the replay, application by "
                              "application, so a difference in the rules is found before it is found by "
                              "a customer.",
        },
        "governance": [
            {"group": "Deployment", "items": [
                {"key": "Environment", "value": "On-premise or private cloud"},
                {"key": "Data residency", "value": "In-kingdom. No outbound internet."}]},
            {"group": "Access", "items": [
                {"key": "Sign-in", "value": "Single sign-on (OIDC or SAML)"},
                {"key": "Roles", "value": "Analyst · Risk approver · Administrator"},
                {"key": "Session", "value": "Server-side, 30-minute idle timeout"}]},
            {"group": "Data protection", "items": [
                {"key": "Personal data", "value": "National ID and name masked; application ID hashed"},
                {"key": "Secrets", "value": "Held in the bank's vault; only references stored here"},
                {"key": "Retention", "value": "Extracts purged after 90 days"}]},
            {"group": "Language model", "items": [
                {"key": "Provider", "value": "On-premise, OpenAI-compatible endpoint"},
                {"key": "Endpoint", "value": "https://llm.bank.internal/v1"},
                {"key": "Scope", "value": "Translates questions; never computes a figure"}]},
        ],
        "regional": [
            {"key": "Language", "value": "English (Arabic available)"},
            {"key": "Currency", "value": "SAR"},
            {"key": "Time zone", "value": "Asia/Riyadh"},
            {"key": "Date format", "value": "Gregorian, with Hijri alongside"},
        ],
        "audit": [
            {"when": "Today 09:12", "who": "Risk admin", "what": "Applied licence file"},
            {"when": "Today 08:47", "who": "Analyst 2", "what": "Ran simulator: SIMAH cutoff 580"},
            {"when": "Yesterday 17:30", "who": "Risk admin", "what": "Loaded rule pack (4 workbooks)"},
            {"when": "Yesterday 16:05", "who": "Data engineer", "what": "Tested connection: Oracle (read-only)"},
            {"when": "Mon 11:20", "who": "Risk admin", "what": "Changed bad-rate ceiling 12% to 11%"},
        ],
        "versions": [
            {"key": "Application", "value": "1.4.0"},
            {"key": "Engine", "value": "2.2.1"},
            {"key": "Configuration", "value": "client-config r17 (preserved)"},
            {"key": "Last patch", "value": "1.3.2 to 1.4.0, applied 14 Sep 2026"},
            {"key": "Patch channel", "value": "Encrypted, signed by Azentio; up to date"},
        ],
        "recompute": {
            "steps": ["Load the applicant table", "Replay the rules", "Refit the risk model",
                      "Score the scenario grid", "Search for strategies", "Write the results"],
            "note": "Runs as a background job and takes a few minutes.",
            "done": "Recompute is not available in this environment. The figures are unchanged.",
        },
        "diagnostics": {
            "bundle": "A bundle of logs, versions and configuration for Azentio support, with no applicant "
                      "data in it. There is no remote access, so this is how a problem is reported.",
            "exports": ["Configuration (YAML)", "Audit log (CSV)"],
            # Results exports belong on the analysis screens, for every role; not drawn yet.
            "results_exports": ["Decline drivers (CSV)", "Simulator scenarios (CSV)", "Portfolio report (PDF)"],
            "note": "Export is available in every licence state.",
        },
    }


# --------------------------------------------------------------------------- build
def load_dataset(cfg: dict) -> pd.DataFrame | None:
    path = resolve_path(cfg["data_path"])
    return pd.read_parquet(path) if path.exists() else None


def build(as_of: dt.date | None = None) -> dict:
    as_of = as_of or dt.date.today()
    cfg = load_client_config()
    rep = cfg["replay"]
    inv = build_inventory(rep["rules_folder"])
    compiled = compile_rules(inv, product=cfg["product"],
                             include_inactive=rep["include_inactive_rules"],
                             stage_map=rep["stage_by_table"], locked=locked_rules(cfg))
    df = load_dataset(cfg)

    rulepack = build_rulepack(cfg, inv, compiled)
    dataset = build_dataset(cfg, df)
    fields = build_fields(compiled, df)
    run = build_run(cfg, df, inv, compiled)
    return {
        "meta": {
            "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "product": cfg["product"],
            "synthetic": True,
            "note": "Rule set, dataset facts, field requirements and policy values are read from the "
                    "engine. Everything under `simulated` is not.",
        },
        "rulepack": rulepack,
        "dataset": dataset,
        "fields": fields,
        "policy": build_policy(cfg),
        "run": run,
        "simulated": build_simulated(as_of, fields),
    }


def write(out: dict, folder: Path = HERE) -> None:
    text = json.dumps(out, indent=1, ensure_ascii=False)
    (folder / "settings.json").write_text(text + "\n", encoding="utf-8")
    (folder / "settings_data.js").write_text("window.__SETTINGS__ = " + text + ";\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args(argv)
    t0 = time.perf_counter()
    write(build())
    print(f"wrote ui/settings.json and ui/settings_data.js in {time.perf_counter() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
