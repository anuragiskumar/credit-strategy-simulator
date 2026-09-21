"""What-if simulation and swap-set analysis (plan step 4).

Answers questions 7 and 8: change a threshold, get the new approval rate and the risk impact,
and see exactly who moves. Everything is a re-replay of the real rules — no rule is
re-implemented here, so a scenario cannot drift from the live rule set.

The risk side is where this has to be careful. Swap-ins are applicants the bank declined, so
it has never seen them repay. Their bad rate is an estimate from the PD model, refused
outright when they sit outside the booked population. The brief's warning, in one line: below
the historical cutoff a confident number tells a CxO to loosen a rule for free.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src import client_analysis as A, client_replay, client_risk


@dataclass(frozen=True)
class Lever:
    """One change a person can describe in a sentence."""
    label: str
    overrides: dict = field(default_factory=dict)
    skipped_wrong_direction: int = 0

    def __post_init__(self):
        if not self.overrides:
            raise ValueError("a lever must change something")


# Which way a threshold has to move to LOOSEN a rule depends on its operator. Lowering a
# `>=` cutoff does not relax a decline rule, it widens it — the opposite of what was asked.
RELAX_DIRECTION = {"lt": -1, "lte": -1, "gt": +1, "gte": +1}


def field_aliases(field_name: str) -> set[str]:
    """Every rule field that means the same thing as this one.

    Income is `income` in racAndPolicies and `netIncome.totalIncome` in simati; length of
    service is `monthCnt` and `netIncome.lengthOfService`. A lever on "income" that moved
    only one of them would report a change of nothing and look like the rule set was inert.
    """
    from src import client_loader
    source = client_loader.FIELD_SOURCES.get(field_name)
    if source is None:
        return {field_name}
    return {f for f, s in client_loader.FIELD_SOURCES.items() if s == source}


def field_lever(inv, field_name: str, from_value: float, to_value: float,
                *, product: str, label: str | None = None,
                locked: frozenset[str] = frozenset(),
                allow_tighten: bool = False) -> Lever:
    """Move every threshold of `from_value` on `field_name` to `to_value`.

    This is Guru's "what is that one thing I change?". 102 rules turn on three SIMAH
    cutoffs, so one lever moves a hundred rules at once.

    Only conditions for which the move is in the loosening direction are changed. A rule
    that tests the same number the other way round is left alone and counted in
    `skipped_wrong_direction`, because silently tightening it while the user asked to
    loosen would show up as an approval *fall* with no explanation.

    A locked rule (a regulatory knock-out) keeps its threshold; only that rule is skipped and
    counted in `skipped_locked`. Other rules testing the same field still move.

    `allow_tighten=True` is for a person who asked for exactly this move, loosening or not:
    every condition at `from_value` moves to `to_value` and nothing is skipped for its
    direction. The optimiser never sets it, because it is searching for loosenings.
    """
    conds, rules = inv.conditions, inv.rules
    scope = rules[(rules["product"].isin([product, "ALL"]) | rules["product"].isna())]
    aliases = field_aliases(field_name)
    hit = conds[conds.rule_id.isin(scope.rule_id) & conds.field.isin(aliases)
                & (conds.value_low == from_value)]
    if hit.empty:
        raise ValueError(f"no {product} rule tests {field_name} at {from_value}")

    # A Pass rule is the mirror of the Fail rule beside it — simati writes `<3500` Fail and
    # `>=3500` Pass as a pair. Loosening one means moving both the same way, so the pair
    # stays coherent and no applicant falls between them.
    kind = rules.set_index("rule_id")["outcome"].str.lower().to_dict()
    wanted = +1 if to_value > from_value else -1
    overrides, skipped, skipped_locked = {}, 0, 0
    for r in hit.itertuples():
        if r.rule_id in locked:
            skipped_locked += 1
            continue
        direction = RELAX_DIRECTION.get(r.operator)
        if direction is not None and kind.get(r.rule_id) == "pass":
            direction = -direction
        if not allow_tighten and (direction is None or direction != wanted):
            skipped += 1
            continue
        overrides[r.rule_id] = {"field": r.field, "value_low": to_value}
    if not overrides and skipped_locked:
        raise ValueError(f"every rule testing {field_name} at {from_value:g} is locked")
    if not overrides:
        raise ValueError(
            f"moving {field_name} {from_value:g} to {to_value:g} would tighten every rule "
            f"that tests it, not loosen any")
    lever = Lever(label=label or f"{field_name}: {from_value:g} -> {to_value:g}",
                  overrides=overrides)
    object.__setattr__(lever, "skipped_wrong_direction", skipped)
    object.__setattr__(lever, "skipped_locked", skipped_locked)
    return lever


def rule_lever(rule_id: str, *, enabled: bool = True, value_low: float | None = None,
               field_name: str | None = None, label: str | None = None) -> Lever:
    """Switch one rule off, or retune one of its thresholds.

    The client already switches rules off by hand — ten SIMAH rules are marked Inactive — so this is
    the change they recognise. Retuning requires `field_name`, because a rule usually tests
    more than one field and only the named one may move.
    """
    patch: dict = {}
    if not enabled:
        patch["enabled"] = False
    if value_low is not None:
        if field_name is None:
            raise ValueError("retuning a rule needs field_name: rules test several fields")
        patch["field"] = field_name
        patch["value_low"] = value_low
    return Lever(label=label or (f"{rule_id} off" if not enabled
                                 else f"{rule_id} -> {value_low:g}"),
                 overrides={rule_id: patch})


NUMERIC_OPERATORS = {"lt", "lte", "gt", "gte", "between", "outside"}


class NotEditable(ValueError):
    """A change a person asked for that the engine will not make, with the reason why."""


def editable_reason(base: "Baseline", rule_id: str) -> str | None:
    """Why this rule cannot be changed in a what-if, or None when it can.

    The same test the optimiser applies: a rule the bank declared a regulatory knock-out, or
    one resting on a field the bank cannot relax (PEP, gender, bureau verdicts), is never
    offered — not by the search, and not by a person clicking through the rule list either.
    """
    c = base.res.compiled.get(rule_id)
    if c is None:
        return "not a rule of this product"
    if not c.is_active:
        return "inactive: the client has already switched it off"
    if c.kind == "pass":
        return "a Pass rule: it moves with the Fail rule it mirrors"
    if c.locked:
        return "locked: the bank has declared it a regulatory knock-out"
    if c.fixed_field:
        return "rests on a fixed field (regulatory, bureau or identity)"
    if not c.relaxable:
        return "has no tunable threshold: switching it off is a policy decision, not a what-if"
    if rule_id in base.res.unevaluable:
        return "cannot be evaluated against these applicants"
    return None


def editable_thresholds(inv, rule_id: str) -> list[dict]:
    """The numbers in a rule a person may move: its tunable numeric conditions."""
    c = inv.conditions
    rows = c[(c.rule_id == rule_id) & (c.tunability == "tunable")
             & c.operator.isin(NUMERIC_OPERATORS) & c.value_low.notna()]
    out = []
    for r in rows.itertuples():
        out.append({"field": r.field, "operator": r.operator,
                    "value_low": float(r.value_low),
                    "value_high": (float(r.value_high) if r.operator in {"between", "outside"}
                                   and pd.notna(r.value_high) else None)})
    return out


def _widens(operator: str, old: dict, new: dict) -> tuple[bool, bool]:
    """(matches more applicants, matches fewer) for a threshold edit on one condition."""
    lo0, hi0 = old["value_low"], old.get("value_high")
    lo1 = new.get("value_low", lo0)
    hi1 = new.get("value_high", hi0)
    more = fewer = False
    if operator in {"lt", "lte"}:
        more, fewer = lo1 > lo0, lo1 < lo0
    elif operator in {"gt", "gte"}:
        more, fewer = lo1 < lo0, lo1 > lo0
    elif operator == "between":
        more = lo1 < lo0 or (hi0 is not None and hi1 > hi0)
        fewer = lo1 > lo0 or (hi0 is not None and hi1 < hi0)
    elif operator == "outside":
        more = lo1 > lo0 or (hi0 is not None and hi1 < hi0)
        fewer = lo1 < lo0 or (hi0 is not None and hi1 > hi0)
    return more, fewer


def _mirrors(inv, rule_id: str, field_name: str, old: dict) -> list[str]:
    """Pass rules written as the other arm of this rule, on the same threshold.

    simati writes `<3500` Fail and `>=3500` Pass as a pair with identical scope. Moving the
    Fail arm alone leaves the pair incoherent, so a rule-level edit moves both — the same
    property `field_lever` has, applied to one rule.
    """
    rules, conds = inv.rules.set_index("rule_id"), inv.conditions
    if rule_id not in rules.index:
        return []
    me = rules.loc[rule_id]
    mine = conds[conds.rule_id == rule_id]
    others = mine[mine.field != field_name]
    key = lambda g: sorted((r.field, r.operator, str(r.value_set), str(r.value_low),
                            str(r.value_high)) for r in g.itertuples())
    scope_key = key(others)
    out = []
    peers = rules[(rules.table == me.table) & (rules.index != rule_id)
                  & (rules.outcome.str.lower() == "pass")]
    for pid in peers.index:
        theirs = conds[conds.rule_id == pid]
        arm = theirs[theirs.field == field_name]
        if len(arm) != 1 or arm.value_low.iloc[0] != old["value_low"]:
            continue
        if key(theirs[theirs.field != field_name]) == scope_key:
            out.append(pid)
    return out


def threshold_lever(base: "Baseline", inv, rule_id: str, field_name: str, *,
                    value_low: float | None = None, value_high: float | None = None,
                    label: str | None = None) -> Lever:
    """Edit one threshold of one rule, in either direction — "what if this were 4000?".

    Unlike `field_lever`, this does exactly what the person asked, tightening included: a
    tightening is the only way anybody is ever newly declined, and it is a question a bank
    genuinely asks. The lever records which way it went so the screen can say so.
    """
    reason = editable_reason(base, rule_id)
    if reason:
        raise NotEditable(f"{rule_id} cannot be changed: {reason}")
    match = [t for t in editable_thresholds(inv, rule_id) if t["field"] == field_name]
    if not match:
        raise NotEditable(f"{rule_id} has no tunable threshold on {field_name}")
    old = match[0]
    new: dict = {}
    for key, v in (("value_low", value_low), ("value_high", value_high)):
        if v is None:
            continue
        v = float(v)
        if not np.isfinite(v):
            raise NotEditable(f"{key} must be a finite number")
        if key == "value_high" and old["value_high"] is None:
            raise NotEditable(f"{rule_id} {field_name} has a single threshold, not a range")
        new[key] = v
    if not new:
        raise NotEditable("give the new value for the threshold")
    lo = new.get("value_low", old["value_low"])
    hi = new.get("value_high", old["value_high"])
    if hi is not None and lo > hi:
        raise NotEditable(f"the range {lo:g}-{hi:g} is back to front")
    if all(new.get(k, old[k]) == old[k] for k in ("value_low", "value_high")):
        raise NotEditable(f"{rule_id} {field_name} is already at that value")

    more, fewer = _widens(old["operator"], old, new)
    # A decline or cap rule that matches more applicants is tighter; fewer, looser.
    direction = "mixed" if more and fewer else "tighten" if more else "loosen" if fewer else "none"
    patch = {"thresholds": {field_name: new}}
    overrides = {rule_id: patch}
    for mirror in _mirrors(inv, rule_id, field_name, old):
        overrides[mirror] = {"thresholds": {field_name: dict(new)}}

    def show(t):
        return f"{t['value_low']:g}" + (f"-{t['value_high']:g}" if t.get("value_high") is not None else "")
    lever = Lever(label=label or f"{rule_id} {field_name}: {show(old)} -> "
                                 f"{show({'value_low': lo, 'value_high': hi})}",
                  overrides=overrides)
    object.__setattr__(lever, "direction", direction)
    return lever


def off_lever(base: "Baseline", rule_id: str, *, label: str | None = None) -> Lever:
    """Switch one rule off, refusing a rule the bank may not drop."""
    reason = editable_reason(base, rule_id)
    if reason:
        raise NotEditable(f"{rule_id} cannot be switched off: {reason}")
    lever = rule_lever(rule_id, enabled=False, label=label)
    object.__setattr__(lever, "direction", "loosen")
    return lever


def combine(*levers: Lever, label: str | None = None) -> Lever:
    """Several changes at once, for the optimiser's option B and C."""
    merged: dict = {}
    for lv in levers:
        for rule_id, patch in lv.overrides.items():
            into = merged.setdefault(rule_id, {})
            for key, value in patch.items():
                if key == "thresholds":
                    for f, bounds in value.items():
                        into.setdefault("thresholds", {}).setdefault(f, {}).update(bounds)
                else:
                    into[key] = value
    return Lever(label=label or " + ".join(lv.label for lv in levers), overrides=merged)


@dataclass
class FullReplay:
    """The whole file, replayed once under the current rules. Windows are row masks over it."""
    df: pd.DataFrame
    frames: dict
    res: client_replay.ReplayResult


def full_replay(df: pd.DataFrame, inv, cfg: dict) -> FullReplay:
    """Replay one product's applicants under that product's rules.

    A file can carry several products. Replaying IJMB applicants against TWQR rules would
    decide them by a policy nobody applied to them, so the file is cut to `cfg["product"]` here,
    once, and everything downstream only ever sees that product.
    """
    df = df[df["product"] == cfg["product"]]
    frames = client_replay.prepare_frames(df, cfg)
    return FullReplay(df=df, frames=frames,
                      res=client_replay.replay(df, inv, cfg, frames=frames))


@dataclass
class Cohort:
    """The performance evidence: booked loans that have run the whole performance window.

    Drawn from the whole file, not the application window. Recent applications have not had
    time to go bad, so the bad rate, the PD model and every observed swap-out rate come from
    here, wherever the application window sits.
    """
    df: pd.DataFrame
    res: client_replay.ReplayResult
    outcome: pd.DataFrame
    frames: dict

    @property
    def booked_from(self):
        return pd.to_datetime(self.df["booking_date"]).min()

    @property
    def booked_to(self):
        return pd.to_datetime(self.df["booking_date"]).max()


@dataclass
class Baseline:
    df: pd.DataFrame                   # the application window's applicants
    res: client_replay.ReplayResult
    outcome: pd.DataFrame
    model: client_risk.PDModel
    cfg: dict                          # with the bad definition set to the window's months
    frames: dict = field(default_factory=dict)
    perf: Cohort | None = None
    window: object = None              # the resolved client_context.AnalysisWindow
    whole: tuple | None = None         # (applicants, outcome) over the product's whole file

    @property
    def approval_rate(self) -> float:
        return float(self.outcome["booked"].mean())

    @property
    def booked_bad_rate(self) -> float:
        """Over mature booked loans only — the performance cohort, not the window."""
        if self.perf is not None:
            return float(self.perf.outcome["observed_bad"].mean())
        return float(self.outcome.loc[self.outcome["booked"], "observed_bad"].mean())

    @property
    def observed_loans(self) -> int:
        """How many booked loans the bad rate actually rests on."""
        if self.perf is not None:
            return int(len(self.perf.df))
        return int(self.outcome["observed_bad"].notna().sum())

    def window_dict(self) -> dict | None:
        """The window this baseline ran on, and the loans its risk figures rest on."""
        if self.window is None:
            return None
        out = self.window.to_dict()
        out["applicants"] = int(len(self.df))
        if self.perf is not None:
            out["mature_loans"] = self.observed_loans
            out["mature_booked_from"] = self.perf.booked_from.strftime("%Y-%m-%d")
            out["mature_booked_to"] = self.perf.booked_to.strftime("%Y-%m-%d")
        return out


def build_baseline(df: pd.DataFrame, inv, cfg: dict, *, window=None,
                   full: FullReplay | None = None, perf_cache: dict | None = None) -> Baseline:
    """The baseline for one analysis window. With no window, the whole file.

    `full` and `perf_cache` let a caller that serves many windows (client_context.ContextCache)
    replay the file once, and fit the PD model once per performance window.
    """
    from src import client_context as C

    full = full or full_replay(df, inv, cfg)
    w = C.resolve(window, full.df, cfg)
    cfg_w = C.cfg_for(cfg, w)
    mask = C.app_mask(full.df, w).to_numpy()

    key = (cfg["product"], w.performance_months)
    if perf_cache is not None and key in perf_cache:
        outcome_all, model = perf_cache[key]
    else:
        outcome_all = A.stage_outcome(full.df, full.res, cfg_w)
        C.check(w, int(mask.sum()), int(outcome_all["mature"].sum()), cfg_w)
        model = client_risk.fit(full.df, outcome_all, cfg_w)
        if perf_cache is not None:
            perf_cache[key] = (outcome_all, model)
    mature = outcome_all["mature"].to_numpy()
    C.check(w, int(mask.sum()), int(mature.sum()), cfg_w)

    perf = Cohort(df=full.df[mature], res=client_replay.subset(full.res, mature),
                  outcome=outcome_all[mature],
                  frames=client_replay.subset_frames(full.frames, mature))
    return Baseline(df=full.df[mask], res=client_replay.subset(full.res, mask),
                    outcome=outcome_all[mask], model=model, cfg=cfg_w,
                    frames=client_replay.subset_frames(full.frames, mask),
                    perf=perf, window=w, whole=(full.df, outcome_all))


def portfolio(base: Baseline, by: str) -> pd.DataFrame:
    """The window's book sliced by `by`, with each slice's bad rate from the mature cohort."""
    df, perf = base.df, base.perf
    pdf = perf.df if perf is not None else None
    if by == "score_band":
        df = A.with_score_band(df, base.cfg)
        pdf = A.with_score_band(pdf, base.cfg) if pdf is not None else None
    return A.portfolio(df, base.outcome, by,
                       perf=(pdf, perf.outcome) if perf is not None else None)


def simulate(base: Baseline, inv, lever: Lever) -> dict:
    """Replay with the lever applied and report what moved."""
    df, cfg = base.df, base.cfg
    res = client_replay.replay(df, inv, cfg, overrides=lever.overrides, frames=base.frames,
                               base=base.res)
    outcome = A.stage_outcome(df, res, cfg)

    was, now = base.outcome["booked"].to_numpy(), outcome["booked"].to_numpy()
    swap_in, swap_out = (~was) & now, was & (~now)

    # Swap-ins were declined, so the bank has never seen them perform. Estimated, and
    # refused when they sit outside the booked population.
    risk_in = client_risk.predict_group(base.model, df, swap_in, cfg)
    risk_out = client_risk.predict_group(base.model, df, swap_out, cfg)

    # The observed side comes from the performance cohort: the same change replayed over the
    # mature loans. Swap-outs in the window are mostly too recent to have an outcome, but
    # mature loans the change would also have declined did, and a tightening is judged on
    # what those loans actually did.
    n_out = int(swap_out.sum())
    still, obs = _still_booked(base, inv, lever)
    n_out_seen = int((~still).sum())
    out_bad = float(obs[~still].mean()) if n_out and n_out_seen else None

    # Expected bad rate of the new book: those who stay, plus the estimated swap-ins. With no
    # swap-ins the new book is exactly the loans that stay, all observed — a tightening must
    # not report "unknown" just because nobody new was approved.
    stays = was & now
    n_stay, n_in = int(stays.sum()), int(swap_in.sum())
    stay_bad = float(obs[still].mean()) if n_stay and still.any() else np.nan
    if n_in == 0 and n_stay:
        new_bad, new_bad_known = stay_bad, True
    elif risk_in.get("known") and n_stay + n_in:
        new_bad = (stay_bad * n_stay + risk_in["estimated_bad_rate"] * n_in) / (n_stay + n_in)
        new_bad_known = True
    else:
        new_bad, new_bad_known = np.nan, False

    return {
        "lever": lever.label,
        "rules_changed": len(lever.overrides),
        "direction": getattr(lever, "direction", None),
        "approval_rate": round(float(now.mean()), 4),
        "approval_rate_before": round(base.approval_rate, 4),
        "approval_rate_change_pp": round(100 * (now.mean() - base.approval_rate), 2),
        "booked_before": int(was.sum()),
        "booked_after": int(now.sum()),
        "swap_in": n_in,
        "swap_out": n_out,
        "swap_in_risk": risk_in,
        "swap_out_risk": risk_out,
        "swap_out_observed_bad_rate": round(out_bad, 4) if out_bad is not None else None,
        "swap_out_observed_loans": n_out_seen if n_out else 0,
        "booked_bad_rate_before": round(base.booked_bad_rate, 4),
        "expected_bad_rate_after": round(float(new_bad), 4) if new_bad_known else None,
        "expected_bad_rate_known": new_bad_known,
        "risk_verdict": _verdict(risk_in, base.booked_bad_rate, cfg, n_in=n_in, n_out=n_out,
                                 out_bad=out_bad),
        "window": base.window_dict(),
        "_outcome": outcome,
        "_swap_in": swap_in,
        "_swap_out": swap_out,
    }


def _still_booked(base: Baseline, inv, lever: Lever) -> tuple[np.ndarray, pd.Series]:
    """Which mature loans a change keeps, and their observed outcomes."""
    perf = base.perf
    if perf is None:            # a baseline built without a cohort reads its own outcome
        booked = base.outcome["booked"].to_numpy()
        res = client_replay.replay(base.df, inv, base.cfg, overrides=lever.overrides,
                                   frames=base.frames, base=base.res)
        now = A.stage_outcome(base.df, res, base.cfg)["booked"].to_numpy()
        return now[booked], base.outcome.loc[booked, "observed_bad"]
    res = client_replay.replay(perf.df, inv, base.cfg, overrides=lever.overrides,
                               frames=perf.frames, base=perf.res)
    now = A.stage_outcome(perf.df, res, base.cfg)["booked"].to_numpy()
    return now, perf.outcome["observed_bad"]


def _verdict(risk_in: dict, booked_bad: float, cfg: dict, *, n_in: int = 1, n_out: int = 0,
             out_bad: float | None = None) -> str:
    if n_in == 0 and n_out == 0:
        return "no applicant changes outcome: other rules already decide everyone this touches"
    if n_in == 0:
        if out_bad is None:
            return (f"{n_out:,} booked loans would be declined; none of the loans it would have "
                    "declined is old enough to show how they repaid")
        ratio = out_bad / max(booked_bad, 1e-9)
        return (f"{n_out:,} booked loans would be declined; mature loans like them went bad at "
                f"{100 * out_bad:.1f}% against {100 * booked_bad:.1f}% for the book "
                f"({ratio:.1f}x)")
    if not risk_in.get("known"):
        return f"unknown — {risk_in.get('reason', 'cannot estimate')}"
    est = risk_in["estimated_bad_rate"]
    ratio = est / max(booked_bad, 1e-9)
    if ratio > cfg["simulate"]["riskier_multiple"]:
        text = f"swap-ins look {ratio:.1f}x riskier than the current book"
    elif ratio < cfg["simulate"]["safer_multiple"]:
        text = f"swap-ins look safer than the current book ({ratio:.1f}x)"
    else:
        text = f"swap-ins look comparable to the current book ({ratio:.1f}x)"
    if n_out:
        text += f"; {n_out:,} booked loans would be declined"
    return text


def swap_set_profile(base: Baseline, result: dict, by: str) -> pd.DataFrame:
    """Who newly gets approved and newly declined, sliced — question 8."""
    df = base.df
    frame = pd.DataFrame({
        by: df[by],
        "swap_in": result["_swap_in"],
        "swap_out": result["_swap_out"],
    })
    g = frame.groupby(by, observed=True)[["swap_in", "swap_out"]].sum()
    g["net"] = g["swap_in"] - g["swap_out"]
    return g.sort_values("net", ascending=False)


def sweep(base: Baseline, inv, field_name: str, from_value: float,
          candidates: list[float], *, product: str) -> pd.DataFrame:
    """Approval and expected bad rate at each possible cutoff — the cutoff analysis."""
    rows = []
    for value in candidates:
        if value == from_value:
            rows.append({"cutoff": value, "approval_rate": round(base.approval_rate, 4),
                         "approval_change_pp": 0.0, "swap_in": 0, "swap_out": 0,
                         "expected_bad_rate": round(base.booked_bad_rate, 4),
                         "risk_known": True, "note": "current"})
            continue
        lever = field_lever(inv, field_name, from_value, value, product=product,
                            locked=client_replay.locked_rules(base.cfg))
        r = simulate(base, inv, lever)
        rows.append({"cutoff": value, "approval_rate": r["approval_rate"],
                     "approval_change_pp": r["approval_rate_change_pp"],
                     "swap_in": r["swap_in"], "swap_out": r["swap_out"],
                     "expected_bad_rate": r["expected_bad_rate_after"],
                     "risk_known": r["expected_bad_rate_known"],
                     "note": r["risk_verdict"]})
    return pd.DataFrame(rows).sort_values("cutoff").reset_index(drop=True)


def driver_gains(base: "Baseline", inv, drivers: pd.DataFrame) -> pd.DataFrame:
    """What switching each rule off on its own would actually book.

    `declines_alone` counts the applicants a rule frees, but freed is not approved: some then
    fail eligibility or walk away. The applicants a rule declines alone are caught by no other
    rule, so switching it off leaves them exactly where they would be with no decline rule at
    all. One outcome with every decline cleared answers every rule at once, and gives the same
    count as replaying each rule off (a test holds the two together). A rule the bank may not
    drop gets no figure.
    """
    res = base.res
    free_rules = res.rules.assign(matched=res.rules["matched"].where(res.rules["kind"] != "block", 0))
    free = client_replay.ReplayResult(hits=res.hits, rules=free_rules,
                                      unevaluable=res.unevaluable, compiled=res.compiled)
    booked_if_free = A.stage_outcome(base.df, free, base.cfg)["booked"].to_numpy()
    blocking = res.rules[(res.rules["kind"] == "block") & (res.rules["matched"] > 0)]["rule_id"]
    hits = res.hits[[c for c in blocking if c in res.hits.columns]].to_numpy()
    only_one = hits.sum(axis=1) == 1
    col = {rid: j for j, rid in enumerate(c for c in blocking if c in res.hits.columns)}

    out = drivers.copy()
    gained = []
    for r in out.itertuples():
        if not r.relaxable or r.rule_id not in col:
            gained.append(pd.NA)
            continue
        alone = hits[:, col[r.rule_id]] & only_one
        gained.append(int((alone & booked_if_free).sum()))
    out["approvals_gained"] = pd.array(gained, dtype="Int64")
    n = max(len(base.df), 1)
    out["approval_change_pp"] = [None if pd.isna(g) else round(100 * g / n, 2) for g in gained]
    return out
