"""The payload behind the three CxO screens, for one analysis context.

`ui/client_export.py` writes it to disk for the offline demo, one payload per precomputed
product and period; the live engine serves the same payload for any product and window at
`/api/view`. One function, so the offline screens and the live ones cannot drift apart.

The UI computes nothing. Every figure on the three screens comes from here, and this computes
nothing either: it calls the same functions the CLIs and the tests call.
"""
from __future__ import annotations

import math
import re
import time

import numpy as np
import pandas as pd

from src import (client_analysis as A, client_api as API, client_optimise as O,
                 client_simulate as S)

GOAL_STEPS = [0.03, 0.08]
"""Goal-seek targets are this far above the context's own approval rate, rounded up to a whole
percent. A fixed target would be below today for a product that already approves more (IJMB
approves nearly half), and would be "reached" by changing nothing."""


def goal_targets(approval_rate: float) -> list[float]:
    return [math.ceil(round((approval_rate + s) * 100, 6)) / 100 for s in GOAL_STEPS]
SWEEPS = [
    {"field": "simahcreditscore", "from": 600, "values": [600, 590, 580, 570, 560],
     "label": "SIMAH score cutoff"},
    {"field": "crifscore", "from": 605, "values": [605, 595, 585, 575, 565],
     "label": "CRIF score cutoff"},
]


def clean(o):
    """NaN/Inf -> None, so the page renders an em dash and never a spurious zero."""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    # bool before int: `bool` subclasses `int`, so checking int first would ship True as 1.
    if isinstance(o, (np.bool_, bool)):
        return bool(o)
    if isinstance(o, (np.integer, int)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return None if not math.isfinite(f) else round(f, 8)
    if isinstance(o, pd.Timestamp):
        return o.strftime("%Y-%m-%d")
    if o is None or isinstance(o, str):
        return o
    if isinstance(o, pd.Series):
        return clean(o.to_dict())
    return str(o)


def _records(df: pd.DataFrame, index_name: str | None = None) -> list[dict]:
    out = df.reset_index() if index_name else df
    if index_name:
        out = out.rename(columns={out.columns[0]: index_name})
    return clean(out.to_dict("records"))


def band_label(band: str) -> str:
    """A score band as a person reads it: "(650.0, 700.0]" is "651–700", the lowest "500 or below"."""
    m = re.fullmatch(r"\(([\d.]+), ([\d.]+)\]", band)
    if not m:
        return band[:1].upper() + band[1:]
    lo, hi = int(float(m[1])), int(float(m[2]))
    return f"{hi} or below" if lo <= 0 else f"{lo + 1}–{hi}"


def value_labels(cfg: dict, book_by: dict) -> dict:
    """Business names for every slice value the screens show, by slice. A code with no name in
    config reads as itself; score bands are named from their edges."""
    named = cfg.get("value_labels") or {}
    out = {k: {str(c): str(v) for c, v in (named.get(k) or {}).items()} for k in book_by}
    out.setdefault("channel", {})
    out["score_band"] = {r["score_band"]: band_label(r["score_band"]) for r in book_by["score_band"]["rows"]}
    return out


def drivers_view(base: S.Baseline, inv, drivers: pd.DataFrame, funnel: pd.DataFrame,
                 funnel_rules: list[dict]) -> tuple[list[dict], dict]:
    """Decline Drivers: every decline rule, grouped by verdict, and every other way applicants are lost.

    The verdict comes from `A.decline_drivers`; this only orders, counts and adds what each rule
    would actually book if switched off on its own.
    """
    cfg = base.cfg
    gains = S.driver_gains(base, inv, drivers)
    order = {v: i for i, v in enumerate(A.VERDICTS)}
    gains = gains.assign(_g=gains["verdict"].map(order),
                         _n=gains["approvals_gained"].fillna(-1).astype(int))
    gains = gains.sort_values(["_g", "_n", "declines"], ascending=[True, False, False]) \
                 .drop(columns=["_g", "_n"])

    groups = []
    for vid, label in A.VERDICTS.items():
        g = gains[gains["verdict"] == vid]
        groups.append({"id": vid, "label": label, "rules": int(len(g)),
                       "declines_alone": int(g["declines_alone"].sum()),
                       "approvals_gained": int(g["approvals_gained"].fillna(0).sum())})

    rules = base.res.rules
    never = rules[(rules["kind"] == "block") & (rules["matched"] == 0)]
    layout = A.funnel_layout(cfg)
    by_stage = {r["stage"]: r for r in funnel_rules}
    total = int(funnel.iloc[0]["entered"]) if len(funnel) else 0
    losses = []
    for r in funnel.to_dict("records"):
        spec = layout["stages"].get(r["stage"], {})
        if spec.get("endpoint") or not r["dropped"]:
            continue
        group = layout["groups"].get(spec.get("group"), {})
        is_rules = r["stage"] in ("hard_reject", "credit_policy")
        losses.append({
            "stage": r["stage"], "label": spec.get("label", r["stage"]),
            "sublabel": spec.get("sublabel"), "group": group.get("label"),
            "loss_type": group.get("loss_type"),
            "dropped": int(r["dropped"]),
            "share_of_applicants": round(r["dropped"] / total, 6) if total else None,
            "decline_rules": is_rules,
            "reasons": [{"label": x["label"], "count": x["count"]}
                        for x in by_stage.get(r["stage"], {}).get("rules", [])[:3]],
        })

    multiple = cfg["drivers"]["earns_place_multiple"]
    summary = {
        "booked_bad_rate": round(base.booked_bad_rate, 6),
        "earns_place_multiple": multiple,
        "threshold": round(base.booked_bad_rate * multiple, 6),
        "groups": groups,
        "never_fire": [{"rule_id": x.rule_id, "stage": x.stage,
                        "label": A.clean_description(x.description) or x.rule_id}
                       for x in never.itertuples()],
        "losses": losses,
        # Decline rules in scope that the replay could not evaluate: they read a value the data
        # does not supply, so they decline nobody here and say nothing about the real book.
        "not_evaluated": [{"rule_id": rid, "stage": c.stage,
                           "label": A.clean_description(c.description) or rid}
                          for rid, c in base.res.compiled.items()
                          if c.kind == "block" and rid not in set(rules["rule_id"])],
    }
    return clean(gains.to_dict("records")), clean(summary)


def build_view(base: S.Baseline, inv, *, quick: bool = False, log=None) -> dict:
    """Everything the three screens show for one analysis context (product and window).

    `quick` leaves out the precomputed scenarios (sweeps, rule toggles, goal-seek). The live
    engine serves the quick view, because with an engine the Simulator asks for scenarios itself.
    """
    log = log or (lambda *_: None)
    t0 = time.time()
    cfg = base.cfg
    df, outcome, res, model = base.df, base.outcome, base.res, base.model

    drivers = A.decline_drivers(df, res, outcome, cfg, model=model,
                                booked_bad_rate=base.booked_bad_rate)
    funnel = A.funnel(df, outcome)
    funnel_rules = clean(A.funnel_rules(res, outcome, cfg, conditions=inv.conditions))
    driver_rows, driver_summary = drivers_view(base, inv, drivers, funnel, funnel_rules)

    book_by = {}
    for slice_name in ("employer_segment", "sector", "channel", "nationality"):
        book = S.portfolio(base, slice_name)
        book_by[slice_name] = {
            "rows": _records(book, slice_name),
            "flags": clean(A.concentration_flags(book, cfg).to_dict("records")),
        }
    book_by["score_band"] = {
        "rows": _records(S.portfolio(base, "score_band"), "score_band"), "flags": [],
    }

    payload = {
        "meta": {
            "generated": pd.Timestamp.now("UTC").strftime("%Y-%m-%d %H:%M UTC"),
            # The extract date: nothing after it is observed, so every figure is "as of" it.
            "data_as_of": f"{A.bad_definition(cfg)['as_of']:%Y-%m-%d}",
            "product": cfg["product"],
            "applicants": int(len(df)),
            "window": clean(base.window_dict()),
            "rules_replayed": int(len(res.rules)),
            "rules_unevaluable": clean(res.unevaluable),
            "synthetic": True,
            "replay_decisions": clean(cfg["replay"]),
            "bad_rate_ceiling": cfg["optimise"]["max_bad_rate"],
            "value_labels": value_labels(cfg, book_by),
        },
        "headline": {
            # Six places, not four: the page rounds once more to show a percent, and rounding a
            # rounded rate can land on the wrong side (47.354% shipped as 0.4735 shows as 47.3%).
            "approval_rate": round(base.approval_rate, 6),
            "booked": int(outcome["booked"].sum()),
            "booked_bad_rate": round(base.booked_bad_rate, 6),
            "exposure": clean(outcome.loc[outcome["booked"], "offered_amount"].sum()),
            "median_offer_gap": clean(
                (df["requested_amount"] - outcome["offered_amount"]).median()),
        },
        "funnel": clean(funnel.to_dict("records")),
        "funnel_layout": clean(A.funnel_layout(cfg)),
        "funnel_rules": funnel_rules,
        "by_channel": _records(A.by_source(df, outcome, "channel"), "channel"),
        "by_agent": _records(A.by_source(df, outcome, "agent_id").head(12), "agent_id"),
        "portfolio": book_by,
        # Over the product's whole file, not the window: it shows how the window compares.
        "over_time": clean(A.over_time(*base.whole, cfg, base.window)) if base.whole else None,
        # Every decline rule, grouped by verdict; the screen shows the top of each group.
        "drivers": driver_rows,
        "drivers_summary": driver_summary,
        "model": {
            "gini": model.gini, "n_train": model.n_train,
            "train_bad_rate": round(model.train_bad_rate, 4),
            "score_floor": model.score_floor, "score_ceiling": model.score_ceiling,
            "booked_missing_score": model.booked_missing_score,
        },
        # Every decline rule, so the Simulator lists them all even with no engine running.
        # Only the precomputed `rule_toggles` can be tried in that mode; the screen says so.
        "rule_catalogue": clean(API.rule_catalogue(base, inv)),
        "sweeps": [], "rule_toggles": [], "goal_seek": [],
        # The Goal form's starting targets, a few points above today, so a product that already
        # approves more is never offered a target it has already passed.
        "goal_targets": goal_targets(base.approval_rate),
    }

    if quick:
        payload["meta"]["quick"] = True
        log(f"  quick build in {time.time() - t0:.0f}s")
        return payload

    offered = {c["field"] for c in API.cutoffs_for(base, inv)}
    for spec in SWEEPS:
        if spec["field"] not in offered:
            continue                   # another product's cutoff: none of this product's rules
        curve = S.sweep(base, inv, spec["field"], spec["from"], spec["values"],
                        product=cfg["product"])
        payload["sweeps"].append({"field": spec["field"], "label": spec["label"],
                                  "from": spec["from"],
                                  "rows": clean(curve.to_dict("records"))})
        log(f"  swept {spec['field']}")

    # The busiest relaxable rules, plus the top rule Decline drivers flags, so the Simulator's
    # "Loosen what Decline drivers flagged" works offline too.
    flagged = drivers[drivers["verdict"] == "review"].head(0)
    if driver_rows:
        first = next((r for r in driver_rows if r["verdict"] == "review"), None)
        flagged = drivers[drivers["rule_id"] == first["rule_id"]] if first else flagged
    top = pd.concat([drivers[drivers["relaxable"]].nlargest(8, "declines_alone"), flagged]) \
            .drop_duplicates("rule_id")
    for r in top.itertuples():
        result = S.simulate(base, inv, S.rule_lever(r.rule_id, enabled=False))
        payload["rule_toggles"].append(clean({
            "rule_id": r.rule_id, "policy_code": r.policy_code,
            "description": r.description, "declines_alone": r.declines_alone,
            "approval_rate": result["approval_rate"],
            "approval_change_pp": result["approval_rate_change_pp"],
            "swap_in": result["swap_in"], "swap_out": result["swap_out"],
            "expected_bad_rate": result["expected_bad_rate_after"],
            "risk_known": result["expected_bad_rate_known"],
            "verdict": result["risk_verdict"],
            "swap_in_by_channel": clean(
                S.swap_set_profile(base, result, "channel").to_dict("index")),
        }))
    log(f"  {len(payload['rule_toggles'])} rule toggles")

    for target in goal_targets(base.approval_rate):
        out = O.goal_seek(base, inv, target, cfg)
        payload["goal_seek"].append({
            "target": target, "reached": bool(out.attrs.get("reached")),
            "ceiling": out.attrs.get("ceiling"),
            "options": clean(out.to_dict("records")),
        })
        log(f"  goal-seek {target:.0%} reached={out.attrs.get('reached')}")

    log(f"  built in {time.time() - t0:.0f}s")
    return payload
