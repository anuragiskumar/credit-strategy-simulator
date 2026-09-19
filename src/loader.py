"""Load and validate the application dataset (Section 5.1).

Only the documented schema columns are validated; any extra column in the file is passed through
untouched. The loader never reads, joins or interprets an outcome column beyond `bad_flag`.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.config import load_config, resolve_path

REQUIRED_COLUMNS = [
    "application_id", "app_date", "age", "employment_type", "monthly_income", "loan_amount",
    "tenor_months", "existing_emi", "proposed_emi", "foir", "bureau_score",
    "bureau_vintage_months", "max_dpd_12m", "enquiries_6m", "fraud_flag", "hist_decision",
    "hist_decline_reason", "manual_override", "booked", "bad_flag",
]
NULLABLE_COLUMNS = {"bureau_score", "hist_decline_reason", "bad_flag"}
EMPLOYMENT_LEVELS = ["salaried", "self_employed", "other"]
DECISION_LEVELS = ["approve", "decline"]
DPD_LEVELS = {0, 30, 60, 90}
FOIR_TOLERANCE = 1e-6


class SchemaError(ValueError):
    """The dataset does not match the Section 5.1 schema."""


def validate_schema(df: pd.DataFrame) -> list[str]:
    """Return a list of problems (empty if the dataset is valid)."""
    problems: list[str] = []
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        return [f"missing columns: {missing}"]

    for col in REQUIRED_COLUMNS:
        if col not in NULLABLE_COLUMNS and df[col].isna().any():
            problems.append(f"{col}: {int(df[col].isna().sum())} unexpected nulls")

    if not df["application_id"].is_unique:
        problems.append("application_id is not unique")

    def _range(col, lo, hi):
        s = df[col].dropna()
        if len(s) and (s.min() < lo or s.max() > hi):
            problems.append(f"{col}: values outside [{lo}, {hi}] (min {s.min()}, max {s.max()})")

    _range("age", 19, 65)
    _range("tenor_months", 12, 60)
    _range("bureau_score", 300, 900)
    _range("foir", 0, 1.2)
    _range("monthly_income", 0, np.inf)
    _range("enquiries_6m", 0, np.inf)
    _range("bureau_vintage_months", 0, np.inf)

    bad_dpd = set(df["max_dpd_12m"].dropna().unique()) - DPD_LEVELS
    if bad_dpd:
        problems.append(f"max_dpd_12m: unexpected values {sorted(bad_dpd)}")
    bad_emp = set(df["employment_type"].dropna().astype(str).unique()) - set(EMPLOYMENT_LEVELS)
    if bad_emp:
        problems.append(f"employment_type: unexpected levels {sorted(bad_emp)}")
    bad_dec = set(df["hist_decision"].dropna().astype(str).unique()) - set(DECISION_LEVELS)
    if bad_dec:
        problems.append(f"hist_decision: unexpected levels {sorted(bad_dec)}")

    if not problems:
        booked = df["booked"].to_numpy(dtype=bool)
        if not np.array_equal(booked, (df["hist_decision"].astype(str) == "approve").to_numpy()):
            problems.append("booked != (hist_decision == approve)")
        bf = df["bad_flag"]
        if bf[booked].isna().any():
            problems.append("bad_flag is null for booked applications")
        if bf[~booked].notna().any():
            problems.append("bad_flag is populated for non-booked applications")
        if not set(bf.dropna().unique()) <= {0, 1}:
            problems.append("bad_flag must be 0/1")
        foir_calc = (df["existing_emi"] + df["proposed_emi"]) / df["monthly_income"]
        if (foir_calc - df["foir"]).abs().max() > FOIR_TOLERANCE:
            problems.append("foir != (existing_emi + proposed_emi) / monthly_income")
        reasons = df["hist_decline_reason"]
        if reasons[booked].notna().any():
            problems.append("hist_decline_reason populated for approved applications")
        if reasons[~booked].isna().any():
            problems.append("hist_decline_reason missing for declined applications")
    return problems


def load_applications(path: str | Path | None = None, cfg: dict | None = None,
                      validate: bool = True) -> pd.DataFrame:
    """Read the parquet dataset, coerce dtypes to the schema and validate."""
    cfg = cfg or load_config()
    p = Path(path) if path else resolve_path(cfg["data_path"])
    if not p.exists():
        raise FileNotFoundError(f"{p} not found — run `python -m src.generate_data` first")
    df = pd.read_parquet(p)

    if "employment_type" in df.columns:
        df["employment_type"] = pd.Categorical(df["employment_type"].astype(str), categories=EMPLOYMENT_LEVELS)
    if "hist_decision" in df.columns:
        df["hist_decision"] = pd.Categorical(df["hist_decision"].astype(str), categories=DECISION_LEVELS)
    if "app_date" in df.columns:
        df["app_date"] = pd.to_datetime(df["app_date"])
    if "bad_flag" in df.columns:
        df["bad_flag"] = df["bad_flag"].astype("Int8")

    if validate:
        problems = validate_schema(df)
        if problems:
            raise SchemaError(f"{p}: " + "; ".join(problems))
    return df
