"""The Simulator's chat: say what you want to achieve, get a scenario replayed by the engine.

    person ──> model picks a plan ──validate_plan──> Engine.simulate / goal_seek ──> template ──> reply
                   ^        (client_llm)                 (deterministic)              ^
                   └── refused? the reason goes back to the model, once ──────────────┘

`client_llm` owns the plan format and knows nothing of the engine; this module shows the model
the rules this product actually has, runs the plan, and words the answer from the engine's own
figures. The model chooses changes. It never supplies a number the person reads: the sentence is
a template over the engine's result, and a model's wording of it (`narrate: true`) is checked
figure by figure, as for every other answer.

The page decides what happens next. A plan is replayed, not applied: the person sees the outcome
and chooses "Use this scenario", which loads it into the Simulator exactly as a goal-seek option.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone

from src import client_llm as L
from src.client_api import ApiError, MAX_CHANGES
from src.config import resolve_path
from src.rule_inventory import redact

MAX_MESSAGE = 1000
MAX_TURN_TEXT = 2000
_LOG_LOCK = threading.Lock()


# --------------------------------------------------------------------------- provider
def provider_from_config(cfg: dict) -> tuple[L.Provider, dict]:
    """The configured model, and a status the page can show. No key means no model, not no chat."""
    a = cfg.get("assistant") or {}
    kind = a.get("provider") or "keyword"
    timeout = float(a.get("timeout_s") or 20)
    key_env = a.get("api_key_env") or "GEMINI_API_KEY"
    status = {"configured": kind, "provider": kind, "model": a.get("model"), "note": None}
    if kind == "gemini":
        key = os.environ.get(key_env)
        if key:
            return L.GeminiProvider(api_key=key, model=a.get("model") or "gemini-3.6-flash",
                                    timeout=timeout, fallbacks=a.get("fallback_models") or (),
                                    thinking=a.get("thinking_level")), status
        note = f"no key in {key_env}"
    elif kind == "http":
        if a.get("base_url"):
            return L.HTTPProvider(a["base_url"], a.get("model") or "", os.environ.get(key_env),
                                  timeout=timeout), status
        note = "no base_url for the on-prem model"
    elif kind == "keyword":
        note = None
    else:
        note = f"unknown provider {kind!r}"
    status.update(provider="keyword", model=None,
                  note=f"{note}: answering without a model" if note else None)
    return L.KeywordProvider(), status


# --------------------------------------------------------------------------- what the model sees
def catalogue(engine, window=None, product=None) -> dict:
    """The rules this product has, as `plan_prompt` and `validate_plan` take them.

    Built from `Engine.rules()`, the list the All rules view shows, so the chat can offer
    exactly what a person could click and nothing else. Names are already redacted there.
    """
    rules = engine.rules(window, product)
    health = engine.health(window, product)
    labels = engine.base.cfg.get("field_labels") or {}

    def label(field: str) -> str:
        return labels.get(field.split(".")[-1], field.split(".")[-1])

    editable, fixed = [], []
    for r in rules:
        s = r.get("sentence") or {}
        if r["editable"]:
            editable.append({
                "rule_id": r["rule_id"], "name": r["label"], "stage": r.get("stage_label"),
                "when": s.get("when"), "applies_to": s.get("applies_to"),
                "declines_alone": r["declines_alone"],
                "thresholds": [{**t, "label": label(t["field"])} for t in r["thresholds"]]})
        else:
            fixed.append({"rule_id": r["rule_id"], "name": r["label"], "reason": r["reason"]})
    return {"product": health["product"], "approval_rate": health["approval_rate"],
            "applicants": health["applicants"],
            "booked_bad_rate": health["booked_bad_rate"], "bad_rate_ceiling": health["bad_rate_ceiling"],
            "max_changes": health.get("max_changes", MAX_CHANGES),
            "cutoffs": health.get("cutoffs") or [], "rules": editable, "fixed": fixed}


# --------------------------------------------------------------------------- answers
def _pct(v, dp: int = 1) -> str:
    return "—" if v is None else f"{float(v) * 100:.{dp}f}%"


def _scenario_sentence(r: dict) -> str:
    """One replayed scenario, from `summarise()`'s fields. Every figure is the engine's."""
    head = (f"Approval moves from {_pct(r['approval_rate_before'])} to {_pct(r['approval_rate'])} "
            f"({r['approval_change_pp']:+.1f} points): {r['swap_in']:,} applicants newly approved "
            f"and {r['swap_out']:,} newly declined.")
    if not r.get("risk_known"):
        return f"{head} The risk of this change cannot be estimated: {r.get('verdict') or 'no estimate'}"
    ceiling = r.get("bad_rate_ceiling")
    over = ceiling is not None and r["expected_bad_rate"] > ceiling
    return (f"{head} The expected bad rate is {_pct(r['expected_bad_rate'], 2)}, against "
            f"{_pct(r['booked_bad_rate_before'], 2)} booked today"
            + (f", above the {_pct(ceiling)} limit." if over else "."))


def _goal_sentence(g: dict) -> str:
    if not g["options"]:
        return "The search found nothing it could change to move approval."
    best, target, ceiling = g["options"][0], _pct(g["target"]), _pct(g["ceiling"])
    risk = (f"an expected bad rate of {_pct(best['expected_bad_rate'], 2)}" if best.get("risk_known")
            else "no bad-rate estimate possible")
    if g["reached"]:
        return (f"{target} approval is reachable within the {ceiling} bad-rate limit. The best option "
                f"gives {_pct(best['approval_rate'])} ({best['approval_change_pp']:+.1f} points), with {risk}.")
    return (f"{target} approval is out of reach within the {ceiling} limit. The closest option gives "
            f"{_pct(best['approval_rate'])} ({best['approval_change_pp']:+.1f} points), with {risk}.")


TEMPLATES = {"scenario": _scenario_sentence, "goal_seek": _goal_sentence}


# --------------------------------------------------------------------------- the loop
def _turns(history, message: str, keep: int) -> list[dict]:
    """The conversation as the page sent it, trimmed. It is the person's own; it is still capped."""
    out = []
    for t in (history if isinstance(history, list) else [])[-keep:] if keep else []:
        if isinstance(t, dict) and t.get("role") in ("user", "assistant") and isinstance(t.get("text"), str):
            out.append({"role": t["role"], "text": t["text"][:MAX_TURN_TEXT]})
    return out + [{"role": "user", "text": message}]


def _current(steps) -> list[dict]:
    if steps is None:
        return []
    if not isinstance(steps, list) or len(steps) > MAX_CHANGES or not all(isinstance(s, dict) for s in steps):
        raise ApiError("current must be the scenario's list of changes")
    return steps


class _Redacting(L.Provider):
    """Runs the client-name redactions over everything sent to the model, whatever built it."""

    def __init__(self, inner: L.Provider):
        self.inner, self.name = inner, inner.name
        self.model = getattr(inner, "model", None)

    def plan(self, turns, catalogue, current, on_try=None):
        if isinstance(self.inner, L.KeywordProvider):
            return self.inner.plan(turns, catalogue, current)
        system = redact(L.plan_prompt(catalogue, current))
        return L._extract_json(self.inner.converse(
            system, [{**t, "text": redact(t["text"])} for t in turns], L.PLAN_SCHEMA, on_try=on_try))

    def phrase(self, prompt):
        return self.inner.phrase(redact(prompt))


def _short(error: str, limit: int = 140) -> str:
    """The first clause of a refusal, for a progress line; the full reason is in the answer."""
    first = error.split("; ")[0]
    return first if len(first) <= limit else first[: limit - 1] + "…"


def respond(engine, body: dict, provider: L.Provider, cfg: dict | None = None, progress=None) -> dict:
    """One message in, one answer out: what the model planned, and what the engine made of it.

    `progress(stage, text)`, when given, is told each step as it starts, in words a person can
    read while they wait: which model is being asked, a correction, the replay, the search.
    Every step is real; nothing is paced by a timer.
    """
    a = (cfg or engine.base.cfg).get("assistant") or {}

    def say(stage: str, text: str) -> None:
        if progress:
            progress(stage, text)

    message = body.get("message")
    if not isinstance(message, str) or not message.strip():
        raise ApiError("say what you want to achieve")
    message = message.strip()
    if len(message) > MAX_MESSAGE:
        raise ApiError(f"keep it under {MAX_MESSAGE} characters")
    window, product = body.get("window"), body.get("product")
    current = _current(body.get("current"))
    turns = asked = _turns(body.get("history"), message, int(a.get("history_turns", 8)))
    say("rules", "Reading the rules you can change")
    cat = catalogue(engine, window, product)
    model = _Redacting(provider)
    tried: list[str] = []                  # models asked in this request; the last one answered

    def on_try(name: str, why) -> None:
        tried.append(name)
        if why:
            say("model", f"{tried[-2] if len(tried) > 1 else 'The model'} is busy, asking {name}")
        else:
            say("model", f"Asking {name} what to change" if attempts == 1 else f"Asking {name} for a corrected plan")
    repairs = 0 if isinstance(provider, L.KeywordProvider) else int(a.get("repairs", 1))

    answer, raw, error, attempts, fallback = None, None, None, 0, None
    while answer is None and attempts <= repairs:
        attempts += 1
        if isinstance(provider, L.KeywordProvider):
            say("model", "Reading the request without a language model")
        try:
            raw = model.plan(turns, cat, current, on_try=on_try)
        except L.TranslationError as e:
            if isinstance(provider, L.KeywordProvider):
                error = str(e)
                break
            # The model is unreachable, and asking it again will not help. The offline matcher
            # still answers a target, a cutoff or a rule ID, so the chat is never simply dead.
            fallback, provider, repairs, attempts, turns = str(e), L.KeywordProvider(), 0, 0, asked
            model = _Redacting(provider)
            say("fallback", "The language model could not be reached; answering without it")
            continue
        try:
            say("check", "Checking the plan against the rules")
            plan = L.validate_plan(raw, cat)
            answer = _run(engine, plan, cat, window, product, say)
        except (L.TranslationError, ApiError) as e:
            error = str(e)
            if attempts <= repairs:
                say("repair", f"Plan refused ({_short(error)}), asking for a correction")
            turns = turns + [{"role": "assistant", "text": json.dumps(raw, default=str)[:MAX_TURN_TEXT]},
                             {"role": "user", "text": f"That plan was refused: {error}. Send a corrected "
                                                      f"plan, or clarify or unsupported if it cannot be done."}]

    if answer is None:
        answer = {"action": "refused", "plan": None, "reply": (
            "I could not turn that into a scenario the engine accepts. " + (error or "")).strip(),
            "narrated_by": "template", "memo": f"(refused: {error})"}
    elif answer["action"] in TEMPLATES:
        subject = answer["result"]["result"] if answer["action"] == "scenario" else answer["result"]
        told = L.narrate(L.EngineCall(intent=answer["action"]), subject,
                         model if a.get("narrate") else None, templates=TEMPLATES)
        answer.update(reply=told["text"], narrated_by=told["source"], narration_rejected=told["rejected"])
    # Which model actually answered: with fallbacks it need not be the configured one.
    answer.update(provider=provider.name, attempts=attempts, fallback=fallback,
                  narrated_by=answer.get("narrated_by") or provider.name,
                  model=(tried[-1] if tried and not isinstance(provider, L.KeywordProvider)
                         else getattr(provider, "model", None)),
                  error=error if answer["action"] == "refused" else None)
    _log(a, body, message, raw, answer)
    return answer


def _run(engine, plan: L.Plan, cat: dict, window, product, say=lambda *_: None) -> dict:
    """Replay a checked plan. An `ApiError` here is the engine refusing it, which goes back to the model."""
    p = plan.as_dict()
    if plan.action in ("clarify", "unsupported"):
        return {"action": plan.action, "plan": p, "reply": plan.text, "narrated_by": None,
                "memo": plan.text}
    if plan.action == "scenario":
        changes = list(plan.changes)
        n = len(changes)
        say("replay", f"Replaying {n} change{'s' if n > 1 else ''} against {cat['applicants']:,} applications")
        out = engine.simulate(changes, window, product)
        out["result"]["bad_rate_ceiling"] = cat["bad_rate_ceiling"]
        return {"action": "scenario", "plan": p, "changes": changes, "result": out,
                "steps_text": engine.describe(changes, window, product), "memo": json.dumps(p)}
    say("search", f"Searching for the changes that reach {plan.target * 100:.1f}% approval"
                  + (f" with {len(plan.frozen)} rules left alone" if plan.frozen else ""))
    out = engine.goal_seek(plan.target, plan.ceiling, list(plan.frozen), window, product)
    for o in out["options"][:3]:
        o["steps_text"] = engine.describe(o.get("changes") or [], window, product)
    return {"action": "goal_seek", "plan": p, "result": out, "memo": json.dumps(p)}


def _log(a: dict, body: dict, message: str, raw, answer: dict) -> None:
    """Append-only: who asked what, what the model said, what the engine did with it."""
    path = a.get("log_path")
    if not path:
        return
    result = answer.get("result") or {}
    headline = (result.get("result") if answer["action"] == "scenario" else
                (result.get("options") or [None])[0]) or {}
    row = {"at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "who": str(body.get("who") or "").strip() or None, "product": body.get("product"),
           "window": body.get("window"), "message": message, "provider": answer.get("provider"),
           "model": answer.get("model"), "raw": raw, "plan": answer.get("plan"),
           "action": answer["action"], "attempts": answer.get("attempts"), "error": answer.get("error"),
           "approval_rate": headline.get("approval_rate"), "expected_bad_rate": headline.get("expected_bad_rate"),
           "narrated_by": answer.get("narrated_by"), "fallback": answer.get("fallback")}
    target = resolve_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with _LOG_LOCK, open(target, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
