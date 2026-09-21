"""Goal-seek: reach a target approval rate, ranked by risk cost (plan step 4, question 9).

Guru's ask: set a goal, e.g. 30% approval, and get options A, B and C that reach it.

The brief flags the gap nobody raised on the call — "maximise approval rate" alone is solved
by approving everyone. So the target is always paired with a **bad rate ceiling**, and an
option that breaches it is reported as failing, not quietly returned.

Two further refusals are deliberate:

  * A rule resting on a regulatory or bureau fact is never a candidate, whatever it costs.
  * An option whose swap-ins cannot be risk-assessed is returned with `risk_known=False`
    rather than a number. It is then ranked last, because a cheap-looking option we cannot
    price is not a cheap option.

The search is a beam search over single changes. It is not a proof of optimality, and the
output is a ranked shortlist for a human to take to a risk committee — which is what the
brief describes and what a bank will accept.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src import client_analysis as A, client_simulate as S
from src.client_replay import locked_rules


@dataclass
class Option:
    label: str
    lever: S.Lever
    approval_rate: float
    approval_change_pp: float
    swap_in: int
    swap_out: int
    expected_bad_rate: float | None
    risk_known: bool
    risk_cost_pp: float | None       # expected bad rate increase, in percentage points
    breaches_ceiling: bool
    detail: dict

    def as_row(self) -> dict:
        return {"option": self.label, "approval_rate": self.approval_rate,
                "approval_change_pp": self.approval_change_pp,
                "swap_in": self.swap_in, "swap_out": self.swap_out,
                "expected_bad_rate": self.expected_bad_rate,
                "risk_known": self.risk_known, "risk_cost_pp": self.risk_cost_pp,
                "breaches_ceiling": self.breaches_ceiling,
                "changes": list(getattr(self.lever, "changes", []))}


def candidate_levers(base: S.Baseline, inv, cfg: dict,
                     frozen: frozenset[str] = frozenset()) -> list[S.Lever]:
    """Everything the bank could plausibly change, one at a time.

    Two kinds. Switching a rule off is what the client already does by hand — ten SIMAH rules are
    marked Inactive — so it is the change they recognise. Moving a cutoff is the change
    Guru described.

    `frozen` is the person's own "don't touch these": treated exactly like a locked rule for
    this one search — never switched off, and skipped by any cutoff move.
    """
    opt = cfg["optimise"]
    drivers = A.decline_drivers(base.df, base.res, base.outcome, cfg, model=base.model)
    levers: list[S.Lever] = []

    eligible = drivers[drivers["relaxable"] & ~drivers["rule_id"].isin(frozen)
                       & (drivers["declines_alone"] >= opt["min_declines_alone"])]
    for r in eligible.nlargest(opt["max_rule_candidates"], "declines_alone").itertuples():
        text = (r.description or r.rule_id)[:60]
        lever = S.rule_lever(r.rule_id, enabled=False, label=f"switch off {r.rule_id} ({text})")
        # The same change in the form the screen sends, so an option can be tried as a scenario.
        object.__setattr__(lever, "changes", [{"type": "off", "rule_id": r.rule_id}])
        levers.append(lever)

    for move in opt["field_moves"]:
        try:
            lever = S.field_lever(inv, move["field"], move["from"], move["to"],
                                  product=cfg["product"], locked=locked_rules(cfg) | frozen,
                                  label=f"{move['label']} ({move['from']:g} to {move['to']:g})")
            object.__setattr__(lever, "changes", [{"type": "cutoff", "field": move["field"],
                                                   "from": move["from"], "to": move["to"]}])
            levers.append(lever)
        except ValueError:
            continue                  # threshold not present for this product; skip quietly
    return levers


def _evaluate(base: S.Baseline, inv, lever: S.Lever, cfg: dict,
              ceiling: float | None = None) -> Option:
    r = S.simulate(base, inv, lever)
    est = r["expected_bad_rate_after"]
    known = r["expected_bad_rate_known"]
    cost = round(100 * (est - base.booked_bad_rate), 3) if known else None
    ceiling = cfg["optimise"]["max_bad_rate"] if ceiling is None else ceiling
    return Option(
        label=lever.label, lever=lever, approval_rate=r["approval_rate"],
        approval_change_pp=r["approval_rate_change_pp"], swap_in=r["swap_in"],
        swap_out=r["swap_out"], expected_bad_rate=est, risk_known=known,
        risk_cost_pp=cost, breaches_ceiling=bool(known and est > ceiling), detail=r)


def _rank_key(o: Option) -> tuple:
    """Cheapest risk first, for options that already reach the target.

    An option we cannot price ranks last, never first: a cheap-looking option we cannot
    price is not a cheap option.
    """
    return (o.breaches_ceiling, not o.risk_known,
            o.risk_cost_pp if o.risk_cost_pp is not None else 1e9,
            -o.approval_change_pp)


def _reach_key(o: Option) -> tuple:
    """Furthest toward the target first.

    Used while searching, and for the shortlist when the target cannot be reached at all.
    Ranking those by risk cost would answer a question nobody asked — the cheapest change
    is the one that does almost nothing — and would hand back a worse approval rate than a
    lower target returns.
    """
    return (o.breaches_ceiling, -o.approval_rate,
            o.risk_cost_pp if o.risk_cost_pp is not None else 1e9)


def goal_seek(base: S.Baseline, inv, target_approval_rate: float, cfg: dict,
              *, max_options: int = 3, ceiling: float | None = None,
              frozen: frozenset[str] = frozenset()) -> pd.DataFrame:
    """Find combinations reaching the target, ranked by risk cost.

    Beam search over single changes: each round adds the change that buys the most approval
    for the least estimated risk, keeping the best few partial strategies alive.

    The target and the bad-rate `ceiling` are the person's to set; the ceiling defaults to
    `optimise.max_bad_rate`. `frozen` names rules they will not have touched.
    """
    opt = cfg["optimise"]
    ceiling = opt["max_bad_rate"] if ceiling is None else float(ceiling)
    candidates = candidate_levers(base, inv, cfg, frozen=frozenset(frozen))
    if not candidates:
        out = pd.DataFrame()
        out.attrs.update(target=target_approval_rate, ceiling=ceiling, reached=False)
        return out

    singles = [_evaluate(base, inv, lv, cfg, ceiling) for lv in candidates]
    evaluated = list(singles)
    beam: list[Option] = sorted(singles, key=_reach_key)[:opt["beam_width"]]
    complete = [o for o in singles if o.approval_rate >= target_approval_rate]

    for _ in range(opt["max_depth"] - 1):
        if len(complete) >= max_options:
            break
        nxt: list[Option] = []
        for partial in beam:
            used = set(partial.lever.overrides)
            for cand in candidates:
                if set(cand.overrides) & used:
                    continue
                combined = S.combine(partial.lever, cand)
                object.__setattr__(combined, "changes", getattr(partial.lever, "changes", [])
                                   + getattr(cand, "changes", []))
                nxt.append(_evaluate(base, inv, combined, cfg, ceiling))
        if not nxt:
            break
        evaluated += nxt
        nxt.sort(key=_reach_key)
        beam, beam_seen = [], set()
        for o in nxt:
            key = frozenset(o.lever.overrides)
            if key in beam_seen:
                continue
            beam_seen.add(key)
            beam.append(o)
            if len(beam) >= opt["beam_width"]:
                break
        complete += [o for o in nxt if o.approval_rate >= target_approval_rate]

    # The same set of changes reached in a different order is the same strategy, not a
    # second option. Without this, A, B and C come back identical with the words shuffled.
    reached = bool(complete)
    pool = complete if reached else evaluated
    order = _rank_key if reached else _reach_key
    chosen, seen = [], set()
    for o in sorted(pool, key=order):
        key = frozenset(o.lever.overrides)
        if key in seen:
            continue
        seen.add(key)
        chosen.append(o)
        if len(chosen) >= max_options:
            break

    rows = []
    for i, o in enumerate(chosen):
        row = o.as_row()
        row["option"] = f"{chr(65 + i)}: {o.label}"
        row["reaches_target"] = o.approval_rate >= target_approval_rate
        rows.append(row)
    out = pd.DataFrame(rows)
    out.attrs["target"] = target_approval_rate
    out.attrs["ceiling"] = ceiling
    out.attrs["reached"] = reached
    return out
