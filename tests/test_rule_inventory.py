"""The inventory is the engine's input format, so the parser is tested per operator.

The workbook-level tests are skipped when the client's files are absent: they are not in the
repo and must not be, until sharing is confirmed under the NDA.
"""
from pathlib import Path

import pytest

from src.rule_inventory import (build_inventory, classify_field, english_description,
                                find_dead_columns, parse_condition)

REPO = Path(__file__).resolve().parents[1]
HAS_FILES = bool(list(REPO.glob("business-rules-*.xlsx")))
needs_files = pytest.mark.skipif(not HAS_FILES, reason="client rule files not present")


@pytest.fixture(scope="module")
def inventory():
    return build_inventory(REPO)


# --------------------------------------------------------------------------- parser
@pytest.mark.parametrize("raw, operator, low, high, values", [
    ("<600", "lt", 600.0, None, ()),
    (">=3500", "gte", 3500.0, None, ()),
    ("<=605", "lte", 605.0, None, ()),
    (">20000", "gt", 20000.0, None, ()),
    ("[348.1..368]", "between", 348.1, 368.0, ()),
    ("[0..530]", "between", 0.0, 530.0, ()),
    ("20 > age or age > 60", "outside", 20.0, 60.0, ()),
    ("<12,>60", "outside", 12.0, 60.0, ()),
    ("<25, >70", "outside", 25.0, 70.0, ()),
    ("4*income<loanAmount", "income_multiple_exceeded", 4.0, None, ()),
    ("10*income", "income_multiple", 10.0, None, ()),
    ("150000", "eq", 150000.0, None, ()),
    ('"ST","SMG","PVTL"', "in", None, None, ("ST", "SMG", "PVTL")),
    ('not("ONP","OP")', "not_in", None, None, ("ONP", "OP")),
    ('not("SAU")', "not_in", None, None, ("SAU",)),
    ("true", "eq", None, None, ("true",)),
    ("MSSGNOAS", "in", None, None, ("MSSGNOAS",)),
])
def test_parse_condition_covers_the_source_grammar(raw, operator, low, high, values):
    (c,) = parse_condition("someField", raw)
    assert (c.operator, c.low, c.high, c.values) == (operator, low, high, values)


def test_blank_and_dash_cells_yield_no_condition():
    assert parse_condition("f", "") == []
    assert parse_condition("f", "-") == []


def test_saudi_and_not_saudi_is_reported_as_a_tautology():
    (c,) = parse_condition("nationality", '"SAU", not("SAU")')
    assert c.operator == "always"


def test_not_list_records_that_null_is_excluded():
    (c,) = parse_condition("employerName", 'not("GOSI","GOSI Taqdeer",null)')
    assert c.operator == "not_in" and c.values == ("GOSI", "GOSI Taqdeer")
    assert "null" in c.note


def test_bilingual_description_splits_into_english_and_arabic():
    en, ar = english_description('if(lang!=null and lang="ar")then "عربي" else "English text"')
    assert (en, ar) == ("English text", "عربي")


def test_plain_description_is_returned_unchanged():
    assert english_description('"Age is not between 20 or 60"') == ("Age is not between 20 or 60", "")


# --------------------------------------------------------------------------- tagging
@pytest.mark.parametrize("field_name, tag", [
    ("simahCreditScore", "tunable"),
    ("crifScore", "tunable"),
    ("netIncome.totalIncome", "tunable"),
    ("age", "tunable"),
    ("customerSegment", "scope"),
    ("product", "scope"),
    ("nationality", "fixed"),
    ("politicallyExposedPerson", "fixed"),
    ("queryResultAl.V_SIM_JUDGEMENT_CNT", "fixed"),
    ("number(queryResultAl.V_SIMAH_LATEST_DEL_NEW)", "fixed"),
])
def test_fields_are_tagged_scope_fixed_or_tunable(field_name, tag):
    assert classify_field(field_name) == tag


# --------------------------------------------------------------------------- workbooks
@needs_files
def test_every_policy_rule_in_the_four_files_is_captured(inventory):
    counts = inventory.rules.groupby("table").size().to_dict()
    assert counts["racAndPolicies"] == 260
    assert counts["simahRulesValidateAl"] == 31
    assert counts["simati_chk_IAF"] == 31
    assert counts["yknBasicCheckValidation"] == 15


@needs_files
def test_the_two_extra_decision_tables_are_captured_too(inventory):
    """The brief's count of 337 misses these; the engine must not."""
    counts = inventory.rules.groupby("table").size().to_dict()
    assert counts["yakeen-post-validation"] == 3
    assert counts["employer_keyword_check"] == 62


@needs_files
def test_no_condition_is_left_unparsed(inventory):
    unparsed = inventory.conditions[inventory.conditions.operator == "unparsed"]
    assert unparsed.empty, unparsed[["rule_id", "field", "raw"]].to_string()


@needs_files
def test_every_rule_has_an_outcome(inventory):
    assert inventory.rules["outcome"].notna().all()


@needs_files
def test_ten_simah_rules_are_switched_off(inventory):
    simah = inventory.rules[inventory.rules.table == "simahRulesValidateAl"]
    assert (~simah["is_active"]).sum() == 10


@needs_files
def test_exception_rules_split_into_amount_caps_and_eligibility_limits(inventory):
    """The brief calls all 223 Exception rows amount caps; 97 of them are not."""
    exc = inventory.rules[inventory.rules.outcome == "Exception"]
    kinds = exc["exception_kind"].value_counts().to_dict()
    assert kinds["amount_cap"] == 126
    assert kinds["eligibility_limit"] == 97
    assert exc[exc.exception_kind == "amount_cap"]["cap_amount"].notna().all()


@needs_files
def test_non_exception_rules_have_no_exception_kind(inventory):
    other = inventory.rules[inventory.rules.outcome != "Exception"]
    assert other["exception_kind"].isna().all()


@needs_files
def test_conflicts_include_the_known_age_band_contradiction(inventory):
    """yknBasicCheckValidation caps G/SG at 60 in one row and 70 in another."""
    overlaps = inventory.conflicts[inventory.conflicts.kind == "overlapping_band"]
    ykn = overlaps[overlaps.table == "yknBasicCheckValidation"]
    assert not ykn.empty
    assert any("20..60" in d and "30..70" in d for d in ykn["detail"])


@needs_files
def test_dead_columns_are_reported(inventory):
    dead = find_dead_columns(REPO)
    assert "ntb" in set(dead["column"])


def test_redaction_replaces_configured_terms_in_descriptions(tmp_path, monkeypatch):
    """Rule text can name the client; it must be scrubbed before it reaches any fixture."""
    from src import rule_inventory as ri

    terms = tmp_path / "redactions.yaml"
    terms.write_text("Acme: Bank\n", encoding="utf-8")
    monkeypatch.setattr(ri, "REDACTIONS_PATH", terms)
    ri._redactions.cache_clear()
    try:
        assert ri.english_description('"PF - ACME Staff not allowed"')[0] == "PF - Bank Staff not allowed"
        assert ri.english_description('"Acmeville is not a match"')[0] == "Acmeville is not a match"
    finally:
        ri._redactions.cache_clear()
