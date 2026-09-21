"""Map an applicant table into the fields the client's rules name (plan step 2).

The brief requires the loader to stay separate from the engine, so the real client file can be
mapped into the same schema without touching the analysis code. Everything source-specific
lives here:

  * `FIELD_SOURCES` — how each rule field is derived from a canonical applicant.
  * `SEGMENT_DIALECTS` (in client_schema) — the three vocabularies for employer segment.
  * `SOURCE_MAPPINGS` — column renames for an incoming third-party file.

The rest of the system only ever sees `rule_frame()` output, keyed by the field names that
appear in the rule inventory's `conditions.field` column.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from src import client_schema
from src.rule_inventory import build_inventory

# Rule fields that carry the same meaning under different names across the four files.
# `monthCnt` (racAndPolicies) and `netIncome.lengthOfService` (simati) are both length of
# service; `income` and `netIncome.totalIncome` are both monthly income.
FIELD_SOURCES: dict[str, str] = {
    "age": "age",
    "gender": "gender",
    "nationality": "nationality",
    "product": "product",
    "program": "program",
    "income": "monthly_income",
    "netincome.totalincome": "monthly_income",
    "netincome.lengthofservice": "length_of_service_months",
    "monthcnt": "length_of_service_months",
    "simahcreditscore": "simah_score",
    "crifscore": "crif_score",
    "simahscorecarddescription": "simah_scorecard",
    "simcusttype": "customer_type",
    "loanamount": "requested_amount",
    "requestamount": "requested_amount",
    "tenure": "tenure_months",
    "downpaymentper": "downpayment_pct",
    "employername": "employer_name",
    "simatiresponse.data.privatesector.employmentstatusinfo[1].employername": "employer_name",
    "salarytobsf": "salary_to_bsf",
    "paydurationinmonth.durationinmonth": "payslip_age_months",
    "miltaryrank": "military_rank",
    "militaryrankdesignation": "military_rank",
    "employeetype": "military_employee_type",
    "sourcetype": "channel",
}

# Fields the rules express as a flag or a coded string rather than a plain column.
BOOLEAN_AS_ONE = {"politicallyexposedperson": "is_pep",
                  "relatedtopep": "related_to_pep",
                  "diplomaticservice": "diplomatic_service"}


class MappingError(ValueError):
    """A source file could not be mapped into the canonical schema."""


def load_applications(path: str | Path) -> pd.DataFrame:
    """Read a canonical applicant file and validate it. Engine-visible columns only."""
    path = Path(path)
    df = pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)
    client_schema.assert_valid(df)
    return df


def map_source(df: pd.DataFrame, mapping: dict[str, str], *,
               constants: dict | None = None) -> pd.DataFrame:
    """Rename a third-party file's columns into the canonical schema.

    `mapping` is {source column: canonical column}. `constants` fills canonical columns the
    source does not carry — a file for one product, say, needs `product` supplied.
    Raises rather than guessing, so a silently missing field cannot reach the analysis.
    """
    out = df.rename(columns=mapping)
    for col, value in (constants or {}).items():
        out[col] = value
    missing = set(client_schema.ENGINE_VISIBLE) - set(out.columns)
    if missing:
        raise MappingError(
            f"source is missing {len(missing)} canonical column(s): {sorted(missing)}. "
            "Add them to the mapping or supply them as constants.")
    out = out[[c for c in client_schema.COLUMNS if c in out.columns]]
    problems = client_schema.validate(out)
    if problems:
        raise MappingError("; ".join(problems))
    return out


def employer_keyword_hit(employer_name: pd.Series, keywords: list[str]) -> pd.Series:
    """Run the client's 61 Arabic substring tests. Returns the Y/N the rules read.

    Derived, never assigned: change the keyword list and the population moves with it.
    """
    name = employer_name.fillna("").astype(str)
    hit = pd.Series(False, index=name.index)
    for kw in keywords:
        hit |= name.str.contains(kw, regex=False, na=False)
    return pd.Series(np.where(hit, "Y", "N"), index=name.index, dtype="string")


@lru_cache(maxsize=4)
def keyword_list(folder: str | Path = ".") -> list[str]:
    """The `contains(?, "...")` terms from racAndPolicies Sheet2.

    Cached: reading the workbooks costs more than the whole replay, and the simulator
    replays hundreds of times while searching for a strategy.
    """
    conds = build_inventory(folder).conditions
    kw = conds[(conds.table == "employer_keyword_check") & (conds.operator == "contains")]
    return tuple(v for v in kw["value_set"].dropna())


def rule_frame(df: pd.DataFrame, table: str, *, keywords: list[str] | None = None) -> pd.DataFrame:
    """Render applicants into the field names one decision table uses.

    The awkward cases, all of which would silently mis-decide applicants if left to a
    plain rename:

      * employer segment has three vocabularies (see client_schema.SEGMENT_DIALECTS);
      * `natureOfEmployment` is "Retired" for a pensioner and absent otherwise;
      * `pensioner` is the string "true"/"false", not a bool;
      * `employer_keyword_check` is computed from the employer name, not stored;
      * PEP-style flags are tested against 1, not True.
    """
    out = pd.DataFrame(index=df.index)
    for field, source in FIELD_SOURCES.items():
        if source in df.columns:
            out[field] = df[source]
    for field, source in BOOLEAN_AS_ONE.items():
        out[field] = df[source].astype(int)

    if table in client_schema.SEGMENT_DIALECTS:
        dialect = client_schema.to_dialect(df, table)
        out["customersegment" if table == "racAndPolicies" else "employeesegment"] = dialect

    out["typeofemployment"] = df["employment_type"].map(client_schema.EMPLOYMENT_TYPE_CODE)
    out["natureofemployment"] = pd.Series(
        np.where(df["is_pensioner"], "Retired", None), index=df.index, dtype="string")
    out["pensioner"] = pd.Series(np.where(df["is_pensioner"], "true", "false"),
                                 index=df.index, dtype="string")
    out["employer_keyword_check"] = employer_keyword_hit(
        df["employer_name"], keywords if keywords is not None else keyword_list())
    return out
