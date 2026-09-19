"""Synthetic application generator (Section 5.2) and calibration report (Section 5.3).

One of only two modules (with validation.py) allowed to touch the synthetic outcome column.

`python -m src.generate_data [--n-rows N] [--seed S] [--out PATH] [--fixture]`
Prints the calibration table to stderr and the same result as JSON to stdout.
"""
from __future__ import annotations

import argparse
import json
import sys

import numpy as np
import pandas as pd

from src.config import load_config, resolve_path

SCHEMA_ORDER = [
    "application_id", "app_date", "age", "employment_type", "monthly_income", "loan_amount",
    "tenor_months", "existing_emi", "proposed_emi", "foir", "bureau_score",
    "bureau_vintage_months", "max_dpd_12m", "enquiries_6m", "fraud_flag", "hist_decision",
    "hist_decline_reason", "manual_override", "booked", "bad_flag", "true_bad",
]


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def _emi(principal: np.ndarray, tenor: np.ndarray, apr: float) -> np.ndarray:
    r = apr / 12.0
    return principal * r / (1.0 - (1.0 + r) ** (-tenor.astype(float)))


def _written_strategy_failures(d: dict, rule_cfgs: list[dict]) -> dict[str, np.ndarray]:
    """Independent implementation of the current strategy (deliberately NOT src/rules.py, so the
    reproduction check in 7.3 is a genuine cross-check). Returns {rule_id: failed bool array}."""
    p = {r["id"]: r["params"] for r in rule_cfgs}
    score = d["bureau_score"]
    return {
        "R1_AGE": (d["age"] < p["R1_AGE"]["min_age"]) | (d["age"] > p["R1_AGE"]["max_age"]),
        "R2_FRAUD": d["fraud_flag"],
        "R3_THIN_FILE": np.isnan(score) | (d["bureau_vintage_months"] < p["R3_THIN_FILE"]["min_vintage"]),
        "R4_BUREAU_HIST": (d["max_dpd_12m"] >= p["R4_BUREAU_HIST"]["dpd_lt"])
        | (d["enquiries_6m"] > p["R4_BUREAU_HIST"]["max_enquiries"]),
        "R5_SCORE": ~(score >= p["R5_SCORE"]["cutoff"]),
        "R6_FOIR": d["foir"] > p["R6_FOIR"]["cap"],
    }


def _first_failed(failed: dict[str, np.ndarray], order: list[str]) -> np.ndarray:
    reason = np.full(len(next(iter(failed.values()))), None, dtype=object)
    for rid in reversed(order):                              # earliest rule wins
        reason = np.where(failed[rid], rid, reason)
    return reason


def generate(cfg: dict) -> pd.DataFrame:
    g = cfg["generator"]
    n = int(cfg["n_rows"])
    rng = np.random.default_rng(cfg["seed"])

    # --- demographics
    outside = rng.random(n) < g["age_outside_share"]
    age_in = rng.integers(21, 61, n)
    age_out = np.where(rng.random(n) < 0.5, rng.integers(g["age_min"], 21, n),
                       rng.integers(61, g["age_max"] + 1, n))
    age = np.where(outside, age_out, age_in)

    emp_levels = list(g["employment_probs"])
    employment = rng.choice(emp_levels, size=n, p=[g["employment_probs"][k] for k in emp_levels])

    # --- bureau
    score = np.clip(np.round(rng.normal(g["score_mean"], g["score_sd"], n)),
                    g["score_min"], g["score_max"])
    no_hit = rng.random(n) < g["no_hit_share"]
    thin = ~no_hit & (rng.random(n) < g["thin_file_share"])
    vintage = np.round(6 + rng.gamma(2.0, 30.0, n)).astype(int)
    vintage = np.where(thin, rng.integers(1, 6, n), vintage)
    vintage = np.where(no_hit, 0, vintage)
    score = np.where(no_hit, np.nan, score)
    score_imp = np.where(no_hit, g["no_hit_score_impute"], score)
    z = (g["score_mean"] - score_imp) / g["score_sd"]

    p_dpd = _sigmoid(g["dpd_any"]["a0"] + g["dpd_any"]["a1"] * z)
    has_dpd = rng.random(n) < p_dpd
    dpd_level = rng.choice(g["dpd_levels"], size=n, p=g["dpd_level_probs"])
    max_dpd = np.where(has_dpd, dpd_level, 0)

    k = g["enquiries"]["gamma_shape"]
    lam = np.exp(g["enquiries"]["e0"] + g["enquiries"]["e1"] * z) * rng.gamma(k, 1.0 / k, n)
    enquiries = rng.poisson(lam)

    fraud = rng.random(n) < g["fraud_share"]

    # --- income, loan, EMI, FOIR
    income = np.maximum(
        np.round(rng.lognormal(np.log(g["income_median"]), g["income_sigma"], n), -2), g["income_min"])
    log_loan = (np.log(g["loan_median"])
                + g["loan_income_elasticity"] * (np.log(income) - np.log(g["income_median"]))
                + rng.normal(0, g["loan_sigma"], n))
    loan = np.exp(log_loan)
    tenor = rng.choice(g["tenors"], size=n)
    emi_unit = _emi(np.ones(n), tenor, g["apr"])
    loan = np.minimum(loan, g["max_proposed_emi_to_income"] * income / emi_unit)
    loan = np.maximum(np.round(loan / g["loan_rounding"]) * g["loan_rounding"], g["loan_min"])
    proposed_emi = np.round(loan * emi_unit, 2)
    foir_target = np.minimum(
        rng.lognormal(np.log(g["foir_target_median"]), g["foir_target_sigma"], n),
        g["foir_max"] - 0.01)
    existing_emi = np.round(np.maximum(0.0, foir_target * income - proposed_emi), 2)
    foir = (existing_emi + proposed_emi) / income

    # --- true default probability, for every applicant
    pdc = g["pd"]
    emp_effect = np.array([pdc["employment"][e] for e in employment])
    logit = (pdc["b0"] + pdc["b1"] * (pdc["score_pivot"] - score_imp) / pdc["score_step"]
             + pdc["b2"] * foir + pdc["b3"] * (max_dpd > 0) + pdc["b4"] * enquiries + emp_effect)
    p = _sigmoid(logit)
    true_bad = (rng.random(n) < p).astype(np.int8)

    # --- written strategy -> decision
    feats = {"age": age, "fraud_flag": fraud, "bureau_score": score,
             "bureau_vintage_months": vintage, "max_dpd_12m": max_dpd,
             "enquiries_6m": enquiries, "foir": foir}
    failed = _written_strategy_failures(feats, cfg["strategy"]["rules"])
    reason = _first_failed(failed, [r["id"] for r in cfg["strategy"]["rules"]])
    written_approve = np.array([r is None for r in reason])
    # Overrides only ever cover applicants failing nothing but the listed rules (never mandatory
    # rules, thin file or bureau history), so eligibility is a subset of "passes all mandatory rules".
    other_fail = np.zeros(n, dtype=bool)
    for rid, f in failed.items():
        if rid not in g["overrides"]["eligible_failed_rules"]:
            other_fail |= f
    eligible = ~written_approve & ~other_fail

    # --- manual overrides (5.2.1)
    ov = g["overrides"]
    n_ov = int(round(ov["rate"] * n))
    n_d2a = int(round(ov["decline_to_approve_share"] * n_ov))
    n_a2d = n_ov - n_d2a

    pool = np.flatnonzero(eligible)
    band_mask = ((score >= ov["band_score"][0]) & (score < ov["band_score"][1])
                 & (foir >= ov["band_foir"][0]) & (foir <= ov["band_foir"][1]))
    band_pool = np.flatnonzero(eligible & band_mask)
    n_band = min(int(round(ov["band_share"] * n_d2a)), len(band_pool))
    w = p[band_pool] ** (-ov["favour_exponent"])        # mildly favourable: lower PD picked more often
    band_pick = (rng.choice(band_pool, size=n_band, replace=False, p=w / w.sum())
                 if n_band else np.array([], dtype=int))
    rest_pool = np.setdiff1d(pool, band_pick)
    n_rest = min(n_d2a - n_band, len(rest_pool))
    rest_pick = rng.choice(rest_pool, size=n_rest, replace=False) if n_rest else np.array([], dtype=int)
    d2a = np.concatenate([band_pick, rest_pick]).astype(int)

    a2d_pool = np.flatnonzero(written_approve)
    a2d = rng.choice(a2d_pool, size=min(n_a2d, len(a2d_pool)), replace=False)

    manual = np.zeros(n, dtype=bool)
    manual[d2a] = True
    manual[a2d] = True
    hist_approve = written_approve.copy()
    hist_approve[d2a] = True
    hist_approve[a2d] = False
    hist_reason = reason.copy()
    hist_reason[d2a] = None
    hist_reason[a2d] = "MANUAL_OVERRIDE"

    bad_flag = pd.array(np.where(hist_approve, true_bad, 0), dtype="Int8")
    bad_flag[~hist_approve] = pd.NA

    start = pd.Timestamp(g["app_date_start"])
    app_date = start + pd.to_timedelta(rng.integers(0, g["app_date_days"], n), unit="D")

    df = pd.DataFrame({
        "application_id": pd.Series(np.char.add("APP", np.char.zfill(np.arange(1, n + 1).astype(str), 8))),
        "app_date": app_date,
        "age": age.astype(np.int64),
        "employment_type": pd.Categorical(employment, categories=emp_levels),
        "monthly_income": income,
        "loan_amount": loan,
        "tenor_months": tenor.astype(np.int64),
        "existing_emi": existing_emi,
        "proposed_emi": proposed_emi,
        "foir": foir,
        "bureau_score": score,
        "bureau_vintage_months": vintage.astype(np.int64),
        "max_dpd_12m": max_dpd.astype(np.int64),
        "enquiries_6m": enquiries.astype(np.int64),
        "fraud_flag": fraud,
        "hist_decision": pd.Categorical(np.where(hist_approve, "approve", "decline"),
                                        categories=["approve", "decline"]),
        "hist_decline_reason": pd.Series(hist_reason, dtype=object),
        "manual_override": manual,
        "booked": hist_approve,
        "bad_flag": bad_flag,
        "true_bad": pd.array(true_bad, dtype="Int8"),
    })
    return df[SCHEMA_ORDER]


# --------------------------------------------------------------------------- calibration (5.3)
def calibration_table(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    # Imported here so the generator itself stays independent of the rule engine.
    from src.rules import evaluate_strategy, reproduction_report, strategy_from_config

    c = cfg["calibration"]
    strategy = strategy_from_config(cfg)
    ev = evaluate_strategy(df, strategy)
    n = len(df)
    booked = df["booked"].to_numpy()
    tb = df["true_bad"].to_numpy(dtype=float)
    score = df["bureau_score"].to_numpy(dtype=float)

    others_pass = ~ev[[f"failed_{r.id}" for r in strategy.rules if r.id != "R5_SCORE"]].any(axis=1).to_numpy()
    lo, hi = c["score_band"]
    in_band = (score >= lo) & (score < hi)
    sal_low = ((df["employment_type"] == "salaried").to_numpy()
               & (df["foir"].to_numpy() <= c["salaried_low_foir_cap"]))

    rule_share = {r.id: float((ev["first_failed_rule"] == r.id).mean()) for r in strategy.rules}
    rep = reproduction_report(df, strategy, ev)
    lo2, hi2 = c["near_cutoff_band"]
    booked_near = int((booked & (score >= lo2) & (score < hi2)).sum())
    booked_near_target = c["booked_650_699_min"] * n / 1_000_000

    rows = [
        ("Baseline approval rate", c["approval_rate"], float((df["hist_decision"] == "approve").mean())),
        ("Observed bad rate of approved", c["observed_bad_rate"],
         float(df.loc[booked, "bad_flag"].astype(float).mean())),
        ("True bad rate, score 680-699, rules otherwise passed", c["true_bad_680_699"],
         float(np.nanmean(tb[in_band & others_pass]))),
        ("True bad rate, score 680-699, salaried, FOIR<=35%, rules otherwise passed",
         c["true_bad_680_699_salaried_low_foir"],
         float(np.nanmean(tb[in_band & others_pass & sal_low]))),
        ("Smallest decline-rule share of applications (waterfall)", [c["rule_min_share"], None],
         min(rule_share.values())),
        ("Reproduction match rate (raw)", c["reproduction_match_rate"], rep["raw_match_rate"]),
        ("Reproduction mismatches that are NOT manual overrides", [0, 0], rep["n_mismatches_not_override"]),
        (f"Booked rows with score 650-699 (target scaled to n={n:,})", [booked_near_target, None], booked_near),
    ]
    out = pd.DataFrame(rows, columns=["metric", "target", "actual"])
    out["pass"] = [
        (t[0] is None or a >= t[0]) and (t[1] is None or a <= t[1])
        for t, a in zip(out["target"], out["actual"])
    ]
    out.attrs["rule_share"] = rule_share
    return out


def _print_calibration(table: pd.DataFrame) -> None:
    def fmt_t(t):
        lo, hi = t
        if lo is None:
            return f"<= {hi}"
        if hi is None:
            return f">= {lo:g}"
        return f"{lo:g} – {hi:g}"

    w = max(len(m) for m in table["metric"])
    print("\nCalibration targets (Section 5.3)", file=sys.stderr)
    for _, r in table.iterrows():
        a = f"{r['actual']:,.0f}" if r["actual"] >= 100 else f"{r['actual']:.4f}"
        print(f"  [{'PASS' if r['pass'] else 'FAIL'}] {r['metric']:<{w}}  target {fmt_t(r['target']):<16} actual {a}",
              file=sys.stderr)
    print("  Decline-rule shares of applications (sequential): "
          + ", ".join(f"{k}={v:.2%}" for k, v in table.attrs["rule_share"].items()), file=sys.stderr)


# --------------------------------------------------------------------------- fixture
def build_fixture(cfg: dict, n_fixture: int = 500, n_override: int = 20, pool_rows: int = 100_000) -> pd.DataFrame:
    """~500-row committed test fixture: a random sample of a larger deterministic build, with
    manual-override rows oversampled (4%) so override-related tests are not vacuous."""
    big = generate({**cfg, "n_rows": pool_rows})
    rng = np.random.default_rng(cfg["seed"] + 1)
    ov_idx = np.flatnonzero(big["manual_override"].to_numpy())
    other_idx = np.flatnonzero(~big["manual_override"].to_numpy())
    d2a = ov_idx[(big["hist_decision"].to_numpy()[ov_idx] == "approve")]
    a2d = ov_idx[(big["hist_decision"].to_numpy()[ov_idx] == "decline")]
    n_d2a = int(round(n_override * cfg["generator"]["overrides"]["decline_to_approve_share"]))
    pick = np.concatenate([
        rng.choice(d2a, n_d2a, replace=False),
        rng.choice(a2d, n_override - n_d2a, replace=False),
        rng.choice(other_idx, n_fixture - n_override, replace=False),
    ])
    rng.shuffle(pick)
    return big.iloc[pick].reset_index(drop=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate the synthetic application dataset.")
    ap.add_argument("--n-rows", type=int, help="override config n_rows")
    ap.add_argument("--seed", type=int, help="override config seed")
    ap.add_argument("--out", help="output parquet path (default: config data_path)")
    ap.add_argument("--fixture", action="store_true", help="build the committed test fixture instead")
    ap.add_argument("--config", help="path to an alternative config.yaml")
    args = ap.parse_args(argv)

    overrides = {}
    if args.n_rows:
        overrides["n_rows"] = args.n_rows
    if args.seed:
        overrides["seed"] = args.seed
    cfg = load_config(args.config, overrides)

    if args.fixture:
        df = build_fixture(cfg)
        out = resolve_path(args.out or cfg["fixture_path"])
    else:
        df = generate(cfg)
        out = resolve_path(args.out or cfg["data_path"])
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    print(f"Wrote {len(df):,} rows to {out}", file=sys.stderr)
    if args.fixture:      # calibration targets are only meaningful at full scale
        print(json.dumps({"path": str(out), "n_rows": int(len(df)),
                          "n_manual_overrides": int(df["manual_override"].sum())}, indent=2))
        return 0

    table = calibration_table(df, cfg)
    _print_calibration(table)
    result = {
        "path": str(out), "n_rows": int(len(df)), "seed": cfg["seed"],
        "all_targets_met": bool(table["pass"].all()),
        "calibration": [
            {"metric": r["metric"], "target": list(r["target"]), "actual": float(r["actual"]),
             "pass": bool(r["pass"])}
            for r in table.to_dict("records")
        ],
        "rule_share": table.attrs["rule_share"],
    }
    print(json.dumps(result, indent=2))
    return 0 if result["all_targets_met"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
