"""Optimiser (REQUIREMENTS.md Section 12.2 Page 5 & Section 11 Phase 4).

Greedy strategy optimiser finding the highest-volume segment overrides subject to
the blended portfolio bad-rate constraint.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import copy
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
from src.optimise import optimise
from src.risk_model import INFERRED, OBSERVED
from src.strategy_io import export_strategy


def render_optimiser_page():
    st.title("⚡ Credit Strategy Optimiser")
    st.markdown(
        "Greedy, explainable optimiser finding segment overrides that maximise approval volume "
        "subject to a blended portfolio bad-rate constraint (Section 10.2)."
    )

    render_provenance_legend()

    cfg = load_app_config()
    df = get_applications_data()
    model = get_trained_model(df, cfg)
    baseline = get_baseline_strategy(cfg)

    # 1. Inputs & Run Controls
    st.subheader("Optimisation Constraints & Controls")

    c_in1, c_in2, c_in3, c_in4 = st.columns([1.5, 1, 1, 1])
    with c_in1:
        default_thresh = float(cfg["constraints"][0]["threshold"])
        max_bad_rate = st.number_input(
            "Max Blended Bad Rate Constraint",
            min_value=0.010,
            max_value=0.080,
            value=default_thresh,
            step=0.001,
            format="%.4f",
            help="Maximum acceptable portfolio blended bad rate (default 3.50%).",
        )
    with c_in2:
        max_segments = st.number_input(
            "Max Segments Added",
            min_value=1,
            max_value=30,
            value=int(cfg["optimiser"]["max_segments_added"]),
            step=1,
            help="Cap on added segment overrides for explainability and operational simplicity.",
        )
    with c_in3:
        min_size = st.number_input(
            "Min Segment Size",
            min_value=100,
            max_value=5000,
            value=int(cfg["optimiser"]["min_segment_size"]),
            step=100,
            help="Ignore micro-segments below this application volume.",
        )
    with c_in4:
        st.write("")
        st.write("")
        run_btn = st.button("🚀 Run Optimiser", type="primary", use_container_width=True)

    # Run / Cache execution in session state
    cache_key = f"opt_res_{max_bad_rate}_{max_segments}_{min_size}"

    if run_btn or cache_key in st.session_state:
        if run_btn:
            # Build custom config copy
            cfg_run = copy.deepcopy(cfg)
            for c in cfg_run["constraints"]:
                if c["metric"] == "blended_bad_rate":
                    c["threshold"] = max_bad_rate
            cfg_run["optimiser"]["max_segments_added"] = int(max_segments)
            cfg_run["optimiser"]["min_segment_size"] = int(min_size)

            with st.spinner("Running greedy optimiser on 1,000,000 applications..."):
                opt_res = optimise(df, baseline, model, cfg_run)
                st.session_state[cache_key] = (opt_res, cfg_run)

        opt_res, cfg_used = st.session_state[cache_key]
        h = opt_res.headline

        # Read thin share metrics directly from opt_res (Section 12.1 Ground Rule)
        thin_share_eval = opt_res.thin_share
        thin_share_tot = opt_res.thin_share_of_total

        st.divider()

        # 2. Headline KPIs (Above the fold, Section 11 Phase 4)
        st.subheader("Optimiser Recommendation Headline")

        col_h1, col_h2, col_h3, col_h4 = st.columns(4)
        with col_h1:
            st.metric(
                "Proposed Approval Rate",
                f"{h.approval_rate:.2%}",
                f"+{h.swap_in_count:,} incremental approvals",
            )
            st.caption(f"{h.approval_count:,} total proposed approvals")

        with col_h2:
            limit_diff = max_bad_rate - h.blended_bad_rate
            st.markdown(
                f"<div>"
                f"<div style='font-size: 0.875rem; color: #666;'>Blended Bad Rate {provenance_badge(f'{OBSERVED}+{INFERRED}')}</div>"
                f"<div style='font-size: 1.8rem; font-weight: 600;'>{format_rate(h.blended_bad_rate)}</div>"
                f"<div style='font-size: 0.8rem; color: {'#2e7d32' if limit_diff >= 0 else '#c62828'};'>"
                f"{limit_diff:+.2%} headroom vs {max_bad_rate:.2%} cap</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

        with col_h3:
            # THIN share beside headline with denominator breakdown
            st.markdown(
                f"<div>"
                f"<div style='font-size: 0.875rem; color: #666;'>THIN Cell Share (Section 9.2)</div>"
                f"<div style='font-size: 1.8rem; font-weight: 600; color: #e65100;'>{thin_share_eval:.1%}</div>"
                f"<div style='font-size: 0.8rem; color: #666;'>"
                f"{thin_share_eval:.1%} of evaluated ({thin_share_tot:.1%} of headline)</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

        with col_h4:
            # Binding constraint beside headline
            bc = opt_res.binding_constraint
            bc_label = (
                "🛑 Appetite-Bound (Bad Rate)" if bc == "bad_rate"
                else ("📦 Slot-Bound (Max Segments)" if bc == "max_segments_added"
                else "🟢 Unconstrained")
            )
            bc_color = "#c62828" if bc == "bad_rate" else ("#f57c00" if bc == "max_segments_added" else "#2e7d32")
            st.markdown(
                f"<div>"
                f"<div style='font-size: 0.875rem; color: #666;'>Binding Constraint</div>"
                f"<div style='font-size: 1.3rem; font-weight: 700; color: {bc_color}; margin-top: 5px;'>{bc_label}</div>"
                f"<div style='font-size: 0.8rem; color: #666;'>Reason greedy search stopped</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

        # Health Warning on THIN cells
        st.warning(
            f"⚠️ **Evidence Health Warning (Section 9.2):** "
            f"**{thin_share_eval:.1%} of evaluated incremental approvals** ({thin_share_tot:.1%} of headline approvals) "
            f"are drawn from cells with fewer than {cfg['model']['min_cell_obs']} booked observations in history. "
            f"Ascending-risk greedy ordering preferentially targets cells with sparse data. "
            f"This is not a footnote — it is the honest risk of this recommendation."
        )

        st.divider()

        # 3. Candidate Funnel (Section 10.2 & 12.2 Page 5)
        st.subheader("Candidate Population Funnel")
        st.caption(
            "Showing the funnel from all historical declines down to the viable candidate pool. "
            "Ten segments out of a starting pool the reader cannot see is a number without a denominator."
        )

        funnel = opt_res.candidate_funnel
        if funnel is not None:
            funnel_stages = [
                "Total Historical Declines",
                "Failed ONLY Relaxable (R5/R6)",
                "Inside Training Support (Have PD)",
                "In Viable Segments (≥ min size)",
                "Approved by Recommendation",
            ]
            funnel_values = [
                funnel.total_declines,
                funnel.failed_only_relaxable,
                funnel.inside_support,
                funnel.in_viable_segments,
                h.swap_in_count,
            ]

            fig_funnel = go.Figure(
                go.Funnel(
                    y=funnel_stages,
                    x=funnel_values,
                    textinfo="value+percent initial+percent previous",
                    opacity=0.85,
                    marker={"color": ["#455a64", "#1976d2", "#0288d1", "#0097a7", "#2e7d32"]},
                )
            )
            fig_funnel.update_layout(height=350, margin=dict(l=20, r=20, t=20, b=20))
            st.plotly_chart(fig_funnel, use_container_width=True)

        st.divider()

        # 4. Added-Segments Rules Table (Reconciles to Headline)
        st.subheader(f"Added Segment Overrides ({len(opt_res.added_segments)} rows)")
        st.markdown(
            "Recommended override rules sorted by ascending inferred bad rate. "
            "**Notice:** The total of the Count column **visibly reconciles** to the headline incremental approvals "
            f"(`{h.swap_in_count:,}`), including the `NOT_MODELLED` row."
        )

        added_df = opt_res.added_segments.copy()
        sum_counts = int(added_df["count"].sum())

        # Verification badge
        if sum_counts == h.swap_in_count:
            st.success(f"✅ Table counts ({sum_counts:,}) exactly sum to headline incremental approvals ({h.swap_in_count:,}).")
        else:
            st.error(f"❌ Table count mismatch: table sums to {sum_counts:,}, headline is {h.swap_in_count:,}!")

        disp_added = added_df.copy()
        disp_added["count"] = disp_added["count"].apply(format_count)
        disp_added["inferred_bad_rate"] = disp_added["inferred_bad_rate"].apply(format_rate)
        disp_added["cumulative_bad_rate"] = disp_added["cumulative_bad_rate"].apply(format_rate)
        disp_added["booked_in_cell"] = disp_added["booked_in_cell"].apply(format_count)
        disp_added["thin"] = disp_added["thin"].apply(lambda v: "⚠️ THIN" if v is True else ("—" if pd.isna(v) else "Normal"))

        st.dataframe(
            disp_added[["rule_description", "count", "inferred_bad_rate", "cumulative_bad_rate", "booked_in_cell", "thin"]].rename(columns={
                "rule_description": "Segment Override Rule",
                "count": "Incremental Approvals",
                "inferred_bad_rate": "Inferred Bad Rate [INFERRED]",
                "cumulative_bad_rate": "Cumulative Portfolio Bad Rate",
                "booked_in_cell": "Joint Support (Booked)",
                "thin": "Evidence Level",
            }),
            use_container_width=True,
            hide_index=True,
        )
        export_downloads(opt_res.added_segments, "optimiser_added_segments", key_suffix="add")

        st.divider()

        # 5. Rejected Segments Table
        st.subheader(f"Rejected Candidate Segments ({len(opt_res.rejected_segments)} evaluated)")
        st.caption("Segments evaluated by the greedy search but skipped, showing why appetite or rule slots ran out.")

        if not opt_res.rejected_segments.empty:
            disp_rej = opt_res.rejected_segments.copy()
            disp_rej["count"] = disp_rej["count"].apply(format_count)
            disp_rej["inferred_bad_rate"] = disp_rej["inferred_bad_rate"].apply(format_rate)

            st.dataframe(
                disp_rej[["rule_description", "count", "inferred_bad_rate", "reason"]].rename(columns={
                    "rule_description": "Candidate Segment",
                    "count": "Candidate Volume",
                    "inferred_bad_rate": "Inferred Bad Rate [INFERRED]",
                    "reason": "Rejection Reason",
                }),
                use_container_width=True,
                hide_index=True,
            )
            export_downloads(opt_res.rejected_segments, "optimiser_rejected_segments", key_suffix="rej")
        else:
            st.info("No candidate segments were rejected.")

        st.divider()

        # 6. Naive Comparison (Section 10.2.3)
        st.subheader("Naive Comparison: Targeted Segments vs Uniform Score Cutoff")
        st.markdown(
            "Comparing the targeted segment strategy against the lowest uniform score cutoff (all other rules unchanged) "
            "that satisfies the same bad-rate constraint on the exact same inferred basis."
        )

        n_res = opt_res.naive_result
        base_cutoff = next((r.params["cutoff"] for r in baseline.rules if r.id == "R5_SCORE"), 700)
        col_nc1, col_nc2, col_nc3 = st.columns(3)
        with col_nc1:
            st.metric(
                "Naive Score Cutoff",
                f"{opt_res.naive_cutoff:.0f}",
                f"{opt_res.naive_cutoff - base_cutoff:+.0f} pts vs baseline ({base_cutoff:.0f})",
            )
        with col_nc2:
            st.metric(
                "Naive Approval Rate",
                f"{n_res.approval_rate:.2%}",
                f"{n_res.approval_count:,} approvals (+{n_res.swap_in_count:,} swap-ins)",
            )
        with col_nc3:
            st.metric(
                "Naive Blended Bad Rate",
                format_rate(n_res.blended_bad_rate),
                f"Constraint: ≤ {max_bad_rate:.2%}",
            )

        app_advantage = h.approval_count - n_res.approval_count
        if app_advantage >= 0:
            st.success(
                f"🎯 **Targeted strategy wins**: Delivers **+{app_advantage:,} more approvals** "
                f"({h.approval_rate - n_res.approval_rate:+.2%} approval rate advantage) "
                f"than the naive score cutoff at the same {max_bad_rate:.2%} bad-rate budget."
            )
        else:
            st.warning(
                f"Naive score cutoff achieved {abs(app_advantage):,} more approvals than targeted strategy."
            )

        st.divider()

        # 7. Sensitivity Strip & Breakeven Penalty (Section 9.3)
        st.subheader("Fragility & Conservatism Sensitivity")
        col_s1, col_s2 = st.columns([1, 2])
        with col_s1:
            bk_pen = opt_res.breakeven_penalty
            def_pen = cfg["model"]["inference_penalty"]
            fragile = bk_pen <= (def_pen + 0.10)
            st.metric(
                "Breakeven Penalty",
                f"{bk_pen:.3f}×",
                f"Default: {def_pen:.2f}× ({'⚠️ FRAGILE' if fragile else 'Robust'})",
                delta_color="inverse" if fragile else "normal",
            )
            st.caption(
                "The penalty multiplier at which the recommended strategy first breaches the bad-rate limit. "
                "If close to the default (1.25×), the recommendation is fragile to model extrapolation error."
            )

        with col_s2:
            sens_df = h.sensitivity.copy()
            sens_df["penalty"] = sens_df["penalty"].apply(lambda v: f"{v:.2f}×")
            sens_df["inferred_bad_rate"] = sens_df["inferred_bad_rate"].apply(format_rate)
            sens_df["blended_bad_rate"] = sens_df["blended_bad_rate"].apply(format_rate)
            st.dataframe(
                sens_df.rename(columns={
                    "penalty": "Penalty Multiplier",
                    "inferred_bad_rate": "Inferred Swap-Ins [INFERRED]",
                    "blended_bad_rate": "Portfolio Blended Bad Rate [OBSERVED+INFERRED]",
                }),
                use_container_width=True,
                hide_index=True,
            )

        st.divider()

        # 8. Export Strategy & Action Buttons (Section 10.5)
        st.subheader("Strategy Export & Deployment")
        st.markdown(
            "Export the recommended strategy as a versioned JSON contract object per Section 10.5, "
            "or load it into the What-if Simulator for interactive testing."
        )

        col_act1, col_act2 = st.columns(2)
        with col_act1:
            exported_json = export_strategy(
                opt_res.strategy,
                opt_res.headline,
                cfg_used["constraints"],
            )
            st.download_button(
                "📥 Export Recommended Strategy (JSON)",
                data=json.dumps(exported_json, indent=2),
                file_name=f"recommended_strategy_{exported_json['strategy_id'][:8]}.json",
                mime="application/json",
                type="primary",
            )

        with col_act2:
            if st.button("🎛️ Load Strategy into What-if Simulator"):
                # Prepare spec for simulator
                st.session_state["pending_whatif_spec"] = {
                    "overrides": [
                        {"conditions": ov.conditions, "relaxes": list(ov.relaxes)}
                        for ov in opt_res.strategy.overrides
                    ],
                    "inference_penalty": cfg_used["model"]["inference_penalty"],
                }
                st.success("Loaded strategy into What-if Simulator! Navigate to the simulator page to inspect.")

    else:
        st.info("👈 Set your constraints above and click **Run Optimiser** to find the optimal strategy.")


if __name__ == "__main__":
    render_optimiser_page()
