"""Export a real-data fixture for the web prototype (ui/).

Every figure in ui/ comes from this file, and this file computes nothing: it calls the same
core functions the headless CLIs call (Section 12.1 / 18.3, extended to the prototype).

    python -m ui.export_fixture --out ui/fixture.json

The scenario grid is precomputed because the prototype has no Python behind it yet. When the
API lands (T2), the grid is deleted and the same keys are served live from `simulate()`.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import load_config
from src.loader import load_applications
from src.optimise import (candidate_declines, combined_trade, optimise,
                          optimiser_result_to_dict, swap_out_analysis)
from src.risk_model import near_cutoff_anchor, train_model
from src.rules import (evaluate_strategy, reproduction_report, strategy_from_config,
                       with_rule_enabled, with_rule_params)
from src.simulate import simulate_detailed
from src.validation import (oracle_available, validate_near_cutoff_oracle,
                            validate_strategy_oracle)
from src.waterfall import build_waterfall, decline_heatmap, single_rule_declines

CUTOFFS = list(range(620, 750, 10))
FOIR_CAPS = [round(0.35 + 0.05 * i, 2) for i in range(9)]
TOGGLES = [(True, True), (False, True), (True, False), (False, False)]
BREAKDOWN_MIN_COUNT = 1000


def clean(o):
    """NaN/Inf -> None so the JSON stays valid and the UI renders an em dash, never a zero."""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return None if not math.isfinite(f) else round(f, 8)
    if isinstance(o, (np.bool_, bool)):
        return bool(o)
    if isinstance(o, pd.Timestamp):
        return o.isoformat()
    if o is None or isinstance(o, (str, int)):
        return o
    if isinstance(o, pd.DataFrame):
        return clean(o.reset_index().to_dict("records"))
    if isinstance(o, pd.Series):
        return clean(o.to_dict())
    return str(o)


def scenario_record(res, det, keep_breakdown: bool) -> dict:
    rec = {
        "approval_count": int(res.approval_count),
        "approval_rate": res.approval_rate,
        "swap_in_count": int(res.swap_in_count),
        "swap_out_count": int(res.swap_out_count),
        "not_modelled_count": int(res.not_modelled_count),
        "observed_bad_rate": res.observed_bad_rate,
        "model_basis_baseline": res.model_basis_baseline,
        "inferred_bad_rate": res.inferred_bad_rate,
        "blended_bad_rate": res.blended_bad_rate,
        "inferred_share": res.inferred_share,
        "sensitivity": clean(res.sensitivity.to_dict("records")) if res.sensitivity is not None else [],
    }
    if keep_breakdown and res.swap_in_breakdown is not None and not res.swap_in_breakdown.empty:
        b = res.swap_in_breakdown
        col = "count" if "count" in b.columns else b.columns[1]
        b = b.loc[b[col] >= BREAKDOWN_MIN_COUNT]
        rec["swap_in_breakdown"] = clean(b.to_dict("records"))
    return clean(rec)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="ui/fixture.json")
    ap.add_argument("--skip-grid", action="store_true")
    args = ap.parse_args(argv)

    t0 = time.time()
    cfg = load_config()
    df = load_applications(cfg=cfg)
    baseline = strategy_from_config(cfg)
    model = train_model(df, cfg)
    ev = evaluate_strategy(df, baseline)
    penalty = cfg["model"]["inference_penalty"]
    print(f"[load] {len(df):,} rows in {time.time() - t0:.1f}s")

    out: dict = {"meta": {
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "n_rows": int(len(df)),
        "config": clean(cfg),
        "synthetic": True,
        "oracle_available": bool(oracle_available(df)),
    }}

    # ---------------------------------------------------------------- 1. overview
    rep = dict(reproduction_report(df, baseline, ev))
    # 10,000 override rows: keep a sample for the drill-down, not the whole list.
    mism = rep.pop("mismatches", None)
    rep["mismatch_sample"] = mism.head(50) if isinstance(mism, pd.DataFrame) else list(mism or [])[:50]
    booked = df["booked"].to_numpy(dtype=bool)
    out["overview"] = clean({
        "reproduction": rep,
        "approval_count": int((ev["decision"] == "approve").sum()),
        "booked_count": int(booked.sum()),
        "observed_bad_rate": float(df.loc[booked, "bad_flag"].mean()),
        "app_date_min": df["app_date"].min(),
        "app_date_max": df["app_date"].max(),
    })
    print("[overview] done")

    # ---------------------------------------------------------------- 2. waterfall
    wf = build_waterfall(df, baseline, ev, adjustment="historical")
    out["waterfall"] = clean({
        "steps": wf.to_dict("records"),
        "single_rule": single_rule_declines(df, baseline, ev).to_dict("records"),
        "heatmap": {
            "rows": list(map(str, decline_heatmap(df, cfg, baseline, ev).index)),
            "cols": list(map(str, decline_heatmap(df, cfg, baseline, ev).columns)),
            "values": decline_heatmap(df, cfg, baseline, ev).to_numpy().tolist(),
        },
    })
    print("[waterfall] done")

    # ---------------------------------------------------------------- 3. risk model
    anchor = near_cutoff_anchor(df, model, cfg)
    out["model"] = clean({
        "auc": model.metrics.get("auc") if hasattr(model, "metrics") else None,
        "metrics": getattr(model, "metrics", {}),
        "coefficients": model.coefficients().to_dict("records"),
        "calibration": model.calibration.to_dict("records") if getattr(model, "calibration", None) is not None else [],
        "support_summary": model.support_summary().to_dict("records"),
        "support_ranges": model.support_ranges().to_dict("records"),
        "anchor": {k: (v.to_dict("records") if isinstance(v, pd.DataFrame) else v)
                   for k, v in anchor.items()},
    })
    print("[model] done")

    # ---------------------------------------------------------------- 4. scenario grid
    out["grid"] = {"cutoffs": CUTOFFS, "foir_caps": FOIR_CAPS,
                   "toggles": [{"R3_THIN_FILE": a, "R4_BUREAU_HIST": b} for a, b in TOGGLES],
                   "scenarios": {}}
    if not args.skip_grid:
        t = time.time()
        total = len(CUTOFFS) * len(FOIR_CAPS) * len(TOGGLES)
        i = 0
        for r3, r4 in TOGGLES:
            for cut in CUTOFFS:
                for cap in FOIR_CAPS:
                    sc = with_rule_params(baseline, {"R5_SCORE": {"cutoff": cut},
                                                     "R6_FOIR": {"cap": cap}})
                    sc = with_rule_enabled(sc, {"R3_THIN_FILE": r3, "R4_BUREAU_HIST": r4})
                    res, det = simulate_detailed(df, baseline, sc, model, cfg)
                    key = f"{cut}|{cap}|{int(r3)}|{int(r4)}"
                    out["grid"]["scenarios"][key] = scenario_record(res, det, keep_breakdown=(r3 and r4))
                    i += 1
                    if i % 50 == 0:
                        print(f"[grid] {i}/{total}  {time.time() - t:.0f}s")
        print(f"[grid] {total} scenarios in {time.time() - t:.0f}s")

    # ---------------------------------------------------------------- 5. optimiser
    t = time.time()
    opt = optimise(df, baseline, model, cfg)
    out["optimiser"] = clean(optimiser_result_to_dict(opt, cfg))
    out["optimiser"]["headline_full"] = scenario_record(opt.headline, None, keep_breakdown=True)
    print(f"[optimiser] done in {time.time() - t:.0f}s")

    # ---------------------------------------------------------------- 6. portfolio quality
    t = time.time()
    diag = swap_out_analysis(df, baseline, cfg)
    eligible, portfolio_rate = candidate_declines(df, baseline, cfg)
    trade = combined_trade(df, baseline, model, cfg, base_result=opt)
    out["portfolio"] = clean({
        "diagnostic": diag.to_dict("records"),
        "eligible": eligible.to_dict("records"),
        "portfolio_rate": portfolio_rate,
        "min_segment_size": cfg["optimiser"]["min_segment_size"],
        "trade": {k: v for k, v in trade.items() if not isinstance(v, (pd.DataFrame,))
                  and k not in {"strategy", "headline"}},
        "trade_headline": scenario_record(trade["headline"], None, keep_breakdown=False)
        if trade.get("headline") is not None else None,
    })
    print(f"[portfolio] done in {time.time() - t:.0f}s")

    # ---------------------------------------------------------------- 7. validation
    if oracle_available(df):
        t = time.time()
        out["validation"] = clean({
            "strategy": validate_strategy_oracle(df, baseline, opt.strategy, opt.headline, model),
            "anchor": validate_near_cutoff_oracle(df, anchor, penalty).to_dict("records"),
        })
        print(f"[validation] done in {time.time() - t:.0f}s")
    else:
        out["validation"] = None

    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(out, separators=(",", ":"))
    path.write_text(blob)
    print(f"[write] {path}  {path.stat().st_size / 1e6:.2f} MB")

    # The prototype has no server, so the same payload ships as a script that
    # assigns a global. ui/app.js reads window.__FIXTURE__ and nothing else.
    js = path.with_name("data.js")
    js.write_text("window.__FIXTURE__ = " + blob + ";\n")
    print(f"[write] {js}  {js.stat().st_size / 1e6:.2f} MB  total {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
