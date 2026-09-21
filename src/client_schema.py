"""Canonical applicant schema for the client rule set, and the dialect maps onto each rule table.

Why a canonical schema at all: the client's four files use three different vocabularies for the same
attribute. A government employee is `ST` in racAndPolicies, `ST` in simati_chk_IAF and `G` in
yknBasicCheckValidation. yknBasicCheckValidation goes further and folds employment type and
pensioner status into the same column — military is `M`, a pensioner is `P`, neither of which
is an employer segment at all.

So the applicant carries one canonical value and the loader renders it into each table's
dialect at replay time. That is the separation the brief asks for: when the real client file
arrives, only the mapping changes, never the analysis.
"""
from __future__ import annotations

import pandas as pd

# --------------------------------------------------------------------------- vocabularies
EMPLOYER_SEGMENTS = [
    "GOV", "SEMI_GOV", "PRIVATE_LARGE", "PRIVATE_SMALL",
    "SELF_EMPLOYED", "BSF_PRIORITY", "BSF_EMPLOYEE",
]
EMPLOYMENT_TYPES = ["CIVILIAN", "MILITARY"]
CHANNELS = ["digital", "branch", "dsa", "telesales"]
PROGRAMS = ["SMART", "PF"]
SCORECARDS = ["CLEAN", "Intermediate", "New To Credit", "Telecom", "Buy Now Pay Later"]

# Guru asked to slice the portfolio by sector. No rule file records one — `V_SECTOR_TYPE` is
# declared and never populated — so sector is an application attribute, not a rule input.
SECTORS = ["government", "healthcare", "education", "it", "finance", "retail",
           "construction", "logistics", "manufacturing", "hospitality"]

# --------------------------------------------------------------------------- dialect maps
SEGMENT_DIALECTS: dict[str, dict[str, str]] = {
    # racAndPolicies.customerSegment
    "racAndPolicies": {
        "GOV": "ST", "SEMI_GOV": "SMG", "PRIVATE_LARGE": "PVTL",
        "PRIVATE_SMALL": "PVTSML", "SELF_EMPLOYED": "SE",
        "BSF_PRIORITY": "PRIO", "BSF_EMPLOYEE": "PRIV-BSF",
    },
    # simati_chk_IAF.employeeSegment — same codes, different words for the last two
    "simati_chk_IAF": {
        "GOV": "ST", "SEMI_GOV": "SMG", "PRIVATE_LARGE": "PVTL",
        "PRIVATE_SMALL": "PVTSML", "SELF_EMPLOYED": "Establishment",
        "BSF_PRIORITY": "BSF Priority", "BSF_EMPLOYEE": "BSF Priority",
    },
    # yknBasicCheckValidation.employeeSegment — single-letter codes
    "yknBasicCheckValidation": {
        "GOV": "G", "SEMI_GOV": "SG", "PRIVATE_LARGE": "PL", "PRIVATE_SMALL": "PS",
        "SELF_EMPLOYED": "SE", "BSF_PRIORITY": "BSFPB", "BSF_EMPLOYEE": "BSFE",
    },
}
EMPLOYMENT_TYPE_CODE = {"CIVILIAN": "CV", "MILITARY": "ML"}

# --------------------------------------------------------------------------- schema
COLUMNS: dict[str, str] = {
    # identity and request
    "application_id": "string",
    "app_date": "datetime64[ns]",
    "product": "string",
    "program": "string",
    "requested_amount": "float64",
    "tenure_months": "int64",
    "downpayment_pct": "float64",   # whole percent (0-100), as the client writes it
    # who the applicant is
    "employer_segment": "string",
    "employment_type": "string",
    "is_pensioner": "bool",
    "nationality": "string",
    "is_saudi": "bool",
    "age": "int64",
    "gender": "string",
    "sector": "string",
    "military_rank": "string",
    "military_employee_type": "string",
    # employment and income
    "employer_name": "string",
    "monthly_income": "float64",
    "length_of_service_months": "int64",
    "payslip_age_months": "int64",
    "salary_to_bsf": "string",
    # bureau
    "simah_score": "float64",            # nullable: new-to-credit applicants have none
    "crif_score": "float64",
    "simah_scorecard": "string",
    "customer_type": "string",           # NTB / ETB
    # regulatory flags
    "is_pep": "bool",
    "related_to_pep": "bool",
    "diplomatic_service": "bool",
    # sourcing — Guru's question 4
    "channel": "string",
    "source_code": "string",
    "agent_id": "string",
    # behaviour and performance
    "walked_away": "bool",
    "latent_bad": "bool",                # ground truth for EVERY applicant, engine must not see it
}

NULLABLE = {"simah_score", "military_rank", "military_employee_type"}

ENGINE_VISIBLE = [c for c in COLUMNS if c != "latent_bad"]
"""What the replay and analysis layers may read.

`latent_bad` is the honest answer for declined applicants too, which no real bank has. It exists
so the reject-inference work in a later phase can be scored against truth; letting the engine
read it directly would make every result meaningless.
"""


class SchemaError(ValueError):
    """The applicant table does not match the canonical schema."""


def validate(df: pd.DataFrame, *, require_latent: bool = False) -> list[str]:
    """Return a list of problems (empty if valid)."""
    problems: list[str] = []
    expected = set(COLUMNS) if require_latent else set(ENGINE_VISIBLE)
    missing = expected - set(df.columns)
    if missing:
        return [f"missing columns: {sorted(missing)}"]

    for col in expected - NULLABLE:
        if df[col].isna().any():
            problems.append(f"{col}: {int(df[col].isna().sum())} null values")
    for col, allowed in [("employer_segment", EMPLOYER_SEGMENTS),
                         ("employment_type", EMPLOYMENT_TYPES),
                         ("channel", CHANNELS), ("program", PROGRAMS),
                         ("sector", SECTORS), ("simah_scorecard", SCORECARDS)]:
        bad = set(df[col].dropna().unique()) - set(allowed)
        if bad:
            problems.append(f"{col}: unexpected values {sorted(bad)}")
    if (df["age"] < 18).any() or (df["age"] > 90).any():
        problems.append("age outside 18-90")
    if (df["monthly_income"] < 0).any():
        problems.append("negative monthly_income")
    if df["is_saudi"].ne(df["nationality"].eq("SAU")).any():
        problems.append("is_saudi disagrees with nationality")
    mil = df["employment_type"].eq("MILITARY")
    if df.loc[~mil, "military_rank"].notna().any():
        problems.append("military_rank set on a non-military applicant")
    if df.loc[mil, "military_rank"].isna().any():
        problems.append("military applicant without a military_rank")
    return problems


def assert_valid(df: pd.DataFrame, *, require_latent: bool = False) -> None:
    problems = validate(df, require_latent=require_latent)
    if problems:
        raise SchemaError("; ".join(problems))


def to_dialect(df: pd.DataFrame, table: str) -> pd.Series:
    """Render `employer_segment` into one rule table's vocabulary.

    yknBasicCheckValidation is the awkward one: its single column also encodes employment type
    and pensioner status, so military and pensioner applicants never show an employer segment
    there at all. Getting this wrong would silently exempt them from that table's age bands.
    """
    if table not in SEGMENT_DIALECTS:
        raise KeyError(f"no segment dialect for {table!r}")
    mapped = df["employer_segment"].map(SEGMENT_DIALECTS[table])
    if table == "yknBasicCheckValidation":
        mapped = mapped.mask(df["is_pensioner"], "P")
        mapped = mapped.mask(df["employment_type"].eq("MILITARY"), "M")
    return mapped.astype("string")
