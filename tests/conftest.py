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
