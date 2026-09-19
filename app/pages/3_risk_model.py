"""Risk Model & Training Support (REQUIREMENTS.md Section 12.2 Page 3).

Displays holdout AUC, calibration chart, coefficients, marginal & joint support ranges,
edge-case support diagnostics (out-of-range in supported bin, dropped categorical levels),
and the near-cutoff empirical anchor (Section 9.4).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.common import (
    export_downloads,
    format_count,
    format_rate,
    get_applications_data,
    get_trained_model,
    load_app_config,
    provenance_badge,
    render_provenance_legend,
)
from src.risk_model import OBSERVED, PREDICTED, near_cutoff_anchor


def render_risk_model_page():
    st.title("🎯 Risk Model & Training Support")
    st.markdown(
        "Logistic regression probability of default (PD) model trained strictly on booked customers, "
        "with explicit marginal and joint support boundaries."
    )

    render_provenance_legend()

    cfg = load_app_config()
    df = get_applications_data()
    model = get_trained_model(df, cfg)

    # 1. Headline Model Performance
    st.subheader("Holdout Model Performance")
    auc = model.metrics["auc"]
    min_auc = cfg["model"]["min_auc"]
    n_train = model.metrics["n_train"]
    n_test = model.metrics["n_test"]
    test_br = model.metrics["test_bad_rate"]

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        auc_delta = auc - min_auc
        st.metric(
            "Holdout AUC",
            f"{auc:.4f}",
            f"{auc_delta:+.4f} vs floor ({min_auc:.2f})",
            delta_color="normal" if auc >= min_auc else "inverse",
        )
    with c2:
        st.metric("Holdout Bad Rate", format_rate(test_br), f"{n_test:,} holdout accounts")
    with c3:
        st.metric("Training Sample", format_count(n_train), f"{model.n_train_rows:,} total supported booked")
    with c4:
        st.metric("Support Deciles Source", "Full Population", "Deciles from 1M apps")

    st.divider()

    # 2. Calibration Chart & Coefficients
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Holdout Calibration by Decile")
        cal = model.metrics["calibration"]
        fig_cal = go.Figure()
        fig_cal.add_trace(
            go.Bar(
                x=cal["decile"],
                y=cal["observed_bad_rate"],
                name=f"Observed Bad Rate {provenance_badge(OBSERVED)}",
                marker_color="#2e7d32",
                opacity=0.75,
            )
        )
        fig_cal.add_trace(
            go.Scatter(
                x=cal["decile"],
                y=cal["mean_predicted"],
                name=f"Predicted PD {provenance_badge(PREDICTED)}",
                mode="lines+markers",
                line=dict(color="#1565c0", width=3),
                marker=dict(size=8),
            )
        )
        fig_cal.update_layout(
            title="Predicted PD vs Observed Bad Rate by Decile",
            xaxis_title="Decile of Predicted PD",
            yaxis_title="Rate",
            yaxis_tickformat=".1%",
            height=380,
            margin=dict(l=20, r=20, t=50, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig_cal, use_container_width=True)

        with st.expander("View Calibration Data Table", expanded=False):
            disp_cal = cal.copy()
            disp_cal["mean_predicted"] = disp_cal["mean_predicted"].apply(format_rate)
            disp_cal["observed_bad_rate"] = disp_cal["observed_bad_rate"].apply(format_rate)
            disp_cal["ratio_obs_to_pred"] = disp_cal["ratio_obs_to_pred"].apply(lambda v: f"{v:.3f}")
            disp_cal["n"] = disp_cal["n"].apply(format_count)
            disp_cal["bads"] = disp_cal["bads"].apply(format_count)
            st.dataframe(
                disp_cal.rename(columns={
                    "decile": "Decile",
                    "n": "Observations",
                    "mean_predicted": "Mean Predicted PD [PREDICTED]",
                    "observed_bad_rate": "Observed Bad Rate [OBSERVED]",
                    "bads": "Defaults",
                    "ratio_obs_to_pred": "Obs / Pred Ratio",
                }),
                use_container_width=True,
                hide_index=True,
            )
            export_downloads(cal, "model_calibration", key_suffix="cal")

    with col2:
        st.subheader("Model Coefficients (Raw Units)")
        coefs = model.coefficients()
        disp_coefs = coefs.copy()
        disp_coefs["coefficient"] = disp_coefs["coefficient"].apply(lambda v: f"{v:+.4f}")
        disp_coefs["odds_ratio"] = disp_coefs["odds_ratio"].apply(lambda v: f"{v:.4f}" if pd.notna(v) else "—")
        disp_coefs["std_coefficient"] = disp_coefs["std_coefficient"].apply(lambda v: f"{v:+.4f}" if pd.notna(v) else "—")
        st.dataframe(
            disp_coefs.rename(columns={
                "term": "Feature Term",
                "kind": "Type",
                "coefficient": "Coefficient (Raw)",
                "odds_ratio": "Odds Ratio",
                "std_coefficient": "Std Coef (Numerics)",
                "reference": "Reference Level",
            }),
            height=380,
            use_container_width=True,
            hide_index=True,
        )
        export_downloads(coefs, "model_coefficients", key_suffix="coef")

    st.divider()

    # 3. Marginal Support & Diagnostics
    st.subheader("Marginal Training Support & Range Diagnostics")
    st.markdown(
        "The model is entitled to speak only within its training support. An applicant is marked **NOT_MODELLED** "
        "if any feature value falls in an unsupported bin or outside the booked min–max range."
    )

    ranges = model.support_ranges()
    summary = model.support_summary()

    # Section 12.2 Page 3 requirement: 3 specific items that are easy to leave out
    # 1) Count of applicants sitting in a supported bin but outside the booked min-max
    supported_bins = summary[(summary["kind"] == "bin") & (summary["supported"])].copy()
    supported_bins["outside_booked_range"] = supported_bins["applications"] - supported_bins["applications_in_booked_range"]
    total_in_bin_outside_range = int(supported_bins["outside_booked_range"].sum())

    # 2) Dropped categorical levels
    dropped_levels = model.dropped_levels_

    col_diag1, col_diag2 = st.columns(2)
    with col_diag1:
        st.markdown(
            f"""
            <div style="background-color: #fff3e0; border: 1px solid #ffe082; border-radius: 8px; padding: 14px 18px; margin-bottom: 12px;">
                <div style="font-weight: 600; color: #e65100; font-size: 1rem;">
                    ⚠️ Supported Bin but Outside Booked Min–Max (Section 9.2)
                </div>
                <div style="font-size: 1.6rem; font-weight: 700; color: #e65100; margin: 4px 0;">
                    {total_in_bin_outside_range:,} applicants
                </div>
                <div style="font-size: 0.85rem; color: #5d4037;">
                    These applicants sit inside decile bins that have ≥ 200 booked rows, but their exact values
                    exceed the booked min–max seen during training (e.g. enquiries_6m > 6).
                    The min–max clause prevents linear extrapolation beyond training data.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_diag2:
        if dropped_levels:
            dropped_desc = ", ".join(f"<code>{d['feature']}={d['level']}</code> ({d['applications']:,} apps, {d['booked_obs']} booked)" for d in dropped_levels)
            st.markdown(
                f"""
                <div style="background-color: #fbe9e7; border: 1px solid #ffccbc; border-radius: 8px; padding: 14px 18px; margin-bottom: 12px;">
                    <div style="font-weight: 600; color: #d84315; font-size: 1rem;">
                        🚫 Categorical Levels Dropped (Section 9.1)
                    </div>
                    <div style="font-size: 1.6rem; font-weight: 700; color: #d84315; margin: 4px 0;">
                        {len(dropped_levels)} dropped levels
                    </div>
                    <div style="font-size: 0.85rem; color: #4e342e;">
                        Dropped for fewer than {cfg['model']['min_level_obs']} booked observations: {dropped_desc}.
                        These applicants are classified as <strong>NOT_MODELLED</strong> instead of receiving a zero coefficient.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.info("No categorical levels were dropped.")

    # Display Support Ranges Table
    st.markdown("**Supported Feature Spans & Population Coverage:**")
    disp_ranges = ranges.copy()
    disp_ranges["share_outside"] = disp_ranges["share_outside"].apply(lambda v: f"{v:.2%}")
    for c in ["booked_obs_inside", "applications_inside", "applications_outside"]:
        disp_ranges[c] = disp_ranges[c].apply(format_count)

    st.dataframe(
        disp_ranges.rename(columns={
            "feature": "Feature",
            "kind": "Type",
            "supported": "Supported Range / Levels",
            "bins_supported": "Supported Bins",
            "booked_min": "Booked Min",
            "booked_max": "Booked Max",
            "booked_obs_inside": "Booked Obs Inside",
            "applications_inside": "Apps Inside Support",
            "applications_outside": "Apps Outside (NOT_MODELLED)",
            "share_outside": "% Outside Support",
        }),
        use_container_width=True,
        hide_index=True,
    )
    export_downloads(ranges, "support_ranges", key_suffix="rng")

    st.divider()

    # 4. Near-Cutoff Inference Anchor (Section 9.4)
    st.subheader("⚓ Near-Cutoff Inference Anchor (Section 9.4)")
    st.markdown(
        "Override-approved applicants (bureau score 650–699, FOIR 0.50–0.60) provide real observed performance "
        "just below the cutoff. Comparing within matched segmentation cells demonstrates the selection effect, "
        "while comparing by score band alone reveals the confounding FOIR mix effect."
    )

    anchor = near_cutoff_anchor(df, model, cfg)
    cells_df = anchor["cells"]
    vw = anchor["volume_weighted"]
    nt = anchor["naive_total"]
    conflict = anchor["direction_conflict"]

    # Warnings & Interpretations
    for w in anchor["warnings"]:
        st.warning(f"⚠️ {w}")

    st.info(
        "**What the implied penalty ratio is NOT (Section 9.4):**\n\n"
        "The ratio `= observed ÷ mean model PD` conflates two effects that cannot be separated without an oracle:\n"
        "1. **Selection effect:** Overrides were human-picked and should outperform their cell.\n"
        "2. **Model calibration error on declines:** The model may simply be conservative in that band.\n\n"
        "A ratio below 1 is evidence of one or the other, **not proof of human selection**.\n"
        "Furthermore, override approvals were human-selected and are therefore favorably biased: "
        "the observed rate is a lower bound on the cell's true rate, making the implied penalty "
        "a **lower bound** on the penalty you should use."
    )

    # Comparison summary: Matched Cells vs Naive Score Band
    c_m1, c_m2, c_m3 = st.columns(3)
    with c_m1:
        st.metric(
            "Volume-Weighted Implied Penalty",
            f"{vw['implied_penalty']:.3f}",
            f"Observed {vw['observed_bad_rate']:.2%} vs Mean PD {vw['mean_model_pd']:.2%}",
        )
    with c_m2:
        st.metric(
            "Naive Score-Band Penalty",
            f"{nt['implied_penalty']:.3f}",
            f"Observed {nt['observed_bad_rate']:.2%} vs Mean PD {nt['mean_model_pd']:.2%}",
        )
    with c_m3:
        penalty_diff = vw['implied_penalty'] - nt['implied_penalty']
        st.metric(
            "Mix Effect Gap",
            f"{penalty_diff:+.3f}",
            "FOIR mix effect reverses sign" if conflict else "Sign matches",
            delta_color="inverse" if conflict else "normal",
        )

    # Adoption button
    if st.button(f"Adopt Implied Penalty ({vw['implied_penalty']:.3f}) for What-if Simulator"):
        st.session_state["adopted_penalty"] = float(round(vw["implied_penalty"], 3))
        st.success(f"Adopted conservatism penalty {vw['implied_penalty']:.3f} into session state!")

    # Matched cells table
    st.markdown("**Matched Segmentation Cells (≥ 200 Overrides):**")
    if not cells_df.empty:
        disp_cells = cells_df.copy()
        disp_cells["observed_bad_rate"] = disp_cells["observed_bad_rate"].apply(format_rate)
        disp_cells["ci_str"] = disp_cells.apply(lambda r: f"[{r['ci_lower']:.2%}, {r['ci_upper']:.2%}]", axis=1)
        disp_cells["mean_model_pd"] = disp_cells["mean_model_pd"].apply(format_rate)
        disp_cells["implied_penalty"] = disp_cells["implied_penalty"].apply(lambda v: f"{v:.3f}")
        for c in ["override_count", "declines_count"]:
            disp_cells[c] = disp_cells[c].apply(format_count)

        cols_to_show = ["cell", "override_count", "observed_bad_rate", "ci_str", "declines_count", "mean_model_pd", "implied_penalty"]
        st.dataframe(
            disp_cells[cols_to_show].rename(columns={
                "cell": "Segmentation Cell",
                "override_count": "Overrides [OBSERVED]",
                "observed_bad_rate": "Observed Bad Rate [OBSERVED]",
                "ci_str": "95% Wilson CI",
                "declines_count": "Declines in Cell",
                "mean_model_pd": "Declines Mean PD [PREDICTED]",
                "implied_penalty": "Implied Penalty",
            }),
            use_container_width=True,
            hide_index=True,
        )
        export_downloads(cells_df, "near_cutoff_anchor_cells", key_suffix="anc")


if __name__ == "__main__":
    render_risk_model_page()
