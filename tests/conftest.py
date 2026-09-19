from pathlib import Path

import pandas as pd
import pytest

from src.config import load_config
from src.loader import load_applications
from src.rules import strategy_from_config

FIXTURE = Path(__file__).parent / "fixtures" / "sample.parquet"


@pytest.fixture(scope="session")
def cfg() -> dict:
    return load_config()


@pytest.fixture(scope="session")
def strategy(cfg):
    return strategy_from_config(cfg)


@pytest.fixture(scope="session")
def sample(cfg) -> pd.DataFrame:
    return load_applications(FIXTURE, cfg)


def make_applicants(rows: list[dict]) -> pd.DataFrame:
    """Hand-built applicants. Unspecified fields default to a clean approve."""
    base = dict(age=35, fraud_flag=False, bureau_score=750.0, bureau_vintage_months=48,
                max_dpd_12m=0, enquiries_6m=1, foir=0.30, employment_type="salaried")
    df = pd.DataFrame([{**base, **r} for r in rows])
    df["employment_type"] = pd.Categorical(df["employment_type"],
                                           categories=["salaried", "self_employed", "other"])
    return df


# ---------------------------------------------------------------- phase 2: a real (small) population
@pytest.fixture(scope="session")
def synthetic(cfg) -> pd.DataFrame:
    """200k synthetic applications — enough signal to train the PD model, far below the 1M build."""
    from src.generate_data import generate
    from src.loader import validate_schema
    df = generate({**cfg, "n_rows": 200_000})
    assert validate_schema(df) == []
    return df


@pytest.fixture(scope="session")
def model(synthetic, cfg):
    from src.risk_model import train_model
    return train_model(synthetic, cfg)


def small_cfg(cfg: dict, **model_overrides) -> dict:
    """Copy of `cfg` with model thresholds lowered so hand-built fixtures can be tiny."""
    import copy
    c = copy.deepcopy(cfg)
    c["model"].update({"min_support_obs": 1, "min_level_obs": 1, "min_cell_obs": 20, **model_overrides})
    return c


def booked_frame(rows: list[dict], n_bad_every: int = 5) -> pd.DataFrame:
    """Hand-built booked customers. Each dict may carry `n` to repeat it; every n_bad_every-th row is bad."""
    out = []
    for r in rows:
        r = dict(r)
        out += [r] * r.pop("n", 1)
    df = make_applicants(out)
    df["bad_flag"] = pd.array([1 if i % n_bad_every == 0 else 0 for i in range(len(df))], dtype="Int8")
    df["booked"] = True
    df["application_id"] = [f"b{i}" for i in range(len(df))]
    return df
