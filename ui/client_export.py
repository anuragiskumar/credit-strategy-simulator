"""Export the fixture for the three CxO screens (plan step 5).

    python -m ui.client_export                 # full, including the goal-seek runs
    python -m ui.client_export --quick         # skips goal-seek and the scenario grid

The UI computes nothing. Every figure on the three screens comes from this file, and this
file computes nothing either: it calls the same functions the CLIs and the tests call. The
prototype has no backend yet, so scenarios are precomputed; when an API lands, the same keys
are served live from `simulate()` and `goal_seek()`.

Each figure carries a provenance tag, because that is the only thing colour encodes:

    OBSERVED      counted from the data — applicants, declines, booked performance
    PREDICTED     the PD model, inside the population it was trained on
    INFERRED      reject inference — swap-ins the bank has never seen repay
    NOT_MODELLED  refused. The group sits outside anything the bank has booked.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import numpy as np
import pandas as pd

from src import client_analysis as A, client_optimise as O, client_simulate as S
from src.config import resolve_path
from src.client_generate import load_client_config
from src.rule_inventory import build_inventory

HERE = Path(__file__).resolve().parent
GOAL_TARGETS = [0.25, 0.30]
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


def build(cfg: dict, inv, *, quick: bool = False) -> dict:
    df = pd.read_parquet(resolve_path(cfg["data_path"]))
    t0 = time.time()
    base = S.build_baseline(df, inv, cfg)
    outcome, res, model = base.outcome, base.res, base.model

    drivers = A.decline_drivers(df, res, outcome, cfg, model=model)
    funnel = A.funnel(df, outcome)

    book_by = {}
    for slice_name in ("employer_segment", "sector", "channel", "nationality"):
        book = A.portfolio(df, outcome, slice_name)
        book_by[slice_name] = {
            "rows": _records(book, slice_name),
            "flags": clean(A.concentration_flags(book, cfg).to_dict("records")),
        }
    bands = pd.cut(df["simah_score"], cfg["portfolio"]["score_bands"])
    banded = df.assign(score_band=bands["simah_score"].astype(str)
                       if isinstance(bands, pd.DataFrame) else bands.astype(str))
    banded["score_band"] = banded["score_band"].fillna("no score")
    book_by["score_band"] = {
        "rows": _records(A.portfolio(banded, outcome, "score_band"), "score_band"),
        "flags": [],
    }

    payload = {
        "meta": {
            "generated": pd.Timestamp.now("UTC").strftime("%Y-%m-%d %H:%M UTC"),
            "product": cfg["product"],
            "applicants": int(len(df)),
            "rules_replayed": int(len(res.rules)),
            "rules_unevaluable": clean(res.unevaluable),
            "synthetic": True,
            "replay_decisions": clean(cfg["replay"]),
            "bad_rate_ceiling": cfg["optimise"]["max_bad_rate"],
        },
        "headline": {
            "approval_rate": round(base.approval_rate, 4),
            "booked": int(outcome["booked"].sum()),
            "booked_bad_rate": round(base.booked_bad_rate, 4),
            "exposure": clean(outcome.loc[outcome["booked"], "offered_amount"].sum()),
            "median_offer_gap": clean(
                (df["requested_amount"] - outcome["offered_amount"]).median()),
        },
        "funnel": clean(funnel.to_dict("records")),
        "funnel_layout": clean(A.funnel_layout(cfg)),
        "funnel_rules": clean(A.funnel_rules(res, outcome, cfg, conditions=inv.conditions)),
        "by_channel": _records(A.by_source(df, outcome, "channel"), "channel"),
        "by_agent": _records(A.by_source(df, outcome, "agent_id").head(12), "agent_id"),
        "portfolio": book_by,
        "drivers": clean(drivers.head(25).to_dict("records")),
        "model": {
            "gini": model.gini, "n_train": model.n_train,
            "train_bad_rate": round(model.train_bad_rate, 4),
            "score_floor": model.score_floor, "score_ceiling": model.score_ceiling,
            "booked_missing_score": model.booked_missing_score,
        },
        "sweeps": [], "rule_toggles": [], "goal_seek": [],
    }

    if quick:
        payload["meta"]["quick"] = True
        print(f"  quick build in {time.time() - t0:.0f}s", flush=True)
        return payload

    for spec in SWEEPS:
        curve = S.sweep(base, inv, spec["field"], spec["from"], spec["values"],
                        product=cfg["product"])
        payload["sweeps"].append({"field": spec["field"], "label": spec["label"],
                                  "from": spec["from"],
                                  "rows": clean(curve.to_dict("records"))})
        print(f"  swept {spec['field']}", flush=True)

    top = drivers[drivers["relaxable"]].nlargest(8, "declines_alone")
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
    print(f"  {len(payload['rule_toggles'])} rule toggles", flush=True)

    for target in GOAL_TARGETS:
        out = O.goal_seek(base, inv, target, cfg)
        payload["goal_seek"].append({
            "target": target, "reached": bool(out.attrs.get("reached")),
            "ceiling": out.attrs.get("ceiling"),
            "options": clean(out.to_dict("records")),
        })
        print(f"  goal-seek {target:.0%} reached={out.attrs.get('reached')}", flush=True)

    print(f"  built in {time.time() - t0:.0f}s", flush=True)
    return payload


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Export the fixture for ui/client.html")
    ap.add_argument("--out", default=str(HERE / "client_fixture.json"))
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args(argv)

    cfg = load_client_config()
    payload = build(cfg, build_inventory(cfg["replay"]["rules_folder"]), quick=args.quick)

    out = Path(args.out)
    out.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    js = out.with_name("client_data.js")
    js.write_text("window.__CLIENT__ = " + json.dumps(payload, ensure_ascii=False) + ";\n",
                  encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size // 1024} KB) and {js.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
