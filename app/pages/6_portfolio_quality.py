"""Portfolio Quality & Swap-Out Analysis (REQUIREMENTS.md Section 12.2 Page 6 & Section 10.3).

Purely OBSERVED analysis of the currently approved book to identify segments with excess defaults,
free bad-rate headroom by declining them, and simulate the combined swap-out / swap-in trade.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import json
import pandas as pd
import streamlit as st

from app.common import (
    export_downloads,
    format_count,
    format_rate,
    get_applications_data,
    get_baseline_strategy,
    get_trained_model,
    load_app_config,
    render_provenance_legend,
)
from src.optimise import candidate_declines, combined_trade, optimise, swap_out_analysis
from src.risk_model import INFERRED, OBSERVED
from src.strategy_io import export_strategy


def render_portfolio_quality_page():
    st.title("🔄 Portfolio Quality & Swap-Out Analysis")
    st.markdown(
        "Evaluate the currently approved portfolio using **purely OBSERVED data** (no reject inference needed). "
        "Identify high-default pockets, free bad-rate headroom, and execute the combined swap trade (Section 10.3)."
    )

    render_provenance_legend()

    cfg = load_app_config()
    df = get_applications_data()
    baseline = get_baseline_strategy(cfg)
    model = get_trained_model(df, cfg)

    # 1. Diagnostic Ranking of Currently Approved Segments
    st.subheader("Diagnostic Ranking of Approved Segments")
    st.markdown(
        "Ranking approved segments by **contribution to total bads** (descending). "
        "Contribution is what actually frees headroom; observed rate alone makes tiny segments look alarming."
    )

    diag_df = swap_out_analysis(df, baseline, cfg)
    total_booked = int(df["booked"].sum())
    total_bads = float(df.loc[df["booked"], "bad_flag"].sum())
    portfolio_rate = total_bads / total_booked if total_booked else 0.0

    # Section 10.3: Note on excluded small segments
    excl_count = diag_df.attrs.get("excluded_segments_count", 0)
    excl_share = diag_df.attrs.get("excluded_booked_share", 0.0)
    excl_booked = diag_df.attrs.get("excluded_booked_count", 0)
    total_cells = len(diag_df) + excl_count

    st.info(
        f"ℹ️ **Sample Size Threshold Filter:** "
        f"**{excl_count} of {total_cells} segments** fell below `min_segment_size` ({cfg['optimiser']['min_segment_size']:,} obs) "
        f"and were excluded from the diagnostic table. Together they cover only **{excl_booked:,} booked accounts ({excl_share:.1%} of the book)**. "
        f"This prevents ranking noise (e.g. tiny 3-customer cells at 66.7% default rate) from obscuring high-volume default pockets."
    )

    # Sorting selector: contribution descending (default) vs rate descending
    sort_option = st.radio(
        "Diagnostic Table Sorting",
        options=["Contribution to Total Defaults (Default)", "Observed Bad Rate"],
        horizontal=True,
    )

    if sort_option == "Observed Bad Rate":
        disp_diag = diag_df.sort_values(by=["observed_bad_rate", "share_of_bads"], ascending=[False, False]).reset_index(drop=True)
    else:
        disp_diag = diag_df.sort_values(by=["share_of_bads", "observed_bad_rate"], ascending=[False, False]).reset_index(drop=True)

    # Format diagnostic dataframe
    table_diag = disp_diag.copy()
    table_diag["count"] = table_diag["count"].apply(format_count)
    table_diag["bads"] = table_diag["bads"].apply(format_count)
    table_diag["observed_bad_rate"] = table_diag["observed_bad_rate"].apply(format_rate)
    table_diag["ci_str"] = table_diag.apply(lambda r: f"[{r['ci_lower']:.2%}, {r['ci_upper']:.2%}]", axis=1)
    table_diag["share_of_booked"] = table_diag["share_of_booked"].apply(lambda v: f"{v:.2%}")
    table_diag["share_of_bads"] = table_diag["share_of_bads"].apply(lambda v: f"{v:.2%}")
    table_diag["cumulative_bads_share"] = table_diag["cumulative_bads_share"].apply(lambda v: f"{v:.2%}")

    cols_diag = ["segment", "count", "bads", "observed_bad_rate", "ci_str", "share_of_booked", "share_of_bads", "cumulative_bads_share"]
    st.dataframe(
        table_diag[cols_diag].rename(columns={
            "segment": "Approved Segment",
            "count": f"Booked Accounts [{OBSERVED}]",
            "bads": f"Defaults [{OBSERVED}]",
            "observed_bad_rate": f"Observed Bad Rate [{OBSERVED}]",
            "ci_str": "95% Wilson CI",
            "share_of_booked": "% of Booked",
            "share_of_bads": "% of Total Bads",
            "cumulative_bads_share": "Cumulative Bads Share",
        }),
        use_container_width=True,
        hide_index=True,
    )
    export_downloads(diag_df, "approved_segments_diagnostic", key_suffix="diag")

    st.divider()

    # 2. Decline List (Section 10.3: excess bads, not total bads)
    st.subheader("Candidate Decline List: Statistically Significant Excess Defaults")
    st.markdown(
        f"The candidate decline list filters for segments whose **observed bad rate is above the portfolio average "
        f"({portfolio_rate:.2%}) AND whose 95% confidence lower bound is still above it**. "
        f"Ranked strictly by **excess bads** `= count × (segment rate − portfolio rate)`."
    )

    eligible_declines, portfolio_rate = candidate_declines(df, baseline, cfg)

    if not eligible_declines.empty:
        disp_decl = eligible_declines.copy()
        disp_decl["count"] = disp_decl["count"].apply(format_count)
        disp_decl["bads"] = disp_decl["bads"].apply(format_count)
        disp_decl["observed_bad_rate"] = disp_decl["observed_bad_rate"].apply(format_rate)
        disp_decl["ci_str"] = disp_decl.apply(lambda r: f"[{r['ci_lower']:.2%}, {r['ci_upper']:.2%}]", axis=1)
        disp_decl["excess_bads"] = disp_decl["excess_bads"].apply(lambda v: f"+{v:,.0f}")
        disp_decl["share_of_bads"] = disp_decl["share_of_bads"].apply(lambda v: f"{v:.2%}")

        st.dataframe(
            disp_decl[["segment", "count", "bads", "observed_bad_rate", "ci_str", "excess_bads", "share_of_bads"]].rename(columns={
                "segment": "Segment to Decline",
                "count": f"Accounts Lost [{OBSERVED}]",
                "bads": f"Defaults Removed [{OBSERVED}]",
                "observed_bad_rate": f"Segment Bad Rate [{OBSERVED}]",
                "ci_str": "95% Wilson CI",
                "excess_bads": "Excess Bads vs Portfolio",
                "share_of_bads": "Share of Portfolio Bads",
            }),
            use_container_width=True,
            hide_index=True,
        )
        export_downloads(eligible_declines, "candidate_decline_list", key_suffix="dec")
    else:
        st.info("No segments met the criteria for excess defaults above the portfolio average with 95% confidence.")

    st.divider()

    # 3. Combined Trade (Section 10.3)
    st.subheader("The Combined Trade: Swap-Outs + Swap-Ins")
    st.markdown(
        "Declining the worst N approved segments frees bad-rate headroom. Feeding that headroom back into the optimiser "
        "finds new replacement approvals below the cutoff. The trade is modeled as a real strategy evaluated by the rule engine."
    )

    c_tr1, c_tr2 = st.columns([1, 3])
    with c_tr1:
        n_worst = st.slider(
            "Number of Segments to Decline (N)",
            min_value=1,
            max_value=max(1, len(eligible_declines)),
            value=min(int(cfg["optimiser"].get("swap_out_decline_count", 3)), len(eligible_declines)),
            step=1,
            help="Number of worst excess-bad segments from the list above to decline.",
        )
        run_trade_btn = st.button("🔄 Execute Combined Trade", type="primary", use_container_width=True)

    trade_key = f"trade_res_{n_worst}"
    if run_trade_btn or trade_key in st.session_state:
        if run_trade_btn:
            with st.spinner(f"Simulating combined trade with {n_worst} excluded segments..."):
                if "base_opt_result" not in st.session_state:
                    st.session_state["base_opt_result"] = optimise(df, baseline, model, cfg)
                base_res = st.session_state["base_opt_result"]
                trade_res = combined_trade(df, baseline, model, cfg, n_worst_segments=n_worst, base_result=base_res)
                st.session_state[trade_key] = trade_res

        trade = st.session_state[trade_key]

        with c_tr2:
            st.markdown(
                f"""
                <div style="background-color: #f1f8e9; border: 1px solid #c5e1a5; border-radius: 8px; padding: 12px 16px;">
                    <div style="font-weight: 600; color: #33691e; font-size: 1rem;">Exchange Rate Summary</div>
                    <div style="font-size: 0.95rem; margin-top: 4px;">
                        • <strong>Swap-Outs Lost:</strong> {trade['approvals_lost']:,} approvals and {trade['bads_removed']:,.0f} defaults removed [{OBSERVED}]<br>
                        • <strong>Freed Headroom:</strong> Retained portfolio bad rate drops to <strong>{trade['retained_observed_bad_rate']:.2%}</strong> [{OBSERVED}]<br>
                        • <strong>Swap-Ins Gained:</strong> {trade['approvals_gained']:,} new approvals across {len(trade['strategy'].overrides)} segments<br>
                        • <strong>Net Portfolio Bad Rate:</strong> <strong>{trade['net_blended_bad_rate']:.2%}</strong> [{OBSERVED}+{INFERRED}]
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.write("")

        # Display the segments actually declined/excluded by the trade
        st.markdown(f"**Actually Excluded Segments ({trade['n_worst_segments_declined']}):**")
        decl_df = pd.DataFrame(trade["declined_segments"])
        if not decl_df.empty:
            disp_actual = decl_df.copy()
            disp_actual["count"] = disp_actual["count"].apply(format_count)
            disp_actual["bads"] = disp_actual["bads"].apply(format_count)
            disp_actual["observed_bad_rate"] = disp_actual["observed_bad_rate"].apply(format_rate)
            disp_actual["ci_str"] = disp_actual.apply(lambda r: f"[{r['ci_lower']:.2%}, {r['ci_upper']:.2%}]", axis=1)
            disp_actual["excess_bads"] = disp_actual["excess_bads"].apply(lambda v: f"+{v:,.0f}")
            disp_actual["share_of_bads"] = disp_actual["share_of_bads"].apply(lambda v: f"{v:.2%}")

            st.dataframe(
                disp_actual[["segment", "count", "bads", "observed_bad_rate", "ci_str", "excess_bads", "share_of_bads"]].rename(columns={
                    "segment": "Excluded Segment",
                    "count": f"Accounts Lost [{OBSERVED}]",
                    "bads": f"Defaults Removed [{OBSERVED}]",
                    "observed_bad_rate": f"Observed Rate [{OBSERVED}]",
                    "ci_str": "95% Wilson CI",
                    "excess_bads": "Excess Defaults",
                    "share_of_bads": "Share of Portfolio Defaults",
                }),
                use_container_width=True,
                hide_index=True,
            )

        # Section 10.3 & 12.2 Page 6: Say what stopped each side of the comparison
        base_bc = trade["base_binding_constraint"]
        trade_bc = trade["binding_constraint"]
        differs = trade["constraints_differ"]

        col_bc1, col_bc2, col_bc3 = st.columns(3)
        with col_bc1:
            st.metric("Base Optimiser Constraint", f"{base_bc}")
        with col_bc2:
            st.metric("Trade Optimiser Constraint", f"{trade_bc}")
        with col_bc3:
            if differs:
                st.warning("⚠️ Constraints differ: Delta withheld")
            else:
                st.success("✅ Constraints match: Like-for-like comparison")

        if differs:
            st.warning(
                f"⚠️ **Comparison Not Like-for-Like (Section 10.3):**\n\n"
                f"The baseline optimiser stopped on **`{base_bc}`** while the trade stopped on **`{trade_bc}`**. "
                f"Reporting a net approval delta charges the trade for an arbitrary limit it may not have reached. "
                f"Net approvals are **{trade['net_approval_count']:,} ({trade['net_approval_rate']:.2%})**; "
                f"the delta is withheld to prevent quoting a non-comparable figure in meetings."
            )
        else:
            st.markdown(
                f"### Net Approval Outcome: **{trade['net_approval_count']:,} ({trade['net_approval_rate']:.2%})** "
                f"[{trade['net_approval_delta']:+,} net change vs baseline]"
            )

        # Section 10.3: Expect trade to come out negative notice
        st.info(
            "📌 **Why does the trade lose net volume on this data? (Section 10.3):**\n\n"
            "The segments worth declining sit at 700+ bureau score and are very large. Their replacements sit below the cutoff "
            "and are smaller, so swapping them one-for-one loses volume even when it improves portfolio quality. "
            "That is the honest answer to *'should I do this?'* — what makes this page valuable is seeing the real exchange rate."
        )

        # Export Trade Strategy Button
        exported_trade_json = export_strategy(
            trade["strategy"],
            trade["headline"],
            cfg["constraints"],
        )
        st.download_button(
            "📥 Export Combined Trade Strategy (JSON)",
            data=json.dumps(exported_trade_json, indent=2),
            file_name=f"trade_strategy_{exported_trade_json['strategy_id'][:8]}.json",
            mime="application/json",
            type="primary",
        )


if __name__ == "__main__":
    render_portfolio_quality_page()
