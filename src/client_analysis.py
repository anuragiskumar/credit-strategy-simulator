"""Funnel, decline drivers and portfolio analytics over a replay (plan step 3).

This is the layer that answers the brief's question catalogue. It reads the hit matrix from
`client_replay` and never re-implements a rule, so a change to the rules moves every number here
at once.

It also never reads `latent_bad`. A bank only observes performance on what it booked, and only
once a loan has been on book long enough to judge; an analysis that quietly used the truth would
report a risk impact no real deployment could reproduce. `observed_performance()` is the one
place performance is read, from `booking_date`, `bad_date` and the declared bad definition.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

STAGES = ["applied", "hard_reject", "credit_policy", "eligibility", "walked_away", "booked"]

# Reasons for the stages no replayed rule decides. Labels live in config under funnel.reasons.
ELIG_PRODUCT_MIN = "elig.product_min"
ELIG_MIN_SHARE = "elig.min_share"
WALKED_ELSEWHERE = "walk.elsewhere"


def _blocking(res, stage: str | None = None) -> pd.DataFrame:
    r = res.rules
    sel = r[(r.kind == "block") & (r.matched > 0)]
    if stage:
        sel = sel[sel.stage == stage]
    cols = [c for c in sel.rule_id if c in res.hits.columns]
    return res.hits[cols]


def offered_amount(df: pd.DataFrame, res, cfg: dict) -> pd.Series:
    """The offer after every applicable cap. Caps are minimums taken together."""
    requested = df["requested_amount"].astype(float)
    offer = requested.copy()
    caps = res.rules[(res.rules.kind == "cap") & (res.rules.matched > 0)]
    income = df["monthly_income"].astype(float)
    for r in caps.itertuples():
        if r.rule_id not in res.hits.columns:
            continue
        hit = res.hits[r.rule_id].to_numpy()
        cap = r.cap_amount
        if cap is None or (isinstance(cap, float) and np.isnan(cap)):
            continue
        if isinstance(cap, str) and "income" in cap:
            multiple = float(cap.split("*")[0])
            value = income * multiple
        else:
            try:
                value = pd.Series(float(cap), index=df.index)
            except (TypeError, ValueError):
                continue
        offer = offer.where(~hit, np.minimum(offer, value))
    return offer


class OutcomeError(ValueError):
    """The observed-outcome configuration cannot be read."""


def bad_definition(cfg: dict) -> dict:
    """The declared bad definition and extract date, checked. Every performance figure uses it."""
    oc = cfg.get("outcome") or {}
    if not oc.get("as_of"):
        raise OutcomeError("outcome.as_of is not set: the engine cannot tell a loan that has not "
                           "gone bad from one it has not yet seen long enough to judge")
    bd = oc.get("bad_definition") or {}
    months = int(bd.get("within_months", 0))
    if months <= 0:
        raise OutcomeError("outcome.bad_definition.within_months must be a positive number of months")
    return {"as_of": pd.Timestamp(oc["as_of"]), "dpd": int(bd.get("dpd", 0)),
            "within_months": months}


def observed_performance(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """What the bank has actually seen of each loan, read against the declared bad definition.

    A loan is `mature` once it has been on book for the definition's whole window by the extract
    date. Only then is "not bad" an answer. An immature loan that has not gone bad yet is not a
    good loan, it is an unknown one, so `observed_bad` is NaN for it.

    An immature loan that has ALREADY gone bad is left out too. Counting its bad while leaving
    out its immature neighbours that are still paying would push the bad rate up for the same
    reason counting them as good would push it down.
    """
    d = bad_definition(cfg)
    booking = pd.to_datetime(df["booking_date"])
    bad = pd.to_datetime(df["bad_date"])
    horizon = booking + pd.DateOffset(months=d["within_months"])
    mature = booking.notna() & (horizon <= d["as_of"])
    went_bad = bad.notna() & (bad <= horizon) & (bad <= d["as_of"])
    return pd.DataFrame({
        "mature": mature,
        "observed_bad": np.where(mature, went_bad.astype(float), np.nan),
    }, index=df.index)


def stage_outcome(df: pd.DataFrame, res, cfg: dict) -> pd.DataFrame:
    """Assign every applicant the first stage they dropped out at, and why.

    The reason is the rule that caught them, derived from the replay — never assigned.
    """
    fn = cfg["funnel"]
    n = len(df)
    stage = pd.Series("booked", index=df.index, dtype="object")
    reason = pd.Series(pd.NA, index=df.index, dtype="object")
    reason_code = pd.Series(pd.NA, index=df.index, dtype="object")

    for stage_name in ("hard_reject", "credit_policy"):
        block = _blocking(res, stage_name)
        if block.empty:
            continue
        caught = block.any(axis=1) & stage.eq("booked")
        first = block.loc[caught].idxmax(axis=1) if caught.any() else pd.Series(dtype="object")
        stage.loc[caught] = stage_name
        reason.loc[caught] = first
        lookup = res.rules.set_index("rule_id")
        reason_code.loc[caught] = first.map(lookup["policy_code"]).to_numpy()

    # Eligibility has two conditions, recorded separately so the stage can be drilled into.
    # An offer failing both is credited to the product minimum: it is the absolute limit, and
    # raising the acceptable share would not rescue it.
    offer = offered_amount(df, res, cfg)
    survived = stage.eq("booked")
    below_min = survived & (offer < fn["product_min_amount"])
    below_share = survived & ~below_min & (offer < df["requested_amount"] * fn["min_acceptable_offer_ratio"])
    stage.loc[below_min | below_share] = "eligibility"
    reason.loc[below_min] = ELIG_PRODUCT_MIN
    reason.loc[below_share] = ELIG_MIN_SHARE

    walked = stage.eq("booked") & df["walked_away"]
    stage.loc[walked] = "walked_away"
    reason.loc[walked] = WALKED_ELSEWHERE

    # Performance is observed ONLY on what the bank booked, and only once a loan is mature. This
    # is the column the analysis may read; `latent_bad` is not. A replay-booked applicant the
    # bank did not actually book (the rules have changed since) has no performance at all.
    perf = observed_performance(df, cfg)
    booked = stage.eq("booked")
    return pd.DataFrame({
        "stage": pd.Categorical(stage, categories=STAGES, ordered=True),
        "reason_rule": reason, "reason_code": reason_code,
        "offered_amount": offer,
        "booked": booked,
        "mature": booked & perf["mature"],
        "observed_bad": perf["observed_bad"].where(booked),
    }, index=df.index)


def funnel(df: pd.DataFrame, outcome: pd.DataFrame) -> pd.DataFrame:
    """Guru's stage-by-stage table: how many drop out where, and how many are left.

    `entered` is how many reach a stage, and `dropped_pct_of_entered` is that stage's own loss
    rate — the figure that says how hard a stage bites, which a share of all applicants hides.
    """
    n = len(df)
    counts = outcome["stage"].value_counts().reindex(STAGES[1:], fill_value=0)
    rows, left = [], n
    rows.append({"stage": "applied", "entered": n, "dropped": 0, "left": n, "left_pct": 100.0,
                 "per_100": 100.0, "dropped_pct_of_entered": 0.0, "dropped_pct_of_total": 0.0})
    for s in STAGES[1:-1]:
        dropped, entered = int(counts[s]), left
        left -= dropped
        rows.append({"stage": s, "entered": entered, "dropped": dropped, "left": left,
                     "left_pct": round(100 * left / n, 1), "per_100": round(100 * left / n, 1),
                     "dropped_pct_of_entered": round(100 * dropped / entered, 1) if entered else 0.0,
                     "dropped_pct_of_total": round(100 * dropped / n, 1)})
    booked = int(counts["booked"])
    rows.append({"stage": "booked", "entered": booked, "dropped": 0, "left": booked,
                 "left_pct": round(100 * booked / n, 1), "per_100": round(100 * booked / n, 1),
                 "dropped_pct_of_entered": 0.0, "dropped_pct_of_total": 0.0})
    return pd.DataFrame(rows)


def funnel_layout(cfg: dict) -> dict:
    """The funnel's labels, groups and loss types, read from config and checked here.

    Grouping is declared, never inferred from row order, so moving a stage between groups is a
    config edit. Every stage must be described, and every evaluation stage must name a group
    that exists; an endpoint (applied, booked) has no group and no loss.
    """
    fn = cfg["funnel"]
    groups, stages = fn["groups"], fn["stages"]
    missing = [s for s in STAGES if s not in stages]
    if missing:
        raise ValueError(f"funnel.stages has no entry for {missing}")
    for s in STAGES:
        st = stages[s]
        if s in (STAGES[0], STAGES[-1]):
            if "group" in st:
                raise ValueError(f"{s} is an endpoint and cannot belong to a group")
        elif st.get("group") not in groups:
            raise ValueError(f"funnel.stages.{s}.group must be one of {sorted(groups)}")
    for g, spec in groups.items():
        if spec.get("loss_type") not in ("lender", "customer"):
            raise ValueError(f"funnel.groups.{g}.loss_type must be lender or customer")
    return {"order": STAGES, "groups": groups, "stages": {s: stages[s] for s in STAGES},
            "headline_top_n": int(fn["headline_top_n"]), "drill_top_n": int(fn["drill_top_n"])}


_BETWEEN_OR = re.compile(r"\bbetween\s+(\d[\d,.]*)\s+or\s+(\d[\d,.]*)", re.I)
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_OPEN_HIGH = 9_999_999          # the rule files' "no upper limit"


def clean_description(text: str | None) -> str:
    """The bank's rule text, with its one systematic slip fixed: "between 20 or 70"."""
    return _BETWEEN_OR.sub(r"between \1 and \2", str(text or "")).strip()


def _num(v) -> str:
    f = float(v)
    return f"{int(f):,}" if f.is_integer() else f"{f:,}"


def _condition_text(c) -> str | None:
    field = str(c.field).split(".")[-1].split("[")[0]
    lo, hi = c.value_low, c.value_high
    values = [v for v in str(c.value_set).split("|") if v and v != "nan"]
    shown = ", ".join(values[:4]) + (f" +{len(values) - 4}" if len(values) > 4 else "")
    op = c.operator
    if op == "outside":
        return f"{field} outside {_num(lo)}–{_num(hi)}"
    if op == "between":
        if float(hi) >= _OPEN_HIGH:
            return f"{field} ≥ {_num(lo)}"
        return f"{field} ≤ {_num(hi)}" if float(lo) == 0 else f"{field} {_num(lo)}–{_num(hi)}"
    sym = {"lt": "<", "gt": ">", "lte": "≤", "gte": "≥"}.get(op)
    if sym:
        return f"{field} {sym} {_num(lo if pd.notna(lo) else hi)}"
    if op == "in":
        return f"{field} {shown}"
    if op == "not_in":
        return f"{field} not {shown}"
    if op == "eq":
        return f"{field} = {shown or _num(lo)}"
    if op == "contains":
        return f"{field} contains {shown}"
    if op == "income_multiple_exceeded":
        return f"{field} above an income multiple"
    return None


def _words(values: list[str], joiner: str = "or", cap: int = 6) -> str:
    if len(values) > cap:
        return ", ".join(values[:cap]) + f" and {len(values) - cap} more"
    return values[0] if len(values) == 1 else ", ".join(values[:-1]) + f" {joiner} " + values[-1]


def _condition_words(c, labels: dict) -> str | None:
    """One condition as a phrase a credit committee reads: "SIMAH score is 650 or below"."""
    if not re.fullmatch(r"[\w.]+", str(c.field)):
        return f"a calculated condition holds ({c.field})"
    raw = str(c.field).split(".")[-1]
    field = labels.get(raw, raw)
    lo, hi, op = c.value_low, c.value_high, c.operator
    values = [v for v in str(c.value_set).split("|") if v and v != "nan"]
    if op == "outside":
        return f"{field} is outside {_num(lo)}–{_num(hi)}"
    if op == "between":
        if float(hi) >= _OPEN_HIGH:
            return f"{field} is {_num(lo)} or above"
        return f"{field} is {_num(hi)} or below" if float(lo) == 0 else \
            f"{field} is between {_num(lo)} and {_num(hi)}"
    v = lo if pd.notna(lo) else hi
    phrase = {"lt": "below {}", "lte": "{} or below", "gt": "above {}", "gte": "{} or above"}.get(op)
    if phrase:
        return f"{field} is " + phrase.format(_num(v))
    if op == "in" and values:
        return f"{field} is {_words(values)}"
    if op == "not_in" and values:
        return f"{field} is not {_words(values)}"
    if op == "eq":
        return f"{field} is {_words(values) if values else _num(lo)}"
    if op == "contains" and values:
        return f"{field} contains {_words(values)}"
    if op == "income_multiple_exceeded":
        return f"{field} is above the allowed multiple of income"
    return None


def rule_sentence(conditions: pd.DataFrame, rule_id: str, labels: dict | None = None) -> dict:
    """What a rule declines, in words: the test (`when`) and who it applies to (`applies_to`).

    Built from the parsed conditions, like `rule_tests`, so it can never disagree with what
    the replay evaluates. Either part is None when the rule has none.
    """
    labels = labels or {}
    c = conditions[conditions["rule_id"] == rule_id]
    when = [w for w in (_condition_words(r, labels) for r in c[c["tunability"] != "scope"].itertuples()) if w]
    scope = [w for w in (_condition_words(r, labels) for r in c[c["tunability"] == "scope"].itertuples()) if w]
    return {"when": " and ".join(when) or None, "applies_to": "; ".join(scope) or None}


def rule_tests(conditions: pd.DataFrame, rule_id: str) -> tuple[str, set[float]]:
    """What a rule actually tests, from its parsed conditions: thresholds first, then scope.

    Also returns every number the conditions use, so a description quoting different numbers
    can be caught.
    """
    c = conditions[conditions["rule_id"] == rule_id]
    c = c.assign(_scope=(c["tunability"] == "scope").astype(int)).sort_values("_scope", kind="stable")
    parts = [t for t in (_condition_text(r) for r in c.itertuples()) if t]
    numbers: set[float] = set()
    for r in c.itertuples():
        for v in (r.value_low, r.value_high, *str(r.value_set).split("|")):
            try:
                numbers.add(float(v))
            except (TypeError, ValueError):
                pass
    return " · ".join(parts), {n for n in numbers if n == n}


def description_disagrees(description: str, numbers: set[float]) -> bool:
    """True when the description quotes a number the rule's conditions never use."""
    quoted = {float(n) for n in _NUMBER.findall(description.replace(",", ""))}
    return bool(quoted) and bool(numbers) and not quoted <= numbers


def funnel_rules(res, outcome: pd.DataFrame, cfg: dict,
                 conditions: pd.DataFrame | None = None) -> list[dict]:
    """Per evaluation stage, how many applicants each rule caught FIRST: the funnel drill-down.

    Counted from `reason_rule`, one reason per applicant, so a stage's rules sum to its total
    (`counted` is exported beside `total` so the screen can show it if they ever disagree).
    No top-N cut: every rule that caught anyone is listed and the screen decides how many to show.
    Not `decline_drivers`, whose counts are any-match and overlap.

    Each replayed rule also carries `sole_cause`: applicants this rule alone stops, who would
    pass every other blocking rule if only it were removed (they may still fail a finance cap
    afterwards). It is never more than `count`, and a stage's sole causes sum to less than its
    total by `multi_caught`, the applicants stopped by more than one rule.
    """
    top_n = int(cfg["funnel"]["headline_top_n"])
    labels = cfg["funnel"].get("reasons", {})
    lookup = res.rules.drop_duplicates("rule_id").set_index("rule_id")
    block = _blocking(res)
    arr = block.to_numpy()
    only_one = arr.sum(axis=1) == 1 if arr.size else np.zeros(len(outcome), dtype=bool)
    sole = {rid: int((arr[:, j] & only_one).sum()) for j, rid in enumerate(block.columns)}
    out = []
    for stage in STAGES[1:-1]:
        reasons = outcome.loc[outcome["stage"] == stage, "reason_rule"].astype("object")
        total = int(len(reasons))
        counts = reasons.fillna("unrecorded").value_counts()
        ordered = sorted(counts.items(), key=lambda kv: (-kv[1], str(kv[0])))
        rows = []
        for rid, count in ordered:
            row = {"rule_id": rid, "count": int(count),
                   "pct_of_stage": round(100 * count / total, 1) if total else 0.0}
            if rid in lookup.index:
                r = lookup.loc[rid]
                label = clean_description(r["description"]) or rid
                tests, numbers = rule_tests(conditions, rid) if conditions is not None else ("", set())
                row.update(label=label, policy_code=r["policy_code"], relaxable=bool(r["relaxable"]),
                           locked=bool(r.get("locked", False)),
                           fixed_field=bool(r.get("fixed_field", False)),
                           sole_cause=sole.get(rid),
                           tests=tests or None,
                           description_disagrees=description_disagrees(label, numbers))
            else:
                row.update(label=labels.get(rid, rid), policy_code=None, relaxable=None,
                           locked=False, fixed_field=False, sole_cause=None,
                           tests=None, description_disagrees=False)
            rows.append(row)
        top = sum(c for _, c in ordered[:top_n])
        sole_known = [r["sole_cause"] for r in rows if r["sole_cause"] is not None]
        sole_total = sum(sole_known) if sole_known else None
        out.append({"stage": stage, "total": total, "counted": int(counts.sum()),
                    "sole_total": sole_total,
                    "multi_caught": total - sole_total if sole_total is not None else None,
                    "n_rules": len(rows), "top_n": top_n,
                    "top_n_pct": round(100 * top / total, 1) if total else 0.0,
                    "rules": rows})
    return out


VERDICTS = {
    "review": "Worth reviewing",
    "earning": "Earning their place",
    "no_estimate": "No estimate",
    "overlap": "Only with other rules",
    "not_relaxable": "Not relaxable",
}
"""The groups Decline Drivers sorts rules into, in the order it shows them. One place decides a
rule's group, so the screen, the Simulator's presets and the CLI never disagree about it."""


def driver_verdict(row) -> str:
    """Which group a rule belongs in. Read in order: each test assumes the ones before it failed."""
    if not row["relaxable"]:
        return "not_relaxable"          # regulatory, bureau or identity: not a risk trade-off
    if row["declines_alone"] == 0:
        return "overlap"                # switching it off alone frees nobody; only a scenario can
    if not row.get("risk_known"):
        return "no_estimate"
    return "review" if row.get("earns_its_place") is False else "earning"


def decline_drivers(df: pd.DataFrame, res, outcome: pd.DataFrame, cfg: dict,
                    model=None, include_oracle: bool = False,
                    booked_bad_rate: float | None = None) -> pd.DataFrame:
    """Which rule declines the most applicants, and how many it declines ON ITS OWN.

    "On its own" is the question Guru actually asked. Switching off a rule that always fires
    alongside another buys nothing, because the other one still catches those people — so
    `declines_alone` is the column that answers "what is the one thing I change?".

    The risk side is deliberately awkward. Declined applicants have no repayment history, so
    the honest answer comes from the PD model and is refused outright for groups the booked
    population never covered. Pass `include_oracle=True` only on synthetic data, and only to
    show how close the honest estimate got.

    `booked_bad_rate` is what a rule's risk is compared with. Pass the baseline's, which comes
    from mature loans: in a recent application window hardly any booked loan has an outcome yet.
    """
    from src import client_risk

    block = _blocking(res)
    if block.empty:
        return pd.DataFrame()
    arr = block.to_numpy()
    only_one = arr.sum(axis=1) == 1
    lookup = res.rules.set_index("rule_id")
    booked_bad = (booked_bad_rate if booked_bad_rate is not None
                  else float(outcome.loc[outcome["booked"], "observed_bad"].mean()))

    rows = []
    for j, rule_id in enumerate(block.columns):
        caught = arr[:, j]
        alone = caught & only_one
        r = lookup.loc[rule_id]
        row = {
            "rule_id": rule_id, "table": r["table"], "stage": r["stage"],
            "policy_code": r["policy_code"], "description": r["description"],
            "label": clean_description(r["description"]) or rule_id,
            "fields": r["fields"], "relaxable": bool(r["relaxable"]),
            "declines": int(caught.sum()),
            "declines_alone": int(alone.sum()),
            "share_of_applicants": round(100 * caught.mean(), 2),
            "sole_reason_pct": round(100 * alone.sum() / max(caught.sum(), 1), 1),
        }
        if model is not None:
            est = client_risk.predict_group(model, df, alone, cfg)
            row["risk_known"] = est.get("known", False)
            row["est_bad_rate_if_relaxed"] = est.get("estimated_bad_rate")
            row["risk_note"] = est.get("reason")
            # Does the rule earn its place? Only meaningful when we can estimate at all.
            # A rule the bank may not drop is never reported as failing to earn its place:
            # the engine would be recommending a compliance breach.
            row["earns_its_place"] = (
                True if not r["relaxable"]
                else None if not est.get("known")
                else bool(est["estimated_bad_rate"] > booked_bad * cfg["drivers"]["earns_place_multiple"]))
            if bool(r.get("locked", False)):
                row["risk_note"] = "locked: the bank has declared it a regulatory knock-out. " \
                                   "Relaxing it is not a risk trade-off."
            elif not r["relaxable"]:
                row["risk_note"] = "not relaxable: rests on a fixed field (regulatory, " \
                                   "bureau or identity). Relaxing it is not a risk trade-off."
            row["verdict"] = driver_verdict(row)
        if include_oracle:
            row["oracle_bad_rate"] = round(client_risk.oracle_bad_rate(df, alone), 4)
        rows.append(row)
    out = pd.DataFrame(rows)
    return out.sort_values("declines_alone", ascending=False).reset_index(drop=True)


def by_source(df: pd.DataFrame, outcome: pd.DataFrame, column: str) -> pd.DataFrame:
    """Approval and decline rates by channel, source or agent — Guru's question 4."""
    j = df[[column]].join(outcome[["stage", "booked"]])
    g = j.groupby(column, observed=True)
    out = pd.DataFrame({
        "applicants": g.size(),
        "booked": g["booked"].sum(),
        "approval_rate": (100 * g["booked"].mean()).round(1),
    })
    declines = j[j["stage"].isin(["hard_reject", "credit_policy"])]
    out["declines"] = declines.groupby(column, observed=True).size().reindex(out.index, fill_value=0)
    out["share_of_all_declines"] = (100 * out["declines"] / max(int(out["declines"].sum()), 1)).round(1)
    return out.sort_values("declines", ascending=False)


def portfolio(df: pd.DataFrame, outcome: pd.DataFrame, by: str,
              score_bands: list | None = None,
              perf: tuple[pd.DataFrame, pd.DataFrame] | None = None) -> pd.DataFrame:
    """Booked book sliced by a segment, with performance — questions 5 and 6.

    Volumes come from the window. The bad rate comes from `perf` (the mature cohort's applicants
    and outcome) when given, because a window of recent business has almost no outcomes yet.
    `observed` says how many loans each slice's bad rate rests on.
    """
    booked = outcome["booked"]
    j = df[booked].join(outcome.loc[booked, ["observed_bad", "offered_amount"]])
    g = j.groupby(by, observed=True)
    if perf is not None:
        p_df, p_out = perf
        risk = p_df[[by]].join(p_out[["observed_bad"]]).groupby(by, observed=True)["observed_bad"]
    else:
        risk = g["observed_bad"]
    out = pd.DataFrame({
        "booked": g.size(),
        "exposure": g["offered_amount"].sum().round(0),
    })
    out["observed"] = risk.count().reindex(out.index).fillna(0).astype(int)
    out["bad_rate"] = (100 * risk.mean()).round(2).reindex(out.index)
    out["share_of_book"] = (100 * out["booked"] / out["booked"].sum()).round(1)
    out["share_of_exposure"] = (100 * out["exposure"] / out["exposure"].sum()).round(1)
    return out.sort_values("share_of_exposure", ascending=False)


def with_score_band(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """The applicants with a `score_band` column for slicing, "no score" for a missing score."""
    bands = pd.cut(df["simah_score"], cfg["portfolio"]["score_bands"]).astype(str)
    return df.assign(score_band=bands.where(df["simah_score"].notna(), "no score"))


def concentration_flags(book: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Over- and under-exposure against an even split — question 6."""
    limits = cfg["portfolio"]
    even = 100.0 / max(len(book), 1)
    flags = []
    for name, row in book.iterrows():
        share = row["share_of_exposure"]
        if share >= limits["over_exposed_multiple"] * even:
            flags.append({"slice": name, "share_of_exposure": share, "flag": "over-exposed"})
        elif share <= limits["under_exposed_multiple"] * even:
            flags.append({"slice": name, "share_of_exposure": share, "flag": "under-exposed"})
    return pd.DataFrame(flags, columns=["slice", "share_of_exposure", "flag"])
