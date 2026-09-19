"""What-if Simulator (REQUIREMENTS.md Section 12.2 Page 4).

Lets users modify relaxable rule parameters, toggle rules, load segment overrides,
and simulate the portfolio impact with strict provenance accounting.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import json
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.common import (
    export_downloads,
    format_count,
    format_rate,
    get_applications_data,
    get_baseline_strategy,
    get_trained_model,
    load_app_config,
    provenance_badge,
    render_provenance_legend,
)
from src.risk_model import INFERRED, NOT_MODELLED, OBSERVED, PREDICTED
from src.simulate import (
    scenario_from_dict,
    simulate_detailed,
)


def render_what_if_page():
    st.title("🎛️ What-if Strategy Simulator")
    st.markdown(
        "Simulate changes to credit policy parameters, toggle relaxable rules, or load segment overrides. "
        "Strictly accounts for observed, predicted, and inferred risk components."
    )

    render_provenance_legend()

    cfg = load_app_config()
    df = get_applications_data()
    model = get_trained_model(df, cfg)
    baseline = get_baseline_strategy(cfg)

    # 1. Parameter Controls & Scenario Configuration
    st.subheader("Policy Parameters & Rule Controls")

    # Initialise session state defaults if not present
    default_penalty = st.session_state.get("adopted_penalty", cfg["model"]["inference_penalty"])

    with st.sidebar:
        st.header("Simulation Settings")
        penalty = st.number_input(
            "Conservatism Penalty (Inferred PD multiplier)",
            min_value=1.0,
            max_value=3.0,
            value=float(default_penalty),
            step=0.05,
            help="Multiplier applied to model PD for historically declined applicants (Section 9.3).",
        )

        st.divider()
        st.subheader("Scenario Import / Export")
        uploaded_file = st.file_uploader("Upload Scenario JSON", type=["json"])
        uploaded_spec = None
        if uploaded_file is not None:
            try:
                uploaded_spec = json.load(uploaded_file)
                st.success("Loaded scenario JSON successfully!")
            except Exception as e:
                st.error(f"Invalid JSON: {e}")

        # Check if optimiser sent a strategy
        if "pending_whatif_spec" in st.session_state:
            st.info("Strategy loaded from Optimiser!")
            if st.button("Clear Loaded Optimiser Strategy"):
                del st.session_state["pending_whatif_spec"]
                st.rerun()

    # Rule Controls in 2 columns
    spec_rules = {}
    spec_enabled = {}

    baseline_rule_params = {r.id: r.params for r in baseline.rules}
    r5_default_cutoff = int(baseline_rule_params.get("R5_SCORE", {}).get("cutoff", 700))
    r6_default_cap = float(baseline_rule_params.get("R6_FOIR", {}).get("cap", 0.50))
    r3_default_vintage = int(baseline_rule_params.get("R3_THIN_FILE", {}).get("min_vintage", 6))
    r4_default_dpd = int(baseline_rule_params.get("R4_BUREAU_HIST", {}).get("dpd_lt", 60))
    r4_default_enq = int(baseline_rule_params.get("R4_BUREAU_HIST", {}).get("max_enquiries", 6))

    col_ctrl1, col_ctrl2 = st.columns(2)

    with col_ctrl1:
        st.markdown("**Bureau Score & FOIR Rules**")
        # R5_SCORE
        r5_enabled = st.checkbox("R5_SCORE Enabled", value=True, help="Bureau score cutoff")
        spec_enabled["R5_SCORE"] = r5_enabled
        r5_cutoff = st.slider(
            "R5_SCORE: Cutoff",
            min_value=300,
            max_value=850,
            value=r5_default_cutoff,
            step=5,
            disabled=not r5_enabled,
        )
        spec_rules["R5_SCORE"] = {"cutoff": r5_cutoff}

        # R6_FOIR
        r6_enabled = st.checkbox("R6_FOIR Enabled", value=True, help="Fixed Obligation to Income Ratio cap")
        spec_enabled["R6_FOIR"] = r6_enabled
        r6_cap = st.slider(
            "R6_FOIR: Cap",
            min_value=0.20,
            max_value=0.90,
            value=r6_default_cap,
            step=0.01,
            disabled=not r6_enabled,
        )
        spec_rules["R6_FOIR"] = {"cap": r6_cap}

    with col_ctrl2:
        st.markdown("**Thin File & Bureau History Rules**")
        # R3_THIN_FILE
        r3_enabled = st.checkbox("R3_THIN_FILE Enabled", value=True, help="Minimum bureau vintage months")
        spec_enabled["R3_THIN_FILE"] = r3_enabled
        r3_vintage = st.number_input(
            "R3_THIN_FILE: Min Vintage (months)",
            min_value=0,
            max_value=24,
            value=r3_default_vintage,
            step=1,
            disabled=not r3_enabled,
        )
        spec_rules["R3_THIN_FILE"] = {"min_vintage": int(r3_vintage)}

        # R4_BUREAU_HIST
        r4_enabled = st.checkbox("R4_BUREAU_HIST Enabled", value=True, help="Delinquency and enquiry caps")
        spec_enabled["R4_BUREAU_HIST"] = r4_enabled
        r4_col1, r4_col2 = st.columns(2)
        dpd_options = [30, 60, 90, 180]
        dpd_idx = dpd_options.index(r4_default_dpd) if r4_default_dpd in dpd_options else 1
        with r4_col1:
            r4_dpd = st.selectbox(
                "Max DPD < (dpd_lt)",
                options=dpd_options,
                index=dpd_idx,
                disabled=not r4_enabled,
            )
        with r4_col2:
            r4_enq = st.number_input(
                "Max Enquiries (6m)",
                min_value=0,
                max_value=20,
                value=r4_default_enq,
                step=1,
                disabled=not r4_enabled,
            )
        spec_rules["R4_BUREAU_HIST"] = {"dpd_lt": int(r4_dpd), "max_enquiries": int(r4_enq)}

    # Build or override scenario spec
    base_spec = {
        "rules": spec_rules,
        "enabled": spec_enabled,
        "inference_penalty": penalty,
    }

    if uploaded_spec:
        scenario_spec = uploaded_spec
        st.info("Running uploaded scenario spec.")
    elif "pending_whatif_spec" in st.session_state:
        scenario_spec = st.session_state["pending_whatif_spec"]
        st.info("Running strategy imported from Optimiser.")
    else:
        scenario_spec = base_spec

    sim_penalty = float(scenario_spec.get("inference_penalty", penalty))

    # Build scenario strategy & run simulation
    try:
        scenario_strategy = scenario_from_dict(baseline, scenario_spec, cfg)
        result, detail = simulate_detailed(df, baseline, scenario_strategy, model, cfg, sim_penalty)
    except Exception as e:
        st.error(f"🚨 **Simulation Error**: {e}")
        return

    st.divider()

    # 2. Baseline vs Scenario Headline KPIs
    st.subheader("Simulation Results: Baseline vs Scenario")

    # Warnings from detail
    for w in detail.warnings:
        st.warning(f"⚠️ {w}")

    if result.inferred_share > cfg["model"]["max_inferred_share"]:
        st.warning(
            f"⚠️ **Extrapolation Risk Alert**: Inferred share of approvals ({result.inferred_share:.2%}) "
            f"exceeds the maximum threshold ({cfg['model']['max_inferred_share']:.2%}). "
            "The strategy relies heavily on extrapolated risk estimates for historically declined applicants."
        )

    col_kpi1, col_kpi2, col_kpi3, col_kpi4 = st.columns(4)
    with col_kpi1:
        st.metric(
            "Approval Rate",
            f"{result.approval_rate:.2%}",
            f"{result.approval_rate - detail.baseline_approval_rate:+.2%} vs baseline ({detail.baseline_approval_rate:.2%})",
        )
        st.caption(f"{result.approval_count:,} total approvals")
    with col_kpi2:
        st.metric(
            "Swap-Ins (New Approvals)",
            format_count(result.swap_in_count),
            f"-{result.swap_out_count:,} swap-outs" if result.swap_out_count else "0 swap-outs",
        )
        st.caption(f"{result.not_modelled_count:,} NOT_MODELLED")
    with col_kpi3:
        st.markdown(
            f"<div>"
            f"<div style='font-size: 0.875rem; color: #666;'>Blended Bad Rate {provenance_badge(f'{OBSERVED}+{INFERRED}')}</div>"
            f"<div style='font-size: 1.8rem; font-weight: 600;'>{format_rate(result.blended_bad_rate)}</div>"
            f"<div style='font-size: 0.8rem; color: #666;'>excludes {result.not_modelled_count:,} unmodelled</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    with col_kpi4:
        st.metric(
            "Inferred Share of Approvals",
            f"{result.inferred_share:.2%}",
            "Extrapolation risk" if result.inferred_share > cfg["model"]["max_inferred_share"] else "Within limit",
            delta_color="inverse" if result.inferred_share > cfg["model"]["max_inferred_share"] else "normal",
        )
        st.caption(f"Conservatism penalty: {sim_penalty:.2f}×")

    # Section 6 & 6.1: Detailed Bad Rate Breakdown
    st.markdown("#### Bad Rate Breakdown & Model-Basis Baseline (Section 6.1)")
    st.caption(
        "Comparing an OBSERVED baseline against a blended scenario mixes real policy effects with model bias. "
        "The model-basis baseline gives the mean PREDICTED PD of the baseline booked population on the same modelling basis."
    )

    br_c1, br_c2, br_c3, br_c4 = st.columns(4)
    with br_c1:
        st.markdown(
            f"**Baseline Observed** {provenance_badge(OBSERVED)}<br>"
            f"<span style='font-size: 1.3rem; font-weight: 600;'>{format_rate(detail.baseline_observed_bad_rate)}</span><br>"
            f"<span style='font-size: 0.8rem; color: #666;'>Actual bad_flag on booked</span>",
            unsafe_allow_html=True,
        )
    with br_c2:
        bias_str = f" ({detail.model_bias_ratio:+.1%} bias)" if pd.notna(detail.model_bias_ratio) else ""
        st.markdown(
            f"**Model-Basis Baseline** {provenance_badge(PREDICTED)}<br>"
            f"<span style='font-size: 1.3rem; font-weight: 600;'>{format_rate(result.model_basis_baseline)}</span><br>"
            f"<span style='font-size: 0.8rem; color: #666;'>Mean PD on booked{bias_str}</span>",
            unsafe_allow_html=True,
        )
    with br_c3:
        st.markdown(
            f"**Scenario Retained** {provenance_badge(OBSERVED)}<br>"
            f"<span style='font-size: 1.3rem; font-weight: 600;'>{format_rate(result.observed_bad_rate)}</span><br>"
            f"<span style='font-size: 0.8rem; color: #666;'>{detail.retained_count:,} retained booked</span>",
            unsafe_allow_html=True,
        )
    with br_c4:
        st.markdown(
            f"**Scenario Swap-Ins** {provenance_badge(INFERRED)}<br>"
            f"<span style='font-size: 1.3rem; font-weight: 600;'>{format_rate(result.inferred_bad_rate)}</span><br>"
            f"<span style='font-size: 0.8rem; color: #666;'>{detail.modelled_swap_in_count:,} modelled swap-ins</span>",
            unsafe_allow_html=True,
        )

    # 3. NOT_MODELLED Panel (Section 6 & 10.1)
    if result.not_modelled_count > 0:
        st.markdown(
            f"""
            <div style="background-color: #f5f5f5; border-left: 5px solid #616161; padding: 12px 16px; margin: 16px 0; border-radius: 4px;">
                <div style="font-weight: 600; font-size: 1rem; color: #333;">
                    {provenance_badge(NOT_MODELLED)} Unmodelled Approvals Panel
                </div>
                <div style="font-size: 0.9rem; margin-top: 6px;">
                    <strong>{result.not_modelled_count:,} approvals ({detail.not_modelled_share:.2%} of scenario approvals)</strong>
                    fall outside the model's training support. They are counted in the approval rate but
                    <strong>strictly excluded from the blended bad-rate numerator and denominator</strong>.
                    Never impute a zero default rate to unmodelled approvals.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.divider()

    # 4. Scenario Waterfall
    st.subheader("Scenario Waterfall")
    wf = result.waterfall
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

    fig_scen_wf = go.Figure(
        go.Waterfall(
            name="Scenario Volume",
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
    fig_scen_wf.update_layout(
        title="Scenario Application Flow to Final Approvals",
        showlegend=False,
        height=450,
        margin={"l": 40, "r": 40, "t": 60, "b": 100},
        xaxis_tickangle=-35,
    )
    st.plotly_chart(fig_scen_wf, use_container_width=True)

    st.divider()

    # 5. Swap-In Breakdown (with NOT_MODELLED and THIN flag, Section 10.1)
    st.subheader("Swap-In Breakdown by Cell & Joint Support")
    st.markdown(
        "Inferred performance of newly approved applicants grouped by segmentation cell. "
        "Includes the **NOT_MODELLED** row and the joint-support count (`booked_in_cell`) with **THIN** flag."
    )

    sib = result.swap_in_breakdown
    if not sib.empty:
        disp_sib = sib.copy()
        disp_sib["count"] = disp_sib["count"].apply(format_count)
        disp_sib["inferred_bad_rate"] = disp_sib["inferred_bad_rate"].apply(format_rate)
        disp_sib["model_pd"] = disp_sib["model_pd"].apply(format_rate)
        disp_sib["share_of_swap_ins"] = disp_sib["share_of_swap_ins"].apply(lambda v: f"{v:.2%}" if pd.notna(v) else "—")
        disp_sib["booked_in_cell"] = disp_sib["booked_in_cell"].apply(format_count)
        disp_sib["thin"] = disp_sib["thin"].apply(lambda v: "⚠️ THIN" if v is True else ("—" if pd.isna(v) else "Normal"))

        cols_sib = ["segment", "count", "share_of_swap_ins", "inferred_bad_rate", "model_pd", "booked_in_cell", "thin", "provenance"]
        st.dataframe(
            disp_sib[cols_sib].rename(columns={
                "segment": "Segmentation Cell",
                "count": "Swap-Ins",
                "share_of_swap_ins": "% of Swap-Ins",
                "inferred_bad_rate": "Inferred Bad Rate [INFERRED]",
                "model_pd": "Model PD [PREDICTED]",
                "booked_in_cell": "Joint Support (Booked)",
                "thin": "Evidence Level",
                "provenance": "Provenance",
            }),
            use_container_width=True,
            hide_index=True,
        )
        export_downloads(sib, "swap_in_breakdown", key_suffix="sib")

    st.divider()

    # 6. Sensitivity Strip (Section 9.3)
    st.subheader("Sensitivity to Conservatism Penalty")
    st.caption("Re-costing portfolio performance across different conservatism penalty assumptions.")
    sens = result.sensitivity
    disp_sens = sens.copy()
    disp_sens["penalty"] = disp_sens["penalty"].apply(lambda v: f"{v:.2f}×")
    disp_sens["inferred_bad_rate"] = disp_sens["inferred_bad_rate"].apply(format_rate)
    disp_sens["blended_bad_rate"] = disp_sens["blended_bad_rate"].apply(format_rate)

    st.dataframe(
        disp_sens.rename(columns={
            "penalty": "Penalty Multiplier",
            "inferred_bad_rate": "Inferred Swap-In Rate [INFERRED]",
            "blended_bad_rate": "Portfolio Blended Bad Rate [OBSERVED+INFERRED]",
        }),
        use_container_width=True,
        hide_index=True,
    )

    # Scenario JSON download
    st.download_button(
        "📥 Download Current Scenario JSON",
        data=json.dumps(scenario_spec, indent=2),
        file_name="strategy_scenario.json",
        mime="application/json",
    )


if __name__ == "__main__":
    render_what_if_page()
