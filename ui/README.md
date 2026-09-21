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

## Two pages, one design system

| File | What it is |
|---|---|
| `tokens.css` | The design system — tokens, components, responsive rules. Shared by both pages |
| `index.html` | Page shell for the original ten screens |
| `app.js` | Those ten screens. Reads `window.__FIXTURE__`, nothing else |
| `export_fixture.py` | Produces `fixture.json` and `data.js` from the 1M-row dataset |
| `client.html` | Page shell for the three CxO screens over a real rule set |
| `client.css` | Layout for those three screens. No new colours |
| `client.js` | Portfolio, Decline drivers, Simulator. Reads `window.__CLIENT__`, nothing else |
| `client_export.py` | Produces `client_fixture.json` and `client_data.js` from the engine |
| `client_notes.js` | Text of the spec notes: what each element on the three screens is and stands for |

`tokens.css` was extracted out of `index.html` so the client screens could reuse it rather than
copy it. The two pages are separate only because they sit on different engines; they merge
when the API lands.

## The three client screens

```bash
python -m ui.client_export && python -m ui.serve
```

Then <http://127.0.0.1:8777/client.html>. See `ENGINE.md` for what they show. The export takes
about three minutes, most of it the two goal-seek runs; `--quick` skips the scenario grid and
takes seconds when only the static parts changed.

### Spec notes

The icon at the top right, beside the theme switch, turns spec notes on. Hidden by default. When on,
every annotated item on the current screen gets a number and each number is explained as a footnote
at the foot of the page; clicking a number jumps between the item and its note.

Adding a note is two edits: tag the element with `N('key')` in `client.js` (or `data-note="key"` in
`client.html`), and add `key: { t: 'Title', d: 'Text' }` to `client_notes.js`. A test fails if a tag has
no text, or text has no tag. Values that come from the data or config (rule count, ceiling, replay
assumptions) are read from the fixture in the notes file rather than typed in, so they cannot drift.

The server sends `Cache-Control: no-store`. The data file is regenerated whenever the engine
changes, and a browser holding an old `client_data.js` shows last week's figures with this week's
screens — silently, in front of whoever is being demoed to.

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
