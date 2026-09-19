"""Originations Strategy Simulator — Streamlit Entry Point (Section 12).

Multi-page Streamlit application declaring navigation across all 8 pages.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is in sys.path so both `app` and `src` can be imported
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

st.set_page_config(
    page_title="Originations Strategy Simulator",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Declare multi-page navigation across the 8 pages (Section 12.2)
pages = {
    "Strategy & Analysis": [
        st.Page("pages/1_overview.py", title="Overview & Reproduction", icon="📊", default=True),
        st.Page("pages/2_waterfall.py", title="Decline Waterfall", icon="📉"),
        st.Page("pages/3_risk_model.py", title="Risk Model & Support", icon="🎯"),
    ],
    "Simulation & Optimisation": [
        st.Page("pages/4_what_if.py", title="What-if Simulator", icon="🎛️"),
        st.Page("pages/5_optimiser.py", title="Credit Optimiser", icon="⚡"),
        st.Page("pages/6_portfolio_quality.py", title="Portfolio Quality (Swap-Out)", icon="🔄"),
    ],
    "Validation & Architecture": [
        st.Page("pages/7_validation.py", title="Synthetic Validation", icon="🧪"),
        st.Page("pages/8_next_steps.py", title="Next Steps & Architecture", icon="📋"),
    ],
}

pg = st.navigation(pages)

# Global sidebar branding & context
with st.sidebar:
    st.markdown("### 🏦 Originations Simulator")
    st.caption("Demo-grade prototype for credit strategy evaluation & optimisation.")
    st.divider()

pg.run()
