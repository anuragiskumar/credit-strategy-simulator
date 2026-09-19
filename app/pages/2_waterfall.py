"""Decline Waterfall & Policy Bottlenecks (REQUIREMENTS.md Section 12.2 Page 2).

Displays sequential waterfall, override adjustment step, segment exclusions,
single-rule declines (near-miss opportunities), and score x FOIR decline heatmap.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.common import (
    export_downloads,
    format_count,
    get_applications_data,
    get_baseline_strategy,
    load_app_config,
    render_provenance_legend,
)
from src.waterfall import build_waterfall, decline_heatmap, single_rule_declines


def render_waterfall_page():
    st.title("📉 Policy Waterfall & Decline Diagnostics")
    st.markdown(
        "Sequential policy filtering, manual override reconciliation, near-miss single rule failures, and decline concentration."
    )

    render_provenance_legend()

    cfg = load_app_config()
    df = get_applications_data()
    baseline = get_baseline_strategy(cfg)

    # 1. Sequential Waterfall
    st.subheader("Sequential Decline Waterfall")
    st.caption(
        "Each rule is evaluated sequentially in priority order. The manual override steps reconcile the written strategy "
        "to the actual booked approvals, derived strictly from the manual_override flag."
    )

    wf = build_waterfall(df, baseline, adjustment="historical")

    # Plotly waterfall chart
    measures = []
    y_vals = []
    text_vals = []

    for _, row in wf.iterrows():
        kind = row["kind"]
        rem = row["remaining"]
        delta = row["delta"]
        if kind == "start":
            measures.append("absolute")
            y_vals.append(rem)
            text_vals.append(f"{rem:,}")
        elif kind in ("subtotal", "end"):
            measures.append("total")
            y_vals.append(rem)
            text_vals.append(f"{rem:,}")
        else:
            measures.append("relative")
            y_vals.append(delta)
            sign = "+" if delta > 0 else ""
            text_vals.append(f"{sign}{delta:,}")

    fig_wf = go.Figure(
        go.Waterfall(
            name="Applications",
            orientation="v",
            measure=measures,
            x=wf["label"],
            textposition="outside",
            text=text_vals,
            y=y_vals,
            connector={"line": {"color": "#9e9e9e", "dash": "dot"}},
            decreasing={"marker": {"color": "#e53935"}},
            increasing={"marker": {"color": "#43a047"}},
            totals={"marker": {"color": "#1e88e5"}},
        )
    )
    fig_wf.update_layout(
        title="Application Volume Through Policy Steps",
        showlegend=False,
        height=500,
        margin={"l": 40, "r": 40, "t": 60, "b": 100},
        xaxis_tickangle=-35,
    )
    st.plotly_chart(fig_wf, use_container_width=True)

    # Table displaying waterfall numbers (visibly summing to total)
    with st.expander("View Waterfall Table & Reconciliations", expanded=True):
        disp_wf = wf.copy()
        disp_wf["delta_str"] = disp_wf["delta"].apply(
            lambda v: f"{int(v):+,}" if pd.notna(v) and v != 0 else ("0" if pd.notna(v) else "—")
        )
        disp_wf["delta_pct_str"] = disp_wf["delta_pct"].apply(
            lambda v: f"{v:+.2%}" if pd.notna(v) else "—"
        )
        disp_wf["remaining_str"] = disp_wf["remaining"].apply(lambda v: f"{int(v):,}")
        disp_wf["remaining_pct_str"] = disp_wf["remaining_pct"].apply(lambda v: f"{v:.2%}")

        show_table = disp_wf[["step", "label", "kind", "delta_str", "delta_pct_str", "remaining_str", "remaining_pct_str"]].rename(
            columns={
                "step": "Step",
                "label": "Policy Step",
                "kind": "Type",
                "delta_str": "Volume Impact",
                "delta_pct_str": "% of Total",
                "remaining_str": "Remaining Volume",
                "remaining_pct_str": "Remaining %",
            }
        )
        st.dataframe(show_table, use_container_width=True, hide_index=True)
        export_downloads(wf, "decline_waterfall", key_suffix="wf")

    st.divider()

    # 2. Single-Rule Declines (Near-Miss Opportunities)
    st.subheader("Near-Miss Analysis: Single-Rule Declines")
    st.markdown(
        "Applicants who passed every rule **except one**. These represent the most accessible volume "
        "opportunities if appetite permits targeted relaxations."
    )

    srd = single_rule_declines(df, baseline)
    col1, col2 = st.columns([3, 2])
    with col1:
        fig_srd = px.bar(
            srd,
            x="rule_id",
            y="single_rule_declines",
            color="mandatory",
            color_discrete_map={True: "#e53935", False: "#1e88e5"},
            labels={"single_rule_declines": "Single-Rule Declines", "rule_id": "Failed Rule", "mandatory": "Mandatory Rule"},
            title="Single-Rule Declines by Rule",
            text_auto=","
        )
        fig_srd.update_layout(height=350, margin={"l": 20, "r": 20, "t": 50, "b": 20})
        st.plotly_chart(fig_srd, use_container_width=True)

    with col2:
        srd_disp = srd.copy()
        srd_disp["single_rule_declines"] = srd_disp["single_rule_declines"].apply(format_count)
        srd_disp["failed_any"] = srd_disp["failed_any"].apply(format_count)
        srd_disp["single_rule_pct_of_applications"] = srd_disp["single_rule_pct_of_applications"].apply(lambda v: f"{v:.2%}")
        st.dataframe(
            srd_disp.rename(columns={
                "rule_id": "Rule ID",
                "mandatory": "Mandatory",
                "failed_any": "Total Failures",
                "single_rule_declines": "Single Failures",
                "single_rule_pct_of_applications": "% of Total",
            }),
            use_container_width=True,
            hide_index=True,
        )
        export_downloads(srd, "single_rule_declines", key_suffix="srd")

    st.divider()

    # 3. Score x FOIR Heatmap
    st.subheader("Decline Density: Bureau Score × FOIR Heatmap")
    st.markdown(
        "Distribution of declined applications across bureau score and FOIR bands (written strategy declines). "
        "Darker cells highlight where declines concentrate."
    )

    heatmap_df = decline_heatmap(df, cfg, baseline)
    fig_heat = px.imshow(
        heatmap_df,
        labels=dict(x="FOIR Band", y="Bureau Score Band", color="Declined Volume"),
        x=list(heatmap_df.columns),
        y=list(heatmap_df.index),
        text_auto="," ,
        color_continuous_scale="Blues",
        aspect="auto",
    )
    fig_heat.update_layout(
        title="Declined Applications by Bureau Score vs FOIR",
        height=450,
        margin={"l": 40, "r": 40, "t": 50, "b": 40},
    )
    st.plotly_chart(fig_heat, use_container_width=True)
    export_downloads(heatmap_df.reset_index(), "decline_heatmap", key_suffix="hm")


if __name__ == "__main__":
    render_waterfall_page()
