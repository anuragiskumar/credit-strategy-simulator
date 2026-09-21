"""Funnel, decline drivers and portfolio analytics over a replay (plan step 3).

This is the layer that answers the brief's question catalogue. It reads the hit matrix from
`client_replay` and never re-implements a rule, so a change to the rules moves every number here
at once.

It also never reads `latent_bad` for a declined applicant. A bank only observes performance on
what it booked, and an analysis that quietly used the truth for everyone would report a risk
impact no real deployment could reproduce.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

STAGES = ["applied", "hard_reject", "credit_policy", "eligibility", "walked_away", "booked"]


def _blocking(res, stage: str | None = None) -> pd.DataFrame:
    r = res.rules
    sel = r[(r.kind == "block") & (r.matched > 0)]
    if stage:
        sel = sel[sel.stage == stage]
    cols = [c for c in sel.rule_id if c in res.hits.columns]
    return res.hits[cols]


def offered_amount(df: pd.DataFrame, res, cfg: dict) -> pd.Series:
    """The offer after every applicable cap. Caps are minimums taken together."""
    requested = df["requested_amount"].astype(float)
    offer = requested.copy()
    caps = res.rules[(res.rules.kind == "cap") & (res.rules.matched > 0)]
    income = df["monthly_income"].astype(float)
    for r in caps.itertuples():
        if r.rule_id not in res.hits.columns:
            continue
        hit = res.hits[r.rule_id].to_numpy()
        cap = r.cap_amount
        if cap is None or (isinstance(cap, float) and np.isnan(cap)):
            continue
        if isinstance(cap, str) and "income" in cap:
            multiple = float(cap.split("*")[0])
            value = income * multiple
        else:
            try:
                value = pd.Series(float(cap), index=df.index)
            except (TypeError, ValueError):
                continue
        offer = offer.where(~hit, np.minimum(offer, value))
    return offer


def stage_outcome(df: pd.DataFrame, res, cfg: dict) -> pd.DataFrame:
    """Assign every applicant the first stage they dropped out at, and why.

    The reason is the rule that caught them, derived from the replay — never assigned.
    """
    fn = cfg["funnel"]
    n = len(df)
    stage = pd.Series("booked", index=df.index, dtype="object")
    reason = pd.Series(pd.NA, index=df.index, dtype="object")
    reason_code = pd.Series(pd.NA, index=df.index, dtype="object")

    for stage_name in ("hard_reject", "credit_policy"):
        block = _blocking(res, stage_name)
        if block.empty:
            continue
        caught = block.any(axis=1) & stage.eq("booked")
        first = block.loc[caught].idxmax(axis=1) if caught.any() else pd.Series(dtype="object")
        stage.loc[caught] = stage_name
        reason.loc[caught] = first
        lookup = res.rules.set_index("rule_id")
        reason_code.loc[caught] = first.map(lookup["policy_code"]).to_numpy()

    offer = offered_amount(df, res, cfg)
    survived = stage.eq("booked")
    too_small = survived & ((offer < df["requested_amount"] * fn["min_acceptable_offer_ratio"])
                            | (offer < fn["product_min_amount"]))
    stage.loc[too_small] = "eligibility"
    reason.loc[too_small] = "offer below acceptable share of request"

    walked = stage.eq("booked") & df["walked_away"]
    stage.loc[walked] = "walked_away"
    reason.loc[walked] = "customer went elsewhere"

    return pd.DataFrame({
        "stage": pd.Categorical(stage, categories=STAGES, ordered=True),
        "reason_rule": reason, "reason_code": reason_code,
        "offered_amount": offer,
        "booked": stage.eq("booked"),
        # Performance is observed ONLY on what the bank booked. This is the column the
        # analysis may read; `latent_bad` is not.
        "observed_bad": np.where(stage.eq("booked"), df["latent_bad"], np.nan),
    }, index=df.index)


def funnel(df: pd.DataFrame, outcome: pd.DataFrame) -> pd.DataFrame:
    """Guru's stage-by-stage table: how many drop out where, and how many are left."""
    n = len(df)
    counts = outcome["stage"].value_counts().reindex(STAGES[1:], fill_value=0)
    rows, left = [], n
    rows.append({"stage": "applied", "dropped": 0, "left": n, "left_pct": 100.0,
                 "per_100": 100.0})
    for s in STAGES[1:-1]:
        dropped = int(counts[s])
        left -= dropped
        rows.append({"stage": s, "dropped": dropped, "left": left,
                     "left_pct": round(100 * left / n, 1), "per_100": round(100 * left / n, 1)})
    booked = int(counts["booked"])
    rows.append({"stage": "booked", "dropped": 0, "left": booked,
                 "left_pct": round(100 * booked / n, 1), "per_100": round(100 * booked / n, 1)})
    return pd.DataFrame(rows)


def decline_drivers(df: pd.DataFrame, res, outcome: pd.DataFrame, cfg: dict,
                    model=None, include_oracle: bool = False) -> pd.DataFrame:
    """Which rule declines the most applicants, and how many it declines ON ITS OWN.

    "On its own" is the question Guru actually asked. Switching off a rule that always fires
    alongside another buys nothing, because the other one still catches those people — so
    `declines_alone` is the column that answers "what is the one thing I change?".

    The risk side is deliberately awkward. Declined applicants have no repayment history, so
    the honest answer comes from the PD model and is refused outright for groups the booked
    population never covered. Pass `include_oracle=True` only on synthetic data, and only to
    show how close the honest estimate got.
    """
    from src import client_risk

    block = _blocking(res)
    if block.empty:
        return pd.DataFrame()
    arr = block.to_numpy()
    only_one = arr.sum(axis=1) == 1
    lookup = res.rules.set_index("rule_id")
    booked_bad = float(outcome.loc[outcome["booked"], "observed_bad"].mean())

    rows = []
    for j, rule_id in enumerate(block.columns):
        caught = arr[:, j]
        alone = caught & only_one
        r = lookup.loc[rule_id]
        row = {
            "rule_id": rule_id, "table": r["table"], "stage": r["stage"],
            "policy_code": r["policy_code"], "description": r["description"],
            "fields": r["fields"], "relaxable": bool(r["relaxable"]),
            "declines": int(caught.sum()),
            "declines_alone": int(alone.sum()),
            "share_of_applicants": round(100 * caught.mean(), 2),
            "sole_reason_pct": round(100 * alone.sum() / max(caught.sum(), 1), 1),
        }
        if model is not None:
            est = client_risk.predict_group(model, df, alone, cfg)
            row["risk_known"] = est.get("known", False)
            row["est_bad_rate_if_relaxed"] = est.get("estimated_bad_rate")
            row["risk_note"] = est.get("reason")
            # Does the rule earn its place? Only meaningful when we can estimate at all.
            # A rule the bank may not drop is never reported as failing to earn its place:
            # the engine would be recommending a compliance breach.
            row["earns_its_place"] = (
                True if not r["relaxable"]
                else None if not est.get("known")
                else bool(est["estimated_bad_rate"] > booked_bad * cfg["drivers"]["earns_place_multiple"]))
            if not r["relaxable"]:
                row["risk_note"] = "not relaxable: rests on a fixed field (regulatory, " \
                                   "bureau or identity). Relaxing it is not a risk trade-off."
        if include_oracle:
            row["oracle_bad_rate"] = round(client_risk.oracle_bad_rate(df, alone), 4)
        rows.append(row)
    out = pd.DataFrame(rows)
    return out.sort_values("declines_alone", ascending=False).reset_index(drop=True)


def by_source(df: pd.DataFrame, outcome: pd.DataFrame, column: str) -> pd.DataFrame:
    """Approval and decline rates by channel, source or agent — Guru's question 4."""
    j = df[[column]].join(outcome[["stage", "booked"]])
    g = j.groupby(column, observed=True)
    out = pd.DataFrame({
        "applicants": g.size(),
        "booked": g["booked"].sum(),
        "approval_rate": (100 * g["booked"].mean()).round(1),
    })
    declines = j[j["stage"].isin(["hard_reject", "credit_policy"])]
    out["declines"] = declines.groupby(column, observed=True).size().reindex(out.index, fill_value=0)
    out["share_of_all_declines"] = (100 * out["declines"] / max(int(out["declines"].sum()), 1)).round(1)
    return out.sort_values("declines", ascending=False)


def portfolio(df: pd.DataFrame, outcome: pd.DataFrame, by: str,
              score_bands: list | None = None) -> pd.DataFrame:
    """Booked book sliced by a segment, with performance — questions 5 and 6."""
    booked = outcome["booked"]
    j = df[booked].join(outcome.loc[booked, ["observed_bad", "offered_amount"]])
    g = j.groupby(by, observed=True)
    out = pd.DataFrame({
        "booked": g.size(),
        "exposure": g["offered_amount"].sum().round(0),
        "bad_rate": (100 * g["observed_bad"].mean()).round(2),
    })
    out["share_of_book"] = (100 * out["booked"] / out["booked"].sum()).round(1)
    out["share_of_exposure"] = (100 * out["exposure"] / out["exposure"].sum()).round(1)
    return out.sort_values("share_of_exposure", ascending=False)


def concentration_flags(book: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Over- and under-exposure against an even split — question 6."""
    limits = cfg["portfolio"]
    even = 100.0 / max(len(book), 1)
    flags = []
    for name, row in book.iterrows():
        share = row["share_of_exposure"]
        if share >= limits["over_exposed_multiple"] * even:
            flags.append({"slice": name, "share_of_exposure": share, "flag": "over-exposed"})
        elif share <= limits["under_exposed_multiple"] * even:
            flags.append({"slice": name, "share_of_exposure": share, "flag": "under-exposed"})
    return pd.DataFrame(flags, columns=["slice", "share_of_exposure", "flag"])
