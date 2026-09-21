"""The engine behind the simulator screen, as plain request -> JSON-ready dict functions.

    engine = Engine.load()                     # ~3s: applicants, rules, baseline, PD model
    engine.rules()                             # every decline rule, with what can be edited
    engine.simulate([{"type": "threshold", "rule_id": "racAndPolicies#028",
                      "field": "income", "value_low": 4000}])
    engine.simulate([{"type": "cutoff", "field": "simahcreditscore", "from": 600, "to": 580}])
    engine.goal_seek(target=0.30, ceiling=0.11, frozen=["racAndPolicies#012"])
    engine.simulate([...], window={"app_from": "2026-03-01", "app_to": "2026-08-31"})

Every call takes an optional `window` (see client_context): which applications are replayed,
and over how many months a booked loan must have run to count. With none, the configured
default window; every result says which window it ran on.

`ui/serve.py` puts these behind HTTP. They live here, not there, so the tests call exactly what
the screen calls, and so the same functions can sit behind a different server on-prem.

Nothing here computes a figure. It validates what a person asked for, turns it into levers,
and hands them to `client_simulate` and `client_optimise` — the same functions the CLIs, the
fixture export and the tests use. A change the engine will not make (a locked rule, a range
entered back to front) comes back as an `ApiError` with the reason in words.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass

import numpy as np
import pandas as pd

from src import client_analysis as A, client_optimise as O, client_simulate as S
from src.client_replay import locked_rules

MAX_CHANGES = 12
"""How many changes one scenario may stack. Each step is re-simulated to show its own effect,
so the cap keeps a request to well under a second; nobody takes twelve changes to committee."""


CUTOFFS = [
    {"field": "simahcreditscore", "label": "SIMAH score cutoff", "from": 600,
     "values": [560, 570, 580, 590, 600, 610, 620, 630, 640]},
    {"field": "crifscore", "label": "CRIF score cutoff", "from": 605,
     "values": [565, 575, 585, 595, 605, 615, 625, 635, 645]},
]
"""The score cutoffs the screen offers as sliders: every rule testing the score at `from` moves
together. Below `from` loosens, above it tightens. Goal-seek's own cutoff moves come from config
and are sent back as the same `cutoff` change, so an option can be applied as a scenario."""


class ApiError(ValueError):
    """A request the engine refuses. `status` is the HTTP code the server should send."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _num(v):
    """JSON-safe number: NaN and infinities become None, never a spurious zero."""
    if v is None:
        return None
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    if isinstance(v, (np.integer, int)):
        return int(v)
    f = float(v)
    return None if not np.isfinite(f) else round(f, 6)


def rule_catalogue(base: S.Baseline, inv) -> list[dict]:
    """Every decline rule the replay evaluates, busiest first, with what a person may change.

    Not a top-N: the screen lists all of them. A rule that declines nobody on its own is
    listed too, labelled as such — that it can be switched off for no gain is a finding.
    """
    drivers = A.decline_drivers(base.df, base.res, base.outcome, base.cfg)
    stats = drivers.set_index("rule_id") if not drivers.empty else pd.DataFrame()
    rows = []
    for rid, c in base.res.compiled.items():
        if c.kind != "block":
            continue
        reason = S.editable_reason(base, rid)
        declines = int(stats.loc[rid, "declines"]) if rid in stats.index else 0
        alone = int(stats.loc[rid, "declines_alone"]) if rid in stats.index else 0
        tests, _ = A.rule_tests(inv.conditions, rid)
        rows.append({
            "rule_id": rid, "table": c.table, "stage": c.stage,
            "policy_code": c.policy_code if isinstance(c.policy_code, str) else None,
            "label": A.clean_description(c.description) or rid,
            "tests": tests or None,
            "declines": declines, "declines_alone": alone,
            "locked": c.locked, "fixed_field": c.fixed_field,
            "editable": reason is None, "reason": reason,
            "thresholds": [{k: _num(v) if k != "field" and k != "operator" else v
                            for k, v in t.items()}
                           for t in S.editable_thresholds(inv, rid)] if reason is None else [],
        })
    rows.sort(key=lambda r: (-r["declines_alone"], -r["declines"], r["rule_id"]))
    return rows


def lever_for(base: S.Baseline, inv, change: dict) -> S.Lever:
    """One change from the screen, as a lever. Raises ApiError with the reason in words."""
    if not isinstance(change, dict):
        raise ApiError("each change must be an object")
    kind = change.get("type")
    try:
        if kind == "off":
            return S.off_lever(base, str(change.get("rule_id")))
        if kind == "cutoff":
            return cutoff_lever(base, inv, change)
        if kind == "threshold":
            return S.threshold_lever(base, inv, str(change.get("rule_id")),
                                     str(change.get("field")),
                                     value_low=_as_float(change.get("value_low")),
                                     value_high=_as_float(change.get("value_high")))
    except S.NotEditable as e:
        raise ApiError(str(e)) from None
    raise ApiError(f"unknown change type {kind!r}: use 'off', 'threshold' or 'cutoff'")


def cutoff_lever(base: S.Baseline, inv, change: dict) -> S.Lever:
    """Move every rule testing `field` at `from` to `to`, as the sweep and goal-seek do.

    Lowering a score or income cutoff loosens; raising it tightens, and a person who asked for
    a tightening gets exactly that, so the move is made whichever way each rule points.
    """
    field = change.get("field")
    lo, to = _as_float(change.get("from")), _as_float(change.get("to"))
    if not isinstance(field, str) or lo is None or to is None:
        raise ApiError("a cutoff change needs a field, a from and a to")
    if lo == to:
        raise ApiError(f"{field} is already at {lo:g}")
    tighten = to > lo
    try:
        lever = S.field_lever(inv, field, lo, to, product=base.cfg["product"],
                              locked=locked_rules(base.cfg), allow_tighten=tighten,
                              label=f"{field} cutoff {lo:g} to {to:g}")
    except ValueError as e:
        raise ApiError(str(e)) from None
    object.__setattr__(lever, "direction", "tighten" if tighten else "loosen")
    return lever


def _change_key(ch: dict) -> tuple:
    """What a change touches, for refusing the same thing twice in one scenario."""
    if ch.get("type") == "cutoff":
        return ("cutoff", ch.get("field"), _as_float(ch.get("from")))
    return (ch.get("rule_id"), ch.get("field") if ch.get("type") == "threshold" else None)


def _as_float(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        raise ApiError(f"{v!r} is not a number") from None


def summarise(base: S.Baseline, result: dict) -> dict:
    """The fields the screen shows, from one `simulate()` result."""
    by_channel = S.swap_set_profile(base, result, "channel")
    return {
        "lever": result["lever"],
        "direction": result.get("direction"),
        "rules_changed": result["rules_changed"],
        "approval_rate": _num(result["approval_rate"]),
        "approval_rate_before": _num(result["approval_rate_before"]),
        "approval_change_pp": _num(result["approval_rate_change_pp"]),
        "booked_after": result["booked_after"],
        "swap_in": result["swap_in"],
        "swap_out": result["swap_out"],
        "expected_bad_rate": _num(result["expected_bad_rate_after"]),
        "risk_known": bool(result["expected_bad_rate_known"]),
        "booked_bad_rate_before": _num(result["booked_bad_rate_before"]),
        "swap_out_observed_bad_rate": _num(result["swap_out_observed_bad_rate"]),
        "verdict": result["risk_verdict"],
        "swap_in_by_channel": {str(k): {"swap_in": int(v["swap_in"]),
                                        "swap_out": int(v["swap_out"])}
                               for k, v in by_channel.to_dict("index").items()},
    }


def simulate_changes(base: S.Baseline, inv, changes: list) -> dict:
    """A ladder of changes: the result after each step, and after all of them.

    `steps[i]` is the book with changes 0..i applied, so the screen can show what each step
    added on top of the ones before it, and reverting a step is just asking again without it.
    """
    if not isinstance(changes, list):
        raise ApiError("changes must be a list")
    if not changes:
        raise ApiError("add at least one change")
    if len(changes) > MAX_CHANGES:
        raise ApiError(f"at most {MAX_CHANGES} changes in one scenario")
    levers = [lever_for(base, inv, ch) for ch in changes]
    # One step per threshold, and a rule switched off cannot also be retuned: either would
    # make the order of the steps silently decide the answer.
    seen: dict[tuple, int] = {}
    off: dict[str, int] = {}
    for i, ch in enumerate(changes):
        rid = ch.get("rule_id")
        key = _change_key(ch)
        clash = seen.get(key)
        if clash is None and ch.get("type") == "off":
            clash = next((j for k, j in seen.items() if len(k) == 2 and k[0] == rid), None)
        if clash is None and ch.get("type") != "cutoff" and rid in off:
            clash = off[rid]
        if clash is not None:
            what = f"the {ch.get('field')} cutoff" if ch.get("type") == "cutoff" else rid
            raise ApiError(f"{what} appears twice (steps {clash + 1} and {i + 1}); "
                           f"edit the existing step instead")
        seen[key] = i
        if ch.get("type") == "off":
            off[rid] = i
    steps, prev = [], None
    for i in range(len(levers)):
        lever = levers[0] if i == 0 else S.combine(*levers[: i + 1])
        step = summarise(base, S.simulate(base, inv, lever))
        step["change"] = levers[i].label
        step["change_direction"] = getattr(levers[i], "direction", None)
        # What this step added on top of the ones before it. Worked out here, not on the
        # page, so the screen never derives a figure.
        step["added_pp"] = round(step["approval_change_pp"] - (prev["approval_change_pp"]
                                                               if prev else 0.0), 2)
        step["added_swap_in"] = step["swap_in"] - (prev["swap_in"] if prev else 0)
        step["added_swap_out"] = step["swap_out"] - (prev["swap_out"] if prev else 0)
        steps.append(step)
        prev = step
    return {"steps": steps, "result": steps[-1]}


def run_goal_seek(base: S.Baseline, inv, target, ceiling=None, frozen=None) -> dict:
    """Goal-seek to the person's own target, under their own bad-rate ceiling."""
    t = _as_float(target)
    if t is None:
        raise ApiError("give a target approval rate")
    if t > 1:
        t = t / 100                        # accept 30 as well as 0.30
    if not base.approval_rate < t <= 1:
        raise ApiError(f"the target must be above today's {100 * base.approval_rate:.1f}% "
                       f"and at most 100%")
    c = _as_float(ceiling)
    if c is not None:
        if c > 1:
            c = c / 100
        if not 0 < c < 1:
            raise ApiError("the bad-rate ceiling must be between 0% and 100%")
    frozen = frozenset(str(r) for r in (frozen or []))
    unknown = sorted(frozen - set(base.res.compiled))
    if unknown:
        raise ApiError(f"not rules of this product: {', '.join(unknown)}")
    out = O.goal_seek(base, inv, t, base.cfg, ceiling=c, frozen=frozen)
    options = []
    for row in out.to_dict("records"):
        options.append({k: (v if isinstance(v, (str, list)) else _num(v)) for k, v in row.items()})
    return {"target": t, "reached": bool(out.attrs.get("reached")),
            "ceiling": _num(out.attrs.get("ceiling")), "frozen": sorted(frozen),
            "options": options}


def goal_search_space(cfg: dict) -> dict:
    """What goal-seek is allowed to try, so the screen can say so rather than imply "anything".

    The rule switch-offs are the busiest relaxable rules (the screen picks them from the rule
    list with these two numbers); the cutoff moves are fixed in config.
    """
    opt = cfg["optimise"]
    return {"min_declines_alone": int(opt["min_declines_alone"]),
            "max_rule_candidates": int(opt["max_rule_candidates"]),
            "field_moves": [f"{m['label']} ({m['from']:g} to {m['to']:g})"
                            for m in opt.get("field_moves") or []],
            "beam_width": int(opt["beam_width"]), "max_depth": int(opt["max_depth"])}


def window_presets(cache, product: str | None = None) -> list[dict]:
    """The windows the period control offers, resolved against this product's dates."""
    from src import client_context as C
    df = cache.product_df(product)
    out = []
    for months in cache.cfg["analysis"]["presets"]["last_months"]:
        w = C.last_months(df, cache.cfg, int(months))
        out.append({"id": f"last_{months}m", "name": f"Last {months} months", **w.to_dict()})
    whole = C.resolve(C.AnalysisWindow(), df, cache.cfg)
    out.append({"id": "all", "name": "All applications", **whole.to_dict()})
    return out


@dataclass
class Engine:
    """Baselines per analysis context, shared by every request. Calls are serialised by a lock.

    `base` is the default: the default product over its default window. A request may name a
    `product` and a `window`; each is built on first use and kept while it is recent. `{}` as a
    window means the product's whole file. An engine made without a `cache` serves only `base`.
    """
    base: S.Baseline
    inv: object
    cache: object = None               # client_context.ContextCache

    def __post_init__(self):
        self._lock = threading.Lock()
        self._rules: dict = {}

    @classmethod
    def load(cls) -> "Engine":
        from src import client_context as C
        from src.client_generate import load_client_config
        from src.config import resolve_path
        from src.rule_inventory import build_inventory
        cfg = load_client_config()
        inv = build_inventory(cfg["replay"]["rules_folder"])
        df = pd.read_parquet(resolve_path(cfg["data_path"]))
        cache = C.ContextCache(df, inv, cfg)
        return cls(base=cache.baseline(), inv=inv, cache=cache)

    def baseline(self, window=None, product=None) -> S.Baseline:
        """The baseline for a request's product and window, or a refusal in words."""
        from src import client_context as C
        if window is None and product is None:
            return self.base
        if self.cache is None:
            raise ApiError("this engine was loaded for one product and window only")
        if product is not None and not isinstance(product, str):
            raise ApiError("product must be a product code, such as TWQR")
        try:
            w = C.AnalysisWindow.from_dict(window) if window is not None else None
            return self.cache.baseline(w, product)
        except C.ContextError as e:
            raise ApiError(str(e)) from None

    def health(self, window=None, product=None) -> dict:
        with self._lock:
            base = self.baseline(window, product)
            out = {"ready": True, "product": base.cfg["product"],
                   "applicants": int(len(base.df)),
                   "approval_rate": _num(base.approval_rate),
                   "booked_bad_rate": _num(base.booked_bad_rate),
                   "bad_rate_ceiling": _num(base.cfg["optimise"]["max_bad_rate"]),
                   "max_changes": MAX_CHANGES,
                   "goal_search": goal_search_space(base.cfg),
                   "cutoffs": CUTOFFS,
                   "window": base.window_dict(),
                   "default_window": self.base.window_dict()}
            if self.cache is not None:
                from src import client_context as C
                p = base.cfg["product"]
                lo, hi = C.data_range(self.cache.product_df(p))
                bd = A.bad_definition(self.cache.cfg)
                out["default_product"] = self.cache.cfg["product"]
                out["products"] = self.cache.products()
                out["default_window"] = self.cache.baseline(None, p).window_dict()
                out["data_range"] = {"app_from": f"{lo:%Y-%m-%d}", "app_to": f"{hi:%Y-%m-%d}"}
                out["outcome"] = {"as_of": f"{bd['as_of']:%Y-%m-%d}", "dpd": bd["dpd"],
                                  "within_months": bd["within_months"]}
                out["window_presets"] = window_presets(self.cache, p)
            return out

    def rules(self, window=None, product=None) -> list[dict]:
        with self._lock:
            base = self.baseline(window, product)
            key = (base.cfg["product"], base.window.key if base.window is not None else None)
            if key not in self._rules:         # a baseline never changes, so neither does this
                self._rules[key] = rule_catalogue(base, self.inv)
            return self._rules[key]

    def simulate(self, changes: list, window=None, product=None) -> dict:
        with self._lock:
            base = self.baseline(window, product)
            out = simulate_changes(base, self.inv, changes)
            out.update(window=base.window_dict(), product=base.cfg["product"])
            return out

    def goal_seek(self, target, ceiling=None, frozen=None, window=None, product=None) -> dict:
        with self._lock:
            base = self.baseline(window, product)
            out = run_goal_seek(base, self.inv, target, ceiling, frozen)
            out.update(window=base.window_dict(), product=base.cfg["product"])
            return out
