"""Client-shaped synthetic applicant generator (plan step 2).

`python -m src.client_generate [--n-rows N] [--seed S] [--out PATH] [--fixture] [--check]`

The population is built so that the client's real 227 TWQR rules decide who is declined and why. The
generator never assigns a decline reason — it only sets field values. That is the brief's
"derive, don't assign" rule, and it is what makes the simulator work: moving a threshold has to
move real people across it.

Four answers are deliberately planted, so the analysis layer can be tested against a known
truth rather than against whatever it happens to produce:

  1. The digital channel carries a weaker applicant mix, so it should dominate the declines.
  2. Length of service does not predict risk, though rules decline on it. Question 10 —
     "which rules cost approvals without reducing risk" — must find it.
  3. A missing SIMAH score is the riskiest state, not a neutral one.
  4. The portfolio is concentrated in IT, thin in finance, and has no government exposure.

`latent_bad` is the true outcome for every applicant, including those who are declined. No real
bank has this. It exists only so reject inference can later be scored against truth, and the
analysis layer must never read it. What the analysis reads is `booking_date` and `bad_date`,
recorded only for the loans the rules actually book (see `_observe`), exactly as a bank's file
would carry them.
"""
from __future__ import annotations

import argparse
import json
import sys
from functools import lru_cache

import numpy as np
import pandas as pd

from src import client_schema
from src.config import ROOT, load_config, resolve_path

CONFIG_PATH = ROOT / "config_client.yaml"


def load_client_config(path=None, overrides: dict | None = None) -> dict:
    return load_config(path or CONFIG_PATH, overrides)


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def _z(x: np.ndarray) -> np.ndarray:
    """Standardise, tolerating NaN and a zero-variance column."""
    m, s = np.nanmean(x), np.nanstd(x)
    return np.zeros_like(x) if s == 0 else (x - m) / s


def _lognormal(rng, median, sigma, n, lo, hi):
    return np.clip(median * np.exp(rng.normal(0.0, sigma, n)), lo, hi)


def _pick(rng, mapping: dict, n):
    keys = list(mapping)
    return rng.choice(keys, size=n, p=[mapping[k] for k in keys])


def _solve_intercept(linear: np.ndarray, target: float) -> float:
    """Shift the logit so the mean probability equals the target bad rate."""
    lo, hi = -12.0, 12.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if _sigmoid(linear + mid).mean() < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def generate(cfg: dict) -> pd.DataFrame:
    n = int(cfg["n_rows"])
    rng = np.random.default_rng(cfg["seed"])
    pop, inc, bur, req = cfg["population"], cfg["income"], cfg["bureau"], cfg["request"]
    src, emp, mil = cfg["sourcing"], cfg["employers"], cfg["military"]

    # --- who they are ------------------------------------------------------
    segment = _pick(rng, pop["employer_segment_probs"], n)
    is_military = (segment == "GOV") & (rng.random(n) < pop["military_share_gov"])
    employment_type = np.where(is_military, "MILITARY", "CIVILIAN")
    is_pensioner = (rng.random(n) < pop["pensioner_share"]) & ~is_military

    is_saudi = rng.random(n) < pop["saudi_share"]
    nationality = np.where(is_saudi, "SAU",
                           rng.choice(pop["non_saudi_nationalities"], size=n))
    gender = np.where(rng.random(n) < pop["female_share"], "Female", "Male")
    sector = _pick(rng, pop["sector_probs"], n)

    a = cfg["age"]
    age = _lognormal(rng, a["median"], a["sigma"], n, a["min"], a["max"])
    age_ret = _lognormal(rng, a["pensioner_median"], a["pensioner_sigma"], n, a["min"], a["max"])
    age = np.round(np.where(is_pensioner, age_ret, age)).astype(int)

    # --- sourcing, before income: the digital plant shifts the applicant mix
    channel = _pick(rng, src["channel_probs"], n)
    is_digital = channel == "digital"
    agent_ix = rng.integers(0, src["agents_per_channel"], n)
    source_ix = rng.integers(0, src["sources_per_channel"], n)
    agent_id = np.char.add(np.char.add(channel.astype(str), "-A"),
                           np.char.zfill(agent_ix.astype(str), 2))
    source_code = np.char.add(np.char.add(channel.astype(str), "-S"), source_ix.astype(str))

    # --- income ------------------------------------------------------------
    median = np.array([inc["median_by_segment"][s] for s in segment], dtype=float)
    median = np.where(is_military, inc["military_median"], median)
    median = np.where(is_pensioner, median * inc["pensioner_multiplier"], median)
    median = np.where(is_digital, median * src["digital_income_multiplier"], median)
    income = np.round(_lognormal(rng, 1.0, inc["sigma"], n, 1e-6, 1e9) * median, 2)
    income = np.clip(income, inc["min"], inc["max"])

    los = cfg["length_of_service"]
    length_of_service = np.round(
        _lognormal(rng, los["median_months"], los["sigma"], n, los["min"], los["max"])).astype(int)
    recent = rng.random(n) < los["recent_joiner_share"]
    length_of_service = np.where(
        recent, rng.integers(0, los["recent_joiner_max_months"] + 1, n), length_of_service)
    length_of_service = np.minimum(length_of_service, np.maximum(0, (age - 18)) * 12)
    payslip_age = _pick(rng, cfg["payslip_age"]["probs"], n).astype(int)
    salary_to_bsf = np.where(rng.random(n) < cfg["salary_to_bsf_share"], "Yes", "No")

    # --- employer name: the rules read it, so emit names and let them decide
    is_staff = rng.random(n) < emp["staff_share"]
    kw_share = np.where(np.isin(segment, ["PRIVATE_SMALL", "SELF_EMPLOYED"]),
                        emp["keyword_share_small"], emp["keyword_share_other"])
    is_keyword = rng.random(n) < kw_share
    employer_name = rng.choice(emp["plain_names"], size=n)
    employer_name = np.where(is_keyword, rng.choice(emp["keyword_names"], size=n), employer_name)
    employer_name = np.where(is_pensioner, rng.choice(emp["retired_names"], size=n), employer_name)
    employer_name = np.where(is_staff, rng.choice(emp["staff_names"], size=n), employer_name)

    # --- bureau ------------------------------------------------------------
    simah = rng.normal(bur["simah_mean"], bur["simah_sd"], n)
    simah = np.where(is_digital, simah + src["digital_simah_shift"], simah)
    simah = np.round(np.clip(simah, bur["simah_min"], bur["simah_max"]))
    no_score_p = np.where(is_digital,
                          bur["no_score_share"] * src["digital_no_score_multiplier"],
                          bur["no_score_share"])
    has_no_score = rng.random(n) < no_score_p
    simah_score = np.where(has_no_score, np.nan, simah)

    crif = np.round(np.clip(simah + bur["crif_offset"] + rng.normal(0, bur["crif_noise_sd"], n),
                            bur["crif_min"], bur["crif_max"]))
    scorecard = _pick(rng, bur["scorecard_probs"], n)
    scorecard = np.where(has_no_score, "New To Credit", scorecard)
    customer_type = np.where(rng.random(n) < pop["ntb_share"], "NTB", "ETB")

    # --- the request -------------------------------------------------------
    # Elasticity below 1: higher earners ask for more, but less than proportionally —
    # the income-to-requested-amount relationship the LendingClub notebook showed.
    base = (req["median_multiple_of_income"] * income
            * (income / np.median(income)) ** (req["income_elasticity"] - 1.0))
    requested = _lognormal(rng, 1.0, req["sigma"], n, 1e-6, 1e9) * base
    small = rng.random(n) < req["small_ticket_share"]
    requested = np.where(
        small, rng.integers(req["small_ticket_min"], req["small_ticket_max"] + 1, n), requested)
    requested = np.clip(np.round(requested / req["rounding"]) * req["rounding"],
                        req["min"], req["max"])
    tenure = rng.choice(req["tenures"], size=n, p=req["tenure_probs"])
    downpayment = _pick(rng, req["downpayment_pct_probs"], n).astype(float)

    # --- regulatory flags --------------------------------------------------
    fl = cfg["flags"]
    is_pep = rng.random(n) < fl["pep_share"]
    related_to_pep = rng.random(n) < fl["related_to_pep_share"]
    diplomatic = rng.random(n) < fl["diplomatic_service_share"]

    # --- latent risk -------------------------------------------------------
    risk, co = cfg["risk"], cfg["risk"]["coefficients"]
    simah_for_risk = np.where(has_no_score, bur["simah_mean"], simah)
    loan_to_income = requested / np.maximum(income, 1.0)
    linear = (
        co["simah_score"] * _z(simah_for_risk)
        + co["crif_score"] * _z(crif.astype(float))
        + co["log_income"] * _z(np.log(income))
        + co["loan_to_income"] * _z(np.log(loan_to_income))
        + co["age"] * _z(age.astype(float))
        + co["length_of_service"] * _z(length_of_service.astype(float))
        + np.where(has_no_score, risk["no_score_uplift"], 0.0)
        + np.array([risk["sector_uplift"][s] for s in sector])
        + np.where(segment == "SELF_EMPLOYED", risk["self_employed_uplift"], 0.0)
        + np.where(is_saudi, 0.0, risk["non_saudi_uplift"])
    )
    linear += _solve_intercept(linear, risk["target_bad_rate"])
    latent_bad = rng.random(n) < _sigmoid(linear)

    # --- behaviour ---------------------------------------------------------
    wa = cfg["walk_away"]
    walk_p = np.where(is_digital, wa["base_share"] * wa["digital_multiplier"], wa["base_share"])
    walked_away = rng.random(n) < walk_p

    # --- assemble ----------------------------------------------------------
    start = pd.Timestamp(cfg["app_date_start"])
    app_date = start + pd.to_timedelta(rng.integers(0, cfg["app_date_days"], n), unit="D")
    rank = np.where(is_military, rng.choice(mil["ranks"], size=n), None)
    mil_type = np.where(is_military, rng.choice(mil["employee_types"], size=n), None)

    df = pd.DataFrame({
        "application_id": [f"APP{i:07d}" for i in range(1, n + 1)],
        "app_date": app_date,
        "product": cfg["product"],
        "program": _pick(rng, pop["program_probs"], n),
        "requested_amount": requested,
        "tenure_months": tenure.astype("int64"),
        "downpayment_pct": downpayment,
        "employer_segment": segment,
        "employment_type": employment_type,
        "is_pensioner": is_pensioner,
        "nationality": nationality,
        "is_saudi": is_saudi,
        "age": age.astype("int64"),
        "gender": gender,
        "sector": sector,
        "military_rank": rank,
        "military_employee_type": mil_type,
        "employer_name": employer_name,
        "monthly_income": income,
        "length_of_service_months": length_of_service.astype("int64"),
        "payslip_age_months": payslip_age.astype("int64"),
        "salary_to_bsf": salary_to_bsf,
        "simah_score": simah_score,
        "crif_score": crif.astype(float),
        "simah_scorecard": scorecard,
        "customer_type": customer_type,
        "is_pep": is_pep,
        "related_to_pep": related_to_pep,
        "diplomatic_service": diplomatic,
        "channel": channel,
        "source_code": source_code,
        "agent_id": agent_id,
        "walked_away": walked_away,
        "booking_date": pd.NaT,
        "bad_date": pd.NaT,
        "latent_bad": latent_bad,
    })
    for col in ("product", "program", "employer_segment", "employment_type", "nationality",
                "gender", "sector", "military_rank", "military_employee_type", "employer_name",
                "salary_to_bsf", "simah_scorecard", "customer_type", "channel", "source_code",
                "agent_id"):
        df[col] = df[col].astype("string")
    df = _observe(df, cfg, rng)
    client_schema.assert_valid(df, require_latent=True)
    return df[list(client_schema.COLUMNS)]


@lru_cache(maxsize=2)
def _inventory(folder: str):
    from src.rule_inventory import build_inventory
    return build_inventory(folder)


def _observe(df: pd.DataFrame, cfg: dict, rng) -> pd.DataFrame:
    """Record performance the way a bank would have it: only for the loans it booked.

    Who was booked is decided by replaying the real rules, not drawn: the bank's history is what
    its current policy approved. Then each booked loan gets a booking date and, if it went bad,
    the date it first reached the bad DPD. Nothing after the extract date is recorded, so the
    most recent loans are genuinely immature, which is what the analysis window has to cope with.

    Every draw here comes after the rest of the population, so the applicants themselves are
    identical to a population generated without performance.
    """
    from src import client_analysis, client_replay

    oc, og = cfg["outcome"], cfg["outcome"]["generate"]
    n = len(df)
    lag = rng.integers(0, og["booking_lag_days"] + 1, n)
    # Days, not calendar months, so the draw is vectorised. A month is taken as 30.44 days and
    # the top of the range is kept just inside the definition window, which a calendar month
    # offset from any booking date always exceeds.
    within = int(oc["bad_definition"]["within_months"])
    lo, hi = og["months_to_bad"]
    days_to_bad = rng.integers(round(lo * 30.44), int(min(hi, within) * 30.44) - 2, n)
    late = rng.random(n) < og["late_bad_share"]
    days_late = rng.integers(round((within + 1) * 30.44), round(2 * within * 30.44), n)

    booked = client_analysis.stage_outcome(
        df, client_replay.replay(df, _inventory(cfg["replay"]["rules_folder"]), cfg), cfg
    )["booked"].to_numpy().copy()

    as_of = pd.Timestamp(oc["as_of"])
    booking = df["app_date"] + pd.to_timedelta(lag, unit="D")
    booked &= (booking <= as_of).to_numpy()      # applied in the last fortnight, not yet booked
    bad_after = np.where(df["latent_bad"], days_to_bad, np.where(late, days_late, -1))
    bad = booking + pd.to_timedelta(np.maximum(bad_after, 0), unit="D")
    went_bad = booked & (bad_after >= 0) & (bad <= as_of).to_numpy()

    df["booking_date"] = booking.where(booked)
    df["bad_date"] = bad.where(went_bad)
    return df


def generate_file(cfg: dict) -> pd.DataFrame:
    """The data file: the default product's applicants, then one block per extra product.

    Each block is a separate population with its own seed, booked by replaying its own product's
    rules. `generate()` stays single-product, so the default product's applicants are identical
    whether or not other products are generated beside them.
    """
    blocks = [generate(cfg)]
    for product, spec in (cfg.get("generate_products") or {}).items():
        if product == cfg["product"]:
            continue
        block = generate({**cfg, "product": product, "n_rows": int(spec["n_rows"]),
                          "seed": int(spec["seed"])})
        start = sum(len(b) for b in blocks) + 1
        ids = pd.Series([f"APP{i:07d}" for i in range(start, start + len(block))],
                        index=block.index)
        block["application_id"] = ids.astype(block["application_id"].dtype)
        blocks.append(block)
    return pd.concat(blocks, ignore_index=True)


# --------------------------------------------------------------------------- calibration
def threshold_coverage(df: pd.DataFrame, folder="." ) -> pd.DataFrame:
    """For every numeric threshold the TWQR rules use, count applicants on each side.

    This is the guardrail that matters most. A rule whose threshold sits outside the
    population never fires, so it silently drops out of the decline-driver ranking — and a
    ranking with a missing rule still looks perfectly plausible, which is exactly the failure
    mode the brief warns about.
    """
    from src import client_loader
    from src.rule_inventory import build_inventory

    inv = build_inventory(folder)
    rules, conds = inv.rules, inv.conditions
    twqr = rules[(rules.table != "employer_keyword_check")
                 & (rules["product"].isin(["TWQR", "ALL"]) | rules["product"].isna())]
    numeric = conds[conds.rule_id.isin(twqr.rule_id)
                    & conds.operator.isin(["lt", "lte", "gt", "gte", "between", "outside"])
                    & (conds.tunability == "tunable")]
    rows = []
    for field, grp in numeric.groupby("field"):
        source = client_loader.FIELD_SOURCES.get(field)
        if source is None or source not in df.columns:
            rows.append({"field": field, "threshold": None, "kind": None, "below": None,
                         "at_or_above": None, "status": "no applicant column"})
            continue
        values = pd.to_numeric(df[source], errors="coerce")
        # A `between` endpoint is often a sentinel (0, or 9999999 standing in for "no limit"),
        # not a cutoff anyone is meant to sit beyond. A `lt`/`gt` threshold always is one.
        comparison = set(grp[grp.operator.isin(["lt", "lte", "gt", "gte"])].value_low.dropna())
        band = {v for v in list(grp.value_low.dropna()) + list(grp.value_high.dropna())}
        for t in sorted(band):
            rows.append({"field": field, "threshold": t,
                         "kind": "cutoff" if t in comparison else "band edge",
                         "below": int((values < t).sum()),
                         "at_or_above": int((values >= t).sum()), "status": "ok"})
    out = pd.DataFrame(rows)
    return out.sort_values(["field", "threshold"], na_position="first").reset_index(drop=True)


def calibration_report(df: pd.DataFrame, cfg: dict, folder=".") -> dict:
    """Population properties the analysis depends on, plus the planted answers."""
    cal = cfg["calibration"]
    cov = threshold_coverage(df, folder)
    usable = cov[cov.status == "ok"]
    thin = usable[(usable[["below", "at_or_above"]].min(axis=1)
                   < cal["min_applicants_per_threshold_side"])]
    # Only a real cutoff with nobody on one side disables a rule. A band edge with nobody
    # beyond it is usually a sentinel standing in for "no limit".
    unreachable = usable[(usable.kind == "cutoff")
                         & (usable[["below", "at_or_above"]].min(axis=1) == 0)]

    by_channel = df.groupby("channel", observed=True).agg(
        applicants=("application_id", "size"),
        median_income=("monthly_income", "median"),
        median_simah=("simah_score", "median"),
        no_score_rate=("simah_score", lambda s: float(s.isna().mean())),
        bad_rate=("latent_bad", "mean"))

    scored_bad = float(df.loc[df.simah_score.notna(), "latent_bad"].mean())
    no_score_ratio = float(df.loc[df.simah_score.isna(), "latent_bad"].mean()) / max(scored_bad, 1e-9)
    los_corr = float(np.corrcoef(df["length_of_service_months"].astype(float),
                                 df["latent_bad"].astype(float))[0, 1])
    return {
        "rows": int(len(df)),
        "bad_rate": float(df["latent_bad"].mean()),
        "bad_rate_target": cal and cfg["risk"]["target_bad_rate"],
        "walk_away_rate": float(df["walked_away"].mean()),
        "thresholds_checked": int(len(usable)),
        "thresholds_thinly_covered": thin.to_dict("records"),
        "rules_that_cannot_fire": unreachable.to_dict("records"),
        "fields_without_a_column": cov[cov.status != "ok"]["field"].tolist(),
        "by_channel": by_channel.round(4).to_dict("index"),
        "planted": {
            "digital_weaker_mix": bool(
                by_channel.loc["digital", "median_income"] < by_channel["median_income"].drop("digital").min()),
            "length_of_service_does_not_predict": abs(los_corr) < 0.02,
            "length_of_service_correlation": round(los_corr, 5),
            "missing_score_is_riskiest": no_score_ratio >= cfg["risk"]["no_score_min_ratio"],
            "missing_score_bad_rate_ratio": round(no_score_ratio, 3),
            "no_government_exposure": int((df["sector"] == "government").sum()) == 0,
        },
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Generate the client-shaped applicant population.")
    ap.add_argument("--n-rows", type=int)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--out")
    ap.add_argument("--fixture", action="store_true", help="also write the small test fixture")
    ap.add_argument("--check", action="store_true", help="print the calibration report only")
    args = ap.parse_args(argv)

    overrides = {k: v for k, v in [("n_rows", args.n_rows), ("seed", args.seed)] if v is not None}
    cfg = load_client_config(overrides=overrides)
    df = generate_file(cfg)
    # Calibration is checked on the default product: the planted answers are planted there.
    report = calibration_report(df[df["product"] == cfg["product"]], cfg)

    if not args.check:
        out = resolve_path(args.out or cfg["data_path"])
        out.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out, index=False)
        print(f"wrote {out} ({len(df):,} rows)", file=sys.stderr)
        if args.fixture:
            fx = resolve_path(cfg["fixture_path"])
            fx.parent.mkdir(parents=True, exist_ok=True)
            df.head(2000).to_parquet(fx, index=False)
            print(f"wrote {fx} (2,000 rows)", file=sys.stderr)

    json.dump(report, sys.stdout, indent=2, default=str)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
