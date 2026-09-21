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
                *, product: str, label: str | None = None) -> Lever:
    """Move every threshold of `from_value` on `field_name` to `to_value`.

    This is Guru's "what is that one thing I change?". 102 rules turn on three SIMAH
    cutoffs, so one lever moves a hundred rules at once.

    Only conditions for which the move is in the loosening direction are changed. A rule
    that tests the same number the other way round is left alone and counted in
    `skipped_wrong_direction`, because silently tightening it while the user asked to
    loosen would show up as an approval *fall* with no explanation.
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
    overrides, skipped = {}, 0
    for r in hit.itertuples():
        direction = RELAX_DIRECTION.get(r.operator)
        if direction is not None and kind.get(r.rule_id) == "pass":
            direction = -direction
        if direction is None or direction != wanted:
            skipped += 1
            continue
        overrides[r.rule_id] = {"field": r.field, "value_low": to_value}
    if not overrides:
        raise ValueError(
            f"moving {field_name} {from_value:g} to {to_value:g} would tighten every rule "
            f"that tests it, not loosen any")
    lever = Lever(label=label or f"{field_name}: {from_value:g} -> {to_value:g}",
                  overrides=overrides)
    object.__setattr__(lever, "skipped_wrong_direction", skipped)
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


def combine(*levers: Lever, label: str | None = None) -> Lever:
    """Several changes at once, for the optimiser's option B and C."""
    merged: dict = {}
    for lv in levers:
        for rule_id, patch in lv.overrides.items():
            merged.setdefault(rule_id, {}).update(patch)
    return Lever(label=label or " + ".join(lv.label for lv in levers), overrides=merged)


@dataclass
class Baseline:
    df: pd.DataFrame
    res: client_replay.ReplayResult
    outcome: pd.DataFrame
    model: client_risk.PDModel
    cfg: dict
    frames: dict = field(default_factory=dict)

    @property
    def approval_rate(self) -> float:
        return float(self.outcome["booked"].mean())

    @property
    def booked_bad_rate(self) -> float:
        return float(self.outcome.loc[self.outcome["booked"], "observed_bad"].mean())


def build_baseline(df: pd.DataFrame, inv, cfg: dict) -> Baseline:
    frames = client_replay.prepare_frames(df, cfg)
    res = client_replay.replay(df, inv, cfg, frames=frames)
    outcome = A.stage_outcome(df, res, cfg)
    return Baseline(df=df, res=res, outcome=outcome, model=client_risk.fit(df, outcome, cfg),
                    cfg=cfg, frames=frames)


def simulate(base: Baseline, inv, lever: Lever) -> dict:
    """Replay with the lever applied and report what moved."""
    df, cfg = base.df, base.cfg
    res = client_replay.replay(df, inv, cfg, overrides=lever.overrides, frames=base.frames)
    outcome = A.stage_outcome(df, res, cfg)

    was, now = base.outcome["booked"].to_numpy(), outcome["booked"].to_numpy()
    swap_in, swap_out = (~was) & now, was & (~now)

    # Swap-ins were declined, so the bank has never seen them perform. Estimated, and
    # refused when they sit outside the booked population.
    risk_in = client_risk.predict_group(base.model, df, swap_in, cfg)
    risk_out = client_risk.predict_group(base.model, df, swap_out, cfg)

    # Expected bad rate of the new book: those who stay, plus the estimated swap-ins.
    stays = was & now
    n_stay, n_in = int(stays.sum()), int(swap_in.sum())
    stay_bad = float(base.outcome.loc[stays, "observed_bad"].mean()) if n_stay else np.nan
    if risk_in.get("known") and n_stay + n_in:
        new_bad = (stay_bad * n_stay + risk_in["estimated_bad_rate"] * n_in) / (n_stay + n_in)
        new_bad_known = True
    else:
        new_bad, new_bad_known = np.nan, False

    return {
        "lever": lever.label,
        "rules_changed": len(lever.overrides),
        "approval_rate": round(float(now.mean()), 4),
        "approval_rate_before": round(base.approval_rate, 4),
        "approval_rate_change_pp": round(100 * (now.mean() - base.approval_rate), 2),
        "booked_before": int(was.sum()),
        "booked_after": int(now.sum()),
        "swap_in": n_in,
        "swap_out": int(swap_out.sum()),
        "swap_in_risk": risk_in,
        "swap_out_risk": risk_out,
        "booked_bad_rate_before": round(base.booked_bad_rate, 4),
        "expected_bad_rate_after": round(float(new_bad), 4) if new_bad_known else None,
        "expected_bad_rate_known": new_bad_known,
        "risk_verdict": _verdict(risk_in, base.booked_bad_rate, cfg),
        "_outcome": outcome,
        "_swap_in": swap_in,
        "_swap_out": swap_out,
    }


def _verdict(risk_in: dict, booked_bad: float, cfg: dict) -> str:
    if not risk_in.get("known"):
        return f"unknown — {risk_in.get('reason', 'cannot estimate')}"
    est = risk_in["estimated_bad_rate"]
    ratio = est / max(booked_bad, 1e-9)
    if ratio > cfg["simulate"]["riskier_multiple"]:
        return f"swap-ins look {ratio:.1f}x riskier than the current book"
    if ratio < cfg["simulate"]["safer_multiple"]:
        return f"swap-ins look safer than the current book ({ratio:.1f}x)"
    return f"swap-ins look comparable to the current book ({ratio:.1f}x)"


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
        lever = field_lever(inv, field_name, from_value, value, product=product)
        r = simulate(base, inv, lever)
        rows.append({"cutoff": value, "approval_rate": r["approval_rate"],
                     "approval_change_pp": r["approval_rate_change_pp"],
                     "swap_in": r["swap_in"], "swap_out": r["swap_out"],
                     "expected_bad_rate": r["expected_bad_rate_after"],
                     "risk_known": r["expected_bad_rate_known"],
                     "note": r["risk_verdict"]})
    return pd.DataFrame(rows).sort_values("cutoff").reset_index(drop=True)
