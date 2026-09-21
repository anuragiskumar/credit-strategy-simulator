"""The thin LLM layer (step 6).

The layer's value is entirely in what it refuses to do. These tests are mostly about that:
a model cannot invent an intent, cannot invent a number, and cannot soften a refusal into a
confident answer. None of them needs a network — `KeywordProvider` needs no model at all,
which is also why phase 1 of the demo can ship without one.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src import client_ask, client_llm
from src.client_generate import generate, load_client_config
from src.client_llm import EngineCall, INTENTS, KeywordProvider, TranslationError
from src.rule_inventory import build_inventory
from src import client_simulate as S

REPO = Path(__file__).resolve().parents[1]
HAS_RULES = bool(list(REPO.glob("business-rules-*.xlsx")))


# --------------------------------------------------------------------------- call format
def test_the_call_format_is_the_frozen_question_catalogue():
    """Ten questions in the brief; ten intents. The engine answers those and says no to more."""
    assert len(INTENTS) == 10
    for name, spec in INTENTS.items():
        assert spec["question"].endswith("?"), name
        assert isinstance(spec["params"], dict)


@pytest.mark.parametrize("question, intent", [
    ("what is my approval rate?", "approval_rate"),
    ("where do applicants drop out, stage by stage?", "funnel"),
    ("which rule declines the most applicants on its own?", "decline_drivers"),
    ("which channel produces the most declines?", "by_source"),
    ("how does my portfolio split by sector?", "portfolio"),
    ("where am I over-exposed?", "concentration"),
    ("if I lower the SIMAH cutoff from 600 to 560 what happens?", "simulate"),
    ("who newly gets approved by channel?", "swap_set"),
    ("how do I get to 30% approval?", "goal_seek"),
    ("which rules cost approvals without reducing risk?", "rules_not_earning_place"),
])
def test_every_catalogue_question_translates_without_a_model(question, intent):
    assert client_llm.parse(question).intent == intent


def test_a_question_outside_the_catalogue_is_refused_with_the_list():
    with pytest.raises(TranslationError) as exc:
        client_llm.parse("what is the weather in Riyadh?")
    assert "approval rate" in str(exc.value)


def test_parameters_are_read_out_of_the_question():
    call = client_llm.parse("how do I get to 30% approval?")
    assert call.params["target"] == pytest.approx(0.30)
    call = client_llm.parse("if I move CRIF from 605 to 580?")
    assert call.params == {"field": "crifscore", "from": 605.0, "to": 580.0}


# --------------------------------------------------------------------------- validation
def test_an_invented_intent_is_rejected():
    with pytest.raises(TranslationError, match="not one of"):
        client_llm.validate_call({"intent": "approve_everyone", "params": {}})


def test_an_invented_parameter_is_rejected():
    with pytest.raises(TranslationError, match="unknown parameter"):
        client_llm.validate_call({"intent": "funnel", "params": {"ignore_risk": True}})


def test_a_value_outside_the_allowed_set_is_rejected():
    with pytest.raises(TranslationError, match="is not one of"):
        client_llm.validate_call({"intent": "portfolio", "params": {"slice": "religion"}})


def test_a_parameter_outside_its_range_is_rejected():
    with pytest.raises(TranslationError, match="above maximum"):
        client_llm.validate_call({"intent": "goal_seek", "params": {"target": 1.5}})


def test_defaults_fill_what_the_question_did_not_say():
    call = client_llm.validate_call({"intent": "decline_drivers"})
    assert call.params == {"top": 5}


def test_the_schema_prompt_lists_every_intent():
    schema = client_llm.call_schema()
    for name in INTENTS:
        assert name in schema
    assert "Never invent a number" in schema


@pytest.mark.parametrize("text", [
    '{"intent": "funnel", "params": {}}',
    '```json\n{"intent": "funnel", "params": {}}\n```',
    'Sure! Here is the call:\n{"intent": "funnel", "params": {}}\nHope that helps.',
])
def test_json_is_recovered_from_however_the_model_wrapped_it(text):
    assert client_llm._extract_json(text)["intent"] == "funnel"


def test_a_reply_with_no_json_is_an_error():
    with pytest.raises(TranslationError, match="no JSON"):
        client_llm._extract_json("I am not able to help with that.")


# --------------------------------------------------------------------------- number guard
def test_a_number_the_engine_never_produced_is_caught():
    allowed = client_llm._numbers_in({"approval_rate": 0.2111, "booked": 10555})
    assert client_llm.verify_numbers("approval is 34.7%", allowed) == ["34.7"]
    assert client_llm.verify_numbers("we booked 12,900 loans", allowed) == ["12,900"]


def test_a_thousands_separator_is_not_mistaken_for_two_numbers():
    """Regression: "10,555" read as 10 and 555 rejected every faithful narration."""
    allowed = client_llm._numbers_in({"approval_rate": 0.2111, "booked": 10555})
    assert client_llm.verify_numbers("approval is 21.1% on 10,555 loans", allowed) == []


class _InventingProvider(client_llm.Provider):
    name = "inventing"

    def translate(self, question):
        return {"intent": "approval_rate", "params": {}}

    def phrase(self, prompt):
        return "Approvals are running at 44.9%, well ahead of plan."


class _FaithfulProvider(_InventingProvider):
    name = "faithful"

    def phrase(self, prompt):
        return "Just 21.1% of applications were approved."


def test_a_model_that_invents_a_figure_is_overruled_by_the_template():
    call = EngineCall("approval_rate", {})
    result = {"approval_rate": 0.2111, "booked": 10555, "applicants": 50000,
              "base": "all applications"}
    out = client_llm.narrate(call, result, _InventingProvider())
    assert out["source"] == "template"
    assert "44.9" in out["rejected"]
    assert "21.1%" in out["text"]


def test_a_faithful_rephrasing_is_kept():
    call = EngineCall("approval_rate", {})
    result = {"approval_rate": 0.2111, "booked": 10555, "applicants": 50000,
              "base": "all applications"}
    out = client_llm.narrate(call, result, _FaithfulProvider())
    assert out["source"] == "faithful"
    assert out["rejected"] is None


def test_no_provider_means_the_template_and_no_network():
    out = client_llm.narrate(EngineCall("funnel", {}),
                         {"stages": [{"stage": "applied", "left_pct": 100.0},
                                     {"stage": "hard_reject", "left_pct": 80.0}]})
    assert out["source"] == "template"
    assert "80 remain after hard reject" in out["text"]


def test_a_refusal_survives_narration():
    """The one thing a fluent model is most likely to smooth away."""
    result = {"field": "income", "from": 3500, "to": 3000, "approval_rate_before": 0.2111,
              "approval_rate": 0.2148, "swap_in": 184, "expected_bad_rate_known": False,
              "expected_bad_rate_after": None, "booked_bad_rate_before": 0.0828,
              "risk_verdict": "unknown — 39% of this group is unlike anything the bank has booked"}
    out = client_llm.narrate(EngineCall("simulate", result), result)
    assert "cannot be estimated" in out["text"]
    assert "unknown" in out["text"]


# --------------------------------------------------------------------------- providers
def test_providers_are_swappable_without_touching_the_call_format():
    http = client_llm.HTTPProvider(base_url="http://localhost:8000/v1", model="qwen")
    assert http.name == "http" and http.base_url == "http://localhost:8000/v1"
    assert isinstance(client_ask.build_provider("keyword"), KeywordProvider)
    assert isinstance(client_ask.build_provider("none"), KeywordProvider)


def test_an_unreachable_on_prem_endpoint_fails_loudly_not_silently():
    http = client_llm.HTTPProvider(base_url="http://127.0.0.1:9/v1", model="x", timeout=0.4)
    with pytest.raises(TranslationError, match="unreachable"):
        http.translate("what is my approval rate?")


def test_a_missing_gemini_key_is_an_error_at_construction(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        client_llm.GeminiProvider()


def test_an_unreachable_narrator_falls_back_to_the_template():
    http = client_llm.HTTPProvider(base_url="http://127.0.0.1:9/v1", model="x", timeout=0.4)
    out = client_llm.narrate(EngineCall("approval_rate", {}),
                         {"approval_rate": 0.2, "booked": 10, "applicants": 50,
                          "base": "all"}, http)
    assert out["source"] == "template"


# --------------------------------------------------------------------------- end to end
@pytest.mark.skipif(not HAS_RULES, reason="client rule files not present")
class TestAgainstTheEngine:
    @pytest.fixture(scope="class")
    @classmethod
    def wired(cls):
        cfg = load_client_config(overrides={"n_rows": 20_000})
        inv = build_inventory(REPO)
        return S.build_baseline(generate(cfg), inv, cfg), inv, cfg

    @pytest.mark.parametrize("question", [
        "what is my approval rate?",
        "where do applicants drop out?",
        "which rule declines the most applicants on its own?",
        "which channel produces the most declines?",
        "how does my portfolio split by sector?",
        "where am I over-exposed?",
        "if I lower the SIMAH cutoff from 600 to 560 what happens?",
        "who newly gets approved by channel?",
        "which rules cost approvals without reducing risk?",
    ])
    def test_every_question_produces_a_sentence_backed_by_the_engine(self, wired, question):
        base, inv, cfg = wired
        out = client_ask.ask(question, base, inv, cfg)
        assert out["answer"] and not out["answer"].startswith("{")
        assert out["narrated_by"] == "template"
        json.dumps(out["result"], default=str)     # must be serialisable for an API

    def test_the_narrated_figure_matches_the_engine(self, wired):
        base, inv, cfg = wired
        out = client_ask.ask("what is my approval rate?", base, inv, cfg)
        assert f"{base.approval_rate * 100:.1f}%" in out["answer"]

    def test_goal_seek_through_the_layer_respects_the_ceiling(self, wired):
        base, inv, cfg = wired
        small = {**cfg, "optimise": {**cfg["optimise"], "beam_width": 1, "max_depth": 1,
                                     "max_rule_candidates": 3, "field_moves": []}}
        out = client_ask.ask("how do I get to 24% approval?", base, inv, small)
        assert out["call"]["params"]["target"] == pytest.approx(0.24)
        assert "ceiling" in out["result"]

    def test_the_layer_never_reads_the_hidden_truth(self, wired):
        """`latent_bad` is not available to a real bank; no answer may contain it."""
        base, inv, cfg = wired
        out = client_ask.ask("which rules cost approvals without reducing risk?", base, inv, cfg)
        assert "oracle" not in json.dumps(out["result"], default=str).lower()
        assert "latent" not in json.dumps(out["result"], default=str).lower()
