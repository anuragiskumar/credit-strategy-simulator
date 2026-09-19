"""What-if simulation (REQUIREMENTS.md Section 10.1).

Accounting. A scenario is *history plus the strategy delta*:

    swap-in   scenario approves, baseline strategy declined, applicant was NOT booked
    swap-out  baseline strategy approved, scenario declines, applicant WAS booked
    retained  booked and not swapped out

Manual overrides that happened historically are left as they were — the scenario only changes the
decisions where the two strategies disagree — so an unchanged scenario reproduces the actual book
with zero swap-ins and swap-outs.

Performance of each group, with provenance (Section 6):

    retained booked           OBSERVED      actual bad_flag
    swap-ins with a PD        INFERRED      model PD x inference penalty
    swap-ins without a PD     NOT_MODELLED  counted as approvals, excluded from the blended rate

    blended = (sum observed bad_flag of retained + sum inferred PD of modelled swap-ins)
              / (retained + modelled swap-ins)
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import load_config
from src.contracts import ScenarioResult, SegmentExclusion, SegmentOverride, Strategy
from src.risk_model import INFERRED, NOT_MODELLED, OBSERVED, PREDICTED, RiskModel, train_model
from src.rules import (evaluate_strategy, strategy_from_config, with_exclusions, with_overrides, with_rule_enabled,
                       with_rule_params)
from src.segments import cell_label, dimension_frame, dimensions_from_config
from src.util import log, print_json
from src.waterfall import build_waterfall


# --------------------------------------------------------------------------- scenario spec
def _override_from_dict(o: dict, default_relaxes: list[str]) -> SegmentOverride:
    """Numeric [lo, hi] lists become (lo, hi) tuples; everything else is left as written."""
    cond = {}
    for k, v in o["conditions"].items():
        is_range = (isinstance(v, (list, tuple)) and len(v) == 2
                    and all(x is None or (isinstance(x, (int, float)) and not isinstance(x, bool)) for x in v)
                    and (k in {"bureau_score", "foir"} or any(x is not None for x in v)))
        cond[k] = (float("-inf") if v[0] is None else v[0],
                   float("inf") if v[1] is None else v[1]) if is_range else v
    return SegmentOverride(conditions=cond, relaxes=tuple(o.get("relaxes", default_relaxes)))


def _exclusion_from_dict(o: dict) -> SegmentExclusion:
    conditions = _override_from_dict({"conditions": o["conditions"]}, []).conditions
    return SegmentExclusion(conditions=conditions, reason=o["reason"])


def scenario_from_dict(baseline: Strategy, spec: dict, config: dict) -> Strategy:
    """Build a scenario Strategy from a JSON-friendly spec:

        {"rules": {"R5_SCORE": {"cutoff": 680}, "R6_FOIR": {"cap": 0.55}},
         "enabled": {"R3_THIN_FILE": false},
         "overrides": [{"conditions": {"bureau_score": [680, 700], "foir_max": 0.35,
                                       "employment_type": ["salaried"]},
                        "relaxes": ["R5_SCORE", "R6_FOIR"]}]}

    Mandatory rules cannot be edited or switched off; the helpers raise if asked to.
    """
    unknown = set(spec) - {"rules", "enabled", "overrides", "exclusions", "inference_penalty"}
    if unknown:
        raise KeyError(f"Unknown scenario keys: {sorted(unknown)}")
    s = baseline
    if spec.get("rules"):
        s = with_rule_params(s, spec["rules"])
    if spec.get("enabled"):
        s = with_rule_enabled(s, spec["enabled"])
    if spec.get("overrides"):
        relaxes = config["segment_overrides"]["default_relaxes"]
        s = with_overrides(s, tuple(_override_from_dict(o, relaxes) for o in spec["overrides"]))
    if "exclusions" in spec:
        s = with_exclusions(s, tuple(_exclusion_from_dict(o) for o in spec["exclusions"]))
    return s


def check_mandatory_unchanged(baseline: Strategy, scenario: Strategy) -> None:
    """Mandatory rules can never be relaxed by the simulator, however the scenario was built."""
    if [r.id for r in baseline.rules] != [r.id for r in scenario.rules]:
        raise ValueError("scenario must have the same rules, in the same order, as the baseline")
    for b, s in zip(baseline.rules, scenario.rules):
        if b.mandatory and (b.params != s.params or b.enabled != s.enabled or not s.mandatory):
            raise ValueError(f"{b.id} is mandatory and cannot be relaxed or switched off")


# --------------------------------------------------------------------------- blended bad rate
def penalised_pd(pds, penalty: float) -> np.ndarray:
    """INFERRED PD = model PD x penalty, capped at 1 so it stays a probability."""
    return np.minimum(np.asarray(pds, dtype=float) * penalty, 1.0)


def inferred_bad_rate(modelled_pds, penalty: float) -> float:
    n = len(modelled_pds)
    return float(penalised_pd(modelled_pds, penalty).mean()) if n else float("nan")


def blended_bad_rate(observed_bads: float, n_retained: int, modelled_pds, penalty: float) -> float:
    """(observed bads of retained + inferred PDs of modelled swap-ins) / (retained + modelled swap-ins).

    `modelled_pds` must contain only rows that have a PD: NOT_MODELLED swap-ins are excluded from
    both numerator and denominator and are never imputed as zero.
    """
    pds = np.asarray(modelled_pds, dtype=float)
    if np.isnan(pds).any():
        raise ValueError("NOT_MODELLED rows (NaN PD) must be excluded before blending")
    n = n_retained + len(pds)
    if n == 0:
        return float("nan")
    return float((observed_bads + penalised_pd(pds, penalty).sum()) / n)


# --------------------------------------------------------------------------- result
@dataclass
class SimulationDetail:
    """Numbers that do not fit in `ScenarioResult` but every report needs."""
    penalty: float
    baseline_approval_count: int
    baseline_approval_rate: float
    baseline_observed_bad_rate: float        # OBSERVED, all booked
    model_basis_coverage: float              # share of baseline booked that has a PD
    model_bias_ratio: float                  # model_basis / observed - 1
    retained_count: int
    retained_bads: float
    modelled_swap_in_count: int
    not_modelled_share: float                # of approvals
    warnings: list[str] = field(default_factory=list)
    seconds: float = 0.0


def _scenario_waterfall(df: pd.DataFrame, scenario: Strategy, ev: pd.DataFrame,
                        final: np.ndarray) -> pd.DataFrame:
    """Rule-by-rule waterfall of the scenario, reconciled to the scenario's actual approvals.

    The engine's approvals differ from the scenario's final approvals only on historical manual
    overrides, which the scenario carries over. That step is computed from the `manual_override` rows
    alone; if any other row differs the accounting upstream is wrong and this raises.
    """
    engine = (ev["decision"] == "approve").to_numpy()
    override = df["manual_override"].to_numpy(dtype=bool)
    if (engine != final)[~override].any():
        raise AssertionError(f"{int((engine != final)[~override].sum())} non-override rows differ between "
                             f"the scenario's rules and its final approvals")
    carried = int(final[override].sum()) - int(engine[override].sum())
    final_count = int(final.sum())

    wf = build_waterfall(df, scenario, ev, adjustment="segment_overrides").iloc[:-1]
    n, engine_count = len(df), int(wf["remaining"].iloc[-1])
    tail = pd.DataFrame([
        {"step": len(wf), "label": "Historical manual overrides carried over (net)", "kind": "adjustment",
         "delta": carried, "remaining": engine_count + carried},
        {"step": len(wf) + 1, "label": "Approved (scenario)", "kind": "end", "delta": None,
         "remaining": engine_count + carried},
    ])
    if engine_count + carried != final_count:
        raise AssertionError(f"scenario waterfall ends at {engine_count + carried}, approvals are {final_count}")
    wf = pd.concat([wf, tail], ignore_index=True)
    wf["delta_pct"] = wf["delta"] / n
    wf["remaining_pct"] = wf["remaining"] / n
    return wf


def _swap_in_breakdown(swap: pd.DataFrame, raw_pd: np.ndarray, penalty: float, model: RiskModel,
                       config: dict) -> pd.DataFrame:
    """Swap-ins by segmentation cell, with the joint-support count and THIN flag beside each inferred
    rate. NOT_MODELLED is always its own row, even when empty."""
    dims = dimensions_from_config(config)
    dim_cols = [d.column for d in dims]
    min_cell = config["model"]["min_cell_obs"]
    total = len(swap)
    modelled = ~np.isnan(raw_pd)

    parts = []
    if modelled.any():
        sw = swap[modelled]
        frame, _ = dimension_frame(sw, dims)
        frame = frame.assign(_raw=raw_pd[modelled], _inf=penalised_pd(raw_pd[modelled], penalty),
                             _cell=model.cell_support(sw).to_numpy())
        g = frame.groupby(dim_cols, observed=True, dropna=False)
        agg = g.agg(count=("_inf", "size"), inferred_bad_rate=("_inf", "mean"),
                    model_pd=("_raw", "mean"), booked_in_cell=("_cell", "first")).reset_index()
        agg.insert(len(dim_cols), "segment", cell_label(agg[dim_cols]))
        agg["thin"] = agg["booked_in_cell"] < min_cell
        agg["provenance"] = INFERRED
        agg[dim_cols] = agg[dim_cols].astype(object)
        parts.append(agg.sort_values(["count", "segment"], ascending=[False, True]))

    nm = {c: "—" for c in dim_cols}
    nm.update({"segment": "NOT_MODELLED (no model support)", "count": int((~modelled).sum()),
               "inferred_bad_rate": np.nan, "model_pd": np.nan, "booked_in_cell": pd.NA,
               "thin": pd.NA, "provenance": NOT_MODELLED})
    out = pd.concat([*parts, pd.DataFrame([nm])], ignore_index=True)
    out["share_of_swap_ins"] = out["count"] / total if total else np.nan
    return out


def _sensitivity(observed_bads: float, n_retained: int, modelled_pds: np.ndarray,
                 penalties: list[float]) -> pd.DataFrame:
    rows = [{"penalty": p, "inferred_bad_rate": inferred_bad_rate(modelled_pds, p),
             "blended_bad_rate": blended_bad_rate(observed_bads, n_retained, modelled_pds, p)}
            for p in sorted(penalties)]
    return pd.DataFrame(rows)


def simulate_detailed(df: pd.DataFrame, baseline: Strategy, scenario: Strategy, model: RiskModel,
                      config: dict, penalty: float | None = None) -> tuple[ScenarioResult, SimulationDetail]:
    t0 = time.perf_counter()
    check_mandatory_unchanged(baseline, scenario)
    m = config["model"]
    penalty = m["inference_penalty"] if penalty is None else penalty
    n = len(df)

    ev_base = evaluate_strategy(df, baseline)
    ev_scen = evaluate_strategy(df, scenario)
    base_a = (ev_base["decision"] == "approve").to_numpy()
    scen_a = (ev_scen["decision"] == "approve").to_numpy()
    booked = df["booked"].to_numpy(dtype=bool)

    swap_in = scen_a & ~base_a & ~booked
    swap_out = base_a & ~scen_a & booked
    retained = booked & ~swap_out
    n_book, n_ret, n_in, n_out = int(booked.sum()), int(retained.sum()), int(swap_in.sum()), int(swap_out.sum())
    approval_count = n_ret + n_in

    # Baseline, OBSERVED and PREDICTED (model-basis) on the same booked population.
    bad = df["bad_flag"].fillna(0).to_numpy(dtype=float)
    baseline_observed = float(bad[booked].sum() / n_book) if n_book else float("nan")
    booked_pd = model.predict_pd(df[booked]).to_numpy()
    has_pd = ~np.isnan(booked_pd)
    model_basis = float(booked_pd[has_pd].mean()) if has_pd.any() else float("nan")
    bias = model_basis / baseline_observed - 1 if baseline_observed else float("nan")

    # Swap-ins: PD where the model has support, NaN (NOT_MODELLED) where it does not.
    swap = df[swap_in]
    raw_pd = model.predict_pd(swap).to_numpy()
    modelled = ~np.isnan(raw_pd)
    n_mod, n_nm = int(modelled.sum()), int((~modelled).sum())
    pds = raw_pd[modelled]

    retained_bads = float(bad[retained].sum())
    observed_rate = retained_bads / n_ret if n_ret else float("nan")
    inf_rate = inferred_bad_rate(pds, penalty)
    blended = blended_bad_rate(retained_bads, n_ret, pds, penalty)

    result = ScenarioResult(
        approval_count=approval_count,
        approval_rate=approval_count / n,
        swap_in_count=n_in,
        swap_out_count=n_out,
        not_modelled_count=n_nm,
        observed_bad_rate=observed_rate,
        model_basis_baseline=model_basis,
        inferred_bad_rate=inf_rate,
        blended_bad_rate=blended,
        inferred_share=n_mod / approval_count if approval_count else float("nan"),
        waterfall=_scenario_waterfall(df, scenario, ev_scen, retained | swap_in),
        swap_in_breakdown=_swap_in_breakdown(swap, raw_pd, penalty, model, config),
        sensitivity=_sensitivity(retained_bads, n_ret, pds, m["sensitivity_penalties"]),
    )

    nm_share = n_nm / approval_count if approval_count else float("nan")
    warnings = []
    if n_nm:
        warnings.append(f"{n_nm:,} of these approvals cannot be scored by the model. "
                        f"The bad rate shown covers only the remainder.")
    if n_mod:
        warnings.append("Inferred performance for previously declined applicants is extrapolation "
                        "below the historical cutoff: the model was trained on booked customers, "
                        "who were selected by the current strategy.")
    if result.inferred_share > m["max_inferred_share"]:
        warnings.append(f"{result.inferred_share:.0%} of approvals rest on inferred performance "
                        f"(limit {m['max_inferred_share']:.0%}).")
    if np.isfinite(bias) and abs(bias) > m["bias_warning_ratio"]:
        warnings.append(f"Model-basis baseline ({model_basis:.2%}) differs from the observed baseline "
                        f"({baseline_observed:.2%}) by {bias:+.0%}: the model is biased on the booked "
                        f"book, so read the scenario delta with that in mind.")

    detail = SimulationDetail(
        penalty=penalty, baseline_approval_count=n_book, baseline_approval_rate=n_book / n,
        baseline_observed_bad_rate=baseline_observed, model_basis_coverage=float(has_pd.mean()),
        model_bias_ratio=bias, retained_count=n_ret, retained_bads=retained_bads,
        modelled_swap_in_count=n_mod, not_modelled_share=nm_share, warnings=warnings,
        seconds=time.perf_counter() - t0)
    return result, detail


def simulate(df: pd.DataFrame, baseline: Strategy, scenario: Strategy,
             model: RiskModel, config: dict) -> ScenarioResult:
    return simulate_detailed(df, baseline, scenario, model, config)[0]


# --------------------------------------------------------------------------- reporting
def _labelled(value: float, provenance: str, **extra) -> dict:
    return {"value": value, "provenance": provenance, **extra}


def blended_statement(result: ScenarioResult) -> str:
    """The sentence that must sit beside every blended figure (Section 6)."""
    s = f"blended bad rate {result.blended_bad_rate:.2%}"
    if result.not_modelled_count:
        s += f" (excludes {result.not_modelled_count:,} approvals with no model support)"
    return s


def result_to_dict(result: ScenarioResult, detail: SimulationDetail, spec: dict | None = None) -> dict:
    r, d = result, detail
    return {
        "scenario": spec or {},
        "inference_penalty": d.penalty,
        "approvals": {
            "baseline_count": d.baseline_approval_count,
            "baseline_rate": d.baseline_approval_rate,
            "scenario_count": r.approval_count,
            "scenario_rate": r.approval_rate,
            "swap_in_count": r.swap_in_count,
            "swap_out_count": r.swap_out_count,
            "modelled_swap_in_count": d.modelled_swap_in_count,
            "not_modelled_count": r.not_modelled_count,
            "not_modelled_share_of_approvals": d.not_modelled_share,
            "inferred_share_of_approvals": r.inferred_share,
        },
        "bad_rate": {
            "baseline_observed": _labelled(d.baseline_observed_bad_rate, OBSERVED, population="baseline booked"),
            "model_basis_baseline": _labelled(r.model_basis_baseline, PREDICTED, population="baseline booked",
                                              coverage=d.model_basis_coverage),
            "scenario_observed_retained": _labelled(r.observed_bad_rate, OBSERVED,
                                                    population="retained booked", n=d.retained_count),
            "scenario_inferred_swap_ins": _labelled(r.inferred_bad_rate, INFERRED,
                                                    population="modelled swap-ins",
                                                    n=d.modelled_swap_in_count),
            "scenario_blended": _labelled(r.blended_bad_rate, f"{OBSERVED}+{INFERRED}",
                                          excludes_not_modelled=r.not_modelled_count),
            "model_bias_ratio": d.model_bias_ratio,
        },
        "statement": blended_statement(r),
        "warnings": d.warnings,
        "waterfall": r.waterfall,
        "swap_in_breakdown": r.swap_in_breakdown,
        "sensitivity": r.sensitivity.assign(provenance=f"{OBSERVED}+{INFERRED}"),
        "simulate_seconds": d.seconds,
    }


def load_scenario_spec(arg: str | None) -> dict:
    """`--scenario` accepts inline JSON or a path to a JSON file; omitted means 'no change'."""
    if not arg:
        return {}
    text = arg if arg.lstrip().startswith("{") else Path(arg).read_text(encoding="utf-8")
    return json.loads(text)


def main(argv: list[str] | None = None) -> int:
    from src.loader import load_applications

    ap = argparse.ArgumentParser(description="Simulate a strategy change against the historical book.")
    ap.add_argument("--scenario", help="scenario JSON (inline or a file path); omit for the baseline")
    ap.add_argument("--data", help="parquet path (default: config data_path)")
    ap.add_argument("--config", help="config.yaml path")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    spec = load_scenario_spec(args.scenario)
    df = load_applications(args.data, cfg)
    baseline = strategy_from_config(cfg)
    scenario = scenario_from_dict(baseline, spec, cfg)

    t0 = time.perf_counter()
    model = train_model(df, cfg)
    train_s = time.perf_counter() - t0
    result, detail = simulate_detailed(df, baseline, scenario, model, cfg, spec.get("inference_penalty"))

    out = result_to_dict(result, detail, spec)
    out["model_train_seconds"] = train_s
    a, b = out["approvals"], out["bad_rate"]
    log(f"\nApprovals   baseline {a['baseline_count']:,} ({a['baseline_rate']:.2%})  ->  "
        f"scenario {a['scenario_count']:,} ({a['scenario_rate']:.2%})   "
        f"swap-ins {a['swap_in_count']:,}  swap-outs {a['swap_out_count']:,}")
    log(f"Bad rate    observed baseline {b['baseline_observed']['value']:.2%} [OBSERVED]   "
        f"model-basis baseline {b['model_basis_baseline']['value']:.2%} [PREDICTED]")
    inf = b["scenario_inferred_swap_ins"]["value"]
    log(f"            scenario retained {b['scenario_observed_retained']['value']:.2%} [OBSERVED]   "
        f"swap-ins {'n/a' if inf != inf else format(inf, '.2%')} [INFERRED @ penalty {detail.penalty}]")
    log(f"            {out['statement']}  [OBSERVED+INFERRED]")
    for w in detail.warnings:
        log(f"WARNING: {w}")
    log("\nSensitivity to the conservatism penalty:")
    log(result.sensitivity.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    log(f"\nsimulate {detail.seconds:.2f}s (model training {train_s:.1f}s not included)")
    print_json(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
