"""Interface contracts shared between phases (REQUIREMENTS.md Section 15). Do not change."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass(frozen=True)
class Rule:
    id: str                  # "R5_SCORE"
    params: dict             # {"cutoff": 700}
    mandatory: bool
    enabled: bool = True


@dataclass(frozen=True)
class SegmentOverride:
    conditions: dict         # {"bureau_score": (680, 700), "foir_max": 0.35,
                             #  "employment_type": ["salaried"]}
    relaxes: tuple           # ("R5_SCORE", "R6_FOIR") — rules this override may bypass


@dataclass(frozen=True)
class SegmentExclusion:
    conditions: dict
    reason: str


@dataclass(frozen=True)
class Strategy:
    rules: tuple             # tuple[Rule, ...] in evaluation order
    overrides: tuple = ()    # tuple[SegmentOverride, ...]
    exclusions: tuple[SegmentExclusion, ...] = ()


@dataclass
class ScenarioResult:
    approval_count: int
    approval_rate: float
    swap_in_count: int
    swap_out_count: int
    not_modelled_count: int          # approvals with no PD; excluded below
    observed_bad_rate: float         # OBSERVED, retained booked
    model_basis_baseline: float      # PREDICTED, baseline booked (Section 6.1)
    inferred_bad_rate: float         # INFERRED, modelled swap-ins
    blended_bad_rate: float          # excludes not_modelled
    inferred_share: float
    waterfall: pd.DataFrame
    swap_in_breakdown: pd.DataFrame  # includes a NOT_MODELLED row and a booked_in_cell column
    sensitivity: pd.DataFrame        # penalty -> blended_bad_rate


@dataclass(frozen=True)
class CandidateFunnel:
    total_declines: int
    failed_only_relaxable: int
    inside_support: int
    in_viable_segments: int


@dataclass
class OptimiserResult:
    headline: ScenarioResult
    added_segments: pd.DataFrame     # conditions, count, inferred_bad_rate, cumulative_bad_rate,
                                     # booked_in_cell, thin
    rejected_segments: pd.DataFrame  # conditions, count, inferred_bad_rate, reason
    naive_cutoff: float
    naive_result: ScenarioResult
    breakeven_penalty: float
    strategy: Strategy
    thin_share: float = 0.0
    thin_share_of_total: float = 0.0
    binding_constraint: str = "none"
    candidate_funnel: Optional[CandidateFunnel] = None
