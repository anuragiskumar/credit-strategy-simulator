# `ui/` — web prototype

A clickable front end for the engine, built to be shown to an executive audience and to serve as
the design specification for the T2 served front end (REQUIREMENTS.md §18.4).

## Why this exists

Streamlit is correct for T0/T1 and wrong from T2 onward — no real session model, no per-widget
authorisation, and a security posture no bank will accept for a multi-user internal application.
The Streamlit app in `app/` is unchanged and still runs; this is the replacement it migrates to.

## The design rule

**Colour encodes provenance and nothing else.** The chrome is achromatic; the only chroma on any
screen tells you the epistemic status of a figure — `OBSERVED`, `PREDICTED`, `INFERRED`,
`NOT_MODELLED`. Magnitude (heatmap density, coefficient bars) is drawn in ink so it never competes.
`NOT_MODELLED` is deliberately grey and always hatched: it is the *absence* of a number and must
not read as a fourth kind of number.

The provenance palette is validated for colour-vision deficiency against both the light and dark
surfaces (adjacent-pair ΔE ≥ 14.9 deutan/protan, ≥ 17.4 normal vision).

## The UI computes nothing

§12.1 and §18.3 extend to this prototype. Every figure comes from `ui/export_fixture.py`, which
calls the same core functions the headless CLIs call. `ui/app.js` contains no arithmetic beyond
turning a number into a string, a width, or an SVG coordinate.

## Files

| File | What it is |
|---|---|
| `index.html` | Page shell and the whole design system (tokens, components, responsive rules) |
| `app.js` | Ten screens, charts, and interaction. Reads `window.__FIXTURE__`, nothing else |
| `export_fixture.py` | Produces `fixture.json` and `data.js` from the real 1M-row dataset |
| `fixture.json` | The exported payload |
| `data.js` | The same payload as a script tag, for a prototype with no server |

## Regenerating the data

```bash
source .venv/bin/activate && python -m ui.export_fixture --out ui/fixture.json
```

Takes about six minutes, almost all of it the 468-scenario what-if grid
(13 cutoffs × 9 affordability caps × 4 rule-toggle combinations). `--skip-grid` drops that to
about ten seconds when only the static pages changed.

## What is real and what is drawn

**Real** — every figure on Baseline, Decline waterfall, Risk model, Portfolio quality, Validation
and the optimiser result. The what-if sliders re-solve against 468 genuinely precomputed scenarios,
so moving the cutoff to 680 shows the number `simulate()` actually returns.

**Drawn** — Champion/challenger and Governance are designed, not built; the optimiser's constraint
slider does not re-solve, because there is no Python behind the page yet. Each of these says so on
its own screen rather than only here.

## Wiring Python behind it

`data.js` is a stand-in for an API. The fixture keys mirror the dataclasses in `src/contracts.py`
(`ScenarioResult`, `OptimiserResult`, `CandidateFunnel`) field for field, so replacing
`window.__FIXTURE__` with fetched responses is the whole migration. Keep the engine call in
`core/`; the API layer stays transport and authorisation only (§18.3).

## Running it locally

Any static server over this directory:

```bash
python -m ui.serve
```

Then open <http://127.0.0.1:8777/index.html>.
