"""Versioned strategy export and import (REQUIREMENTS.md Section 10.5)."""
from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.contracts import OptimiserResult, ScenarioResult, SegmentOverride, Strategy
from src.rules import with_exclusions, with_overrides, with_rule_params
from src.simulate import _exclusion_from_dict, _override_from_dict


def _json_conditions(conditions: dict) -> dict:
    return {k: [None if isinstance(x, (int, float)) and not math.isfinite(x) else x for x in v]
            if isinstance(v, tuple) else v for k, v in conditions.items()}


def export_strategy(strategy: Strategy,
                    result: ScenarioResult | OptimiserResult | None = None,
                    constraints: list[dict] | None = None,
                    parent_strategy_id: str | None = None,
                    strategy_id: str | None = None,
                    path: Path | str | None = None) -> dict:
    """Export strategy to versioned JSON format (Section 10.5)."""
    sid = strategy_id or str(uuid.uuid4())
    created = datetime.now(timezone.utc).isoformat()

    # Base rules: export rule params
    base_rules = {r.id: dict(r.params) for r in strategy.rules}

    # Segment overrides: convert tuples to lists for JSON compatibility
    overrides_list = []
    for ov in strategy.overrides:
        item = {"conditions": _json_conditions(ov.conditions)}
        if ov.relaxes:
            item["relaxes"] = list(ov.relaxes)
        overrides_list.append(item)

    exclusions_list = [
        {"conditions": _json_conditions(ex.conditions),
         "reason": ex.reason}
        for ex in strategy.exclusions
    ]

    # Constraints
    c_list = []
    if constraints:
        for c in constraints:
            c_list.append({"name": c["name"], "threshold": c["threshold"]})

    # Expected outcomes
    expected = {}
    if result is not None:
        sr = result.headline if isinstance(result, OptimiserResult) else result
        expected = {
            "approval_rate": float(sr.approval_rate),
            "blended_bad_rate": float(sr.blended_bad_rate),
            "inferred_share": float(sr.inferred_share),
            "not_modelled_count": int(sr.not_modelled_count),
        }

    data = {
        "strategy_id": sid,
        "created_at": created,
        "parent_strategy_id": parent_strategy_id,
        "base_rules": base_rules,
        "segment_overrides": overrides_list,
        "segment_exclusions": exclusions_list,
        "constraints": c_list,
        "expected": expected,
    }

    if path is not None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2, allow_nan=False), encoding="utf-8")

    return data


def import_strategy(source: str | Path | dict,
                    baseline: Strategy,
                    config: dict) -> tuple[Strategy, dict[str, Any]]:
    """Import strategy from versioned JSON format (Section 10.5).

    Returns (strategy, metadata).
    """
    if isinstance(source, (str, Path)):
        s = str(source)
        if s.lstrip().startswith("{"):
            data = json.loads(s)
        else:
            data = json.loads(Path(s).read_text(encoding="utf-8"))
    elif isinstance(source, dict):
        data = source
    else:
        raise TypeError(f"Expected path, json string or dict, got {type(source)}")

    # Update base rules if params differ
    s = baseline
    rule_changes = {}
    for r in baseline.rules:
        if r.id in data.get("base_rules", {}):
            new_params = data["base_rules"][r.id]
            if new_params != r.params:
                rule_changes[r.id] = new_params
    if rule_changes:
        s = with_rule_params(s, rule_changes)

    # Reconstruct overrides
    default_relaxes = config.get("segment_overrides", {}).get("default_relaxes", ["R5_SCORE", "R6_FOIR"])
    overrides = []
    for ov_dict in data.get("segment_overrides", []):
        overrides.append(_override_from_dict(ov_dict, default_relaxes))

    s = with_overrides(s, tuple(overrides))
    s = with_exclusions(s, tuple(_exclusion_from_dict(o) for o in data.get("segment_exclusions", [])))

    metadata = {
        "strategy_id": data.get("strategy_id"),
        "created_at": data.get("created_at"),
        "parent_strategy_id": data.get("parent_strategy_id"),
        "constraints": data.get("constraints", []),
        "expected": data.get("expected", {}),
    }

    return s, metadata
