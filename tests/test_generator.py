import pandas as pd
import pytest

from src.generate_data import calibration_table, generate
from src.loader import SchemaError, load_applications, validate_schema


def _cfg(cfg, **kw):
    return {**cfg, **kw}


def test_generator_is_deterministic_for_a_seed(cfg):
    a = generate(_cfg(cfg, n_rows=3000))
    b = generate(_cfg(cfg, n_rows=3000))
    pd.testing.assert_frame_equal(a, b)
    c = generate(_cfg(cfg, n_rows=3000, seed=cfg["seed"] + 1))
    assert not a["bureau_score"].equals(c["bureau_score"])


def test_generated_data_passes_schema_validation(cfg):
    assert validate_schema(generate(_cfg(cfg, n_rows=3000))) == []


def test_fixture_loads_and_has_overrides_of_both_directions(sample):
    assert 400 <= len(sample) <= 600
    ov = sample[sample["manual_override"]]
    assert set(ov["hist_decision"]) == {"approve", "decline"}
    assert (ov.loc[ov["hist_decision"] == "decline", "hist_decline_reason"] == "MANUAL_OVERRIDE").all()


def test_override_approvals_are_marginal_only_r5_r6_failures(cfg):
    df = generate(_cfg(cfg, n_rows=50_000))
    ov_in = df[df["manual_override"] & (df["hist_decision"] == "approve")]
    assert len(ov_in) == 350
    assert ov_in["fraud_flag"].eq(False).all() and ov_in["age"].between(21, 60).all()
    assert ov_in["bureau_score"].notna().all() and (ov_in["max_dpd_12m"] < 60).all()
    assert (ov_in["bureau_score"].between(650, 699) & ov_in["foir"].between(0.5, 0.6)).mean() > 0.7


def test_calibration_targets_are_met_at_400k_rows(cfg):
    # The salaried / low-FOIR / 680-699 cell is ~1.3% of rows, so it needs volume to be stable.
    df = generate(_cfg(cfg, n_rows=400_000))
    table = calibration_table(df, cfg)
    assert table["pass"].all(), table.to_string()


# ------------------------------------------------------------------ loader
def test_loader_rejects_missing_column(sample, tmp_path, cfg):
    p = tmp_path / "bad.parquet"
    sample.drop(columns=["foir"]).to_parquet(p)
    with pytest.raises(SchemaError, match="missing columns"):
        load_applications(p, cfg)


def test_loader_rejects_duplicate_ids_and_inconsistent_booking(sample, tmp_path, cfg):
    dup = sample.copy()
    dup.loc[1, "application_id"] = dup.loc[0, "application_id"]
    assert any("not unique" in m for m in validate_schema(dup))
    inconsistent = sample.copy()
    i = inconsistent.index[inconsistent["booked"]][0]
    inconsistent.loc[i, "booked"] = False
    assert any("booked" in m for m in validate_schema(inconsistent))


def test_loader_accepts_a_dataset_without_the_synthetic_outcome_column(sample, tmp_path, cfg):
    p = tmp_path / "real_like.parquet"
    sample.drop(columns=["true_bad"]).to_parquet(p)
    df = load_applications(p, cfg)
    assert len(df) == len(sample)


def test_calibration_targets_are_met_at_one_million_rows(cfg):
    """The targets in 5.3 are stated for the full 1M build; check them at that size, in memory."""
    df = generate({**cfg, "n_rows": 1_000_000})
    table = calibration_table(df, cfg)
    assert table["pass"].all(), table.to_string()
