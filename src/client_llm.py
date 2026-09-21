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

    def plan(self, turns: list[dict], catalogue: dict, current: list[dict], on_try=None) -> dict:
        """The scenario builder: a conversation in, one raw plan out (see `validate_plan`).

        A model provider answers from `plan_prompt`; `KeywordProvider` matches words, so the
        chat keeps working with no model and no network.
        """
        return _extract_json(self.converse(plan_prompt(catalogue, current), turns, PLAN_SCHEMA, on_try))

    def converse(self, system: str, turns: list[dict], schema: dict | None = None, on_try=None) -> str:
        """Several turns in, the model's reply out. `turns` are {"role": "user"|"assistant", "text"}.

        `on_try(model, why_previous_failed)` is called before each model is asked, so a caller can
        say which model it is waiting on. It is per call, not per provider: one provider serves
        every request the server is handling at once."""
        raise TranslationError(f"the {self.name} provider cannot hold a conversation")


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

    def plan(self, turns: list[dict], catalogue: dict, current: list[dict], on_try=None) -> dict:
        """The three requests a presenter can make by rote, so a dropped network is not a dead chat.

        "Reach 30% approval, bad rate under 11%" is a goal-seek; "SIMAH to 580" moves a cutoff;
        "switch off racAndPolicies#012" names a rule. Anything else is answered with how to ask.
        """
        q = turns[-1]["text"].lower() if turns else ""
        off = re.findall(r"\b([a-z_]+#\d+)", turns[-1]["text"], re.I) if turns else []
        if off and re.search(r"switch off|turn off|remove|drop|disable", q):
            known = {r["rule_id"].lower(): r["rule_id"] for r in catalogue.get("rules", [])}
            steps = [c for c in current if c.get("type") != "off" or c.get("rule_id") not in off]
            return {"action": "scenario",
                    "changes": steps + [{"type": "off", "rule_id": known.get(r.lower(), r)} for r in off]}
        for cut in catalogue.get("cutoffs", []):
            name = cut["label"].split()[0].lower()            # "SIMAH score cutoff" -> "simah"
            m = re.search(rf"{name}\D{{0,40}}?\b(\d{{3}})\b", q)
            if m:
                steps = [c for c in current if not (c.get("type") == "cutoff" and c.get("field") == cut["field"])]
                return {"action": "scenario",
                        "changes": steps + [{"type": "cutoff", "field": cut["field"], "to": float(m.group(1))}]}
        target = (re.search(r"(\d+(?:\.\d+)?)\s*%\s*(?:approv|acceptance)", q)
                  or re.search(r"(?:target|reach|get (?:\w+ )?to|approv\w*)\D{0,30}?(\d+(?:\.\d+)?)\s*%", q))
        if target:
            ceiling = re.search(r"bad[- ]rate\D{0,30}?(\d+(?:\.\d+)?)\s*%", q)
            return {"action": "goal_seek", "target": float(target.group(1)) / 100,
                    "ceiling": float(ceiling.group(1)) / 100 if ceiling else None, "frozen": []}
        return {"action": "clarify", "question": (
            "Without a language model I understand three kinds of request: a target "
            "(\"reach 30% approval with bad rate under 11%\"), a score cutoff (\"SIMAH to 580\"), "
            "or a rule by its ID (\"switch off racAndPolicies#012\"). Which do you want?")}


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
        return self.converse(system, [{"role": "user", "text": user}])

    def converse(self, system: str, turns: list[dict], schema: dict | None = None, on_try=None) -> str:
        if on_try:
            on_try(self.model, None)
        payload = {"model": self.model, "temperature": 0,
                   "messages": [{"role": "system", "content": system}]
                   + [{"role": "assistant" if t["role"] == "assistant" else "user",
                       "content": t["text"]} for t in turns]}
        if schema is not None:
            # JSON mode is the one structured-output switch vLLM, Ollama and llama.cpp all honour.
            payload["response_format"] = {"type": "json_object"}
        body = json.dumps(payload).encode()
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(f"{self.base_url}/chat/completions", body, headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read())
        except (urllib.error.URLError, TimeoutError) as exc:
            raise TranslationError(f"{self.base_url} unreachable: {_http_reason(exc)}") from exc
        try:
            return payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise TranslationError(f"{self.base_url} sent no reply") from None

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

    RETRY = {429, 500, 503, 504}
    """Overloaded or rate-limited: the next model may answer. Any other error (a bad key, a bad
    request) would fail the same way on every model, so it is reported at once."""

    def __init__(self, api_key: str | None = None, model: str = "gemini-3.6-flash",
                 timeout: float = 30.0, fallbacks: list[str] | tuple = (),
                 thinking: str | None = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.thinking = thinking               # Gemini 3's thinkingLevel; None leaves the model's default
        self.model = model
        self.fallbacks = tuple(m for m in fallbacks if m and m != model)
        self.timeout = timeout
        self.last_model: str | None = None     # which model answered the last call
        if not self.api_key:
            raise ValueError("no Gemini API key: pass api_key or set GEMINI_API_KEY")

    def _generate(self, system: str, user: str) -> str:
        return self.converse(system, [{"role": "user", "text": user}])

    def converse(self, system: str, turns: list[dict], schema: dict | None = None, on_try=None) -> str:
        """Ask the configured model, then each fallback in turn while they are overloaded."""
        config: dict[str, Any] = {"temperature": 0}
        if schema is not None:
            # Gemini's structured output: the reply is JSON of this shape, not prose around it.
            config.update(responseMimeType="application/json", responseSchema=schema)
        if self.thinking:
            # Picking rules from a list needs little reasoning; the default level spends seconds on it.
            config["thinkingConfig"] = {"thinkingLevel": self.thinking}
        body = json.dumps({
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "model" if t["role"] == "assistant" else "user",
                          "parts": [{"text": t["text"]}]} for t in turns],
            "generationConfig": config,
        }).encode()
        failures = []
        for model in (self.model, *self.fallbacks):
            if on_try:
                on_try(model, failures[-1] if failures else None)
            req = urllib.request.Request(
                f"{self.ENDPOINT}/{model}:generateContent", body,
                {"Content-Type": "application/json", "x-goog-api-key": self.api_key})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    payload = json.loads(resp.read())
            except urllib.error.HTTPError as exc:
                failures.append(f"{model}: {_http_reason(exc)}")
                if exc.code in self.RETRY:
                    continue
                break
            except (urllib.error.URLError, TimeoutError) as exc:
                failures.append(f"{model}: {_http_reason(exc)}")
                continue
            self.last_model = model
            try:
                return payload["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError, TypeError):
                # A blocked or empty answer has no candidate text; say why rather than a KeyError.
                why = (payload.get("promptFeedback") or {}).get("blockReason") or "no answer"
                raise TranslationError(f"Gemini sent no plan ({why})") from None
        raise TranslationError("Gemini unreachable: " + "; ".join(failures))

    def translate(self, question: str) -> dict:
        return _extract_json(self._generate(call_schema(), question))

    def phrase(self, prompt: str) -> str | None:
        try:
            return self._generate(NARRATION_SYSTEM, prompt).strip()
        except (TranslationError, KeyError, IndexError):
            return None


def _http_reason(exc: Exception) -> str:
    """An HTTP error with the service's own message (bad key, quota, unknown model), not just its code."""
    if isinstance(exc, urllib.error.HTTPError):
        try:
            detail = json.loads(exc.read() or b"{}").get("error") or {}
            message = detail.get("message") if isinstance(detail, dict) else str(detail)
        except (ValueError, OSError):
            message = None
        return f"HTTP {exc.code}" + (f": {message[:200]}" if message else "")
    return str(exc)


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


# --------------------------------------------------------------------------- scenario builder
# The chat on the Simulator screen. A person says what they want to achieve; the model answers
# with ONE plan, and the engine replays it. The same three properties hold as for the question
# catalogue: the format is closed, every rule and field is checked against the rules this
# product actually has, and no figure the person reads comes from the model.
PLAN_ACTIONS = ("scenario", "goal_seek", "clarify", "unsupported")
CHANGE_TYPES = ("off", "threshold", "cutoff")
MAX_TEXT = 400
"""A clarifying question or a refusal is a sentence, not an essay."""

PLAN_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": list(PLAN_ACTIONS)},
        "changes": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": list(CHANGE_TYPES)},
                "rule_id": {"type": "string"},
                "field": {"type": "string"},
                "value_low": {"type": "number"},
                "value_high": {"type": "number"},
                "to": {"type": "number"}},
            "required": ["type"]}},
        "target": {"type": "number"},
        "ceiling": {"type": "number"},
        "frozen": {"type": "array", "items": {"type": "string"}},
        "question": {"type": "string"},
        "reason": {"type": "string"}},
    "required": ["action"],
}
"""The plan, as Gemini's structured output takes it. Flat on purpose: one object whose `action`
says which of the other keys count, because a union of shapes is where models improvise."""


@dataclass(frozen=True)
class Plan:
    action: str
    changes: tuple = ()
    target: float | None = None
    ceiling: float | None = None
    frozen: tuple = ()
    text: str | None = None            # the clarifying question, or why it cannot be done

    def as_dict(self) -> dict:
        out: dict[str, Any] = {"action": self.action}
        if self.action == "scenario":
            out["changes"] = [dict(c) for c in self.changes]
        elif self.action == "goal_seek":
            out.update(target=self.target, ceiling=self.ceiling, frozen=list(self.frozen))
        else:
            out["question" if self.action == "clarify" else "reason"] = self.text
        return out


def _finite(value, what: str) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise TranslationError(f"{what}: {value!r} is not a number") from None
    if v != v or v in (float("inf"), float("-inf")):
        raise TranslationError(f"{what} must be a finite number")
    return v


def _rate(value, what: str) -> float:
    """A rate as a fraction. "30" and "0.30" both mean 30%, as the goal-seek form accepts."""
    v = _finite(value, what)
    v = v / 100 if v > 1 else v
    if not 0 < v <= 1:
        raise TranslationError(f"{what} must be between 0% and 100%")
    return v


def validate_plan(raw: dict, catalogue: dict) -> Plan:
    """Coerce a model's plan into one the engine can replay, or refuse it in words.

    `catalogue` is what the model was shown (`plan_prompt`): the changeable rules with their
    thresholds, the rules that may not be changed and why, and the score cutoffs. A rule or a
    field outside it is refused here, before the engine is asked, so the refusal can go back to
    the model once as a correction. The engine still checks everything again.
    """
    if not isinstance(raw, dict):
        raise TranslationError(f"expected an object, got {type(raw).__name__}")
    action = raw.get("action")
    if action not in PLAN_ACTIONS:
        raise TranslationError(f"{action!r} is not one of {list(PLAN_ACTIONS)}")

    if action in ("clarify", "unsupported"):
        text = raw.get("question" if action == "clarify" else "reason")
        if not isinstance(text, str) or not text.strip():
            raise TranslationError(f"{action} needs a sentence to show the person")
        return Plan(action=action, text=text.strip()[:MAX_TEXT])

    rules = {r["rule_id"]: r for r in catalogue.get("rules", [])}
    fixed = {r["rule_id"]: r for r in catalogue.get("fixed", [])}

    def rule(rid) -> dict:
        if rid in rules:
            return rules[rid]
        if rid in fixed:
            raise TranslationError(f"{rid} ({fixed[rid]['name']}) cannot be changed: {fixed[rid]['reason']}")
        raise TranslationError(f"{rid!r} is not a rule of this product")

    if action == "goal_seek":
        ceiling = raw.get("ceiling")
        frozen = raw.get("frozen") or []
        if not isinstance(frozen, list):
            raise TranslationError("frozen must be a list of rule IDs")
        for rid in frozen:
            rule(rid)
        return Plan(action=action, target=_rate(raw.get("target"), "target"),
                    ceiling=None if ceiling is None else _rate(ceiling, "ceiling"),
                    frozen=tuple(dict.fromkeys(str(r) for r in frozen)))

    changes = raw.get("changes")
    if not isinstance(changes, list) or not changes:
        raise TranslationError("a scenario needs at least one change")
    limit = int(catalogue.get("max_changes", 12))
    if len(changes) > limit:
        raise TranslationError(f"at most {limit} changes in one scenario")
    cutoffs = {c["field"]: c for c in catalogue.get("cutoffs", [])}
    out = []
    for i, ch in enumerate(changes, 1):
        if not isinstance(ch, dict) or ch.get("type") not in CHANGE_TYPES:
            raise TranslationError(f"change {i}: type must be one of {list(CHANGE_TYPES)}")
        kind = ch["type"]
        if kind == "off":
            out.append({"type": "off", "rule_id": rule(ch.get("rule_id"))["rule_id"]})
        elif kind == "cutoff":
            cut = cutoffs.get(ch.get("field"))
            if cut is None:
                raise TranslationError(f"change {i}: {ch.get('field')!r} is not a score cutoff of this "
                                       f"product; the cutoffs are {sorted(cutoffs)}")
            # `from` is where today's rules test the score, which the model has no business choosing.
            out.append({"type": "cutoff", "field": cut["field"], "from": cut["from"],
                        "to": _finite(ch.get("to"), f"change {i}: to")})
        else:
            r = rule(ch.get("rule_id"))
            # A rule that tests one field leaves nothing to choose; smaller models drop the field.
            field_name = ch.get("field") or (r["thresholds"][0]["field"] if len(r["thresholds"]) == 1 else None)
            t = next((t for t in r["thresholds"] if t["field"] == field_name), None)
            if t is None:
                raise TranslationError(f"change {i}: {r['rule_id']} has no threshold on {field_name!r}; "
                                       f"it has {[t['field'] for t in r['thresholds']]}")
            step = {"type": "threshold", "rule_id": r["rule_id"], "field": t["field"]}
            for key in ("value_low", "value_high"):
                if ch.get(key) is not None:
                    step[key] = _finite(ch[key], f"change {i}: {key}")
            if "value_high" in step and t.get("value_high") is None:
                raise TranslationError(f"change {i}: {r['rule_id']} tests {t['field']} against one value, "
                                       f"so give value_low only")
            if len(step) == 3:
                raise TranslationError(f"change {i}: give the new value_low (and value_high for a range)")
            out.append(step)
    return Plan(action="scenario", changes=tuple(out))


OPERATOR_WORDS = {"lt": "declines below", "lte": "declines at or below",
                  "gt": "declines above", "gte": "declines at or above",
                  "between": "declines inside", "outside": "declines outside"}


def _threshold_words(t: dict) -> str:
    rng = (f"{t['value_low']:g}–{t['value_high']:g}" if t.get("value_high") is not None
           else f"{t['value_low']:g}")
    return f"{t['field']} ({t.get('label') or t['field']}) {t['operator']} {rng}"


def plan_prompt(catalogue: dict, current: list[dict]) -> str:
    """The system prompt for the scenario builder. Built from the engine's own rule list, per request."""
    pct = lambda v: "unknown" if v is None else f"{v * 100:.1f}%"  # noqa: E731
    limit = int(catalogue.get("max_changes", 12))
    lines = [
        f"You are the scenario builder in Azentio's Credit Strategy Optimiser, for the product "
        f"{catalogue.get('product')}. A bank's risk team tells you in plain language what they want "
        f"to achieve with their credit decline rules. You translate that into ONE JSON plan. The "
        f"engine replays the plan against the applicants and computes every figure: never state, "
        f"estimate or promise a result.",
        "",
        "Actions:",
        '- "scenario": "changes" is the COMPLETE list of changes to replay. It replaces the current '
        "scenario, so keep the current changes unless the person asks to drop or alter them. Change types:",
        '    {"type":"off","rule_id":"<id>"}  switch a rule off (lets more applicants through)',
        '    {"type":"threshold","rule_id":"<id>","field":"<field>","value_low":n,"value_high":n}  '
        "set a rule's threshold, in either direction. value_high only for a range (between/outside)",
        '    {"type":"cutoff","field":"<field>","to":n}  move a score cutoff for every rule that tests it',
        '- "goal_seek": when they name an outcome but not the changes, such as a target approval rate '
        "or a bad-rate ceiling. target and ceiling are fractions (0.30 is 30%). A relative ask "
        '("5 points more approval") is added to today\'s rate. "frozen" lists rule IDs the search must not touch.',
        '- "clarify": "question" is one short question, when the request is ambiguous (several rules '
        "could match, no number given). Asking is better than guessing.",
        '- "unsupported": "reason" says why, when the request is outside the above: a rule that may '
        "not be changed, a question about the data rather than a change, or advice on what the bank "
        "should do.",
        "",
        "Rules for the plan:",
        "- Use only rule IDs and fields listed below, spelled exactly. Never change a rule listed under "
        "\"may not be changed\".",
        f"- At most {limit} changes. One change per rule threshold and one per cutoff.",
        "- A threshold \"declines below\" a value lets more through when the value is lowered; one "
        "that \"declines above\" lets more through when it is raised; a range lets more through when "
        "it narrows (inside) or widens (outside). Loosen means let more through; tighten means fewer.",
        "- When a person names a rule by its description, match it to the ID below. If two or more fit, clarify.",
        "",
        f"Today: approval rate {pct(catalogue.get('approval_rate'))}, booked bad rate "
        f"{pct(catalogue.get('booked_bad_rate'))}, bad-rate limit {pct(catalogue.get('bad_rate_ceiling'))}.",
        "",
        "Score cutoffs (field | name | today | values the screen offers):",
    ]
    for c in catalogue.get("cutoffs", []):
        lines.append(f"  {c['field']} | {c['label']} | {c['from']:g} | "
                     + ", ".join(f"{v:g}" for v in c.get("values", [])))
    lines += ["", "Rules that may be changed (rule_id | name | stage | declines when | applies to | "
              "declines on its own | thresholds as field operator value):"]
    for r in catalogue.get("rules", []):
        lines.append(" | ".join([r["rule_id"], r["name"], r.get("stage") or "", r.get("when") or "",
                                 r.get("applies_to") or "all applicants", str(r.get("declines_alone", "")),
                                 "; ".join(_threshold_words(t) for t in r["thresholds"]) or "none"]))
    if catalogue.get("fixed"):
        lines += ["", "Rules that may not be changed (rule_id | name | why):"]
        lines += [f"  {r['rule_id']} | {r['name']} | {r['reason']}" for r in catalogue["fixed"]]
    lines += ["", "Current scenario: " + (json.dumps(current) if current else "none, today's rules")]
    return "\n".join(lines)
