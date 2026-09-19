"""Strategy definition and vectorised rule engine (Section 7)."""
from __future__ import annotations

import numpy as np
import pandas as pd
from pandas.api.types import is_numeric_dtype

from src.contracts import Rule, SegmentOverride, Strategy


# --------------------------------------------------------------------------- rules
# Each function returns a boolean array: True where the applicant FAILS the rule.
def _r1_age(df: pd.DataFrame, p: dict) -> np.ndarray:
    age = df["age"].to_numpy()
    return ~((age >= p["min_age"]) & (age <= p["max_age"]))


def _r2_fraud(df: pd.DataFrame, p: dict) -> np.ndarray:
    return df["fraud_flag"].to_numpy(dtype=bool)


def _r3_thin_file(df: pd.DataFrame, p: dict) -> np.ndarray:
    score = df["bureau_score"].to_numpy(dtype=float)
    return np.isnan(score) | (df["bureau_vintage_months"].to_numpy() < p["min_vintage"])


def _r4_bureau_hist(df: pd.DataFrame, p: dict) -> np.ndarray:
    return (df["max_dpd_12m"].to_numpy() >= p["dpd_lt"]) | (
        df["enquiries_6m"].to_numpy() > p["max_enquiries"]
    )


def _r5_score(df: pd.DataFrame, p: dict) -> np.ndarray:
    # NaN >= cutoff is False, so a missing score fails.
    return ~(df["bureau_score"].to_numpy(dtype=float) >= p["cutoff"])


def _r6_foir(df: pd.DataFrame, p: dict) -> np.ndarray:
    return df["foir"].to_numpy(dtype=float) > p["cap"]


RULE_FUNCS = {
    "R1_AGE": _r1_age,
    "R2_FRAUD": _r2_fraud,
    "R3_THIN_FILE": _r3_thin_file,
    "R4_BUREAU_HIST": _r4_bureau_hist,
    "R5_SCORE": _r5_score,
    "R6_FOIR": _r6_foir,
}


# --------------------------------------------------------------------------- strategy
def strategy_from_config(cfg: dict) -> Strategy:
    rules = tuple(
        Rule(id=r["id"], params=dict(r.get("params", {})), mandatory=bool(r["mandatory"]),
             enabled=bool(r.get("enabled", True)))
        for r in cfg["strategy"]["rules"]
    )
    return Strategy(rules=rules)


def with_rule_params(strategy: Strategy, changes: dict[str, dict]) -> Strategy:
    """Copy of `strategy` with edited params, e.g. {"R5_SCORE": {"cutoff": 680}}.

    Mandatory rules can never be edited.
    """
    known = {r.id for r in strategy.rules}
    unknown = set(changes) - known
    if unknown:
        raise KeyError(f"Unknown rules: {sorted(unknown)}")
    new_rules = []
    for r in strategy.rules:
        if r.id in changes:
            if r.mandatory:
                raise ValueError(f"{r.id} is mandatory and cannot be relaxed")
            r = Rule(r.id, {**r.params, **changes[r.id]}, r.mandatory, r.enabled)
        new_rules.append(r)
    return Strategy(rules=tuple(new_rules), overrides=strategy.overrides)


def with_rule_enabled(strategy: Strategy, enabled: dict[str, bool]) -> Strategy:
    """Copy of `strategy` with rules switched on/off. Mandatory rules can never be switched off."""
    known = {r.id for r in strategy.rules}
    unknown = set(enabled) - known
    if unknown:
        raise KeyError(f"Unknown rules: {sorted(unknown)}")
    new_rules = []
    for r in strategy.rules:
        if r.id in enabled:
            if r.mandatory and not enabled[r.id]:
                raise ValueError(f"{r.id} is mandatory and cannot be switched off")
            r = Rule(r.id, r.params, r.mandatory, bool(enabled[r.id]))
        new_rules.append(r)
    return Strategy(rules=tuple(new_rules), overrides=strategy.overrides)


def with_overrides(strategy: Strategy, overrides: tuple[SegmentOverride, ...]) -> Strategy:
    return Strategy(rules=strategy.rules, overrides=tuple(overrides))


# --------------------------------------------------------------------------- overrides
def override_condition_mask(df: pd.DataFrame, conditions: dict) -> np.ndarray:
    """Boolean mask of rows satisfying every condition of a segment override.

    Key forms:
      "<col>_max": v          col <= v
      "<col>_min": v          col >= v
      "<col>": (lo, hi)       numeric column, lo <= col < hi
      "<col>": [a, b, ...]    non-numeric column, col in list
    """
    mask = np.ones(len(df), dtype=bool)
    for key, val in conditions.items():
        if key not in df.columns and key.endswith("_max") and key[:-4] in df.columns:
            mask &= df[key[:-4]].to_numpy(dtype=float) <= val
        elif key not in df.columns and key.endswith("_min") and key[:-4] in df.columns:
            mask &= df[key[:-4]].to_numpy(dtype=float) >= val
        elif key in df.columns:
            col = df[key]
            if is_numeric_dtype(col) and not isinstance(col.dtype, pd.CategoricalDtype):
                if len(val) != 2:
                    raise ValueError(f"Numeric condition '{key}' needs (lo, hi), got {val!r}")
                x = col.to_numpy(dtype=float)
                mask &= (x >= val[0]) & (x < val[1])
            else:
                vals = list(val) if isinstance(val, (list, tuple, set)) else [val]
                mask &= col.isin(vals).to_numpy()
        else:
            raise KeyError(f"Override condition '{key}' does not match a column")
    return mask


# --------------------------------------------------------------------------- engine
def evaluate_strategy(df: pd.DataFrame, strategy: Strategy) -> pd.DataFrame:
    """Returns, aligned to df.index:
       decision            category  approve/decline
       first_failed_rule   str|None
       failed_<RULE_ID>    bool      one column per rule
       approved_by_override bool

    `failed_*` and `first_failed_rule` always describe the BASE rules, even for rows that a
    segment override later approves; use `decision` / `approved_by_override` for the outcome.
    Disabled rules never fail.
    """
    ids = [r.id for r in strategy.rules]
    n = len(df)
    failed = np.zeros((n, len(ids)), dtype=bool)
    for j, rule in enumerate(strategy.rules):
        if not rule.enabled:
            continue
        if rule.id not in RULE_FUNCS:
            raise KeyError(f"No implementation for rule '{rule.id}'")
        failed[:, j] = RULE_FUNCS[rule.id](df, rule.params)

    base_decline = failed.any(axis=1)
    first_idx = failed.argmax(axis=1)
    id_arr = np.array(ids, dtype=object)
    first_failed = np.where(base_decline, id_arr[first_idx], None)

    by_override = np.zeros(n, dtype=bool)
    mandatory_ids = {r.id for r in strategy.rules if r.mandatory}
    for ov in strategy.overrides:
        relaxes = set(ov.relaxes)
        bad = relaxes - set(ids)
        if bad:
            raise KeyError(f"Override relaxes unknown rules: {sorted(bad)}")
        if relaxes & mandatory_ids:
            raise ValueError(f"Override cannot relax mandatory rules: {sorted(relaxes & mandatory_ids)}")
        must_pass = [j for j, rid in enumerate(ids) if rid not in relaxes]
        others_fail = failed[:, must_pass].any(axis=1) if must_pass else np.zeros(n, dtype=bool)
        by_override |= override_condition_mask(df, ov.conditions) & ~others_fail & base_decline

    approve = ~base_decline | by_override
    out = {
        "decision": pd.Categorical(np.where(approve, "approve", "decline"),
                                   categories=["approve", "decline"]),
        "first_failed_rule": pd.Series(first_failed, index=df.index, dtype=object),
    }
    for j, rid in enumerate(ids):
        out[f"failed_{rid}"] = failed[:, j]
    out["approved_by_override"] = by_override
    return pd.DataFrame(out, index=df.index)


# --------------------------------------------------------------------------- reproduction (7.3)
class ReproductionError(AssertionError):
    """The rule engine disagrees with history on a row that was not a manual override."""


def reproduction_report(df: pd.DataFrame, strategy: Strategy,
                        evaluation: pd.DataFrame | None = None) -> dict:
    """Compare the engine to hist_decision. Never rounds a non-override mismatch away."""
    ev = evaluate_strategy(df, strategy) if evaluation is None else evaluation
    engine = ev["decision"].astype(str).to_numpy()
    hist = df["hist_decision"].astype(str).to_numpy()
    override = df["manual_override"].to_numpy(dtype=bool)
    match = engine == hist

    non_ov = ~override
    n_non_ov = int(non_ov.sum())
    mism = ~match
    mism_df = pd.DataFrame({
        "application_id": df["application_id"].to_numpy()[mism],
        "engine_decision": engine[mism],
        "hist_decision": hist[mism],
        "manual_override": override[mism],
    })
    mism_df["direction"] = mism_df["engine_decision"] + "→" + mism_df["hist_decision"]

    # Where history declined a non-override row, the recorded reason must be the engine's first failed rule.
    dec_non_ov = non_ov & (hist == "decline")
    reason_ok = (df["hist_decline_reason"].astype(object).to_numpy()[dec_non_ov]
                 == ev["first_failed_rule"].to_numpy()[dec_non_ov])

    return {
        "n": int(len(df)),
        "raw_match_rate": float(match.mean()),
        "match_rate_excl_overrides": float(match[non_ov].mean()) if n_non_ov else 1.0,
        "n_mismatches": int(mism.sum()),
        "n_mismatches_not_override": int((mism & non_ov).sum()),
        "n_manual_overrides": int(override.sum()),
        "n_override_decline_to_approve": int(((engine == "decline") & (hist == "approve") & override).sum()),
        "n_override_approve_to_decline": int(((engine == "approve") & (hist == "decline") & override).sum()),
        "decline_reason_match_rate": float(reason_ok.mean()) if len(reason_ok) else 1.0,
        "mismatches": mism_df,
    }


def assert_reproduction(report: dict) -> None:
    """Fail loudly if any non-override row disagrees, or a decline reason disagrees."""
    if report["n_mismatches_not_override"] > 0 or report["match_rate_excl_overrides"] < 1.0:
        raise ReproductionError(
            f"Rule engine does not reproduce history: {report['n_mismatches_not_override']} "
            f"non-override mismatches (match rate excl. overrides = "
            f"{report['match_rate_excl_overrides']:.6f}, must be 1.0)")
    if report["decline_reason_match_rate"] < 1.0:
        raise ReproductionError(
            f"Decline reasons disagree with first failed rule "
            f"(match rate {report['decline_reason_match_rate']:.6f}, must be 1.0)")
