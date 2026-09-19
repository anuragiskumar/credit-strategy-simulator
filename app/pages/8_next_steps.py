"""Next Steps & Production Roadmap (REQUIREMENTS.md Section 12.2 Page 8).

Static documentation covering Champion/Challenger deployment, additional constraint dimensions,
pricing/limits, and existing-book portfolio management.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from app.common import render_provenance_legend


def render_next_steps_page():
    st.title("📋 Next Steps & Production Architecture")
    st.markdown(
        "Roadmap for transitioning the Originations Strategy Simulator prototype into a production decisioning engine."
    )

    render_provenance_legend()

    # Section 1: Champion/Challenger Deployment
    st.subheader("1. Champion / Challenger Execution Framework")
    st.markdown(
        """
        The simulator produces a self-contained, versioned strategy JSON object (Section 10.5) that defines:
        - Exact base rules and cutoff values.
        - Segment overrides with explicit eligibility criteria and relaxed rule tuples.
        - Segment exclusions for portfolio de-risking.
        - Active business constraints and expected headline outcomes.

        **Production Deployment Path:**
        1. **Deployment Registry:** Store exported strategy objects in a version-controlled repository (Git / MLflow / Model Registry).
        2. **Canary Routing:** Use a real-time decisioning gateway (e.g. AWS Lambda / BentoML / custom microservice) to split incoming traffic:
           - 80% Champion (Current Baseline Strategy)
           - 20% Challenger (Optimised Strategy Object)
        3. **Vintage Tracking:** Automatically tag incoming applications with `strategy_version` and track delinquency maturation across cohorts.
        """
    )

    st.divider()

    # Section 2: Additional Business Constraints
    st.subheader("2. Extending the Constraint Framework (Section 10.2.1)")
    st.markdown(
        """
        While this prototype implements the `blended_bad_rate` constraint, the underlying architecture in `src/optimise.py`
        is designed to evaluate constraints generically via `config.yaml`:

        ```yaml
        constraints:
          - name: bad_rate
            metric: blended_bad_rate
            operator: "<="
            threshold: 0.035
            enabled: true
          - name: max_fraud_rate
            metric: fraud_rate
            operator: "<="
            threshold: 0.005
            enabled: true
          - name: min_return_on_assets
            metric: projected_roa
            operator: ">="
            threshold: 0.025
            enabled: true
        ```

        **Planned Metric Extensions:**
        - **Expected Loss (EL = PD × LGD × EAD):** Integrating Loss Given Default and Exposure at Default models.
        - **Fraud Rate:** Verification thresholds and behavioral biometrics checks.
        - **Net Interest Margin (NIM) & Profitability:** Weighing credit loss against projected interest and fee income.
        """
    )

    st.divider()

    # Section 3: Pricing, Credit Limits & Existing Book
    st.subheader("3. Pricing, Exposure & Existing-Book Actions")
    st.markdown(
        """
        **Pricing & Limit Setting:**
        - Schema columns `loan_amount` and `tenor_months` are already captured in the data schema to support risk-based pricing.
        - Higher-risk swap-in segments below the cutoff can be granted lower credit limits or risk-premium APRs to mitigate loss severity.

        **Existing-Book & Account Management:**
        - **Credit Line Increases (CLI):** Identifying seasoned, low-risk accounts in existing books for proactive expansion.
        - **Pre-Delinquency Collections:** Triggering early-warning outreach for accounts whose bureau trajectory deteriorates.
        - **Renewals & Cross-Sell:** Pre-approved underwriting strategies tailored to existing customer payment track records.
        """
    )


if __name__ == "__main__":
    render_next_steps_page()
