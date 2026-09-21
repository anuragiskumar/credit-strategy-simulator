"""Probability-of-default model and the honesty guard around it (plan steps 3-4).

The brief's sharpest warning: below the historical cutoff a confident number is dangerous,
because it tells a CxO to loosen a rule for free. The notebook found exactly that — under 660
the bad rate was stuck at 14.5% purely because nobody below it was ever funded.

So this module does two things, and the second matters more:

  1. `fit()` trains a PD model on BOOKED applicants only, which is all a real bank has.
  2. `coverage()` reports where the model is extrapolating, and `predict_group()` refuses to
     give a point estimate for a group the booked population never covered. It returns
     "unknown" instead.

`latent_bad` is available in synthetic data for every applicant. `oracle_bad_rate()` exposes it
under a name nobody can mistake for a production number, so the demo can show how close the
honest estimate got.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

FEATURES = ["simah_score", "crif_score", "log_income", "log_loan_to_income", "age",
            "length_of_service_months", "no_simah_score"]
"""What the model reads. Asserted in `features()` so this list cannot drift from the code
and quietly mislead whoever is reviewing what the bank is deciding on."""


def features(df: pd.DataFrame, impute_score: float) -> pd.DataFrame:
    income = df["monthly_income"].astype(float).clip(lower=1.0)
    amount = df["requested_amount"].astype(float).clip(lower=1.0)
    simah = df["simah_score"].astype(float)
    out = pd.DataFrame({
        # A missing score is imputed AND flagged, so the model can learn that missing is its
        # own segment rather than an average applicant. The notebook's second finding.
        "simah_score": simah.fillna(impute_score),
        "crif_score": df["crif_score"].astype(float),
        "log_income": np.log(income),
        "log_loan_to_income": np.log(amount / income),
        "age": df["age"].astype(float),
        "length_of_service_months": df["length_of_service_months"].astype(float),
        "no_simah_score": simah.isna().astype(float),
    }, index=df.index)
    assert list(out.columns) == FEATURES, "features() drifted from FEATURES"
    return out


@dataclass
class PDModel:
    pipeline: Pipeline
    gini: float
    n_train: int
    train_bad_rate: float
    impute_score: float
    score_floor: float          # lowest SIMAH score actually booked
    score_ceiling: float
    booked_missing_score: bool  # did the bank book anyone with no score at all?

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        X = features(df, self.impute_score)
        return self.pipeline.predict_proba(X)[:, 1]

    def in_support(self, df: pd.DataFrame) -> np.ndarray:
        """True where the bank has actually booked applicants like this one.

        Outside it the model is extrapolating into territory it has never funded, and the
        estimate is a guess dressed as a number. Two distinct cases:

          * a score below the lowest ever booked — the LendingClub trap, where the bad rate
            looked flat under 660 only because nobody under 660 was funded;
          * a missing score, which is in support only if the bank booked applicants with no
            score. It does here, so they count; on a book that never funded them, they
            would not.
        """
        s = df["simah_score"].astype(float)
        within = (s >= self.score_floor) & (s <= self.score_ceiling)
        return within.fillna(self.booked_missing_score).to_numpy()


def fit(df: pd.DataFrame, outcome: pd.DataFrame, cfg: dict) -> PDModel:
    """Train on mature booked loans only — the only performance a real bank observes.

    A loan booked last month has not had time to go bad. Training on it as a good would teach
    the model that recent business is safe, which is the same flattering error as counting it
    in the bad rate.
    """
    rk = cfg["risk_model"]
    booked = (outcome["booked"] & outcome["observed_bad"].notna()).to_numpy()
    if booked.sum() < rk["min_training_rows"]:
        raise ValueError(f"only {int(booked.sum())} booked loans are old enough to judge; need "
                         f"{rk['min_training_rows']} to fit a PD model")
    train = df[booked]
    y = outcome.loc[booked, "observed_bad"].astype(int).to_numpy()
    impute = float(train["simah_score"].median())
    X = features(train, impute)
    pipe = Pipeline([("scale", StandardScaler()),
                     ("lr", LogisticRegression(max_iter=rk["max_iter"], C=rk["C"]))])
    pipe.fit(X, y)
    auc = roc_auc_score(y, pipe.predict_proba(X)[:, 1])
    scored = train["simah_score"].dropna()
    return PDModel(pipeline=pipe, gini=round(2 * auc - 1, 4), n_train=int(booked.sum()),
                   train_bad_rate=float(y.mean()), impute_score=impute,
                   score_floor=float(scored.min()), score_ceiling=float(scored.max()),
                   booked_missing_score=bool(train["simah_score"].isna().sum()
                                             >= rk["min_missing_score_booked"]))


def predict_group(model: PDModel, df: pd.DataFrame, mask: np.ndarray, cfg: dict) -> dict:
    """Estimated bad rate for a group, with an explicit refusal when we cannot know.

    A group mostly outside the booked score range gets `known=False` and no point estimate.
    That is the "we don't know" the brief asks the simulator to be able to say.
    """
    rk = cfg["risk_model"]
    n = int(mask.sum())
    if n == 0:
        return {"n": 0, "known": False, "reason": "no applicants in this group"}
    # A verdict on a handful of applicants is noise. Telling a risk committee that a rule
    # "does not earn its place" on the evidence of ten people is worse than saying nothing.
    if n < rk["min_group_size"]:
        return {"n": n, "known": False,
                "reason": f"only {n} applicants; below the {rk['min_group_size']} needed "
                          f"for an estimate worth acting on"}
    group = df[mask]
    supported = model.in_support(group)
    coverage = float(supported.mean())
    if coverage < rk["min_support_coverage"]:
        # Say which kind of gap it is. "Outside the booked score range" and "has no score
        # at all" are different problems and a risk committee will ask which.
        no_score = float(group["simah_score"].isna().mean())
        cause = (f"{100 * no_score:.0f}% have no SIMAH score at all"
                 if no_score > (1 - coverage) / 2 else
                 f"they sit outside the {model.score_floor:.0f}-{model.score_ceiling:.0f} "
                 f"score range the bank has ever booked")
        return {"n": n, "known": False, "support_coverage": round(coverage, 3),
                "reason": f"{100 * (1 - coverage):.0f}% of this group is unlike anything "
                          f"the bank has booked — {cause}; no estimate is defensible"}
    p = model.predict(group)
    return {"n": n, "known": True, "support_coverage": round(coverage, 3),
            "estimated_bad_rate": round(float(p.mean()), 4),
            "low": round(float(np.quantile(p, rk["interval_low"])), 4),
            "high": round(float(np.quantile(p, rk["interval_high"])), 4)}


def oracle_bad_rate(df: pd.DataFrame, mask: np.ndarray) -> float:
    """The TRUE bad rate of any group, declined included.

    Only exists because the population is synthetic. Never available in production, and never
    used to produce a number the demo presents as something the engine worked out.
    """
    if mask.sum() == 0:
        return float("nan")
    return float(df.loc[mask, "latent_bad"].mean())
