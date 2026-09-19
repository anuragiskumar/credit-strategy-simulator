"""Overview page (REQUIREMENTS.md Section 12.2 Page 1).

Displays population size, baseline approval rate, observed bad rate, reproduction match rate,
manual override accounting, performance-window assumption, and data provenance guide.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from app.common import (
    export_downloads,
    format_count,
    format_rate,
    get_applications_data,
    get_baseline_strategy,
    load_app_config,
    provenance_badge,
    render_provenance_legend,
)
from src.risk_model import OBSERVED
from src.rules import reproduction_report


def render_overview_page():
    st.title("📊 Portfolio Overview & Strategy Reproduction")
    st.markdown(
        "Baseline strategy performance, historical override accounting, and strategy reproduction validation."
    )

    render_provenance_legend()

    cfg = load_app_config()
    df = get_applications_data()
    baseline = get_baseline_strategy(cfg)

    # Historical metrics computed directly from data
    n_total = len(df)
    n_booked = int(df["booked"].sum())
    approval_rate = n_booked / n_total if n_total else 0.0
    bads_booked = float(df.loc[df["booked"], "bad_flag"].sum())
    observed_bad_rate = bads_booked / n_booked if n_booked else 0.0

    # Section 12.2 Page 1: Headline KPIs
    st.subheader("Historical Portfolio KPIs")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Applications", format_count(n_total))
    with col2:
        st.metric("Booked Approvals", format_count(n_booked), f"{approval_rate:.2%} approval rate")
    with col3:
        st.markdown(
            f"<div>"
            f"<div style='font-size: 0.875rem; color: #666;'>Observed Bad Rate {provenance_badge(OBSERVED)}</div>"
            f"<div style='font-size: 1.8rem; font-weight: 600;'>{format_rate(observed_bad_rate)}</div>"
            f"<div style='font-size: 0.8rem; color: #666;'>{format_count(bads_booked)} defaults / {format_count(n_booked)} booked</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    with col4:
        st.metric("Strategy Rules", f"{len(baseline.rules)} rules", "2 mandatory, 4 relaxable")

    st.divider()

    # Section 7.3 & 12.2: Strategy Reproduction Check
    st.subheader("Strategy Reproduction & Historical Override Analysis")
    st.markdown(
        "Re-evaluating the written baseline strategy against historical decisions. "
        "A healthy originations pipeline must match history for **100% of non-override applications**."
    )

    rep = reproduction_report(df, baseline)
    raw_rate = rep["raw_match_rate"]
    excl_rate = rep["match_rate_excl_overrides"]
    n_mismatches = rep["n_mismatches"]
    n_non_ov = rep["n_mismatches_not_override"]
    n_overrides = rep["n_manual_overrides"]
    d2a = rep["n_override_decline_to_approve"]
    a2d = rep["n_override_approve_to_decline"]

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Raw Reproduction Match", f"{raw_rate:.2%}", f"{n_mismatches:,} total mismatches")
    with c2:
        if excl_rate < 1.0 or n_non_ov > 0:
            st.markdown(
                f"<div style='background-color: #ffebee; border: 2px solid #c62828; border-radius: 8px; padding: 10px;'>"
                f"<div style='font-size: 0.85rem; color: #c62828; font-weight: 600;'>Excluding Manual Overrides</div>"
                f"<div style='font-size: 1.8rem; font-weight: 700; color: #c62828;'>{excl_rate:.4%}</div>"
                f"<div style='font-size: 0.8rem; color: #c62828;'>FAILED: {n_non_ov:,} non-override mismatches</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
            st.error(
                f"🚨 **Reproduction Error**: Rule engine does not match historical decisions for non-override rows! "
                f"Found {n_non_ov} unexplained mismatches. The rule engine must reproduce history at exactly 100%."
            )
        else:
            st.metric(
                "Match Excl. Overrides",
                "100.00%",
                "0 unexplained mismatches",
                delta_color="normal",
            )
    with c3:
        st.metric(
            "Manual Overrides",
            format_count(n_overrides),
            f"{n_overrides / n_total:.2%} of applications",
        )

    st.markdown(
        f"""
        **Override Breakdown:**
        - **Decline → Approve (Marginal approvals):** `{d2a:,}` applicants ({d2a / n_overrides:.1%} of overrides).
          Drawn predominantly from score 650–699 and FOIR 0.50–0.60, providing observed performance below cutoff.
        - **Approve → Decline (Exclusions):** `{a2d:,}` applicants ({a2d / n_overrides:.1%} of overrides).
          Historical policy exceptions or manual reviewer declines.
        """
    )

    # Mismatch Table
    if n_mismatches > 0:
        with st.expander(f"View Sample Reproduction Mismatches ({min(100, n_mismatches)} of {n_mismatches:,})", expanded=False):
            mism_df = rep["mismatches"].head(100)
            st.dataframe(
                mism_df,
                use_container_width=True,
                hide_index=True,
            )
            export_downloads(rep["mismatches"], "reproduction_mismatches")

    st.divider()

    # Section 5.1 & 12.2: Performance-Window Assumption & Provenance Note
    st.subheader("Key Modeling Assumptions & Data Governance")

    st.info(
        "📌 **Performance-Window Assumption (Section 5.1):**\n\n"
        "Every booked application is treated as **fully seasoned** — 12 months of performance is assumed available "
        "for all of them, including the most recent cohort. Real data would require vintage-based censoring "
        "and time-to-event survival modeling."
    )

    st.warning(
        "⚠️ **Reject Inference & Selection Bias Notice:**\n\n"
        "Approved applicants who received loans were selected by the historical strategy. Declines who are newly approved "
        "under what-if simulations or optimisations do not have observed performance. Their risk is **INFERRED** from the "
        "risk model and adjusted with a conservatism penalty (default 1.25×). Manual overrides just below the cutoff provide "
        "the only empirical anchor, but reflect human selection."
    )


if __name__ == "__main__":
    render_overview_page()
