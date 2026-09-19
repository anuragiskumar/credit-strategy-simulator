import pytest

from src.contracts import SegmentOverride
from src.rules import evaluate_strategy, with_overrides
from src.waterfall import build_waterfall, decline_heatmap, single_rule_declines


def test_waterfall_sums_to_total_and_reconciles_to_actual_approvals(sample, strategy):
    wf = build_waterfall(sample, strategy)
    n = len(sample)
    assert wf["delta"].iloc[0] == n
    assert wf.loc[wf["kind"].isin(["start", "rule", "adjustment"]), "delta"].sum() == int(
        (sample["hist_decision"] == "approve").sum())
    assert wf["remaining"].iloc[-1] == int((sample["hist_decision"] == "approve").sum())
    # every application is either removed by exactly one rule or approved by the written strategy
    removed = -wf.loc[wf["kind"] == "rule", "delta"].sum()
    subtotal = wf.loc[wf["kind"] == "subtotal", "remaining"].iloc[0]
    assert removed + subtotal == n


def test_override_adjustment_steps_match_override_counts(sample, strategy):
    wf = build_waterfall(sample, strategy).set_index("label")
    ov = sample[sample["manual_override"]]
    assert wf.loc["Manual override: decline → approve", "delta"] == (ov["hist_decision"] == "approve").sum()
    assert wf.loc["Manual override: approve → decline", "delta"] == -(ov["hist_decision"] == "decline").sum()


def test_waterfall_rule_steps_are_sequential_first_failures(sample, strategy):
    ev = evaluate_strategy(sample, strategy)
    wf = build_waterfall(sample, strategy, ev).set_index("label")
    for rule in strategy.rules:
        assert -wf.loc[f"Removed by {rule.id}", "delta"] == (ev["first_failed_rule"] == rule.id).sum()


def test_waterfall_segment_override_mode_reconciles(sample, strategy):
    ov = SegmentOverride({"bureau_score": (650, 700)}, ("R5_SCORE",))
    scenario = with_overrides(strategy, (ov,))
    ev = evaluate_strategy(sample, scenario)
    wf = build_waterfall(sample, scenario, ev, adjustment="segment_overrides")
    assert wf["remaining"].iloc[-1] == int((ev["decision"] == "approve").sum())
    assert ev["approved_by_override"].sum() > 0


def test_waterfall_without_adjustment_and_bad_mode(sample, strategy):
    wf = build_waterfall(sample, strategy, adjustment=None)
    assert wf["kind"].iloc[-1] == "subtotal"
    with pytest.raises(ValueError):
        build_waterfall(sample, strategy, adjustment="nope")


def test_single_rule_declines(sample, strategy):
    ev = evaluate_strategy(sample, strategy)
    tbl = single_rule_declines(sample, strategy, ev).set_index("rule_id")
    failed = ev[[f"failed_{r.id}" for r in strategy.rules]]
    only = failed[failed.sum(axis=1) == 1]
    for rule in strategy.rules:
        assert tbl.loc[rule.id, "single_rule_declines"] == int(only[f"failed_{rule.id}"].sum())
        assert tbl.loc[rule.id, "single_rule_declines"] <= tbl.loc[rule.id, "failed_any"]


def test_heatmap_counts_every_written_decline(sample, strategy, cfg):
    ev = evaluate_strategy(sample, strategy)
    hm = decline_heatmap(sample, cfg, strategy, ev)
    assert int(hm.to_numpy().sum()) == int((ev["decision"] == "decline").sum())
    assert "No score" in hm.index
    assert hm.loc["No score"].sum() == int(sample.loc[(ev["decision"] == "decline").to_numpy(),
                                                       "bureau_score"].isna().sum())


def test_override_steps_come_from_the_flag_not_from_a_residual(sample, strategy):
    """Corrupting a non-override row must raise; a residual step would have absorbed it."""
    from src.rules import ReproductionError
    df = sample.copy()
    i = df.index[~df["manual_override"] & (df["hist_decision"] == "decline")][0]
    df.loc[i, "hist_decision"] = "approve"
    df["hist_decision"] = df["hist_decision"].astype("category")
    with pytest.raises(ReproductionError, match="non-override rows disagree"):
        build_waterfall(df, strategy)


def test_flagged_override_that_agrees_with_the_strategy_raises(sample, strategy):
    from src.rules import ReproductionError
    df = sample.copy()
    i = df.index[~df["manual_override"]][0]
    df.loc[i, "manual_override"] = True
    with pytest.raises(ReproductionError, match="agree with the written strategy"):
        build_waterfall(df, strategy)
