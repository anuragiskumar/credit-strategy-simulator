"""The thin LLM layer (plan step 6): plain English in, narrated results out.

The layer translates in both directions and does nothing else. It computes nothing and
decides nothing, which is what makes it swappable and what makes it safe to leave out
entirely — `KeywordProvider` needs no model at all, so phase 1 runs offline.

    question ──parse──> EngineCall ──execute──> engine result ──narrate──> sentence
                 ^                   (deterministic)                ^
                 └── LLM, or no LLM at all ──────────────────────────┘

Three properties hold whichever provider is used:

  * **The call format is closed.** `INTENTS` is the frozen question catalogue. A model that
    returns anything else is rejected, not improvised around.
  * **The LLM never produces a number.** Narration is built from templates with engine values
    substituted. When a model phrases the sentence instead, `verify_numbers` checks every
    numeral in it against the engine result and falls back to the template if one is invented.
  * **A refusal survives translation.** Where the engine says it cannot estimate, the sentence
    says so too. That is the one thing a fluent model is most likely to smooth away.

On-prem matters more than any particular vendor here: a Saudi bank running in a private cloud
cannot call an external API, so `HTTPProvider` speaks the OpenAI-compatible protocol that
vLLM, Ollama and llama.cpp all serve. `GeminiProvider` is the hosted option for a demo.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable

# --------------------------------------------------------------------------- call format
# The frozen question catalogue from the brief. The engine is done when it answers these ten,
# so they are exactly the intents the LLM may produce — nothing else is a valid translation.
INTENTS: dict[str, dict] = {
    "approval_rate": {
        "question": "What is my approval rate, and on what base?",
        "params": {}},
    "funnel": {
        "question": "Where do applicants drop out, stage by stage?",
        "params": {}},
    "decline_drivers": {
        "question": "Which rule declines the most applicants on its own?",
        "params": {"top": {"type": "int", "default": 5, "min": 1, "max": 25}}},
    "by_source": {
        "question": "Which channel, source or agent produces the most declines?",
        "params": {"column": {"type": "enum", "values": ["channel", "source_code", "agent_id"],
                              "default": "channel"}}},
    "portfolio": {
        "question": "How does my portfolio split, and how does each slice perform?",
        "params": {"slice": {"type": "enum",
                             "values": ["employer_segment", "sector", "channel",
                                        "nationality", "score_band"],
                             "default": "employer_segment"}}},
    "concentration": {
        "question": "Where am I over- or under-exposed?",
        "params": {"slice": {"type": "enum",
                             "values": ["employer_segment", "sector", "channel", "nationality"],
                             "default": "sector"}}},
    "simulate": {
        "question": "If I change this threshold, what happens?",
        "params": {"field": {"type": "enum",
                             "values": ["simahcreditscore", "crifscore", "income", "age"],
                             "default": "simahcreditscore"},
                   "from": {"type": "float", "default": 600.0},
                   "to": {"type": "float", "default": 560.0}}},
    "swap_set": {
        "question": "Who newly gets approved and declined, and are the swap-ins riskier?",
        "params": {"field": {"type": "enum",
                             "values": ["simahcreditscore", "crifscore", "income", "age"],
                             "default": "simahcreditscore"},
                   "from": {"type": "float", "default": 600.0},
                   "to": {"type": "float", "default": 560.0},
                   "by": {"type": "enum", "values": ["channel", "employer_segment", "sector"],
                          "default": "channel"}}},
    "goal_seek": {
        "question": "What combination of changes reaches a target approval rate?",
        "params": {"target": {"type": "float", "default": 0.30, "min": 0.01, "max": 0.99}}},
    "rules_not_earning_place": {
        "question": "Which rules cost approvals without reducing risk?",
        "params": {"top": {"type": "int", "default": 5, "min": 1, "max": 25}}},
}


class TranslationError(ValueError):
    """The question could not be turned into a call the engine understands."""


@dataclass(frozen=True)
class EngineCall:
    intent: str
    params: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"intent": self.intent, "params": dict(self.params)}


def validate_call(raw: dict) -> EngineCall:
    """Coerce a model's output into a call, or refuse it.

    Anything outside the catalogue is an error rather than a best guess: a plausible-looking
    answer to a question nobody asked is worse than saying the question is not supported.
    """
    if not isinstance(raw, dict):
        raise TranslationError(f"expected an object, got {type(raw).__name__}")
    intent = raw.get("intent")
    if intent not in INTENTS:
        raise TranslationError(
            f"{intent!r} is not one of the {len(INTENTS)} questions the engine answers")
    spec = INTENTS[intent]["params"]
    given = raw.get("params") or {}
    if not isinstance(given, dict):
        raise TranslationError("params must be an object")
    unknown = set(given) - set(spec)
    if unknown:
        raise TranslationError(f"{intent}: unknown parameter(s) {sorted(unknown)}")

    params: dict[str, Any] = {}
    for name, rule in spec.items():
        value = given.get(name, rule.get("default"))
        if rule["type"] == "enum":
            if value not in rule["values"]:
                raise TranslationError(
                    f"{intent}.{name}: {value!r} is not one of {rule['values']}")
        elif rule["type"] in ("int", "float"):
            try:
                value = int(value) if rule["type"] == "int" else float(value)
            except (TypeError, ValueError):
                raise TranslationError(f"{intent}.{name}: {value!r} is not a number") from None
            if "min" in rule and value < rule["min"]:
                raise TranslationError(f"{intent}.{name}: {value} below minimum {rule['min']}")
            if "max" in rule and value > rule["max"]:
                raise TranslationError(f"{intent}.{name}: {value} above maximum {rule['max']}")
        params[name] = value
    return EngineCall(intent=intent, params=params)


def call_schema() -> str:
    """The prompt fragment describing the call format. One source of truth for every provider."""
    lines = ["You translate a question into ONE JSON object and nothing else.",
             'Format: {"intent": "<name>", "params": {...}}', "",
             "Available intents:"]
    for name, spec in INTENTS.items():
        params = ", ".join(
            f"{p}:{r['type']}" + (f"({'|'.join(map(str, r['values']))})" if r["type"] == "enum" else "")
            for p, r in spec["params"].items()) or "none"
        lines.append(f"  {name} — {spec['question']}  params: {params}")
    lines += ["", "Return only the JSON. Never invent a number: you choose the intent and its",
              "parameters, and the engine computes every figure."]
    return "\n".join(lines)


# --------------------------------------------------------------------------- providers
class Provider:
    """Turns a question into a raw dict. Swappable, and optional."""
    name = "base"

    def translate(self, question: str) -> dict:
        raise NotImplementedError

    def phrase(self, prompt: str) -> str | None:
        """Optional: rephrase a narration. Returning None keeps the template."""
        return None


# Ordered longest-first so "declines alone" wins over "declines".
KEYWORDS: list[tuple[str, str]] = [
    (r"cost.*approval|earn.*place|without (reducing|buying)", "rules_not_earning_place"),
    (r"target|goal|get to|reach", "goal_seek"),
    (r"swap|newly\s+\w*\s*(approved|declined)|who moves", "swap_set"),
    (r"if i (change|move|lower|raise)|what if|simulat", "simulate"),
    (r"over[- ]?exposed|under[- ]?exposed|concentrat", "concentration"),
    (r"portfolio|segment|slice|score band|perform", "portfolio"),
    (r"channel|source|agent|branch|digital", "by_source"),
    (r"which rule|decline driver|declines the most|on its own|alone", "decline_drivers"),
    (r"drop out|funnel|stage", "funnel"),
    (r"approval rate|how many.*approv", "approval_rate"),
]


class KeywordProvider(Provider):
    """No model at all. Deterministic, offline, and good enough for the demo's phase 1.

    It exists so the engine is never blocked on a model being available, and so the call
    format can be exercised in tests without a network.
    """
    name = "keyword"

    def translate(self, question: str) -> dict:
        q = question.lower()
        for pattern, intent in KEYWORDS:
            if re.search(pattern, q):
                return {"intent": intent, "params": _params_from_text(intent, q)}
        raise TranslationError(
            "no rule matched this question. The engine answers: "
            + "; ".join(spec["question"] for spec in INTENTS.values()))


def _params_from_text(intent: str, q: str) -> dict:
    """Pull the obvious numbers and enums out of the question. Defaults fill the rest."""
    params: dict[str, Any] = {}
    spec = INTENTS[intent]["params"]
    if "target" in spec:
        m = re.search(r"(\d+(?:\.\d+)?)\s*%", q)
        if m:
            params["target"] = float(m.group(1)) / 100
    if "from" in spec and "to" in spec:
        nums = [float(x) for x in re.findall(r"\b(\d{2,6})\b", q)]
        if len(nums) >= 2:
            params["from"], params["to"] = nums[0], nums[1]
    if "field" in spec:
        for needle, value in (("crif", "crifscore"), ("simah", "simahcreditscore"),
                              ("income", "income"), ("salary", "income"), ("age", "age")):
            if needle in q:
                params["field"] = value
                break
    for key in ("column", "by", "slice"):
        if key in spec:
            for value in spec[key]["values"]:
                if value.replace("_", " ") in q or value in q:
                    params[key] = value
                    break
    if "top" in spec:
        m = re.search(r"\btop\s+(\d+)", q)
        if m:
            params["top"] = int(m.group(1))
    return params


class HTTPProvider(Provider):
    """Any OpenAI-compatible chat endpoint: vLLM, Ollama, llama.cpp, or a hosted service.

    This is the on-prem route, and the one that generalises. A Saudi bank running in a
    private cloud points `base_url` at its own server and nothing else changes.
    """
    name = "http"

    def __init__(self, base_url: str, model: str, api_key: str | None = None,
                 timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    def _chat(self, system: str, user: str) -> str:
        body = json.dumps({
            "model": self.model, "temperature": 0,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
        }).encode()
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(f"{self.base_url}/chat/completions", body, headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read())
        except (urllib.error.URLError, TimeoutError) as exc:
            raise TranslationError(f"{self.base_url} unreachable: {exc}") from exc
        return payload["choices"][0]["message"]["content"]

    def translate(self, question: str) -> dict:
        return _extract_json(self._chat(call_schema(), question))

    def phrase(self, prompt: str) -> str | None:
        try:
            return self._chat(NARRATION_SYSTEM, prompt).strip()
        except TranslationError:
            return None


class GeminiProvider(Provider):
    """The hosted option. Fine for a demo; an external API is a non-starter on-prem."""
    name = "gemini"
    ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, api_key: str | None = None, model: str = "gemini-2.5-flash",
                 timeout: float = 30.0):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.model = model
        self.timeout = timeout
        if not self.api_key:
            raise ValueError("no Gemini API key: pass api_key or set GEMINI_API_KEY")

    def _generate(self, system: str, user: str) -> str:
        body = json.dumps({
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"parts": [{"text": user}]}],
            "generationConfig": {"temperature": 0},
        }).encode()
        url = f"{self.ENDPOINT}/{self.model}:generateContent"
        req = urllib.request.Request(
            url, body, {"Content-Type": "application/json", "x-goog-api-key": self.api_key})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read())
        except (urllib.error.URLError, TimeoutError) as exc:
            raise TranslationError(f"Gemini unreachable: {exc}") from exc
        return payload["candidates"][0]["content"]["parts"][0]["text"]

    def translate(self, question: str) -> dict:
        return _extract_json(self._generate(call_schema(), question))

    def phrase(self, prompt: str) -> str | None:
        try:
            return self._generate(NARRATION_SYSTEM, prompt).strip()
        except (TranslationError, KeyError, IndexError):
            return None


def _extract_json(text: str) -> dict:
    """Models fence their JSON, apologise around it, or both."""
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", cleaned, re.S)
    if not match:
        raise TranslationError(f"no JSON in the model's reply: {text[:120]!r}")
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise TranslationError(f"unparseable JSON: {text[:120]!r}") from exc


def parse(question: str, provider: Provider | None = None) -> EngineCall:
    """Question -> validated engine call."""
    return validate_call((provider or KeywordProvider()).translate(question))


# --------------------------------------------------------------------------- narration
NARRATION_SYSTEM = (
    "You rephrase a finished analysis into one or two plain sentences for a bank executive. "
    "Every number is already correct: copy them exactly and never add, round or infer a "
    "figure. If the analysis says something is unknown or cannot be estimated, say so "
    "plainly — do not smooth it over. No preamble."
)

# Thousands separators first, or "10,555" is read as 10 and 555 and every faithful
# narration gets rejected for inventing figures it did not invent.
NUMBER_RE = re.compile(r"-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|-?\d+(?:\.\d+)?")


def verify_numbers(text: str, allowed: list[float], tolerance: float = 0.051) -> list[str]:
    """Return any numeral in `text` that does not appear in the engine's result.

    The guard that makes a fluent model safe here. A model asked to phrase a result will
    occasionally produce a figure that reads well and is wrong; this catches it, and the
    caller falls back to the template.
    """
    bad = []
    for token in NUMBER_RE.findall(text):
        value = float(token.replace(",", ""))
        if not any(abs(value - a) <= tolerance for a in allowed):
            bad.append(token)
    return bad


def _numbers_in(obj: Any, out: list[float] | None = None) -> list[float]:
    """Every number the engine produced, including percentage renderings of each."""
    out = [] if out is None else out
    if isinstance(obj, dict):
        for v in obj.values():
            _numbers_in(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _numbers_in(v, out)
    elif isinstance(obj, bool):
        pass
    elif isinstance(obj, (int, float)):
        value = float(obj)
        out += [value, round(value, 1), round(value, 2),
                round(value * 100, 1), round(value * 100, 2), round(value * 100)]
    return out


def narrate(call: EngineCall, result: dict, provider: Provider | None = None,
            templates: dict[str, Callable[[dict], str]] | None = None) -> dict:
    """Engine result -> a sentence, with the template always available as the fallback.

    Returns the sentence and how it was produced, so a screen can show which. A number the
    model invented never reaches the reader.
    """
    template = (templates or TEMPLATES).get(call.intent)
    base = template(result) if template else json.dumps(result)
    if provider is None:
        return {"text": base, "source": "template", "rejected": None}

    phrased = provider.phrase(
        f"{base}\n\nFull result:\n{json.dumps(result, default=str)[:1500]}")
    if not phrased:
        return {"text": base, "source": "template", "rejected": "provider returned nothing"}
    invented = verify_numbers(phrased, _numbers_in(result) + _numbers_in(call.params))
    if invented:
        return {"text": base, "source": "template",
                "rejected": f"model produced figures not in the result: {invented}"}
    return {"text": phrased, "source": provider.name, "rejected": None}


def _pct(v, dp: int = 1) -> str:
    return "—" if v is None else f"{float(v) * 100:.{dp}f}%"


def _slice(name) -> str:
    """Quote a slice name. Without it, the sector "it" reads as the pronoun."""
    return f'"{name}"'.replace("_", " ")


TEMPLATES: dict[str, Callable[[dict], str]] = {
    "approval_rate": lambda r: (
        f"{_pct(r['approval_rate'])} of all {r['applicants']:,} applications were approved and "
        f"booked ({r['booked']:,}). The base is every application received, not only those "
        f"that reached a decision."),
    "funnel": lambda r: (
        "Of every 100 applications: "
        + ", ".join(f"{row['left_pct']:.0f} remain after {row['stage'].replace('_', ' ')}"
                    for row in r["stages"][1:])
        + "."),
    "decline_drivers": lambda r: (
        f"{r['top'][0]['rule_id']} declines the most applicants on its own — "
        f"{r['top'][0]['declines_alone']:,} that no other rule catches, of "
        f"{r['top'][0]['declines']:,} it declines in total. {r['top'][0]['description']}"),
    "by_source": lambda r: (
        f"{r['top']['name']} produces {r['top']['share_of_all_declines']:.1f}% of all declines "
        f"from {r['top']['applicants']:,} applications, at a {r['top']['approval_rate']:.1f}% "
        f"approval rate."),
    "portfolio": lambda r: (
        f"The largest slice by exposure is {_slice(r['top']['name'])} at "
        f"{r['top']['share_of_exposure']:.1f}% of the book, with a "
        f"{r['top']['bad_rate']:.2f}% bad rate."),
    "concentration": lambda r: (
        ("Concentration flags: "
         + "; ".join(f"{_slice(f['slice'])} {f['flag']}" for f in r["flags"]) + ".")
        if r["flags"] else "No slice is materially over- or under-exposed."),
    "simulate": lambda r: (
        f"Moving {r['field']} from {r['from']:g} to {r['to']:g} takes the approval rate from "
        f"{_pct(r['approval_rate_before'])} to {_pct(r['approval_rate'])}, approving "
        f"{r['swap_in']:,} applicants who are currently declined. "
        + (f"Their estimated bad rate is {_pct(r['expected_bad_rate_after'], 2)} against a "
           f"booked {_pct(r['booked_bad_rate_before'], 2)}."
           if r["expected_bad_rate_known"] else
           f"The risk of that change cannot be estimated: {r['risk_verdict']}")),
    "swap_set": lambda r: (
        f"{r['swap_in']:,} applicants are newly approved and {r['swap_out']:,} newly declined. "
        f"The largest movement is in {_slice(r['largest']['name'])} with "
        f"{r['largest']['swap_in']:,} "
        f"newly approved. " + (r["risk_verdict"] or "")),
    "goal_seek": lambda r: (
        (f"{_pct(r['target'], 0)} approval is reachable. The cheapest option raises approvals to "
         f"{_pct(r['best']['approval_rate'])} for an estimated "
         f"{r['best']['risk_cost_pp']:+.2f} percentage points of bad rate.")
        if r["reached"] else
        (f"{_pct(r['target'], 0)} approval is not reachable with the changes available. The "
         f"closest is {_pct(r['best']['approval_rate'])}.")),
    "rules_not_earning_place": lambda r: (
        (f"{r['count']} rules cost approvals without buying safety. The largest is "
         f"{r['top'][0]['rule_id']}, which alone declines {r['top'][0]['declines_alone']:,} "
         f"applicants whose estimated bad rate of "
         f"{_pct(r['top'][0]['est_bad_rate_if_relaxed'], 1)} is no worse than the book's.")
        if r["count"] else "Every rule that can be judged earns its place."),
}
