"""Tests for Streamlit UI helpers, page modules, AppTest rendering, and integration (Phase 4)."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

from app.common import (
    format_count,
    format_dataframe_for_display,
    format_rate,
    get_applications_data,
    get_baseline_strategy,
    get_trained_model,
    load_app_config,
    provenance_badge,
    provenance_text,
)
from src.optimise import optimise
from src.risk_model import INFERRED, NOT_MODELLED, OBSERVED, PREDICTED
from src.rules import with_rule_params
from src.simulate import scenario_from_dict, simulate_detailed
from src.validation import validate_strategy_oracle

PAGES_DIR = Path(__file__).resolve().parent.parent / "app" / "pages"
PAGE_FILES = [
    "1_overview.py",
    "2_waterfall.py",
    "3_risk_model.py",
    "4_what_if.py",
    "5_optimiser.py",
    "6_portfolio_quality.py",
    "7_validation.py",
    "8_next_steps.py",
]


def test_format_rate():
    assert format_rate(0.0345) == "3.45%"
    assert format_rate(0.0) == "0.00%"
    assert format_rate(np.nan) == "—"
    assert format_rate(None) == "—"


def test_format_count():
    assert format_count(12400) == "12,400"
    assert format_count(0) == "0"
    assert format_count(np.nan) == "—"
    assert format_count(None) == "—"


def test_provenance_badge():
    for label in [OBSERVED, PREDICTED, INFERRED, NOT_MODELLED]:
        badge = provenance_badge(label)
        assert label in badge
        assert "background-color" in badge
        assert provenance_text(label) == f"[{label}]"


def test_format_dataframe_for_display():
    df = pd.DataFrame({
        "counts": [1000, np.nan],
        "rates": [0.05, np.nan],
        "other": ["A", "B"],
    })
    disp = format_dataframe_for_display(
        df,
        rate_cols=["rates"],
        count_cols=["counts"],
        provenance_cols={"rates": INFERRED},
    )
    assert disp["counts"].iloc[0] == "1,000"
    assert disp["counts"].iloc[1] == "—"
    assert disp[f"rates [{INFERRED}]"].iloc[0] == "5.00%"
    assert disp[f"rates [{INFERRED}]"].iloc[1] == "—"


def test_page_files_exist_and_importable():
    for filename in PAGE_FILES:
        page_path = PAGES_DIR / filename
        assert page_path.exists(), f"{filename} does not exist in {PAGES_DIR}"
        spec = importlib.util.spec_from_file_location(f"page_{filename[:-3]}", page_path)
        assert spec is not None
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        assert hasattr(mod, f"render_{filename.split('_', 1)[1][:-3]}_page")


def test_streamlit_app_compiles():
    app_path = Path(__file__).resolve().parent.parent / "app" / "streamlit_app.py"
    assert app_path.exists()
    compiled = compile(app_path.read_text(encoding="utf-8"), str(app_path), "exec")
    assert compiled is not None


def test_apptest_pages_render_without_exception():
    for filename in ["streamlit_app.py"] + [f"pages/{p}" for p in PAGE_FILES]:
        app_file = Path(__file__).resolve().parent.parent / "app" / filename
        at = AppTest.from_file(str(app_file), default_timeout=30).run()
        assert len(at.exception) == 0, f"{filename} raised an exception: {at.exception}"


def test_apptest_optimiser_run_button():
    page_file = str(PAGES_DIR / "5_optimiser.py")
    at = AppTest.from_file(page_file, default_timeout=30).run()
    assert len(at.exception) == 0
    assert len(at.button) > 0
    at.button[0].click().run()
    assert len(at.exception) == 0


def test_apptest_portfolio_quality_trade_button():
    page_file = str(PAGES_DIR / "6_portfolio_quality.py")
    at = AppTest.from_file(page_file, default_timeout=30).run()
    assert len(at.exception) == 0
    assert len(at.button) > 0
    at.button[0].click().run()
    assert len(at.exception) == 0


def test_apptest_oracle_validation_run_button():
    page_file = str(PAGES_DIR / "7_validation.py")
    at = AppTest.from_file(page_file, default_timeout=30).run()
    assert len(at.exception) == 0
    assert len(at.button) > 0
    at.button[0].click().run()
    assert len(at.exception) == 0


def test_scenario_json_roundtrip_equality():
    cfg = load_app_config()
    df = get_applications_data()
    model = get_trained_model(df, cfg)
    baseline = get_baseline_strategy(cfg)

    spec = {
        "rules": {
            "R5_SCORE": {"cutoff": 680},
            "R6_FOIR": {"cap": 0.45},
        },
        "enabled": {
            "R5_SCORE": True,
            "R6_FOIR": True,
        },
        "inference_penalty": 1.35,
    }

    # JSON round-trip
    spec_json = json.dumps(spec)
    loaded_spec = json.loads(spec_json)

    # UI simulation logic
    ui_penalty = float(loaded_spec.get("inference_penalty", 1.25))
    ui_strategy = scenario_from_dict(baseline, loaded_spec, cfg)
    ui_res, ui_det = simulate_detailed(df, baseline, ui_strategy, model, cfg, ui_penalty)

    # CLI simulation logic (identical call with loaded spec)
    cli_strategy = scenario_from_dict(baseline, loaded_spec, cfg)
    cli_res, cli_det = simulate_detailed(df, baseline, cli_strategy, model, cfg, loaded_spec.get("inference_penalty"))

    assert ui_res.approval_count == cli_res.approval_count
    assert ui_res.blended_bad_rate == cli_res.blended_bad_rate
    assert ui_res.inferred_bad_rate == cli_res.inferred_bad_rate
    assert ui_res.swap_in_count == cli_res.swap_in_count


def test_naive_oracle_row_assertion():
    cfg = load_app_config()
    df = get_applications_data()
    model = get_trained_model(df, cfg)
    baseline = get_baseline_strategy(cfg)

    opt_res = optimise(df, baseline, model, cfg)
    naive_strategy = with_rule_params(baseline, {"R5_SCORE": {"cutoff": int(opt_res.naive_cutoff)}})
    val_naive = validate_strategy_oracle(df, baseline, naive_strategy, opt_res.naive_result, model)

    assert val_naive["approval_count"] == opt_res.naive_result.approval_count


def test_max_inferred_share_warning(monkeypatch):
    from app import common
    real_load = common.load_app_config

    def mock_load(path=None):
        cfg = real_load(path)
        cfg_copy = copy.deepcopy(cfg)
        cfg_copy["model"]["max_inferred_share"] = 0.05
        return cfg_copy

    monkeypatch.setattr(common, "load_app_config", mock_load)

    page_file = str(PAGES_DIR / "4_what_if.py")
    at = AppTest.from_file(page_file, default_timeout=30).run()
    at.slider[0].set_value(650).run()

    warning_texts = [w.value for w in at.warning]
    assert any("Extrapolation Risk Alert" in w for w in warning_texts)
