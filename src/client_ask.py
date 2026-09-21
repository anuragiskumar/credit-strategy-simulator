"""Ask the engine a question in plain English (plan step 6).

    python -m src.client_ask "which rules cost approvals without reducing risk?"

This is the orchestration: `client_llm` translates, this module executes, `client_llm` narrates.
The split matters — `client_llm` has no engine dependency at all, so the call format can be
tested, reviewed and handed to whoever builds the assistant without pulling in pandas.

Every figure in every answer comes from the same functions the screens and the CLIs use.
The LLM chooses which question is being asked; it never computes and never decides.
"""
from __future__ import annotations

import argparse
import json
import sys

import pandas as pd

from src import client_analysis as A, client_llm, client_optimise as O, client_simulate as S
from src.client_replay import locked_rules
from src.config import resolve_path
from src.client_generate import load_client_config
from src.rule_inventory import build_inventory


def _top_row(frame: pd.DataFrame, name_col: str) -> dict:
    row = frame.reset_index().iloc[0]
    out = {k: (v.item() if hasattr(v, "item") else v) for k, v in row.items()}
    out["name"] = str(row[name_col] if name_col in row else row.iloc[0])
    return out


def execute(call: client_llm.EngineCall, base: S.Baseline, inv, cfg: dict) -> dict:
    """Run one validated call against the engine. Returns plain JSON-able values."""
    df, outcome, res, p = base.df, base.outcome, base.res, call.params
    intent = call.intent

    if intent == "approval_rate":
        return {"approval_rate": base.approval_rate, "booked": int(outcome["booked"].sum()),
                "applicants": int(len(df)),
                "base": "all applications received, not only those that reached a decision"}

    if intent == "funnel":
        return {"stages": A.funnel(df, outcome).to_dict("records")}

    if intent in ("decline_drivers", "rules_not_earning_place"):
        drivers = A.decline_drivers(df, res, outcome, cfg, model=base.model,
                                    booked_bad_rate=base.booked_bad_rate)
        if intent == "decline_drivers":
            top = drivers.head(p["top"])
        else:
            top = drivers[(drivers["earns_its_place"] == False)  # noqa: E712
                          & drivers["relaxable"]].head(p["top"])
        keep = ["rule_id", "policy_code", "description", "declines", "declines_alone",
                "sole_reason_pct", "est_bad_rate_if_relaxed", "risk_known", "earns_its_place"]
        cols = [c for c in keep if c in top.columns]
        return {"count": int(len(top)), "booked_bad_rate": base.booked_bad_rate,
                "top": top[cols].to_dict("records")}

    if intent == "by_source":
        table = A.by_source(df, outcome, p["column"])
        return {"column": p["column"], "top": _top_row(table, p["column"]),
                "rows": table.reset_index().to_dict("records")}

    if intent == "portfolio":
        book = S.portfolio(base, p["slice"])
        return {"slice": p["slice"], "top": _top_row(book, p["slice"]),
                "rows": book.reset_index().to_dict("records")}

    if intent == "concentration":
        book = S.portfolio(base, p["slice"])
        return {"slice": p["slice"],
                "flags": A.concentration_flags(book, cfg).to_dict("records")}

    if intent in ("simulate", "swap_set"):
        lever = S.field_lever(inv, p["field"], p["from"], p["to"], product=cfg["product"],
                              locked=locked_rules(cfg))
        result = S.simulate(base, inv, lever)
        out = {k: v for k, v in result.items() if not k.startswith("_")}
        out.update({"field": p["field"], "from": p["from"], "to": p["to"]})
        if intent == "swap_set":
            profile = S.swap_set_profile(base, result, p["by"])
            out["by"] = p["by"]
            out["largest"] = _top_row(profile, p["by"])
            out["rows"] = profile.reset_index().to_dict("records")
        return out

    if intent == "goal_seek":
        table = O.goal_seek(base, inv, p["target"], cfg)
        options = table.to_dict("records")
        return {"target": p["target"], "reached": bool(table.attrs.get("reached")),
                "ceiling": table.attrs.get("ceiling"),
                "best": options[0] if options else None, "options": options}

    raise client_llm.TranslationError(f"no executor for intent {intent!r}")


def ask(question: str, base: S.Baseline, inv, cfg: dict,
        provider: client_llm.Provider | None = None,
        narrator: client_llm.Provider | None = None) -> dict:
    """Plain English in, narrated result out. The whole loop, in one call."""
    call = client_llm.parse(question, provider)
    result = execute(call, base, inv, cfg)
    narration = client_llm.narrate(call, result, narrator)
    return {"question": question, "call": call.as_dict(), "result": result,
            "answer": narration["text"], "narrated_by": narration["source"],
            "narration_rejected": narration["rejected"]}


def build_provider(kind: str, **kw) -> client_llm.Provider | None:
    """`none` and `keyword` need no model, which is the point of the layer being thin."""
    if kind in ("none", "keyword"):
        return client_llm.KeywordProvider()
    if kind == "http":
        return client_llm.HTTPProvider(base_url=kw["base_url"], model=kw["model"],
                                   api_key=kw.get("api_key"))
    if kind == "gemini":
        return client_llm.GeminiProvider(model=kw.get("model") or "gemini-2.5-flash")
    raise ValueError(f"unknown provider {kind!r}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Ask the engine a question in plain English.")
    ap.add_argument("question", nargs="*", help="omit to list the questions it answers")
    ap.add_argument("--provider", default="keyword",
                    choices=["keyword", "none", "http", "gemini"],
                    help="keyword needs no model at all (the default)")
    ap.add_argument("--base-url", help="OpenAI-compatible endpoint, for on-prem")
    ap.add_argument("--model", help="model name for --provider http/gemini")
    ap.add_argument("--narrate", action="store_true",
                    help="let the provider phrase the answer (numbers are still verified)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if not args.question:
        print(client_llm.call_schema())
        return 0

    cfg = load_client_config()
    inv = build_inventory(cfg["replay"]["rules_folder"])
    df = pd.read_parquet(resolve_path(cfg["data_path"]))
    base = S.build_baseline(df, inv, cfg)

    provider = build_provider(args.provider, base_url=args.base_url, model=args.model)
    narrator = provider if args.narrate and args.provider not in ("keyword", "none") else None
    out = ask(" ".join(args.question), base, inv, cfg, provider, narrator)

    if args.json:
        json.dump(out, sys.stdout, indent=2, default=str)
        print()
    else:
        print(f"call    {out['call']['intent']}  {out['call']['params']}")
        print(f"answer  {out['answer']}")
        print(f"        [narrated by {out['narrated_by']}]", file=sys.stderr)
        if out["narration_rejected"]:
            print(f"        [fell back: {out['narration_rejected']}]", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
