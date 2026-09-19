"""Risk model, training support (Section 9.2) and provenance labels (Section 6)."""
import numpy as np
import pandas as pd
import pytest

from src.risk_model import (INFERRED, NOT_MODELLED, OBSERVED, PREDICTED, ModelQualityError,
                            RiskModel, label_applicants)
from tests.conftest import booked_frame, make_applicants, small_cfg


def _fit(cfg, booked, population=None, **model_overrides):
    return RiskModel(small_cfg(cfg, **model_overrides)).fit(booked, population=population)


# ------------------------------------------------------------------ 9.1 training
def test_model_meets_auc_floor_and_reports_calibration(model, cfg):
    assert model.metrics["auc"] >= cfg["model"]["min_auc"]
    model.assert_quality()
    cal = model.metrics["calibration"]
    assert len(cal) == 10 and cal["n"].sum() == model.metrics["n_test"]
    # the model's predicted bad rate should track the observed one across the deciles
    assert abs(np.average(cal["mean_predicted"], weights=cal["n"])
               - np.average(cal["observed_bad_rate"], weights=cal["n"])) < 0.005


def test_assert_quality_fails_loudly_below_the_floor(model, cfg):
    weak = RiskModel({**cfg, "model": {**cfg["model"], "min_auc": 0.99}})
    weak.metrics = model.metrics
    with pytest.raises(ModelQualityError):
        weak.assert_quality()


def test_training_is_deterministic(synthetic, cfg):
    booked = synthetic[synthetic["booked"]]
    a = RiskModel(cfg).fit(booked, population=synthetic)
    b = RiskModel(cfg).fit(booked, population=synthetic)
    assert a.metrics["auc"] == b.metrics["auc"]
    pd.testing.assert_frame_equal(a.coefficients(), b.coefficients())


def test_coefficients_have_the_expected_signs(model):
    c = model.coefficients().set_index("term")["coefficient"]
    assert c["bureau_score"] < 0 and c["foir"] > 0 and c["enquiries_6m"] > 0
    assert c["max_dpd_12m=30"] > 0
    assert c["employment_type=self_employed"] > 0 and c["employment_type=other"] > 0


def test_model_ignores_the_outcome_columns_other_than_bad_flag(synthetic, cfg):
    """Fitting on a frame with the synthetic outcome scrambled must give the identical model."""
    booked = synthetic[synthetic["booked"]]
    scrambled = booked.copy()
    for col in scrambled.columns:
        if col.endswith("_bad"):
            scrambled[col] = scrambled[col].sample(frac=1.0, random_state=1).to_numpy()
    a = RiskModel(cfg).fit(booked, population=synthetic)
    b = RiskModel(cfg).fit(scrambled, population=synthetic)
    pd.testing.assert_frame_equal(a.coefficients(), b.coefficients())


# ------------------------------------------------------------------ 9.2 marginal support
def _wide_booked():
    """Booked customers: scores 700-800, dpd 0 (many) and 30 (many), dpd 60 / 90 absent."""
    rng = np.random.default_rng(0)
    rows = []
    for i in range(400):
        rows.append(dict(bureau_score=float(rng.integers(700, 800)), foir=float(rng.uniform(0.2, 0.5)),
                         max_dpd_12m=30 if i % 4 == 0 else 0, enquiries_6m=int(rng.integers(0, 4)),
                         employment_type=["salaried", "self_employed", "other"][i % 3]))
    return booked_frame(rows)


def _decline_pool():
    """Declined applicants spread over score 400-700 and FOIR 0.5-1.0 so the population deciles are
    fine-grained in the tails (with a thin tail a single decile spans the whole gap)."""
    rng = np.random.default_rng(1)
    return make_applicants([dict(bureau_score=float(rng.uniform(400, 700)), foir=float(rng.uniform(0.5, 1.0)))
                            for _ in range(1500)])


def test_predict_pd_is_nan_outside_support_and_never_zero(cfg):
    booked = _wide_booked()
    applicants = make_applicants([
        dict(bureau_score=450.0),                               # below every booked score
        dict(bureau_score=np.nan),                              # no-hit
        dict(bureau_score=750.0, bureau_vintage_months=3),      # thin file: has a score, short history
        dict(bureau_score=750.0, foir=0.9),                     # FOIR above anything booked
        dict(bureau_score=750.0),                               # control: inside support
    ])
    pop = pd.concat([booked, _decline_pool(), applicants], ignore_index=True)
    m = _fit(cfg, booked, population=pop)
    pdv = m.predict_pd(applicants)
    assert pdv.iloc[:4].isna().all(), pdv
    assert 0 < pdv.iloc[4] < 1
    assert m.support_mask(applicants).tolist() == [False, False, False, False, True]


def test_level_with_no_booked_observations_is_dropped_not_zeroed(cfg):
    booked = _wide_booked()
    applicants = make_applicants([dict(max_dpd_12m=60), dict(max_dpd_12m=90), dict(max_dpd_12m=30)])
    pop = pd.concat([booked, _decline_pool(), applicants], ignore_index=True)
    m = _fit(cfg, booked, population=pop)
    assert m.levels_["max_dpd_12m"] == [0, 30]
    terms = set(m.coefficients()["term"])
    assert "max_dpd_12m=60" not in terms and "max_dpd_12m=90" not in terms   # no coefficient at all
    dropped = pd.DataFrame(m.dropped_levels_)
    assert set(dropped["level"]) == {60, 90} and (dropped["booked_obs"] == 0).all()
    pdv = m.predict_pd(applicants)
    assert pdv.iloc[:2].isna().all()          # the riskiest applicants must NOT score as safe
    assert pdv.iloc[2] > 0


def test_categorical_level_below_min_level_obs_is_dropped(cfg):
    rows = [dict(bureau_score=750.0 + i % 40, foir=0.3 + (i % 10) / 100, employment_type="salaried",
                 enquiries_6m=i % 3) for i in range(300)]
    rows += [dict(bureau_score=760.0 + i, foir=0.35, employment_type="other", enquiries_6m=1) for i in range(30)]
    m = _fit(cfg, booked_frame(rows), min_level_obs=100)
    assert m.levels_["employment_type"] == ["salaried"]
    assert [d["level"] for d in m.dropped_levels_ if d["feature"] == "employment_type"] == ["other"]


def test_numeric_bin_below_min_support_obs_is_unsupported(cfg):
    """Deciles come from the full population; a bin holding too few booked customers is unsupported."""
    booked = _wide_booked()                                   # scores 700-799
    low = make_applicants([dict(bureau_score=float(s)) for s in range(500, 700)] * 5)   # declined pool
    pop = pd.concat([booked, low], ignore_index=True)
    m = _fit(cfg, booked, population=pop, min_support_obs=10)
    s = m.support_summary()
    bins = s[(s["feature"] == "bureau_score") & (s["kind"] == "bin")]
    assert (bins.loc[bins["hi"] <= 690, "supported"] == False).all()      # noqa: E712
    assert bins["supported"].any() and not bins["supported"].all()
    # counts, not just flags, and the distance from the threshold
    assert {"booked_obs", "applications", "threshold", "headroom"} <= set(s.columns)
    assert (bins["headroom"] == bins["booked_obs"] / 10 - 1).all()


def test_support_ranges_report_counts_inside_and_outside(model, synthetic):
    r = model.support_ranges().set_index("feature")
    n = len(synthetic)
    assert (r["applications_inside"] + r["applications_outside"] == n).all()
    assert r.loc["max_dpd_12m", "applications_outside"] == int(synthetic["max_dpd_12m"].isin([60, 90]).sum())
    assert r.loc["max_dpd_12m", "supported"] == "0, 30"
    assert r.loc["bureau_score", "applications_outside"] >= int(synthetic["bureau_score"].isna().sum())


# ------------------------------------------------------------------ 9.2 joint support
def _cell_fixture():
    booked = booked_frame([
        dict(bureau_score=690.0, foir=0.55, employment_type="salaried", n=30),        # cell A
        dict(bureau_score=670.0, foir=0.55, employment_type="self_employed", n=12),   # cell B
        dict(bureau_score=750.0, foir=0.30, employment_type="salaried", n=60),        # cell C
        dict(bureau_score=750.0, foir=0.42, employment_type="salaried", n=40),        # cell D
    ])
    return booked


def test_cell_support_returns_the_in_cell_booked_count(cfg):
    booked = _cell_fixture()
    m = _fit(cfg, booked)
    q = make_applicants([
        dict(bureau_score=685.0, foir=0.52, employment_type="salaried"),          # A
        dict(bureau_score=661.0, foir=0.51, employment_type="self_employed"),     # B
        dict(bureau_score=799.0, foir=0.10, employment_type="salaried"),          # C: open-ended bands
        dict(bureau_score=710.0, foir=0.45, employment_type="salaried"),          # D
        dict(bureau_score=685.0, foir=0.52, employment_type="other"),             # no booked in cell
        dict(bureau_score=np.nan, foir=0.52, employment_type="salaried"),         # undefined cell
    ])
    assert m.cell_support(q).tolist() == [30, 12, 60, 40, 0, 0]
    assert m.is_thin(m.cell_support(q)).tolist() == [False, True, False, False, True, True]  # min_cell_obs=20


def test_joint_support_is_independent_of_marginal_support(cfg):
    """Every marginal check passes, the cell is empty: the row still gets a PD and reports zero."""
    # Low scores are booked only at high FOIR; low FOIR is booked only at high scores.
    booked = pd.concat([_cell_fixture(), booked_frame(
        [dict(bureau_score=780.0, foir=0.20, employment_type="salaried", n=30)])], ignore_index=True)
    lowfoir_lowscore = make_applicants([dict(bureau_score=675.0, foir=0.20, employment_type="salaried")])
    pop = pd.concat([booked, lowfoir_lowscore], ignore_index=True)
    m = _fit(cfg, booked, population=pop)
    assert m.support_mask(lowfoir_lowscore).iloc[0]                 # score bin, FOIR bin, levels all supported
    assert m.predict_pd(lowfoir_lowscore).notna().iloc[0]
    assert m.cell_support(lowfoir_lowscore).iloc[0] == 0            # ...but no booked customer in the cell


def test_cell_support_table_lists_empty_cells_and_candidates(cfg):
    booked = _cell_fixture()
    m = _fit(cfg, booked)
    cand = make_applicants([dict(bureau_score=685.0, foir=0.52, employment_type="salaried")] * 3)
    t = m.cell_support_table(candidates=cand)
    assert t["booked_obs"].sum() == len(booked)
    assert (t["booked_obs"] == 0).any() and t["thin"].any()
    a = t[t["cell"].str.contains("680–699") & t["cell"].str.contains("0.50–0.60") & t["cell"].str.contains("salaried")]
    assert a["booked_obs"].iloc[0] == 30 and a["candidates"].iloc[0] == 3


# ------------------------------------------------------------------ provenance
def test_provenance_labels(synthetic, model, cfg):
    sub = synthetic.iloc[:20_000]
    lab = label_applicants(sub, model)
    booked = sub["booked"].to_numpy()
    raw = model.predict_pd(sub)
    assert (lab.loc[booked, "performance_provenance"] == OBSERVED).all()
    assert (lab.loc[booked & raw.notna().to_numpy(), "pd_provenance"] == PREDICTED).all()
    inferred = ~booked & raw.notna().to_numpy()
    assert (lab.loc[inferred, "performance_provenance"] == INFERRED).all()
    np.testing.assert_allclose(lab.loc[inferred, "pd"], np.minimum(raw[inferred] * cfg["model"]["inference_penalty"], 1))
    nm = ~booked & raw.isna().to_numpy()
    assert nm.any() and (lab.loc[nm, "performance_provenance"] == NOT_MODELLED).all()
    assert lab.loc[nm, "pd"].isna().all()                              # never an imputed zero


# ------------------------------------------------------------------ support = dense bin AND inside the booked range
def test_value_beyond_the_booked_range_is_unsupported_even_in_a_dense_bin(cfg):
    """Booked customers have 0-3 enquiries. The population has a few 12s, so the top decile bin is wide
    and dense; a marginal bin check alone would certify enquiries=12."""
    booked = _wide_booked()                                         # enquiries 0-3
    tail = make_applicants([dict(enquiries_6m=e) for e in [4, 5, 6, 8, 12] * 3])
    pop = pd.concat([booked, tail], ignore_index=True)
    m = _fit(cfg, booked, population=pop)
    s = m.support_summary()
    top = s[(s["feature"] == "enquiries_6m") & (s["kind"] == "bin")].iloc[-1]
    assert top["supported"] and top["hi"] == 12                    # the bin passes on density...
    q = make_applicants([dict(enquiries_6m=e) for e in (0, 3, 4, 12)])
    assert m.support_mask(q).tolist() == [True, True, False, False]  # ...but the value is out of range
    assert m.predict_pd(q).iloc[2:].isna().all()
    r = m.support_ranges().set_index("feature").loc["enquiries_6m"]
    assert (r["booked_min"], r["booked_max"]) == (0, 3) and r["supported"].endswith("–3")
    assert r["applications_inside"] + r["applications_outside"] == len(pop)


def test_real_model_scores_nobody_above_six_enquiries(model, synthetic):
    r = model.support_ranges().set_index("feature").loc["enquiries_6m"]
    assert r["booked_max"] == 6
    high = synthetic[synthetic["enquiries_6m"] > 6]
    assert len(high) > 0 and model.predict_pd(high).isna().all()


def test_empty_training_set_raises_a_useful_error(sample, cfg):
    """A dataset too small to fit the model must say so, not surface sklearn's `n_samples=0`.

    Pointing the app at a small extract is an ordinary mistake — ORIGSIM_DATA_PATH, `--data`, or a
    trimmed client sample. The support filters are what empty the training set, so the error has to
    name them and their thresholds; sklearn's split error names none of it.
    """
    import pytest

    from src.risk_model import ModelQualityError, train_model

    with pytest.raises(ModelQualityError) as exc:
        train_model(sample, cfg)

    message = str(exc.value)
    assert "min_support_obs" in message
    assert "min_level_obs" in message
    assert "config.yaml" in message
