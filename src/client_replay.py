"""Replay the client's rules over an applicant population (plan step 3).

Each rule becomes a vectorised predicate over the fields its own decision table names. The
result is a hit matrix — applicants × rules — which everything downstream reads: the funnel,
the decline-driver ranking, the simulator and the optimiser.

Three things the export does not tell us, so they are decisions recorded in config rather
than assumptions buried in code. `config_client.yaml: replay` holds them and the report states
which was used:

  * evaluation order — 33 overlapping bands mean order changes the outcome;
  * whether a condition on a missing value matches;
  * what happens to an applicant no rule matches.

All three are open questions for the client (see SYNTHETIC-POPULATION.md). Changing one is a config
edit, and the funnel is expected to move when it changes.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src import client_loader
from src.rule_inventory import Inventory

# Rule outcomes that stop an applicant, as opposed to capping their offer.
BLOCKING_OUTCOMES = {"decline", "fail"}

# Fields whose presence makes a rule off-limits to the optimiser, however much it costs in
# approvals. Two kinds: facts the regulator decides (PEP, diplomatic service), and attributes
# a bank must not decide on (gender). Bureau default and judgement events are added by prefix
# below — they are the bureau's verdict, not a threshold the client chose.
#
# Nationality and customer segment are deliberately NOT here. They scope a rule to a
# population; the tunable threshold inside it is still the bank's to move. Marking them
# off-limits would put 177 of 226 rules beyond the optimiser for no reason.
NON_RELAXABLE_FIELDS = {"politicallyexposedperson", "relatedtopep", "diplomaticservice",
                        "gender"}
NON_RELAXABLE_PREFIXES = ("v_simah", "v_sim_", "vsimah", "simbc")
NEVER = "never_evaluable"


@dataclass(frozen=True)
class CompiledRule:
    rule_id: str
    table: str
    outcome: str
    kind: str                 # "block", "cap" or "pass"
    cap_amount: str | None
    policy_code: str | None
    description: str
    is_active: bool
    stage: str                # "hard_reject" or "credit_policy" or "eligibility"
    fields: tuple[str, ...]
    evaluable: bool
    relaxable: bool = True
    locked: bool = False          # declared in config: a regulatory knock-out
    fixed_field: bool = False     # inferred: tests a field the bank cannot relax
    note: str = ""


def _as_float(series: pd.Series) -> np.ndarray:
    return pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)


def _condition_mask(frame: pd.DataFrame, cond, null_matches: bool) -> np.ndarray | None:
    """Boolean array: True where this applicant satisfies the condition.

    Returns None when the field is not available, which makes the whole rule unevaluable.
    """
    field, op = cond.field, cond.operator
    if op == "always":
        return np.ones(len(frame), dtype=bool)
    if field not in frame.columns:
        return None

    if op in {"lt", "lte", "gt", "gte", "eq", "between", "outside"}:
        v = _as_float(frame[field])
        known = ~np.isnan(v)
        with np.errstate(invalid="ignore"):
            if op == "lt":
                m = v < cond.value_low
            elif op == "lte":
                m = v <= cond.value_low
            elif op == "gt":
                m = v > cond.value_low
            elif op == "gte":
                m = v >= cond.value_low
            elif op == "eq":
                m = v == cond.value_low
            elif op == "between":
                m = (v >= cond.value_low) & (v <= cond.value_high)
            else:
                m = (v < cond.value_low) | (v > cond.value_high)
        return np.where(known, m, null_matches)

    if op in {"in", "not_in", "contains"}:
        values = list(set(str(cond.value_set).split("|"))) if cond.value_set else []
        col = frame[field]
        present = col.notna().to_numpy()
        if op == "contains":
            text = col.astype("string").fillna("")
            m = np.zeros(len(col), dtype=bool)
            for kw in values:
                m |= text.str.contains(kw, regex=False, na=False).to_numpy()
            return m
        hit = col.astype("string").isin(values).to_numpy()
        m = hit if op == "in" else ~hit
        # The client writes not(...,null) to exclude missing values as well as the listed ones.
        return np.where(present, m, null_matches)

    if op == "income_multiple_exceeded":
        if "income" not in frame.columns or "loanamount" not in frame.columns:
            return None
        income, amount = _as_float(frame["income"]), _as_float(frame["loanamount"])
        with np.errstate(invalid="ignore"):
            m = amount > cond.value_low * income
        return np.where(np.isnan(income) | np.isnan(amount), null_matches, m)

    return None                                        # unparsed: cannot be evaluated


def locked_rules(cfg: dict) -> frozenset[str]:
    """The rules the bank has declared regulatory knock-outs (config replay.locked_rules)."""
    return frozenset(cfg.get("replay", {}).get("locked_rules") or ())


def compile_rules(inv: Inventory, *, product: str, include_inactive: bool = False,
                  stage_map: dict[str, str] | None = None,
                  locked: frozenset[str] = frozenset()) -> list[CompiledRule]:
    """Select the rules that apply to one product and tag each with a funnel stage.

    Two different reasons stop a rule being relaxed, and they are kept apart because one is
    known and one is guessed: `locked` is the bank's declaration; `fixed_field` is inferred
    from the fields a rule tests. Either makes it non-relaxable.
    """
    rules, conds = inv.rules, inv.conditions
    unknown = sorted(set(locked) - set(rules["rule_id"]))
    if unknown:
        raise ValueError(f"replay.locked_rules names rules that do not exist: {unknown}")
    applicable = rules[(rules.table != "employer_keyword_check")
                       & (rules["product"].isin([product, "ALL"]) | rules["product"].isna())]
    by_rule = {rid: g for rid, g in conds.groupby("rule_id")}
    out = []
    for r in applicable.itertuples():
        outcome = (r.outcome or "").lower()
        if outcome == "pass":
            kind = "pass"
        elif outcome in BLOCKING_OUTCOMES:
            kind = "block"
        elif outcome == "exception":
            kind = "cap" if r.exception_kind == "amount_cap" else "block"
        elif outcome == "inactive":
            kind = "block"
        else:
            kind = "pass"
        g = by_rule.get(r.rule_id)
        fields = tuple(sorted(set(g.field))) if g is not None else ()
        # Relaxable means two things at once: there is a number to move, and moving it is
        # the bank's call. Code can measure what a rule costs; it cannot know the bank is
        # allowed to drop it, so anything regulatory stays a human's decision.
        fixed_field = bool(g is not None and (
            g.field.isin(NON_RELAXABLE_FIELDS).any()
            or g.field.str.startswith(NON_RELAXABLE_PREFIXES).any()))
        is_locked = r.rule_id in locked
        relaxable = bool(g is not None and (g.tunability == "tunable").any()
                         and not fixed_field and not is_locked)
        out.append(CompiledRule(
            rule_id=r.rule_id, table=r.table, outcome=r.outcome or "", kind=kind,
            cap_amount=r.cap_amount if isinstance(r.cap_amount, str) else None,
            policy_code=r.policy_code, description=r.description_en or "",
            is_active=bool(r.is_active),
            stage=(stage_map or {}).get(r.table, "credit_policy"),
            fields=fields, evaluable=True, relaxable=relaxable,
            locked=is_locked, fixed_field=fixed_field))
    if not include_inactive:
        out = [c for c in out if c.is_active]
    return out


@dataclass
class ReplayResult:
    hits: pd.DataFrame            # applicants x rule_id, True where the rule matched
    rules: pd.DataFrame           # one row per rule, with how many it caught
    unevaluable: list[str]

    def matched(self, rule_id: str) -> np.ndarray:
        return self.hits[rule_id].to_numpy()


def prepare_frames(df: pd.DataFrame, cfg: dict) -> dict[str, pd.DataFrame]:
    """Render the applicants into every decision table's dialect, once.

    The simulator replays hundreds of times over the same population; only the rules change,
    never the applicants. Preparing the frames once takes this from seconds to milliseconds.
    """
    keywords = list(client_loader.keyword_list(cfg["replay"].get("rules_folder", ".")))
    frames = {t: client_loader.rule_frame(df, t, keywords=keywords)
              for t in ("racAndPolicies", "simati_chk_IAF", "yknBasicCheckValidation")}
    frames["yakeen-post-validation"] = frames["simati_chk_IAF"]
    return frames


def replay(df: pd.DataFrame, inv: Inventory, cfg: dict, *,
           overrides: dict[str, dict] | None = None,
           frames: dict[str, pd.DataFrame] | None = None) -> ReplayResult:
    """Evaluate every applicable rule against every applicant.

    `overrides` retunes a rule for a what-if: {rule_id: {"value_low": 650}} or
    {rule_id: {"enabled": False}}. Used by the simulator; unused here.
    """
    rep = cfg["replay"]
    compiled = compile_rules(inv, product=cfg["product"],
                             include_inactive=rep["include_inactive_rules"],
                             stage_map=rep["stage_by_table"], locked=locked_rules(cfg))
    overrides = overrides or {}
    compiled = [c for c in compiled if overrides.get(c.rule_id, {}).get("enabled", True)]

    frames = frames if frames is not None else prepare_frames(df, cfg)

    conds = inv.conditions
    by_rule = {rid: g for rid, g in conds.groupby("rule_id")}
    null_matches = rep["condition_on_missing_value_matches"]

    hits, rows, unevaluable = {}, [], []
    for c in compiled:
        frame = frames.get(c.table)
        if frame is None:
            unevaluable.append(c.rule_id)
            continue
        mask = np.ones(len(df), dtype=bool)
        ok = True
        for cond in by_rule.get(c.rule_id, pd.DataFrame()).itertuples():
            patched = _apply_override(cond, overrides.get(c.rule_id))
            m = _condition_mask(frame, patched, null_matches)
            if m is None:
                ok = False
                break
            mask &= m
        if not ok:
            unevaluable.append(c.rule_id)
            continue
        hits[c.rule_id] = mask
        rows.append({"rule_id": c.rule_id, "table": c.table, "stage": c.stage,
                     "outcome": c.outcome, "kind": c.kind, "cap_amount": c.cap_amount,
                     "policy_code": c.policy_code, "description": c.description,
                     "is_active": c.is_active, "relaxable": c.relaxable,
                     "locked": c.locked, "fixed_field": c.fixed_field,
                     "matched": int(mask.sum()), "fields": ", ".join(c.fields)})
    hit_df = pd.DataFrame(hits, index=df.index) if hits else pd.DataFrame(index=df.index)
    return ReplayResult(hits=hit_df, rules=pd.DataFrame(rows), unevaluable=unevaluable)


def _apply_override(cond, override: dict | None):
    """Return the condition, with its threshold replaced when the simulator asks for one.

    The override must name the field it applies to. A rule commonly tests several — the
    CRIF-and-SIMAH decline rules test two scores — and patching all of them while the user
    asked to move one silently moves the other, which shows up as approvals falling when
    the user loosened something.
    """
    if not override:
        return cond
    patch = {k: v for k, v in override.items() if k in {"value_low", "value_high"}}
    if not patch:
        return cond
    target = override.get("field")
    if target is not None and cond.field != target:
        return cond
    return cond._replace(**patch) if hasattr(cond, "_replace") else cond
