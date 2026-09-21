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
| `serve.py` | Serves the pages and, unless `--static`, the simulator's engine API from `src/client_api.py` |
| `client_notes.js` | Text of the spec notes: what each element on the three screens is and stands for |
| `settings.html`, `settings.js` | Settings: what the analysis runs on, for every signed-in person. Reads `window.__SETTINGS__` |
| `admin.html`, `admin.js` | Administration: licence, data source, mapping editor, rule workbooks, platform. Administrators only |
| `settings_kit.js`, `page_shell.js` | Rendering helpers and the shell (rail, strip, spec notes, theme) the two pages share |
| `settings_notes.js`, `admin_notes.js` | Spec notes for the two pages. No key may appear in both |
| `settings.css` | Layout for both. Every class is `su-` prefixed, and it is loaded after `client.css` |
| `settings_export.py` | Produces `settings.json` and `settings_data.js`. Separate from `client_export.py` so either can be rebuilt alone |
| `session.js` | What the signed-in person may do. The only thing any page asks; knows no role names |
| `demo_bar.js` | **Demo only.** The "View as" menu that stands in for the server. Delete its one tag per page to remove it |
| `shell.css` | The Azentio brand in the top bar, and rail items that link to another page |

`tokens.css` was extracted out of `index.html` so the client screens could reuse it rather than
copy it. The two pages are separate only because they sit on different engines; they merge
when the API lands.

## The three client screens

```bash
python -m ui.client_export && python -m ui.serve
```

Then <http://127.0.0.1:8777/client.html>. See `ENGINE.md` for what they show. The export takes
about 25 seconds; `--quick` skips the scenario grid and takes seconds when only the static parts
changed.

### Simulator: live engine or precomputed

`python -m ui.serve` serves the pages **and** the engine (`src/client_api.py`) on the same port. The
baseline loads in about three seconds in the background; the Simulator screen polls
`/api/health` and switches to live mode when it is ready. Live, a person can:

- switch off any of the 113 decline rules, or edit any tunable threshold in either direction;
- stack changes into a scenario, see what each step added, and revert any step;
- goal-seek to their own target approval rate and bad-rate ceiling, keeping chosen rules untouched.
- say what they want in plain words under **Ask**, and get a scenario the engine has replayed
  (a language model chooses the changes, the engine computes every figure; see `ENGINE.md`, step 6).
  Set `GEMINI_API_KEY` in the shell that starts the server; without it the chat answers with no model.

Each change replays in well under a tenth of a second, because only the changed rules are
re-evaluated (`client_replay.replay(..., base=)`, held to a full replay by a test). A goal-seek
takes about ten seconds.

`python -m ui.serve 8777 --static`, or opening the file from disk, gives the precomputed fallback:
the full rule list, but only the switch-offs in `rule_toggles` can be tried, one at a time, and
goal-seek shows its two fixed targets. The screen says which mode it is in.

| Endpoint | |
|---|---|
| `GET /api/health` | ready flag, today's rates, the default ceiling, what goal-seek may try |
| `GET /api/rules` | every decline rule, what each tests, whether it can be changed and why not |
| `POST /api/simulate` | `{"changes": [{"type": "off", "rule_id": …} \| {"type": "threshold", "rule_id": …, "field": …, "value_low": …, "value_high": …}]}` |
| `POST /api/goal-seek` | `{"target": 0.30, "ceiling": 0.11, "frozen": [rule_id, …]}` |
| `GET /api/scenarios` | saved scenarios, newest first, and how many may be compared at once |
| `POST /api/scenarios` | `{"name", "changes", "product", "window", "preset", "who"}`: re-runs the steps and keeps the engine's answer, with who saved it and when |
| `POST /api/scenarios/compare` | `{"ids": […]}`: re-runs each in its own product and period, and says what has moved since it was saved |
| `POST /api/scenarios/delete` | `{"id", "who"}`: off the list; the record of who saved and deleted it is kept |

A refused change (a locked rule, a range back to front) comes back as HTTP 400 with the reason in
words, and the screen keeps the previous scenario.

### Settings and Administration

Two pages of their own, linked from the rail of every screen.

```bash
python -m ui.settings_export      # seconds; independent of client_export
```

| Page | Who | What |
|---|---|---|
| `settings.html` | Everyone | Readiness, rule set, policy and risk appetite, run and data quality |
| | + `data.view` | Applicant data facts and the field mapping, read-only |
| | + `recompute.run` | Recompute |
| | + `audit.view` | Audit log |
| `admin.html` | `admin.view` | Licence, data source, field mapping editor, rule workbooks, outcomes, platform and security, versions, diagnostics |

**Who sees what.** A page never checks a role. It asks `Session.can('<action>')` (`session.js`) and
draws what comes back true. In the deployed product the server answers from the signed-in user's
attributes and refuses the action whatever the page draws; hiding a control is presentation, not
security. With no provider, Session allows nothing extra, so a missing provider fails closed.

**The demo menu.** `demo_bar.js` is the "View as" menu at the top right of every page: Business
user, Analyst, Risk approver, Administrator, plus presenter controls (show what is live, the licence
stage, "a renewed licence has arrived"). It is the only file that knows role names and the only one
that uses browser storage, so the choice survives moving between pages. It replaces `?dev=1`. It
never ships: delete its `<script>` tag from each page and every page still works.

**The licence.** Only an administrator sees it, as its current state. Anyone else meets it only as a
paused action with a plain message and no dates. The stages a licence passes through are contract
terms that differ by client, so they are read from the licence file (`paused` per stage in the
fixture) and explained in the spec notes, never drawn.

Part of each page is real and part is simulated. The rule set, dataset facts, field requirements,
policy values and replay timing are read from the engine. Everything under the fixture's
`simulated` key is not, and carries a dashed **PREVIEW** tag, once per block, which is
deliberately not a colour. None of it changes a figure on any other screen. Nothing leaves the
browser, a chosen file is never read, and the demo password field is never read.

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
