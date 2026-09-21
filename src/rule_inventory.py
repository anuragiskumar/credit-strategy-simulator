"""Normalise the client's Excel decision tables into one rule inventory (Plan step 1).

The four exports each hold one or more decision tables: row = rule, column = field,
cell = condition. This module flattens them into two tidy tables — one row per rule,
one row per (rule, field) condition — plus a conflict report.

Nothing here interprets applicant data; it only reads rules. The parser is strict:
an expression it does not recognise is kept verbatim with operator `unparsed` so it
shows up in the report rather than being silently dropped.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field
from functools import lru_cache
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd
import yaml

REDACTIONS_PATH = Path(__file__).resolve().parents[1] / "redactions.local.yaml"

# Columns that carry the rule's outcome or metadata rather than a condition.
META_COLUMNS = {
    "ruleresult", "decision", "description", "errormessage", "policycode",
    "policylevel", "logicid", "product", "executionlevel", "excecutionlevel",
    "result",
}
# Columns that scope a rule to a population rather than test a credit criterion.
SCOPE_FIELDS = {
    "customersegment", "employeesegment", "empsegment", "employeetype",
    "typeofemployment", "natureofemployment", "program", "subproduct", "product",
    "simcusttype", "sourcetype", "ntb", "pensioner",
}
# Facts the bank cannot negotiate: identity, regulator, bureau events, staff exclusions.
FIXED_FIELDS = {
    "nationality", "gender", "politicallyexposedperson", "relatedtopep",
    "diplomaticservice", "isbsfemployee", "v_bsf_employee", "employername",
    "employer_keyword_check", "salarytobsf", "v_is_loan_transfer", "v_nationality",
    "v_employmenttype", "v_comp_appl_id", "v_scr_asset_make", "v_sector_type",
    "militaryrankdesignation", "miltaryrank", "simahscorecarddescription",
}
FIXED_PREFIXES = ("v_simah", "v_sim_", "vsimah", "simbc")


def _norm(name: str) -> str:
    """Canonical key for a column header: strip accessors, wrappers and case."""
    s = str(name).strip().strip('"')
    s = re.sub(r"^number\((.*)\)$", r"\1", s)
    s = s.split(".")[-1] if s.startswith("queryResultAl.") else s
    s = re.sub(r"\.result$", "", s)
    return s.lower()


def classify_field(field_name: str) -> str:
    """Tag a field `scope`, `fixed` or `tunable`. A proposal for a human to confirm."""
    k = _norm(field_name)
    if k in SCOPE_FIELDS:
        return "scope"
    if k in FIXED_FIELDS or k.startswith(FIXED_PREFIXES):
        return "fixed"
    return "tunable"


@dataclass
class Condition:
    field: str
    operator: str
    low: float | None = None
    high: float | None = None
    values: tuple[str, ...] = ()
    raw: str = ""
    note: str = ""


def _nums(s: str) -> list[float]:
    return [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", s)]


def _strs(s: str) -> tuple[str, ...]:
    """Split a comma-separated list of literals, quoted or bare."""
    parts = re.findall(r'"([^"]*)"', s)
    if parts:
        return tuple(p.strip() for p in parts)
    return tuple(p.strip() for p in s.split(",") if p.strip())


def parse_condition(field_name: str, raw_value) -> list[Condition]:
    """Turn one cell into one or more conditions. Never raises."""
    raw = str(raw_value).strip()
    f = _norm(field_name)
    mk = lambda **kw: [Condition(field=f, raw=raw, **kw)]

    if raw in ("", "-", "None"):
        return []

    # "SAU", not("SAU") — every value matches, so the column constrains nothing.
    if re.fullmatch(r'"[^"]+"\s*,\s*not\("[^"]+"\)', raw):
        return mk(operator="always", note="tautology: matches every value")

    # [300..530]
    if m := re.fullmatch(r"\[(-?[\d.]+)\.\.(-?[\d.]+)\]", raw):
        return mk(operator="between", low=float(m.group(1)), high=float(m.group(2)))

    # <600  >=3500  =0
    if m := re.fullmatch(r"(<=|>=|<|>|=)\s*(-?[\d.]+)", raw):
        op = {"<": "lt", "<=": "lte", ">": "gt", ">=": "gte", "=": "eq"}[m.group(1)]
        return mk(operator=op, low=float(m.group(2)))

    # 20 > age or age > 60   /   <20, >60   /   <12,>60
    if m := re.fullmatch(r"(-?[\d.]+)\s*>\s*\w+\s+or\s+\w+\s*>\s*(-?[\d.]+)", raw):
        return mk(operator="outside", low=float(m.group(1)), high=float(m.group(2)))
    if m := re.fullmatch(r"<\s*(-?[\d.]+)\s*,\s*>\s*(-?[\d.]+)", raw):
        return mk(operator="outside", low=float(m.group(1)), high=float(m.group(2)))

    # 4*income<loanAmount  — the affordability multiple
    if m := re.fullmatch(r"(-?[\d.]+)\s*\*\s*(\w+)\s*<\s*(\w+)", raw):
        return mk(operator="income_multiple_exceeded", low=float(m.group(1)),
                  note=f"{m.group(3)} above {m.group(1)}x {m.group(2)}")
    if m := re.fullmatch(r"(-?[\d.]+)\s*\*\s*(\w+)", raw):
        return mk(operator="income_multiple", low=float(m.group(1)),
                  note=f"{m.group(1)}x {m.group(2)}")

    # not("GOSI","GOSI Taqdeer",null)
    if m := re.fullmatch(r"not\((.*)\)", raw, re.S):
        vals = _strs(m.group(1))
        has_null = "null" in m.group(1)
        return mk(operator="not_in", values=vals,
                  note="null excluded" if has_null else "")

    # contains(?, "مؤسسة")
    if m := re.fullmatch(r'contains\(\?,\s*"(.*)"\)', raw, re.S):
        return mk(operator="contains", values=(m.group(1),))

    if raw in ("true", "false"):
        return mk(operator="eq", values=(raw,))

    if re.fullmatch(r"-?[\d.]+", raw):
        return mk(operator="eq", low=float(raw))

    # "ST","SMG","PVTL"
    if re.fullmatch(r'"[^"]*"(\s*,\s*"[^"]*")*', raw, re.S):
        return mk(operator="in", values=_strs(raw))

    # Bare identifier, e.g. MSSGNOAS
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", raw):
        return mk(operator="in", values=(raw,), note="unquoted literal in source")

    return mk(operator="unparsed", note="expression not recognised by the parser")


@lru_cache(maxsize=1)
def _redactions() -> tuple[tuple[re.Pattern, str], ...]:
    """Whole-word, case-insensitive term -> replacement pairs from `redactions.local.yaml`.

    Rule text is the client's own and can name the client. The demo is shown to other banks, so
    the name must never reach the fixture or the screens. The terms live in a git-ignored file
    rather than in code or config, because listing the name here would put it in the repository.
    """
    if not REDACTIONS_PATH.exists():
        return ()
    terms = yaml.safe_load(REDACTIONS_PATH.read_text(encoding="utf-8")) or {}
    return tuple((re.compile(rf"\b{re.escape(str(k))}\b", re.I), str(v)) for k, v in terms.items())


def redact(text: str) -> str:
    for pattern, replacement in _redactions():
        text = pattern.sub(replacement, text)
    return text


def english_description(value) -> tuple[str, str]:
    """Split the client's bilingual `if(lang="ar") then ... else ...` descriptions. -> (en, ar)."""
    if value is None:
        return "", ""
    s = str(value).strip()
    m = re.match(r'^if\(.*?\)\s*then\s*"(.*)"\s*else\s*"(.*)"\s*$', s, re.S)
    if m:
        return redact(m.group(2).strip()), redact(m.group(1).strip())
    return redact(s.strip('"').strip()), ""


@dataclass
class Inventory:
    rules: pd.DataFrame
    conditions: pd.DataFrame
    conflicts: pd.DataFrame = dc_field(default_factory=pd.DataFrame)


def _cell(row, hdr, name):
    for j, h in enumerate(hdr):
        if h is not None and _norm(h) == name:
            return row[j] if j < len(row) else None
    return None


def read_workbook(path: Path) -> tuple[list[dict], list[dict]]:
    """Return (rule records, condition records) for every decision table in one file."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    mapping = {}
    if "Mapping" in wb.sheetnames:
        for r in wb["Mapping"].iter_rows(values_only=True):
            if r[0] and str(r[0]).strip() != "Sheet Number":
                mapping[str(r[0]).strip()] = str(r[1]).strip()

    rules, conds = [], []
    for ws in wb.worksheets:
        if ws.title == "Mapping":
            continue
        rows = list(ws.iter_rows(values_only=True))
        if len(rows) < 2:
            continue
        hdr = rows[0]
        table = mapping.get(ws.title, ws.title)
        for i, row in enumerate(rows[1:], start=2):
            if all(c is None for c in row):
                continue
            rule_id = f"{table}#{i:03d}"
            outcome = _cell(row, hdr, "ruleresult") or _cell(row, hdr, "decision") or _cell(row, hdr, "result")
            desc_en, desc_ar = english_description(
                _cell(row, hdr, "description") or _cell(row, hdr, "errormessage")
            )
            cap = _cell(row, hdr, "requestamount")
            n_cond = 0
            for j, h in enumerate(hdr):
                if h is None or j >= len(row) or row[j] is None:
                    continue
                key = _norm(h)
                if key in META_COLUMNS or key == "requestamount":
                    continue
                if key == "a":                     # the unnamed '"A"' marker column
                    continue
                for c in parse_condition(h, row[j]):
                    n_cond += 1
                    conds.append({
                        "rule_id": rule_id, "table": table, "field": c.field,
                        "operator": c.operator, "value_low": c.low, "value_high": c.high,
                        "value_set": "|".join(c.values) if c.values else None,
                        "tunability": classify_field(c.field), "raw": c.raw, "note": c.note,
                    })
            rules.append({
                "rule_id": rule_id, "source_file": path.name, "sheet": ws.title,
                "table": table, "source_row": i,
                "product": _clean(_cell(row, hdr, "product")),
                "outcome": _clean(outcome),
                "policy_code": _clean(_cell(row, hdr, "policycode")) or _clean(_cell(row, hdr, "logicid")),
                "policy_level": _clean(_cell(row, hdr, "policylevel")),
                "execution_level": _clean(_cell(row, hdr, "executionlevel")) or _clean(_cell(row, hdr, "excecutionlevel")),
                "action_cap": _clean(cap),
                "condition_count": n_cond,
                "description_en": desc_en,
                "description_ar": desc_ar,
            })
    wb.close()
    return rules, conds


def _clean(v):
    if v is None:
        return None
    return str(v).strip().strip('"').strip() or None


def build_inventory(folder: Path | str = ".", pattern: str = "business-rules-*.xlsx") -> Inventory:
    folder = Path(folder)
    files = sorted(folder.glob(pattern))
    if not files:
        raise FileNotFoundError(f"no rule files matching {pattern!r} in {folder}")
    all_rules, all_conds = [], []
    for f in files:
        r, c = read_workbook(f)
        all_rules += r
        all_conds += c
    rules = pd.DataFrame(all_rules)
    conds = pd.DataFrame(all_conds)
    rules = _derive_cap(rules, conds)
    rules["is_active"] = rules["outcome"].str.lower() != "inactive"
    rules["blocks_applicant"] = rules["outcome"].str.lower().isin(["decline", "fail"])
    return Inventory(rules=rules, conditions=conds, conflicts=find_conflicts(rules, conds))


def _derive_cap(rules: pd.DataFrame, conds: pd.DataFrame) -> pd.DataFrame:
    """Resolve what an `Exception` row actually does.

    Two distinct things share the outcome label. Most cap the finance amount: the cap is
    `requestAmount`, or — when that column holds 0 — the `loanAmount` trigger the row fires
    above. The rest set an eligibility limit instead (age band, tenure, length of service,
    down payment) and never name an amount. The simulator has to treat them differently:
    a cap moves the offer, a limit moves the applicant out of the funnel.
    """
    trig = (conds[(conds.field == "loanamount") & conds.operator.isin(["gt", "gte", "eq"])]
            .set_index("rule_id")["value_low"].to_dict())

    def cap(r):
        a = r["action_cap"]
        if a and a not in ("0", "0.0"):
            return a
        t = trig.get(r["rule_id"])
        return str(int(t)) if t is not None else None

    rules = rules.copy()
    rules["cap_amount"] = rules.apply(cap, axis=1)
    rules["exception_kind"] = np.where(
        rules["outcome"].str.lower() != "exception", None,
        np.where(rules["cap_amount"].notna(), "amount_cap", "eligibility_limit"))
    return rules


def find_conflicts(rules: pd.DataFrame, conds: pd.DataFrame) -> pd.DataFrame:
    """Duplicates, overlaps, tautologies, unparsed cells and dead columns.

    Each finding is something a human must resolve before the rules can be replayed
    with confidence; the brief treats surfacing them as a deliverable in itself.
    """
    out = []

    def _sig_col(col):
        return conds[col].astype(object).where(conds[col].notna(), "~").astype(str)
    sig_parts = (_sig_col("field") + ":" + _sig_col("operator") + ":" + _sig_col("value_low")
                 + ":" + _sig_col("value_high") + ":" + _sig_col("value_set"))
    sig = (conds.assign(s=sig_parts).sort_values(["rule_id", "s"])
           .groupby("rule_id")["s"].apply(lambda x: " & ".join(x)))
    merged = rules.set_index("rule_id").join(sig.rename("signature"))
    merged["product"] = merged["product"].fillna("~")

    # Same table, same product, same conditions -> a genuine duplicate row.
    for (tbl, prod, s_), grp in merged.groupby(["table", "product", "signature"], dropna=False):
        if len(grp) < 2:
            continue
        same = len(set(grp["outcome"].fillna(""))) == 1 and len(set(grp["cap_amount"].fillna(""))) == 1
        out.append({
            "kind": "duplicate_identical" if same else "duplicate_conflicting",
            "table": tbl, "rule_ids": ", ".join(grp.index),
            "detail": f"product {prod}: same conditions, "
                      + ("same outcome — one row is redundant" if same
                         else f"different outcome/cap {sorted(set(grp['outcome'].fillna('')))}"
                              f" {sorted(set(grp['cap_amount'].fillna('')))}"),
        })

    # Same conditions across products: expected, but worth listing so it is not mistaken
    # for 337 independent policies.
    for (tbl, s_), grp in merged.groupby(["table", "signature"], dropna=False):
        prods = set(grp["product"])
        if len(grp) > 1 and len(prods) > 1:
            out.append({"kind": "restated_per_product", "table": tbl,
                        "rule_ids": ", ".join(grp.index),
                        "detail": f"one policy written once per product: {sorted(prods)}"})

    # Two rules that differ ONLY in the threshold on one field, yet whose populations
    # overlap, contradict each other: the same applicant matches both bands.
    num_ops = {"lt", "lte", "gt", "gte", "between", "outside", "eq"}
    cond_by_rule = {rid: g for rid, g in conds.groupby("rule_id")}

    def _scope_map(rid) -> dict[str, frozenset]:
        g = cond_by_rule[rid]
        g = g[(g.tunability == "scope") & g.value_set.notna()]
        return {r.field: frozenset(r.value_set.split("|")) for r in g.itertuples()}

    def _populations_overlap(a: dict, b: dict) -> bool:
        """A field absent from a rule is unconstrained, so it cannot separate them."""
        for fld in set(a) & set(b):
            if not (a[fld] & b[fld]):
                return False
        return True

    def _others(rid, fld) -> tuple:
        g = cond_by_rule[rid]
        g = g[(g.field != fld) & (g.tunability != "scope")]
        return tuple(sorted(f"{r.field}:{r.operator}:{r.value_low}:{r.value_high}:{r.value_set}"
                            for r in g.itertuples()))

    def _band_key(op, lo, hi):
        f = lambda v: None if v is None or v != v else float(v)
        return (op, f(lo), f(hi))

    nums = conds[conds.operator.isin(num_ops) & (conds.tunability == "tunable")]
    for (tbl, fld), grp in nums.groupby(["table", "field"]):
        recs = [(r.rule_id, _scope_map(r.rule_id), _band_key(r.operator, r.value_low, r.value_high),
                 merged.loc[r.rule_id, "product"], merged.loc[r.rule_id, "outcome"],
                 _others(r.rule_id, fld)) for r in grp.itertuples()]
        for i in range(len(recs)):
            for j in range(i + 1, len(recs)):
                a, b = recs[i], recs[j]
                if a[3] != b[3] or a[4] != b[4] or a[5] != b[5]:
                    continue                          # they differ elsewhere
                if a[2] == b[2] or a[1] == b[1]:
                    continue                          # same band, or same population
                if not _populations_overlap(a[1], b[1]):
                    continue
                shared = {f: sorted(a[1][f] & b[1][f]) for f in set(a[1]) & set(b[1])}
                out.append({"kind": "overlapping_band", "table": tbl,
                            "rule_ids": f"{a[0]}, {b[0]}",
                            "detail": f"{fld}: {shared or 'all applicants'} match both "
                                      f"{_band(a[2])} and {_band(b[2])} — same outcome "
                                      f"{a[4]}, nothing else separates them"})

    # The description quotes a number close to — but not equal to — one the conditions
    # use. Unrelated prose numbers are ignored; a near miss is usually a typo, and the
    # description is what the bank shows the customer.
    cond_nums = (conds.groupby("rule_id")
                 .apply(lambda g: {v for v in list(g.value_low.dropna()) + list(g.value_high.dropna())},
                        include_groups=False))
    field_digits = (conds.groupby("rule_id")
                    .apply(lambda g: {float(x) for f in g.field for x in re.findall(r"\d+", f)},
                           include_groups=False))
    near = {}
    for rid, r in merged.iterrows():
        desc = r["description_en"] or ""
        quoted = {float(x) for x in re.findall(r"\b\d{2,}(?:\.\d+)?\b", desc)}
        if not quoted:
            continue
        have = cond_nums.get(rid, set()) | ({float(r["cap_amount"])} if _is_num(r["cap_amount"]) else set())
        spelled = field_digits.get(rid, set())          # e.g. V_SIMAHSIXTYBYLASTTWELEVE
        for q in quoted - have - spelled:
            for h in sorted(have, key=lambda x: abs(q - x)):
                gap = abs(q - h)
                # Ignore the client's ".1" band-boundary convention and inclusive/exclusive
                # off-by-ones; only a gap big enough to change an outcome matters.
                if gap >= 2 and gap / max(abs(q), abs(h), 1) >= 0.005 and gap / max(abs(q), abs(h), 1) < 0.25:
                    near.setdefault((r["table"], q, h), []).append(rid)
                break
    for (tbl, q, h), rids in sorted(near.items()):
        out.append({"kind": "description_mismatch", "table": tbl,
                    "rule_ids": ", ".join(rids[:4]) + (f" (+{len(rids) - 4} more)" if len(rids) > 4 else ""),
                    "detail": f"description says {q:g}, the condition uses {h:g}"
                              f" — {len(rids)} rule(s) affected"})

    # The brief plans to show policyCode as the customer-facing decline reason, so a
    # code that maps to more than one rule is ambiguous at the screen.
    coded = merged[merged["policy_code"].notna()]
    for code, grp in coded.groupby("policy_code"):
        if len(grp) > 1 and len(set(grp["signature"].fillna(""))) > 1:
            out.append({"kind": "duplicate_policy_code", "table": ", ".join(sorted(set(grp["table"]))),
                        "rule_ids": ", ".join(grp.index),
                        "detail": f"policy code {code} is used by {len(grp)} rules with "
                                  f"different conditions"})

    for _, c in conds[conds.operator == "always"].iterrows():
        out.append({"kind": "tautology", "table": c["table"], "rule_ids": c["rule_id"],
                    "detail": f"{c['field']} = {c['raw']} constrains nothing"})
    for _, c in conds[conds.operator == "unparsed"].iterrows():
        out.append({"kind": "unparsed", "table": c["table"], "rule_ids": c["rule_id"],
                    "detail": f"{c['field']} = {c['raw']}"})
    return pd.DataFrame(out, columns=["kind", "table", "rule_ids", "detail"])


def _band(t) -> str:
    op, lo, hi = t
    return f"{op} {lo:g}" + (f"..{hi:g}" if hi is not None else "")


def _is_num(v) -> bool:
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


def find_dead_columns(folder: Path | str = ".", pattern: str = "business-rules-*.xlsx") -> pd.DataFrame:
    """Columns declared in a decision table but never given a value in any row."""
    out = []
    for path in sorted(Path(folder).glob(pattern)):
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        for ws in wb.worksheets:
            if ws.title == "Mapping":
                continue
            rows = list(ws.iter_rows(values_only=True))
            if len(rows) < 2:
                continue
            hdr = rows[0]
            for j, h in enumerate(hdr):
                if h is None:
                    continue
                if all(j >= len(r) or r[j] is None for r in rows[1:]):
                    out.append({"source_file": path.name, "sheet": ws.title,
                                "column": str(h).strip()})
        wb.close()
    return pd.DataFrame(out, columns=["source_file", "sheet", "column"])




def export_inventory(out_dir: Path | str = "data/rule_inventory",
                     folder: Path | str = ".") -> dict[str, Path]:
    """Write the inventory to CSV. Returns the paths written."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    inv = build_inventory(folder)
    dead = find_dead_columns(folder)
    written = {}
    for name, df in [("rules", inv.rules), ("conditions", inv.conditions),
                     ("conflicts", inv.conflicts), ("dead_columns", dead)]:
        path = out_dir / f"{name}.csv"
        df.to_csv(path, index=False)
        written[name] = path
    return written


if __name__ == "__main__":
    for name, path in export_inventory().items():
        print(f"wrote {path}")
