"""Export the fixture for the three CxO screens (plan step 5).

    python -m ui.client_export                 # full, including the goal-seek runs
    python -m ui.client_export --quick         # skips goal-seek and the scenario grid

One payload per precomputed context: every product the data carries, over each period preset
(config `analysis.presets`, plus all applications). The default context sits at the top level,
the rest under `contexts`, and `context_menu` tells the period and product controls what exists.
A custom range needs the live engine, which serves the same payload at `/api/view`.

The UI computes nothing. Every figure on the three screens comes from this file, and this
file computes nothing either: it calls the same functions the CLIs and the tests call. The
prototype has no backend yet, so scenarios are precomputed; when an API lands, the same keys
are served live from `simulate()` and `goal_seek()`.

Each figure carries a provenance tag, because that is the only thing colour encodes:

    OBSERVED      counted from the data — applicants, declines, booked performance
    PREDICTED     the PD model, inside the population it was trained on
    INFERRED      reject inference — swap-ins the bank has never seen repay
    NOT_MODELLED  refused. The group sits outside anything the bank has booked.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from src import client_analysis as A, client_api as API, client_context as C, client_policy
from src.client_generate import load_client_config
from src.client_view import clean, build_view  # noqa: F401 — `clean` is part of this module's API
from src.config import resolve_path
from src.rule_inventory import build_inventory

HERE = Path(__file__).resolve().parent


def context_id(product: str, preset: str) -> str:
    return f"{product}:{preset}"


def context_menu(cache) -> dict:
    """What the period and product controls offer, per product, with each preset's context id."""
    products = {}
    for p in cache.products():
        lo, hi = C.data_range(cache.product_df(p))
        presets = [{**w, "context": context_id(p, w["id"])} for w in API.window_presets(cache, p)]
        products[p] = {"data_range": {"app_from": f"{lo:%Y-%m-%d}", "app_to": f"{hi:%Y-%m-%d}"},
                       "presets": presets}
    default = cache.cfg["analysis"]["default_window"]["last_months"]
    bd = A.bad_definition(cache.cfg)
    return {"default_product": cache.cfg["product"],
            "default_context": context_id(cache.cfg["product"], f"last_{default}m"),
            "products": products,
            "outcome": {"as_of": f"{bd['as_of']:%Y-%m-%d}", "dpd": bd["dpd"],
                        "within_months": bd["within_months"]}}


def build(cfg: dict, inv, *, quick: bool = False) -> dict:
    cache = C.ContextCache(pd.read_parquet(resolve_path(cfg["data_path"])), inv, cfg)
    menu = context_menu(cache)
    payload, contexts = None, {}
    for product, spec in menu["products"].items():
        for preset in spec["presets"]:
            print(f"{preset['context']}  ({preset['label']})", flush=True)
            base = cache.baseline(C.AnalysisWindow.from_dict(preset), product)
            view = build_view(base, inv, quick=quick, log=lambda m: print(m, flush=True))
            view["meta"]["context"] = preset["context"]
            view["meta"]["preset"] = preset["id"]
            if preset["context"] == menu["default_context"]:
                payload = view
            else:
                contexts[preset["context"]] = view
    if payload is None:
        raise SystemExit(f"the default context {menu['default_context']} was not built")
    payload["contexts"] = contexts
    payload["context_menu"] = menu
    return payload


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Export the fixture for ui/client.html")
    ap.add_argument("--out", default=str(HERE / "client_fixture.json"))
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args(argv)

    # The config file plus every approved setting (src/client_policy.py), as the engine loads it.
    file_cfg = load_client_config()
    cfg = client_policy.PolicyStore(resolve_path(file_cfg["policy"]["path"])).effective(file_cfg)
    payload = build(cfg, build_inventory(cfg["replay"]["rules_folder"]), quick=args.quick)

    out = Path(args.out)
    out.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    js = out.with_name("client_data.js")
    js.write_text("window.__CLIENT__ = " + json.dumps(payload, ensure_ascii=False) + ";\n",
                  encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size // 1024} KB) and {js.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
