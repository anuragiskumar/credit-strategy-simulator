"""Synthetic Validation (REQUIREMENTS.md Section 12.2 Page 7 & Section 10.4).

Compares simulated and optimised estimates against the ground-truth synthetic oracle.
Degrades cleanly when true_bad is not present.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
from src.optimise import optimise
from src.risk_model import INFERRED, OBSERVED, PREDICTED, near_cutoff_anchor
from src.rules import with_rule_params
from src.simulate import simulate
from src.validation import (
    DISCLAIMER,
    oracle_available,
    validate_near_cutoff_oracle,
    validate_strategy_oracle,
)


def render_validation_page():
    st.title("🧪 Synthetic Oracle Validation (Ground Truth)")

    cfg = load_app_config()
    df = get_applications_data()

    # Section 10.4 & 12.2: Degrade cleanly if oracle is not available
    if not oracle_available(df):
        st.warning(
            "🔒 **Validation Unavailable on Real Data**\n\n"
            "This dataset does not contain ground-truth synthetic outcomes. "
            "Oracle validation is only available on synthetic datasets where outcomes for historically declined "
            "applicants are known."
        )
        return

    st.markdown(
        f"""
        <div style="background-color: #ede7f6; border-left: 5px solid #5e35b1; padding: 12px 16px; margin-bottom: 20px; border-radius: 4px;">
            <div style="font-weight: 700; color: #4527a0; font-size: 1.1rem;">
                🔬 {DISCLAIMER}
            </div>
            <div style="font-size: 0.9rem; color: #311b92; margin-top: 4px;">
                This page uses synthetic ground-truth outcomes (<code>true_bad</code>) to evaluate model calibration,
                the conservatism penalty, and the accuracy of reject inference.
                <strong>This analysis is impossible with real-world credit data.</strong>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    render_provenance_legend()

    baseline = get_baseline_strategy(cfg)
    model = get_trained_model(df, cfg)

    run_btn = st.button("🧪 Run Oracle Validation", type="primary")

    cache_key = "oracle_val_results"
    if run_btn or cache_key in st.session_state:
        if run_btn or cache_key not in st.session_state:
            with st.spinner("Computing strategy oracle comparisons..."):
                # Baseline
                base_result = simulate(df, baseline, baseline, model, cfg)
                val_base = validate_strategy_oracle(df, baseline, baseline, base_result, model)

                # Optimised
                opt_res = optimise(df, baseline, model, cfg)
                val_opt = validate_strategy_oracle(df, baseline, opt_res.strategy, opt_res.headline, model)

                # Naive
                naive_strategy = with_rule_params(baseline, {"R5_SCORE": {"cutoff": int(opt_res.naive_cutoff)}})
                val_naive = validate_strategy_oracle(df, baseline, naive_strategy, opt_res.naive_result, model)

                # Near-Cutoff anchor validation
                anchor = near_cutoff_anchor(df, model, cfg)
                val_anchor_df = validate_near_cutoff_oracle(df, anchor, cfg["model"]["inference_penalty"])

                st.session_state[cache_key] = {
                    "val_base": val_base,
                    "val_opt": val_opt,
                    "val_naive": val_naive,
                    "opt_res": opt_res,
                    "val_anchor_df": val_anchor_df,
                }

        cached = st.session_state[cache_key]
        val_base = cached["val_base"]
        val_opt = cached["val_opt"]
        val_naive = cached["val_naive"]
        opt_res = cached["opt_res"]
        val_anchor_df = cached["val_anchor_df"]

        # 1. Oracle Comparison for Strategies: Baseline, Naive, and Optimised
        st.subheader("Strategy Oracle Performance Comparison")
        st.caption(
            "Comparing estimated blended bad rates against true default rates across baseline, naive, and optimised strategies."
        )

        # Strategy comparison table
        strategy_rows = [
            {
                "Strategy": "Baseline Strategy",
                "Approvals": val_base["approval_count"],
                "Estimated Blended Rate": val_base["blended_bad_rate_estimate"],
                "True Bad Rate (Modelled)": val_base["true_bad_rate_modelled"],
                "True Bad Rate (All)": val_base["true_bad_rate_all_approvals"],
                "Estimation Error": val_base["estimation_error"],
                "NOT_MODELLED Count": val_base["not_modelled_count"],
                "NOT_MODELLED True Rate": val_base["not_modelled_true_bad_rate"],
            },
            {
                "Strategy": f"Naive Uniform Cutoff ({opt_res.naive_cutoff:.0f})",
                "Approvals": val_naive["approval_count"],
                "Estimated Blended Rate": val_naive["blended_bad_rate_estimate"],
                "True Bad Rate (Modelled)": val_naive["true_bad_rate_modelled"],
                "True Bad Rate (All)": val_naive["true_bad_rate_all_approvals"],
                "Estimation Error": val_naive["estimation_error"],
                "NOT_MODELLED Count": val_naive["not_modelled_count"],
                "NOT_MODELLED True Rate": val_naive["not_modelled_true_bad_rate"],
            },
            {
                "Strategy": "Optimised Targeted Overrides",
                "Approvals": val_opt["approval_count"],
                "Estimated Blended Rate": val_opt["blended_bad_rate_estimate"],
                "True Bad Rate (Modelled)": val_opt["true_bad_rate_modelled"],
                "True Bad Rate (All)": val_opt["true_bad_rate_all_approvals"],
                "Estimation Error": val_opt["estimation_error"],
                "NOT_MODELLED Count": val_opt["not_modelled_count"],
                "NOT_MODELLED True Rate": val_opt["not_modelled_true_bad_rate"],
            },
        ]

        strat_df = pd.DataFrame(strategy_rows)
        disp_strat = strat_df.copy()
        disp_strat["Approvals"] = disp_strat["Approvals"].apply(format_count)
        disp_strat["Estimated Blended Rate"] = disp_strat["Estimated Blended Rate"].apply(format_rate)
        disp_strat["True Bad Rate (Modelled)"] = disp_strat["True Bad Rate (Modelled)"].apply(format_rate)
        disp_strat["True Bad Rate (All)"] = disp_strat["True Bad Rate (All)"].apply(format_rate)
        disp_strat["Estimation Error"] = disp_strat["Estimation Error"].apply(lambda v: f"{v:+.2%}" if pd.notna(v) else "—")
        disp_strat["NOT_MODELLED Count"] = disp_strat["NOT_MODELLED Count"].apply(format_count)
        disp_strat["NOT_MODELLED True Rate"] = disp_strat["NOT_MODELLED True Rate"].apply(format_rate)

        st.dataframe(disp_strat, use_container_width=True, hide_index=True)
        export_downloads(strat_df, "oracle_strategy_validation", key_suffix="strat")

        st.divider()

        # 2. NOT_MODELLED Approvals True Risk (Section 10.4)
        st.subheader("Cost of Unmodelled Approvals (NOT_MODELLED)")
        st.markdown(
            f"Under the optimised strategy, **{val_opt['not_modelled_count']:,} approvals** "
            f"sit outside the model's training support and were excluded from headline bad rates. "
            f"The synthetic oracle reveals their true default rate is **{val_opt['not_modelled_true_bad_rate']:.2%}** "
            f"(compared to the {val_opt['blended_bad_rate_estimate']:.2%} estimated blended rate)."
        )

        if pd.notna(val_opt['not_modelled_true_bad_rate']) and val_opt['not_modelled_true_bad_rate'] > val_opt['blended_bad_rate_estimate']:
            st.warning(
                f"⚠️ **Hidden Unmodelled Risk Confirmed:** Unmodelled approvals default at a substantially higher rate "
                f"({val_opt['not_modelled_true_bad_rate']:.2%}) than modelled approvals ({val_opt['true_bad_rate_modelled']:.2%}). "
                f"Excluding them from the blended bad rate is essential to avoid corrupting credit governance."
            )

        st.divider()

        # 3. Near-Cutoff Conservatism Penalty Validation (Section 10.4)
        st.subheader("Near-Cutoff Penalty Validation")
        penalty_label = f"{cfg['model']['inference_penalty']}×"
        st.markdown(
            f"Checking whether the default {penalty_label} conservatism penalty was adequate against true outcomes in the near-cutoff bands."
        )

        if not val_anchor_df.empty:
            disp_anc = val_anchor_df.copy()
            disp_anc["observed_bad_rate"] = disp_anc["observed_bad_rate"].apply(format_rate)
            disp_anc["mean_model_pd"] = disp_anc["mean_model_pd"].apply(format_rate)
            disp_anc["inferred_pd"] = disp_anc["inferred_pd"].apply(format_rate)
            disp_anc["implied_penalty"] = disp_anc["implied_penalty"].apply(lambda v: f"{v:.3f}")

            st.dataframe(
                disp_anc.rename(columns={
                    "cell": "Segmentation Cell",
                    "observed_bad_rate": f"Observed Rate (Overrides) [{OBSERVED}]",
                    "mean_model_pd": f"Model PD (Declines) [{PREDICTED}]",
                    "inferred_pd": f"Inferred PD ({penalty_label}) [{INFERRED}]",
                    "implied_penalty": "Implied Penalty",
                }),
                use_container_width=True,
                hide_index=True,
            )
            export_downloads(val_anchor_df, "oracle_anchor_validation", key_suffix="anc_val")
    else:
        st.info("Click **Run Oracle Validation** above to evaluate strategies and risk assumptions against synthetic ground truth.")


if __name__ == "__main__":
    render_validation_page()
