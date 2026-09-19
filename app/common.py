"""Common helpers, caching, and display components for the Streamlit UI."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st

from src.config import load_config
from src.contracts import Strategy
from src.loader import load_applications
from src.risk_model import (
    INFERRED,
    NOT_MODELLED,
    OBSERVED,
    PREDICTED,
    RiskModel,
    train_model,
)
from src.rules import strategy_from_config

PROVENANCE_COLORS = {
    OBSERVED: "#2e7d32",        # Green
    PREDICTED: "#1565c0",       # Blue
    INFERRED: "#e65100",        # Orange
    NOT_MODELLED: "#616161",    # Gray
    f"{OBSERVED}+{INFERRED}": "#7b1fa2",  # Purple
}


def load_app_config(config_path: str | Path | None = None) -> dict:
    return load_config(config_path)


@st.cache_data(show_spinner="Loading application dataset (1M rows)...")
def get_applications_data(data_path: str | None = None) -> pd.DataFrame:
    cfg = load_app_config()
    return load_applications(path=data_path, cfg=cfg)


@st.cache_resource(show_spinner="Training risk model on booked population...")
def get_trained_model(df: pd.DataFrame, cfg: dict | None = None) -> RiskModel:
    cfg = cfg or load_app_config()
    return train_model(df, cfg)


def get_baseline_strategy(cfg: dict | None = None) -> Strategy:
    cfg = cfg or load_app_config()
    return strategy_from_config(cfg)


def format_rate(val: float | None) -> str:
    """Format a rate as percentage or '—' if NaN/None (Section 12.1)."""
    if val is None or pd.isna(val) or not np.isfinite(val):
        return "—"
    return f"{val:.2%}"


def format_count(val: int | float | None) -> str:
    """Format an integer count with commas or '—' if NaN/None."""
    if val is None or pd.isna(val) or not np.isfinite(val):
        return "—"
    return f"{int(val):,}"


def provenance_badge(label: str) -> str:
    """Render a colored markdown/HTML pill for provenance."""
    bg_color = PROVENANCE_COLORS.get(label, "#546e7a")
    return (
        f'<span style="background-color: {bg_color}; color: white; '
        f'padding: 2px 8px; border-radius: 12px; font-size: 0.75rem; '
        f'font-weight: 600; letter-spacing: 0.5px; display: inline-block; '
        f'vertical-align: middle; margin-left: 4px;">{label}</span>'
    )


def provenance_text(label: str) -> str:
    """Plain text badge for labels inside plain text or table headers."""
    return f"[{label}]"


def render_provenance_legend() -> None:
    """Display provenance legend as required by Section 6."""
    st.markdown(
        f"""
        <div style="background-color: #f8f9fa; border: 1px solid #e0e0e0; border-radius: 8px; padding: 12px 16px; margin-bottom: 20px;">
            <span style="font-weight: 600; font-size: 0.9rem; margin-right: 15px;">Data Provenance:</span>
            {provenance_badge(OBSERVED)} <span style="font-size: 0.85rem; margin-right: 12px;">Actual bad_flag of booked</span>
            {provenance_badge(PREDICTED)} <span style="font-size: 0.85rem; margin-right: 12px;">Model PD for booked</span>
            {provenance_badge(INFERRED)} <span style="font-size: 0.85rem; margin-right: 12px;">Model PD × penalty for declines</span>
            {provenance_badge(NOT_MODELLED)} <span style="font-size: 0.85rem;">Outside training support (no PD)</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def export_downloads(df: pd.DataFrame | None, filename_prefix: str,
                     json_data: Any | None = None, key_suffix: str = "") -> None:
    """Render CSV and JSON download buttons for any table (Section 12.3)."""
    col1, col2, _ = st.columns([1, 1, 4])
    if df is not None and not df.empty:
        csv_data = df.to_csv(index=False).encode("utf-8")
        col1.download_button(
            label="📥 Download CSV",
            data=csv_data,
            file_name=f"{filename_prefix}.csv",
            mime="text/csv",
            key=f"dl_csv_{filename_prefix}_{key_suffix}",
        )
    if json_data is not None:
        if isinstance(json_data, (pd.DataFrame, pd.Series)):
            json_str = json_data.to_json(orient="records", indent=2)
        elif isinstance(json_data, (dict, list)):
            json_str = json.dumps(json_data, indent=2, default=str)
        else:
            json_str = str(json_data)
        col2.download_button(
            label="📥 Download JSON",
            data=json_str.encode("utf-8"),
            file_name=f"{filename_prefix}.json",
            mime="application/json",
            key=f"dl_json_{filename_prefix}_{key_suffix}",
        )


def format_dataframe_for_display(
    df: pd.DataFrame,
    rate_cols: list[str] | None = None,
    count_cols: list[str] | None = None,
    provenance_cols: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Format DataFrame columns for display: rates as %, counts with commas, NaN as '—'."""
    disp = df.copy()
    rate_cols = rate_cols or []
    count_cols = count_cols or []
    provenance_cols = provenance_cols or {}

    for c in count_cols:
        if c in disp.columns:
            disp[c] = disp[c].apply(format_count)

    for c in rate_cols:
        if c in disp.columns:
            disp[c] = disp[c].apply(format_rate)

    # Rename headers to include provenance badges if specified
    rename_dict = {}
    for c, prov in provenance_cols.items():
        if c in disp.columns:
            rename_dict[c] = f"{c} [{prov}]"
    if rename_dict:
        disp = disp.rename(columns=rename_dict)

    return disp
